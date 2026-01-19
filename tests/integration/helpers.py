"""
Shared helper functions for JoustMania integration tests.

These helpers provide:
- Game event waiting utilities
- Menu interaction helpers
- Mock controller manipulation
- Client factory functions
"""

import asyncio
import os
import sys

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from proto import (
    controller_manager_mock_pb2,
    controller_manager_mock_pb2_grpc,
    game_coordinator_pb2,
    game_coordinator_pb2_grpc,
    menu_pb2,
    menu_pb2_grpc,
)


# =============================================================================
# Client factory functions
# =============================================================================


async def get_menu_client(docker_compose):
    """Get Menu service gRPC client."""
    host = docker_compose.get_service_host("menu", 50054)
    port = docker_compose.get_service_port("menu", 50054)
    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    return menu_pb2_grpc.MenuServiceStub(channel), channel


async def get_mock_client(docker_compose):
    """Get Mock controller control gRPC client."""
    host = docker_compose.get_service_host("controller-manager", 50062)
    port = docker_compose.get_service_port("controller-manager", 50062)
    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    return controller_manager_mock_pb2_grpc.MockControllerServiceStub(channel), channel


async def get_game_client(docker_compose):
    """Get GameCoordinator gRPC client."""
    host = docker_compose.get_service_host("game-coordinator", 50053)
    port = docker_compose.get_service_port("game-coordinator", 50053)
    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    return game_coordinator_pb2_grpc.GameCoordinatorServiceStub(channel), channel


# =============================================================================
# Controller helpers
# =============================================================================


async def get_mock_controller_serials(docker_compose) -> list[str]:
    """Get list of mock controller serials via ListMockControllers."""
    host = docker_compose.get_service_host("controller-manager", 50062)
    port = docker_compose.get_service_port("controller-manager", 50062)
    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(channel)

    response = await client.ListMockControllers(controller_manager_mock_pb2.ListRequest())
    await channel.close()

    return list(response.serials)


async def get_controller_serials(docker_compose) -> list[str]:
    """Get list of connected controller serials via ListMockControllers."""
    return await get_mock_controller_serials(docker_compose)


async def get_ready_players(docker_compose):
    """Helper function to get mock controllers and convert them to players."""
    serials = await get_mock_controller_serials(docker_compose)

    # Convert serials to players
    players = []
    for i, serial in enumerate(serials):
        players.append(
            game_coordinator_pb2.Player(serial=serial, team=i % 2, alive=True, score=0)
        )
    return players


# =============================================================================
# Game event helpers
# =============================================================================


async def wait_for_game_event(game_client, target_events: list[str], timeout=10):
    """Wait for a specific game event via StreamGameEvents.

    Args:
        game_client: The GameCoordinator gRPC client
        target_events: List of event types to wait for (e.g., ["game_started"])
        timeout: Maximum time to wait in seconds

    Raises:
        TimeoutError: If the event is not received within the timeout
    """

    async def wait():
        async for event in game_client.StreamGameEvents(
            game_coordinator_pb2.StreamEventsRequest()
        ):
            if event.event_type in target_events:
                return event

    try:
        return await asyncio.wait_for(wait(), timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Game did not emit event {target_events} within {timeout} seconds")


async def wait_for_game_running(game_client, timeout=15):
    """Wait for game to reach RUNNING state (after countdown).

    Waits for the "game_started" event which is emitted when the game loop
    begins after the countdown completes.
    """
    await wait_for_game_event(game_client, ["game_started"], timeout)


async def wait_for_game_end(game_client, timeout=10):
    """Wait for game to reach ENDED state.

    Waits for "game_ended", "game_force_ended", or "game_error" events which
    indicate the game has finished.
    """
    await wait_for_game_event(game_client, ["game_ended", "game_force_ended", "game_error"], timeout)


async def force_end_game_and_wait(game_client, timeout=10):
    """Force end game and wait for the end event.

    Starts streaming before calling ForceEndGame to avoid race condition
    where the event is published before the stream is established.
    """
    end_events = ["game_ended", "game_force_ended", "game_error"]

    async def wait_for_end():
        async for event in game_client.StreamGameEvents(
            game_coordinator_pb2.StreamEventsRequest()
        ):
            if event.event_type in end_events:
                return event

    # Start the stream task, then call ForceEndGame
    stream_task = asyncio.create_task(wait_for_end())

    # Give the stream a moment to establish
    await asyncio.sleep(0.1)

    # Force end game
    await game_client.ForceEndGame(game_coordinator_pb2.ForceEndGameRequest())

    # Wait for the end event with timeout
    try:
        await asyncio.wait_for(stream_task, timeout=timeout)
    except asyncio.TimeoutError:
        stream_task.cancel()
        raise TimeoutError(f"Game did not emit event {end_events} within {timeout} seconds")


# =============================================================================
# Menu helpers
# =============================================================================


async def select_game_mode(menu_client, game_mode: str):
    """Navigate menu to select a specific game mode.

    Args:
        menu_client: Menu service gRPC client
        game_mode: Game mode name (e.g., "JoustFFA", "JoustTeams", "JoustRandomTeams")
    """
    # Send web command to select game mode directly
    response = await menu_client.ProcessInput(
        menu_pb2.ProcessInputRequest(
            input_type="web_command",
            data={"command": "select_game", "game_name": game_mode},
        )
    )
    return response.success


async def mark_controllers_ready(mock_client, serials: list[str]):
    """Mark controllers as ready by simulating button presses.

    In the Menu system, pressing TRIGGER marks controller as ready.
    (MOVE cycles game modes instead)

    Controllers are automatically known to the Menu via initial connection
    events sent when the Menu subscribes to the button stream.

    Args:
        mock_client: Mock controller service gRPC client
        serials: List of controller serial numbers to mark ready
    """
    for serial in serials:
        # Simulate Trigger button press to mark ready
        # TRIGGER = 0 in the proto enum
        await mock_client.SimulateButton(
            controller_manager_mock_pb2.ButtonRequest(
                serial=serial,
                button=controller_manager_mock_pb2.ButtonRequest.Button.TRIGGER,
                pressed=True,
            )
        )
        await asyncio.sleep(0.1)
        # Release button
        await mock_client.SimulateButton(
            controller_manager_mock_pb2.ButtonRequest(
                serial=serial,
                button=controller_manager_mock_pb2.ButtonRequest.Button.TRIGGER,
                pressed=False,
            )
        )
        await asyncio.sleep(0.1)


async def trigger_game_start(mock_client, serial: str):
    """Trigger game start by simulating trigger press from a ready controller.

    NOTE: This is typically not needed - the game auto-starts when all
    controllers become ready. This function is only needed if you want
    to manually trigger a game start when not all controllers are ready.

    Args:
        mock_client: Mock controller service gRPC client
        serial: Serial of a ready controller to trigger the game start
    """
    # Simulate trigger press to start game
    # TRIGGER = 0 in the proto enum
    await mock_client.SimulateButton(
        controller_manager_mock_pb2.ButtonRequest(
            serial=serial,
            button=controller_manager_mock_pb2.ButtonRequest.Button.TRIGGER,
            pressed=True,
        )
    )
    await asyncio.sleep(0.1)
    # Release trigger
    await mock_client.SimulateButton(
        controller_manager_mock_pb2.ButtonRequest(
            serial=serial,
            button=controller_manager_mock_pb2.ButtonRequest.Button.TRIGGER,
            pressed=False,
        )
    )


async def reset_all_controllers(mock_client, serials: list[str]):
    """Reset all controllers to non-ready state.

    This is useful between tests to ensure clean state.

    Args:
        mock_client: Mock controller service gRPC client
        serials: List of controller serial numbers to reset
    """
    # The Menu's StateManager resets on game end, but we can force
    # a state reset by reconnecting or using admin mode
    pass  # Controllers reset automatically when game ends


# =============================================================================
# Full flow helpers
# =============================================================================


async def start_game_via_menu(
    docker_compose, game_mode: str = "JoustFFA", timeout: float = 20.0
) -> tuple:
    """Start a game through the Menu service (full flow).

    This simulates the real user flow:
    1. Start the Menu service
    2. Controllers connect and see menu
    3. Controllers mark themselves as ready (Move button)
    4. Game auto-starts when all controllers are ready
    5. Menu requests game from Supervisor
    6. Supervisor calls GameCoordinator.StartGame

    Args:
        docker_compose: Docker compose fixture
        game_mode: Game mode to select (default: "JoustFFA")
        timeout: Timeout for game to start

    Returns:
        Tuple of (game_client, game_channel, mock_client, mock_channel)
    """
    # Get clients
    menu_client, menu_channel = await get_menu_client(docker_compose)
    mock_client, mock_channel = await get_mock_client(docker_compose)

    # Get game coordinator client to wait for game start
    game_host = docker_compose.get_service_host("game-coordinator", 50053)
    game_port = docker_compose.get_service_port("game-coordinator", 50053)
    game_channel = grpc.aio.insecure_channel(f"{game_host}:{game_port}")
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    # Force-end any previous game to ensure clean state
    await game_client.ForceEndGame(game_coordinator_pb2.ForceEndGameRequest(reason="test_cleanup"))
    await asyncio.sleep(2.0)  # Allow game cleanup to complete

    # Stop Menu first to clear any stale controller state, then restart fresh
    await menu_client.StopMenu(menu_pb2.StopMenuRequest())
    await asyncio.sleep(0.5)

    # Start the Menu service
    start_response = await menu_client.StartMenu(menu_pb2.StartMenuRequest())
    if not start_response.success:
        raise RuntimeError(f"Failed to start Menu: {start_response.error}")
    await asyncio.sleep(1)  # Allow Menu to initialize and receive controller events

    # Get controller serials
    serials = await get_controller_serials(docker_compose)
    if not serials:
        raise RuntimeError("No controllers connected")

    # Select game mode
    await select_game_mode(menu_client, game_mode)
    await asyncio.sleep(0.5)

    # Mark all controllers as ready - game auto-starts when all are ready
    # Controllers are automatically known to Menu via initial connection events
    print(f"Marking {len(serials)} controllers as ready: {serials}")
    await mark_controllers_ready(mock_client, serials)
    print("Controllers marked as ready, waiting for game start...")
    await asyncio.sleep(1)

    # Wait for game to start (game_started event)
    # Game auto-starts after 0.3s delay when all controllers become ready
    await wait_for_game_running(game_client, timeout=timeout)

    # Close menu channel (not needed anymore)
    await menu_channel.close()

    return game_client, game_channel, mock_client, mock_channel
