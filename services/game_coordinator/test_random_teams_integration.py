"""
Integration tests for Random Teams game mode with mock gRPC services.

Tests the full Random Teams game flow using mocked ControllerManager and Settings services,
verifying random team assignment, team formation phase, game logic, event publishing,
and win conditions without real hardware.
"""

import asyncio
import importlib.util
import os
import sys
import time

import pytest

# Setup paths
test_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(test_dir))
games_dir = os.path.join(test_dir, "games")

# Add project root for any needed imports
sys.path.insert(0, project_root)

# Import random_teams directly without triggering package initialization
spec = importlib.util.spec_from_file_location("random_teams", os.path.join(games_dir, "random_teams.py"))
random_teams = importlib.util.module_from_spec(spec)
sys.modules["random_teams"] = random_teams
spec.loader.exec_module(random_teams)

# Import protobuf files directly without triggering package initialization
# Controller Manager protobufs
controller_pb_path = os.path.join(project_root, "services", "controller_manager")
sys.path.insert(0, controller_pb_path)
import controller_manager_pb2

# Settings protobufs
settings_pb_path = os.path.join(project_root, "services", "settings")
sys.path.insert(0, settings_pb_path)
import settings_pb2


class MockControllerManagerService:
    """Mock ControllerManager gRPC service for testing."""

    def __init__(self, num_controllers: int = 4):
        """
        Initialize mock controller manager.

        Args:
            num_controllers: Number of mock controllers to simulate
        """
        self.num_controllers = num_controllers
        self.controllers = []
        self._initialize_controllers()

    def _initialize_controllers(self):
        """Create mock controller objects."""
        for i in range(self.num_controllers):
            controller = controller_manager_pb2.ControllerState(
                serial=f"mock_controller_{i}",
                move_num=i,
                battery=80,
                trigger_pressed=False,
                move_pressed=False,
                ready=True,
                team=0,
                color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                accel=controller_manager_pb2.Vector3(x=0.0, y=0.0, z=1.0),
                gyro=controller_manager_pb2.Vector3(x=0.0, y=0.0, z=0.0),
            )
            self.controllers.append(controller)

    def GetReadyControllers(self, request):
        """Mock GetReadyControllers RPC."""
        return controller_manager_pb2.GetReadyControllersResponse(controllers=self.controllers, success=True, error="")

    async def StreamControllerStates(self, request):
        """
        Mock StreamControllerStates RPC.

        Simulates random teams game where some players die.
        Kill 3 out of 4 players to guarantee one team is eliminated.
        """
        start_time = time.time()
        frame = 0

        # Simulate game for 7 seconds
        while time.time() - start_time < 7.0:
            frame += 1

            # Update controller states
            for i, controller in enumerate(self.controllers):
                # Kill controllers 1, 2, and 3 at different times
                # This guarantees at least one team is fully eliminated
                if time.time() - start_time > 2.0 and i == 1:
                    controller.accel.x = 5.0  # High acceleration = death
                    controller.accel.y = 3.0
                    controller.accel.z = 4.0
                elif time.time() - start_time > 3.0 and i == 2:
                    controller.accel.x = 6.0
                    controller.accel.y = 4.0
                    controller.accel.z = 3.0
                elif time.time() - start_time > 4.0 and i == 3:
                    controller.accel.x = 7.0
                    controller.accel.y = 5.0
                    controller.accel.z = 4.0
                else:
                    # Normal idle state (small movements)
                    controller.accel.x = 0.1
                    controller.accel.y = 0.0
                    controller.accel.z = 1.0

            # Yield state update
            yield controller_manager_pb2.ControllerStateUpdate(
                controllers=self.controllers, timestamp=int(time.time() * 1000)
            )

            # 60 FPS = ~16.67ms per frame
            await asyncio.sleep(1.0 / 60.0)

    async def StreamGameplayData(self, request):
        """
        Mock StreamGameplayData RPC (Phase 41).

        Simulates random teams game where some players die.
        Kill 3 out of 4 players to guarantee one team is eliminated.
        """
        start_time = time.time()
        frame = 0

        # Simulate game for 7 seconds
        while time.time() - start_time < 7.0:
            frame += 1

            # Update controller states
            gameplay_data_list = []
            for i, controller in enumerate(self.controllers):
                # Kill controllers 1, 2, and 3 at different times
                # This guarantees at least one team is fully eliminated
                if time.time() - start_time > 2.0 and i == 1:
                    controller.accel.x = 5.0  # High acceleration = death
                    controller.accel.y = 3.0
                    controller.accel.z = 4.0
                elif time.time() - start_time > 3.0 and i == 2:
                    controller.accel.x = 6.0
                    controller.accel.y = 4.0
                    controller.accel.z = 3.0
                elif time.time() - start_time > 4.0 and i == 3:
                    controller.accel.x = 7.0
                    controller.accel.y = 5.0
                    controller.accel.z = 4.0
                else:
                    # Normal idle state (small movements)
                    controller.accel.x = 0.1
                    controller.accel.y = 0.0
                    controller.accel.z = 1.0

                # Convert to GameplayData (no buttons)
                gd = controller_manager_pb2.GameplayData(
                    serial=controller.serial,
                    move_num=int(controller.serial.split("_")[-1]),
                    battery=controller.battery,
                    ready=controller.ready,
                    team=controller.team,
                    color=controller.color,
                    accel=controller.accel,
                    gyro=controller.gyro,
                )
                gameplay_data_list.append(gd)

            # Yield gameplay data update
            yield controller_manager_pb2.GameplayDataUpdate(
                controllers=gameplay_data_list, timestamp=int(time.time() * 1000)
            )

            # 60 FPS = ~16.67ms per frame
            await asyncio.sleep(1.0 / 60.0)


class MockSettingsService:
    """Mock Settings gRPC service for testing."""

    def __init__(self):
        """Initialize mock settings."""
        self.settings = {
            "sensitivity": "MEDIUM",
            "play_audio": "false",  # Disable audio in tests
            "color_lock": "false",
            "random_teams": "true",
            "random_team_size": "2",
        }

    def GetSettings(self, request):
        """Mock GetSettings RPC."""
        return settings_pb2.GetSettingsResponse(settings=self.settings, success=True, error="")


class EventCollector:
    """Collects events published by the game."""

    def __init__(self):
        self.events: list[tuple] = []  # List of (event_type, data)

    def publish(self, event_type: str, data: dict):
        """Collect published event."""
        self.events.append((event_type, data))
        print(f"Event published: {event_type} - {data}")

    def get_events_of_type(self, event_type: str) -> list[dict]:
        """Get all events of a specific type."""
        return [data for et, data in self.events if et == event_type]

    def count_events_of_type(self, event_type: str) -> int:
        """Count events of a specific type."""
        return len(self.get_events_of_type(event_type))


@pytest.fixture
def mock_controller_manager():
    """Fixture providing mock ControllerManager service."""
    return MockControllerManagerService(num_controllers=4)


@pytest.fixture
def mock_settings():
    """Fixture providing mock Settings service."""
    return MockSettingsService()


@pytest.fixture
def event_collector():
    """Fixture providing event collector."""
    return EventCollector()


@pytest.mark.asyncio
async def test_random_teams_game_full_lifecycle(mock_controller_manager, mock_settings, event_collector):
    """
    Test full Random Teams game lifecycle:
    - Game starts with 4 players
    - Players are randomly assigned to 2 teams
    - Team formation phase shows team colors
    - Countdown runs
    - Game loop processes controller states
    - Players die
    - Winning team determined
    - Game ends
    """
    # Create Random Teams game with mock services (2 teams)
    game = random_teams.RandomTeamsGame(
        controller_manager_client=mock_controller_manager,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_random_teams_1",
        num_teams=2,
    )

    # Run the game
    await game.run()

    # Verify game completed
    assert game.state == random_teams.GameState.ENDED

    # Verify events were published
    assert event_collector.count_events_of_type("game_starting") == 1
    assert event_collector.count_events_of_type("players_initialized") == 1
    assert event_collector.count_events_of_type("team_formation_start") == 1
    assert event_collector.count_events_of_type("team_formation_end") == 1
    assert event_collector.count_events_of_type("countdown_start") == 1
    assert event_collector.count_events_of_type("countdown_end") == 1
    assert event_collector.count_events_of_type("game_started") == 1

    # Verify players were initialized with random teams
    players_init_events = event_collector.get_events_of_type("players_initialized")
    assert len(players_init_events) == 1
    assert players_init_events[0]["player_count"] == 4
    assert players_init_events[0]["num_teams"] == 2

    # Verify team formation phase occurred
    formation_events = event_collector.get_events_of_type("team_formation_start")
    assert len(formation_events) == 1
    assert formation_events[0]["duration"] == 5  # TEAM_FORMATION_DURATION

    # Verify deaths occurred (3 out of 4 players die to guarantee team elimination)
    death_events = event_collector.get_events_of_type("player_death")
    assert len(death_events) == 3, f"Expected 3 deaths, got {len(death_events)}"

    # Verify each death event has team name
    for death_event in death_events:
        assert "team_name" in death_event
        assert death_event["team_name"] in [
            "Pink",
            "Magenta",
            "Orange",
            "Yellow",
            "Green",
            "Turquoise",
            "Blue",
            "Purple",
        ]

    # Verify team winner was determined
    winner_events = event_collector.get_events_of_type("team_winner")
    assert len(winner_events) == 1, f"Expected 1 team winner, got {len(winner_events)}"

    # Winner should have team info
    assert "team" in winner_events[0]
    assert "team_name" in winner_events[0]
    assert "team_color" in winner_events[0]
    assert "winning_players" in winner_events[0]

    # Verify game ended
    assert event_collector.count_events_of_type("game_ended") == 1

    print(f"\n✅ Random Teams test passed! Total events: {len(event_collector.events)}")
    print("Events timeline:")
    for event_type, data in event_collector.events:
        print(f"  - {event_type}: {data}")


@pytest.mark.asyncio
async def test_random_teams_assignment_is_random(mock_controller_manager, mock_settings, event_collector):
    """
    Test that team assignments are actually random.

    Run the same setup multiple times and verify we get different assignments.
    """
    assignments_seen = set()

    # Run game initialization 5 times
    for i in range(5):
        game = random_teams.RandomTeamsGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            game_id=f"test_random_{i}",
            num_teams=2,
        )

        # Only initialize players, don't run full game
        await game._load_settings()
        await game._initialize_players()

        # Get team assignment as a tuple (hashable)
        assignment = tuple(sorted([(serial, player.team) for serial, player in game.players.items()]))

        assignments_seen.add(assignment)

    # We should see at least 2 different assignments out of 5 runs
    # (With 4 players and 2 teams, there are multiple possible assignments)
    assert (
        len(assignments_seen) >= 2
    ), f"Expected different random assignments, got same assignment {len(assignments_seen)} times"

    print(f"✅ Random assignment test passed! Saw {len(assignments_seen)} different team configurations")


@pytest.mark.asyncio
async def test_random_teams_game_settings_loaded(mock_controller_manager, mock_settings, event_collector):
    """Test that game loads settings from Settings service."""
    # Customize settings
    mock_settings.settings["sensitivity"] = "FAST"
    mock_settings.settings["play_audio"] = "true"

    # Create game
    game = random_teams.RandomTeamsGame(
        controller_manager_client=mock_controller_manager,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_random_teams_3",
        num_teams=2,
    )

    # Load settings (called internally by run(), but we can test separately)
    await game._load_settings()

    # Verify settings were loaded
    assert game.sensitivity == random_teams.Sensitivity.FAST
    assert game.play_audio is True

    print("✅ Random Teams settings loading test passed!")


@pytest.mark.asyncio
async def test_random_teams_game_force_end(mock_settings, event_collector):
    """Test that force_end() stops the Random Teams game."""
    # Create mock controller manager that streams forever
    mock_cm = MockControllerManagerService(num_controllers=4)

    async def infinite_stream(request):
        """Stream indefinitely (until force_end)."""
        while True:
            yield controller_manager_pb2.ControllerStateUpdate(
                controllers=mock_cm.controllers, timestamp=int(time.time() * 1000)
            )
            await asyncio.sleep(1.0 / 60.0)

    mock_cm.StreamControllerStates = infinite_stream

    # Create game
    game = random_teams.RandomTeamsGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_random_teams_4",
        num_teams=2,
    )

    # Start game in background task
    game_task = asyncio.create_task(game.run())

    # Wait a bit, then force end (during team formation phase)
    await asyncio.sleep(1.0)
    game.force_end()

    # Wait for game to finish
    try:
        await asyncio.wait_for(game_task, timeout=2.0)
    except TimeoutError:
        pytest.fail("Game did not end after force_end() was called")

    # Verify game stopped
    assert game.running is False

    print("✅ Random Teams force end test passed!")


@pytest.mark.asyncio
async def test_random_teams_with_three_teams(mock_settings, event_collector):
    """Test Random Teams game with 3 teams and 6 players."""
    # Create mock controller manager with 6 controllers
    mock_cm = MockControllerManagerService(num_controllers=6)

    # Make some controllers die to end the game
    async def three_team_stream(request):
        """Stream with some controllers dying."""
        start_time = time.time()

        for _i in range(200):  # Run for ~3.3 seconds
            elapsed = time.time() - start_time

            for idx, controller in enumerate(mock_cm.controllers):
                # Kill controllers 1 and 4 (likely on same team due to random assignment)
                if elapsed > 1.5 and idx == 1:
                    controller.accel.x = 8.0
                    controller.accel.y = 6.0
                    controller.accel.z = 5.0
                elif elapsed > 2.0 and idx == 4:
                    controller.accel.x = 7.0
                    controller.accel.y = 5.0
                    controller.accel.z = 4.0
                else:
                    # Normal idle state
                    controller.accel.x = 0.1
                    controller.accel.y = 0.0
                    controller.accel.z = 1.0

            yield controller_manager_pb2.ControllerStateUpdate(
                controllers=mock_cm.controllers, timestamp=int(time.time() * 1000)
            )
            await asyncio.sleep(1.0 / 60.0)

    # Replace stream method
    mock_cm.StreamControllerStates = three_team_stream

    # Create and run game
    game = random_teams.RandomTeamsGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_random_teams_5",
        num_teams=3,
    )

    await game.run()

    # Verify game completed successfully
    assert game.state == random_teams.GameState.ENDED

    # Verify exactly 2 deaths
    death_events = event_collector.get_events_of_type("player_death")
    assert len(death_events) == 2

    # Verify team formation phase occurred
    assert event_collector.count_events_of_type("team_formation_start") == 1

    print("✅ Three-team random assignment test passed!")


if __name__ == "__main__":
    """Run tests directly with pytest."""
    import subprocess

    print("Running Random Teams integration tests...")
    result = subprocess.run(
        [
            "pytest",
            __file__,
            "-v",
            "-s",  # Show print statements
            "--tb=short",  # Short traceback
        ]
    )

    sys.exit(result.returncode)
