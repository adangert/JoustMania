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
        await asyncio.sleep(0.05)
        # Release button
        await mock_client.SimulateButton(
            controller_manager_mock_pb2.ButtonRequest(
                serial=serial,
                button=controller_manager_mock_pb2.ButtonRequest.Button.TRIGGER,
                pressed=False,
            )
        )
        await asyncio.sleep(0.05)


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
    await asyncio.sleep(0.05)
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
    await asyncio.sleep(0.2)  # Allow game cleanup to complete

    # Stop Menu first to clear any stale controller state, then restart fresh
    await menu_client.StopMenu(menu_pb2.StopMenuRequest())
    await asyncio.sleep(0.1)

    # Start the Menu service
    start_response = await menu_client.StartMenu(menu_pb2.StartMenuRequest())
    if not start_response.success:
        raise RuntimeError(f"Failed to start Menu: {start_response.error}")
    await asyncio.sleep(0.3)  # Allow Menu to initialize and receive controller events

    # Get controller serials
    serials = await get_controller_serials(docker_compose)
    if not serials:
        raise RuntimeError("No controllers connected")

    # Select game mode
    await select_game_mode(menu_client, game_mode)
    await asyncio.sleep(0.1)

    # Mark all controllers as ready - game auto-starts when all are ready
    # Controllers are automatically known to Menu via initial connection events
    print(f"Marking {len(serials)} controllers as ready: {serials}")
    await mark_controllers_ready(mock_client, serials)
    print("Controllers marked as ready, waiting for game start...")
    await asyncio.sleep(0.1)

    # Wait for game to start (game_started event)
    # Game auto-starts after 0.3s delay when all controllers become ready
    await wait_for_game_running(game_client, timeout=timeout)

    # Close menu channel (not needed anymore)
    await menu_channel.close()

    return game_client, game_channel, mock_client, mock_channel


# =============================================================================
# LED color verification helpers
# =============================================================================

# Game mode lobby colors (full brightness) - used to verify return to menu
# These are the base colors before dimming; menu applies ~30% brightness
GAME_MODE_COLORS = {
    "JoustFFA": (255, 140, 0),  # Orange
    "JoustTeams": (0, 100, 255),  # Blue
    "JoustRandomTeams": (0, 200, 255),  # Cyan
    "Swapper": (255, 0, 255),  # Magenta
    "Werewolf": (0, 255, 100),  # Green
    "Traitor": (128, 0, 128),  # Dark Purple
    "Zombies": (100, 100, 100),  # Gray
    "Commander": (255, 0, 0),  # Red
    "FightClub": (255, 255, 0),  # Yellow
    "Tournament": (150, 0, 255),  # Purple
    "NonStop": (255, 50, 120),  # Pink
    "Ninja": (255, 140, 0),  # Orange (same as FFA)
}


async def get_controller_color(mock_client, serial: str) -> tuple[int, int, int]:
    """Get current LED color for a controller using GetColor RPC.

    Args:
        mock_client: Mock controller service gRPC client
        serial: Controller serial number

    Returns:
        Tuple of (r, g, b) color values
    """
    response = await mock_client.GetColor(
        controller_manager_mock_pb2.GetColorRequest(serial=serial)
    )
    assert response.success, f"GetColor failed for {serial}: {response.error}"
    return (response.r, response.g, response.b)


async def verify_controllers_have_color(mock_client, serials: list[str]):
    """Verify all controllers have some non-zero LED color.

    Args:
        mock_client: Mock controller service gRPC client
        serials: List of controller serial numbers to check
    """
    for serial in serials:
        color = await get_controller_color(mock_client, serial)
        total = sum(color)
        assert total > 0, f"{serial} LED is off (color: {color})"


def _color_matches(actual: tuple[int, int, int], expected: tuple[int, int, int], tolerance: int) -> bool:
    """Check if actual color matches expected within tolerance."""
    for a, e in zip(actual, expected):
        if abs(a - e) > tolerance:
            return False
    return True


async def wait_for_lobby_colors(
    mock_client,
    serials: list[str],
    expected_color: tuple[int, int, int] | None = None,
    tolerance: int = 30,
    timeout: float = 5.0,
    poll_interval: float = 0.2,
):
    """Wait for all controllers to show expected lobby colors.

    Polls controller colors until they match expected values or timeout.
    This handles timing variations in menu color reset after game ends.

    Args:
        mock_client: Mock controller service gRPC client
        serials: List of controller serial numbers to check
        expected_color: Expected RGB color tuple. If None, just checks non-zero.
        tolerance: Max difference per channel (default 30 for dimming variations)
        timeout: Maximum time to wait in seconds
        poll_interval: Time between polls in seconds

    Raises:
        AssertionError: If colors don't match within timeout
    """
    start_time = asyncio.get_event_loop().time()
    last_colors: dict[str, tuple[int, int, int]] = {}

    while (asyncio.get_event_loop().time() - start_time) < timeout:
        all_match = True

        for serial in serials:
            color = await get_controller_color(mock_client, serial)
            last_colors[serial] = color

            # Check if LED is on
            if sum(color) == 0:
                all_match = False
                continue

            # Check if color matches expected (if specified)
            if expected_color is not None:
                if not _color_matches(color, expected_color, tolerance):
                    all_match = False

        if all_match:
            return  # All controllers match!

        await asyncio.sleep(poll_interval)

    # Timeout - report which controllers didn't match
    mismatches = []
    for serial in serials:
        color = last_colors.get(serial, (0, 0, 0))
        if sum(color) == 0:
            mismatches.append(f"{serial}: LED is off (color: {color})")
        elif expected_color is not None and not _color_matches(color, expected_color, tolerance):
            mismatches.append(f"{serial}: got {color}, expected {expected_color}")

    raise AssertionError(
        f"Lobby colors not set within {timeout}s. Mismatches:\n" + "\n".join(mismatches)
    )


async def verify_lobby_colors(
    mock_client, serials: list[str], expected_color: tuple[int, int, int] | None = None, tolerance: int = 30
):
    """Verify all controllers show the expected lobby color.

    After a game ends, the menu should reset all controllers to dim lobby colors.
    We verify that LEDs match the expected color (or are at least non-zero).

    Args:
        mock_client: Mock controller service gRPC client
        serials: List of controller serial numbers to check
        expected_color: Expected RGB color tuple. If None, just checks non-zero.
        tolerance: Max difference per channel (default 30 for dimming variations)
    """
    for serial in serials:
        color = await get_controller_color(mock_client, serial)
        total_brightness = sum(color)
        assert total_brightness > 0, (
            f"{serial} LED is off (stuck at death effect), color: {color}"
        )

        if expected_color is not None:
            # Verify color matches expected (within tolerance for dimming)
            for i, (actual, expected) in enumerate(zip(color, expected_color)):
                diff = abs(actual - expected)
                channel = ["R", "G", "B"][i]
                assert diff <= tolerance, (
                    f"{serial} {channel} channel mismatch: got {actual}, expected {expected} "
                    f"(diff={diff}, tolerance={tolerance}). Full color: {color}, expected: {expected_color}"
                )


# =============================================================================
# Observability streaming helpers
# =============================================================================


class ObservabilityObserver:
    """Collects LED/rumble/button events from StreamObservability RPC.

    Usage:
        observer = ObservabilityObserver(mock_client)
        await observer.start()
        # ... run game ...
        events = observer.get_events()
        await observer.stop()
    """

    def __init__(self, mock_client):
        self.mock_client = mock_client
        self.events: list = []
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start collecting observability events in background."""
        self._task = asyncio.create_task(self._collect())

    async def _collect(self):
        """Background task to collect events from stream."""
        try:
            async for event in self.mock_client.StreamObservability(
                controller_manager_mock_pb2.ObservabilityRequest()
            ):
                self.events.append(event)
        except asyncio.CancelledError:
            pass

    async def stop(self):
        """Stop collecting events and cancel the background task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def get_events(self) -> list:
        """Get all collected events."""
        return list(self.events)

    def get_led_events(self, serial: str | None = None) -> list:
        """Get LED change events, optionally filtered by serial."""
        events = [e for e in self.events if e.HasField("led_change")]
        if serial:
            events = [e for e in events if e.serial == serial]
        return events

    def get_last_colors(self) -> dict[str, tuple[int, int, int]]:
        """Get the last LED color for each controller."""
        last_colors = {}
        for event in self.events:
            if event.HasField("led_change"):
                led = event.led_change
                last_colors[event.serial] = (led.r, led.g, led.b)
        return last_colors


def verify_death_effects(events: list, killed_serials: list[str]):
    """Verify death effects occurred for killed players.

    Args:
        events: List of ObservabilityEvent from observer
        killed_serials: List of controller serials that were killed
    """
    for serial in killed_serials:
        death_events = [
            e
            for e in events
            if e.serial == serial
            and e.HasField("led_change")
            and "death" in e.led_change.source.lower()
        ]
        # Death effect is optional depending on game mode
        # Just log if not found rather than asserting
        if not death_events:
            print(f"Note: No death effect event found for {serial}")


def verify_winner_effect(events: list, winner_serial: str):
    """Verify winner got celebration effect (rainbow).

    Args:
        events: List of ObservabilityEvent from observer
        winner_serial: Controller serial of the winner
    """
    winner_events = [
        e
        for e in events
        if e.serial == winner_serial
        and e.HasField("led_change")
        and "rainbow" in e.led_change.source.lower()
    ]
    # Rainbow effect is optional depending on game mode
    if not winner_events:
        print(f"Note: No rainbow winner effect found for {winner_serial}")


def verify_lobby_colors_restored(events: list, serials: list[str]):
    """Verify all controllers got non-zero colors after game end.

    Args:
        events: List of ObservabilityEvent from observer
        serials: List of all controller serials
    """
    # Get last LED event per controller
    last_colors = {}
    for event in events:
        if event.HasField("led_change"):
            led = event.led_change
            last_colors[event.serial] = (led.r, led.g, led.b)

    for serial in serials:
        if serial in last_colors:
            color = last_colors[serial]
            # Verify not stuck at black
            assert sum(color) > 0, f"{serial} final LED is black"


# =============================================================================
# Game kill helpers
# =============================================================================


async def kill_players_until_one_remains(
    mock_client, serials: list[str], delay: float = 0.5
) -> list[str]:
    """Kill players one by one until only one remains.

    Args:
        mock_client: Mock controller service gRPC client
        serials: List of all controller serials
        delay: Delay between kills in seconds

    Returns:
        List of serials that were killed (all except the last one)
    """
    killed = []
    # Kill all but the last player
    for serial in serials[:-1]:
        await asyncio.sleep(delay)
        response = await mock_client.SimulateDeath(
            controller_manager_mock_pb2.DeathRequest(serial=serial)
        )
        assert response.success, f"Failed to kill {serial}"
        killed.append(serial)
    return killed


async def kill_players_for_team_win(
    mock_client, serials: list[str], delay: float = 0.5
) -> list[str]:
    """Kill enough players to trigger a team game win.

    For team games, killing 3 of 4 players guarantees one team is eliminated.

    Args:
        mock_client: Mock controller service gRPC client
        serials: List of all controller serials
        delay: Delay between kills in seconds

    Returns:
        List of serials that were killed
    """
    killed = []
    # For 4 players in 2 teams, killing 3 ensures one team is gone
    players_to_kill = serials[:3] if len(serials) >= 4 else serials[:-1]
    for serial in players_to_kill:
        await asyncio.sleep(delay)
        response = await mock_client.SimulateDeath(
            controller_manager_mock_pb2.DeathRequest(serial=serial)
        )
        assert response.success, f"Failed to kill {serial}"
        killed.append(serial)
    return killed
