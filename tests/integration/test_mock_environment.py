"""
Integration tests using testcontainers with mock environment.

These tests spin up the entire JoustMania stack using docker-compose.yml with
docker-compose.override.yml (mock mode) and run end-to-end game simulations
without requiring physical hardware.

Usage:
    # Run tests normally (auto-teardown) - using uv script
    ./scripts/testing/test-mock.py

    # Pause before teardown to inspect Jaeger
    ./scripts/testing/test-mock-with-pause.py

    # Or run manually with pytest
    uv run --package joustmania-integration-tests pytest tests/integration/ -v
    PAUSE_BEFORE_TEARDOWN=1 uv run --package joustmania-integration-tests pytest tests/integration/ -v -s

    When paused, you can:
    - Browse Jaeger UI at http://localhost:16686
    - Inspect distributed traces
    - Check service logs
    - Test manual gRPC calls
    - Press ENTER to tear down and complete tests
"""

import asyncio
import os

# Import protobufs
import sys
import time

import grpc
import pytest
from testcontainers.compose import DockerCompose

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from proto import (
    controller_manager_mock_pb2,
    controller_manager_mock_pb2_grpc,
    controller_manager_pb2,
    controller_manager_pb2_grpc,
    game_coordinator_pb2,
    game_coordinator_pb2_grpc,
    menu_pb2,
    menu_pb2_grpc,
)


async def get_ready_players(docker_compose):
    """Helper function to get ready controllers and convert them to players."""
    host = docker_compose.get_service_host("controller-manager", 50052)
    port = docker_compose.get_service_port("controller-manager", 50052)
    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    response = await client.GetControllers(controller_manager_pb2.GetControllersRequest())
    await channel.close()

    # Convert controllers to players
    players = []
    for i, controller in enumerate(response.controllers):
        players.append(
            game_coordinator_pb2.Player(serial=controller.serial, team=i % 2, alive=True, score=0)
        )
    return players


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

    Waits for "game_ended" or "game_error" events which indicate the game
    has finished.
    """
    await wait_for_game_event(game_client, ["game_ended", "game_error"], timeout)


# =============================================================================
# Menu-based game start helpers
# =============================================================================


async def get_controller_serials(docker_compose) -> list[str]:
    """Get list of connected controller serials from ControllerManager."""
    host = docker_compose.get_service_host("controller-manager", 50052)
    port = docker_compose.get_service_port("controller-manager", 50052)
    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    response = await client.GetControllers(controller_manager_pb2.GetControllersRequest())
    await channel.close()

    return [c.serial for c in response.controllers]


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

    In the Menu system, pressing Move button marks controller as ready.

    Args:
        mock_client: Mock controller service gRPC client
        serials: List of controller serial numbers to mark ready
    """
    for serial in serials:
        # Simulate Move button press to mark ready
        # MOVE = 1 in the proto enum
        await mock_client.SimulateButton(
            controller_manager_mock_pb2.ButtonRequest(
                serial=serial,
                button=controller_manager_mock_pb2.ButtonRequest.Button.MOVE,
                pressed=True,
            )
        )
        await asyncio.sleep(0.1)
        # Release button
        await mock_client.SimulateButton(
            controller_manager_mock_pb2.ButtonRequest(
                serial=serial,
                button=controller_manager_mock_pb2.ButtonRequest.Button.MOVE,
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

    # Start the Menu service if not already running
    start_response = await menu_client.StartMenu(menu_pb2.StartMenuRequest())
    if not start_response.success and "already running" not in start_response.error.lower():
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
    print(f"Marking {len(serials)} controllers as ready: {serials}")
    await mark_controllers_ready(mock_client, serials)
    print("Controllers marked as ready, waiting for game start...")

    # Check menu status after marking ready
    await asyncio.sleep(2)
    status = await menu_client.GetMenuStatus(menu_pb2.GetMenuStatusRequest())
    print(f"Menu status: state={status.state}, selection={status.current_selection}, ready_count={status.ready_controller_count}")

    # Wait for game to start (game_started event)
    # Game auto-starts after 0.3s delay when all controllers become ready
    await wait_for_game_running(game_client, timeout=timeout)

    # Close menu channel (not needed anymore)
    await menu_channel.close()

    return game_client, game_channel, mock_client, mock_channel


@pytest.fixture(scope="module")
def docker_compose():
    """Fixture to start docker-compose mock environment.

    Uses docker-compose.yml with overrides for testing:
    - docker-compose.override.yml: port exposures for testing
    - docker-compose.ci.yml: mock mode for audio/controllers (no hardware)
    """
    compose = DockerCompose(
        context=".",
        compose_file_name=[
            "docker-compose.yml",
            "docker-compose.override.yml",
            "docker-compose.ci.yml",
        ],
        pull=False,
        build=True,
    )

    compose.start()

    # Wait for services to be ready
    time.sleep(10)

    print("\n" + "=" * 80)
    print("🚀 Mock environment is running!")
    print("=" * 80)
    print("Jaeger UI: http://localhost:16686")
    print("WebUI: http://localhost:80")
    print("Mock Control API: localhost:50062")
    print("=" * 80)

    yield compose

    # Optional pause before teardown (set PAUSE_BEFORE_TEARDOWN=1 to inspect Jaeger)
    if os.getenv("PAUSE_BEFORE_TEARDOWN"):
        print("\n" + "=" * 80)
        print("⏸️  PAUSED - Inspect Jaeger at http://localhost:16686")
        print("=" * 80)
        print("Press ENTER to tear down the environment...")
        input()

    compose.stop()


@pytest.fixture(autouse=True)
async def ensure_game_stopped(docker_compose):
    """Ensure no game is running before and after each test.

    This fixture runs automatically for every test to prevent
    'Game already in progress' errors between tests.
    """
    async def force_end_game():
        """Force end any running game."""
        try:
            host = docker_compose.get_service_host("game-coordinator", 50053)
            port = docker_compose.get_service_port("game-coordinator", 50053)
            channel = grpc.aio.insecure_channel(f"{host}:{port}")
            client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(channel)

            # Try to force end any running game
            await client.ForceEndGame(game_coordinator_pb2.ForceEndGameRequest())

            # Wait a moment for cleanup
            await asyncio.sleep(0.5)

            await channel.close()
        except Exception:
            pass  # Ignore errors (no game running, service not ready, etc.)

    # Before test: ensure no game is running
    await force_end_game()

    yield

    # After test: cleanup any game that was started
    await force_end_game()


@pytest.mark.asyncio
async def test_mock_controller_manager_connection(docker_compose):
    """Test that we can connect to mock controller manager."""
    # Get dynamically assigned port for controller manager
    host = docker_compose.get_service_host("controller-manager", 50052)
    port = docker_compose.get_service_port("controller-manager", 50052)

    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    # Get ready controllers
    response = await client.GetControllers(controller_manager_pb2.GetControllersRequest())

    assert response.success
    assert len(response.controllers) == 4  # Default MOCK_CONTROLLER_COUNT

    # Verify controller serials
    serials = [c.serial for c in response.controllers]
    assert "mock_controller_0" in serials
    assert "mock_controller_1" in serials
    assert "mock_controller_2" in serials
    assert "mock_controller_3" in serials

    await channel.close()


@pytest.mark.asyncio
async def test_mock_controller_control_api(docker_compose):
    """Test that we can control mock controllers via control API."""
    # Get dynamically assigned port for mock control API
    host = docker_compose.get_service_host("controller-manager", 50062)
    port = docker_compose.get_service_port("controller-manager", 50062)

    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(channel)

    # List mock controllers
    response = await client.ListMockControllers(controller_manager_mock_pb2.ListRequest())

    assert response.count == 4
    assert len(response.serials) == 4

    # Simulate movement
    move_response = await client.SimulateMovement(
        controller_manager_mock_pb2.MovementRequest(
            serial="mock_controller_0", accel_x=2.0, accel_y=1.5, accel_z=1.2
        )
    )

    assert move_response.success

    # Simulate death
    death_response = await client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
    )

    assert death_response.success
    assert death_response.accel_magnitude > 2.8  # Death threshold for FAST sensitivity

    # Reset controller
    reset_response = await client.ResetController(
        controller_manager_mock_pb2.ResetRequest(serial="mock_controller_0")
    )

    assert reset_response.success

    await channel.close()


@pytest.mark.asyncio
async def test_ffa_game_with_mock_controllers(docker_compose):
    """Test full FFA game lifecycle starting via Menu."""

    # Get mock client first to set up auto-end
    mock_client, mock_channel = await get_mock_client(docker_compose)

    # Enable auto game end: kill players after 12 seconds (3s countdown + 9s gameplay)
    auto_end_response = await mock_client.SetAutoGameEnd(
        controller_manager_mock_pb2.AutoGameEndRequest(duration_seconds=12.0, enabled=True)
    )
    assert auto_end_response.success

    # Start game via Menu flow (handles ready state, game selection, and start)
    game_client, game_channel, _, _ = await start_game_via_menu(
        docker_compose, game_mode="JoustFFA", timeout=25.0
    )

    # Wait for auto-end to trigger and game to finish
    # 12s auto-end + 1s winner delay + 2s teardown = ~15s total
    await wait_for_game_end(game_client, timeout=20)

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_teams_game_with_mock_controllers(docker_compose):
    """Test full Teams game lifecycle starting via Menu."""

    # Start game via Menu flow
    game_client, game_channel, mock_client, mock_channel = await start_game_via_menu(
        docker_compose, game_mode="JoustTeams", timeout=25.0
    )

    # Simulate deaths - kill 3 players to ensure one team wins
    # Note: With random_teams=true (default), team assignment is randomized,
    # so we can't assume specific players are on the same team.
    # Killing 3 players guarantees one team is eliminated.
    await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
    )
    await asyncio.sleep(1)

    await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_1")
    )
    await asyncio.sleep(1)

    await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_2")
    )
    await asyncio.sleep(2)

    # Game should auto-end when one team is eliminated (only player 3 remains)
    # Wait for game to end (with extra time for winner celebration)
    await wait_for_game_end(game_client, timeout=15)

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_controller_state_streaming(docker_compose):
    """Test streaming controller states from mock controller manager."""

    # Wait for controllers to be discovered and ready first
    players = await get_ready_players(docker_compose)
    assert len(players) == 4, f"Expected 4 ready players, got {len(players)}"

    # Get dynamically assigned port for controller manager
    host = docker_compose.get_service_host("controller-manager", 50052)
    port = docker_compose.get_service_port("controller-manager", 50052)

    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    # Start streaming at 10Hz
    stream_request = controller_manager_pb2.StreamRequest(update_frequency_hz=10)

    frame_count = 0
    frames_with_controllers = 0
    async for state_update in client.StreamControllerStates(stream_request):
        assert state_update.timestamp > 0

        # Count frames that have controllers (may take a moment to appear)
        if len(state_update.controllers) == 4:
            frames_with_controllers += 1

        frame_count += 1
        if frame_count >= 10:  # Receive up to 10 frames
            break

    # At least some frames should have all 4 controllers
    assert frames_with_controllers >= 1, f"Expected at least 1 frame with 4 controllers, got {frames_with_controllers} in {frame_count} frames"

    await channel.close()


@pytest.mark.asyncio
async def test_distributed_tracing_propagation(docker_compose):
    """Test that distributed tracing works end-to-end via Menu flow.

    This test verifies the complete trace chain:
    Menu -> Supervisor -> GameCoordinator -> Game
    """

    # Start game via Menu flow - this creates a complete trace chain
    game_client, game_channel, mock_client, mock_channel = await start_game_via_menu(
        docker_compose, game_mode="JoustFFA", timeout=25.0
    )

    # Wait for game to run briefly
    await asyncio.sleep(2)

    # Force end game
    await game_client.ForceEndGame(game_coordinator_pb2.ForceEndGameRequest())

    # Wait for game to fully end
    await wait_for_game_end(game_client, timeout=10)

    # Note: To verify tracing, check Jaeger UI at http://localhost:16686
    # Search for service="menu-service" and verify the complete trace chain:
    # - Menu: select_game_mode span
    # - Menu: game_requested event with trace context
    # - Supervisor: orchestrate_game_start span
    # - GameCoordinator: StartGame span (child of orchestrate_game_start)
    # - GameCoordinator: game_lifecycle span (child of StartGame)

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_multiple_games_sequence(docker_compose):
    """Test running multiple games in sequence via Menu flow."""

    # Run 3 games in sequence, each started via Menu
    for i in range(3):
        # Start game via Menu flow
        game_client, game_channel, mock_client, mock_channel = await start_game_via_menu(
            docker_compose, game_mode="JoustFFA", timeout=25.0
        )

        # Wait and simulate death
        await asyncio.sleep(1)
        await mock_client.SimulateDeath(
            controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
        )
        await asyncio.sleep(1)

        # End game
        await game_client.ForceEndGame(game_coordinator_pb2.ForceEndGameRequest())

        # Wait for game to fully end before starting next game
        await wait_for_game_end(game_client, timeout=10)

        # Close channels for this iteration
        await game_channel.close()
        await mock_channel.close()

        # Reset controllers for next game
        mock_client_reset, mock_channel_reset = await get_mock_client(docker_compose)
        for j in range(4):
            await mock_client_reset.ResetController(
                controller_manager_mock_pb2.ResetRequest(serial=f"mock_controller_{j}")
            )
        await mock_channel_reset.close()

        # Brief pause between games
        await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_controller_effects(docker_compose):
    """Test controller visual effects (FLASH, PULSE, RAINBOW, FADE) - Phase 31."""

    # Get dynamically assigned port for controller manager
    host = docker_compose.get_service_host("controller-manager", 50052)
    port = docker_compose.get_service_port("controller-manager", 50052)

    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    # Test 1: FLASH effect on single controller
    flash_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_FLASH,
            color=controller_manager_pb2.RGB(r=255, g=0, b=0),  # Red
            duration_ms=500,
            speed=5,
        )
    )
    assert flash_response.success
    await asyncio.sleep(0.6)  # Wait for effect to complete

    # Test 2: PULSE effect on single controller
    pulse_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_1",
            effect=controller_manager_pb2.EFFECT_PULSE,
            color=controller_manager_pb2.RGB(r=0, g=255, b=0),  # Green
            duration_ms=500,
            speed=3,
        )
    )
    assert pulse_response.success
    await asyncio.sleep(0.6)

    # Test 3: RAINBOW effect on single controller
    rainbow_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_2",
            effect=controller_manager_pb2.EFFECT_RAINBOW,
            duration_ms=500,
            speed=5,
        )
    )
    assert rainbow_response.success
    await asyncio.sleep(0.6)

    # Test 4: FADE_OUT effect
    fade_out_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_3",
            effect=controller_manager_pb2.EFFECT_FADE_OUT,
            color=controller_manager_pb2.RGB(r=0, g=0, b=255),  # Blue
            duration_ms=300,
        )
    )
    assert fade_out_response.success
    await asyncio.sleep(0.4)

    # Test 5: FADE_IN effect
    fade_in_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_3",
            effect=controller_manager_pb2.EFFECT_FADE_IN,
            color=controller_manager_pb2.RGB(r=255, g=255, b=0),  # Yellow
            duration_ms=300,
        )
    )
    assert fade_in_response.success
    await asyncio.sleep(0.4)

    # Test 6: EFFECT_NONE (solid color)
    none_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_NONE,
            color=controller_manager_pb2.RGB(r=255, g=0, b=255),  # Magenta
            duration_ms=0,
        )
    )
    assert none_response.success

    # Test 7: Effect on all controllers (empty serial)
    all_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="",  # All controllers
            effect=controller_manager_pb2.EFFECT_FLASH,
            color=controller_manager_pb2.RGB(r=255, g=255, b=255),  # White
            duration_ms=500,
            speed=10,  # Fast flash
        )
    )
    assert all_response.success
    await asyncio.sleep(0.6)

    # Test 8: Effect cancellation (start new effect before previous completes)
    # Start long-running effect
    await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_PULSE,
            color=controller_manager_pb2.RGB(r=255, g=0, b=0),
            duration_ms=2000,  # 2 seconds
            speed=1,
        )
    )
    await asyncio.sleep(0.2)  # Let it start

    # Cancel by starting new effect
    cancel_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_FLASH,
            color=controller_manager_pb2.RGB(r=0, g=255, b=0),
            duration_ms=300,
            speed=5,
        )
    )
    assert cancel_response.success
    await asyncio.sleep(0.4)

    await channel.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "game_mode",
    [
        "JoustFFA",
        "JoustTeams",
        "JoustRandomTeams",
        # Note: Nonstop Joust not included - players respawn so spans don't end on death
    ],
)
async def test_staggered_player_deaths(docker_compose, game_mode):
    """Test game with staggered player deaths to show varied span lengths in Jaeger.

    This test demonstrates realistic gameplay where players die at different times,
    creating varied player lifecycle span lengths in distributed traces.

    For FFA: Players die one by one until winner remains
    For Teams/Random Teams: Players from different teams die, last team wins

    Note: Nonstop Joust is excluded because players respawn - deaths don't end spans.
    """

    # Start game via Menu flow
    game_client, game_channel, mock_client, mock_channel = await start_game_via_menu(
        docker_compose, game_mode=game_mode, timeout=25.0
    )

    print(f"\n=== Starting {game_mode} game with staggered deaths ===")

    # Simulate deaths at different times to create varied span lengths
    # For team games, kill players from different teams to avoid early game end

    # Player 0 dies first (shortest span)
    await asyncio.sleep(1)
    death_0 = await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
    )
    assert death_0.success
    print(f"  Player 0 died at ~3s (accel: {death_0.accel_magnitude:.2f})")

    # Player 2 dies second (different team for team modes)
    await asyncio.sleep(2)
    death_2 = await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_2")
    )
    assert death_2.success
    print(f"  Player 2 died at ~5s (accel: {death_2.accel_magnitude:.2f})")

    # Player 1 dies third
    await asyncio.sleep(2)
    death_1 = await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_1")
    )
    assert death_1.success
    print(f"  Player 1 died at ~7s (accel: {death_1.accel_magnitude:.2f})")

    # Player 3 wins (longest span) - wait for game to end naturally
    # Game will: detect win → sleep 1 second (showing winner) → teardown
    await wait_for_game_end(game_client, timeout=15)

    print("  Game ended with player 3 as winner")
    print("  Check Jaeger UI: http://localhost:16686")
    print(f"  Search for: {game_mode.replace(' ', '-')}")
    print("  Look for varied player/team span lengths!")

    # Cleanup
    await game_channel.close()
    await mock_channel.close()
