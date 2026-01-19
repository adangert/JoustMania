"""
Integration tests for FFA game mode with mock gRPC services.

Tests the full FFA game flow using mocked ControllerManager and Settings services,
verifying game logic, event publishing, and win conditions without real hardware.
"""

import asyncio
import importlib.util
import os

# Import the FFA game
import sys
import time

import pytest

# Setup paths
test_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(test_dir))
games_dir = os.path.join(test_dir, "games")

# Add project root for any needed imports
sys.path.insert(0, project_root)

# Import ffa directly without triggering package initialization
spec = importlib.util.spec_from_file_location("ffa", os.path.join(games_dir, "ffa.py"))
ffa = importlib.util.module_from_spec(spec)
sys.modules["ffa"] = ffa
spec.loader.exec_module(ffa)

# Import protobuf files directly without triggering package initialization
# Controller Manager protobufs
controller_pb_path = os.path.join(project_root, "services", "controller_manager")
sys.path.insert(0, controller_pb_path)
import controller_manager_pb2

# Settings protobufs
settings_pb_path = os.path.join(project_root, "services", "settings")
sys.path.insert(0, settings_pb_path)
import settings_pb2

# Game Coordinator protobufs (for Player message)
from proto import game_coordinator_pb2


class MockBidirectionalStream:
    """Mock bidirectional gRPC stream for StreamGameplayDataDynamic."""

    def __init__(self, controller_manager, death_schedule=None, infinite=False):
        """
        Initialize mock bidirectional stream.

        Args:
            controller_manager: Parent MockControllerManagerService
            death_schedule: Dict mapping time offset to controller index for deaths
            infinite: If True, stream indefinitely (for force_end tests)
        """
        self.controller_manager = controller_manager
        self.death_schedule = death_schedule or {2.0: 1, 3.0: 2}  # Default: controller 1 at 2s, 2 at 3s
        self.start_time = None
        self.running = True
        self.filter_serials = None  # None = all controllers
        self.infinite = infinite

    async def write(self, message):
        """Handle client messages (config, filter updates, effects)."""
        # Process config
        if message.HasField("config"):
            # Initial configuration received
            self.start_time = time.time()
        # Process filter updates
        elif message.HasField("filter_update"):
            self.filter_serials = set(message.filter_update.serials) if message.filter_update.serials else None
        # Ignore game effects (they're just visual feedback)

    def __aiter__(self):
        return self

    async def __anext__(self):
        """Yield next gameplay data update."""
        if not self.running:
            raise StopAsyncIteration

        # Wait for config to be received
        if self.start_time is None:
            await asyncio.sleep(0.01)
            return controller_manager_pb2.GameplayDataUpdate(controllers=[], timestamp=int(time.time() * 1000))

        elapsed = time.time() - self.start_time

        # Stop after 5 seconds (unless infinite mode)
        if not self.infinite and elapsed > 5.0:
            self.running = False
            raise StopAsyncIteration

        # Update controller states based on death schedule
        gameplay_data_list = []
        for i, controller in enumerate(self.controller_manager.controllers):
            # Check if this controller should die based on schedule
            died = False
            for death_time, death_index in self.death_schedule.items():
                if elapsed > death_time and i == death_index:
                    controller.accel.x = 5.0 + i  # High acceleration = death
                    controller.accel.y = 3.0 + i
                    controller.accel.z = 4.0
                    died = True
                    break

            if not died:
                # Normal idle state (small movements)
                controller.accel.x = 0.1
                controller.accel.y = 0.0
                controller.accel.z = 1.0

            # Apply filter if set
            if self.filter_serials is not None and controller.serial not in self.filter_serials:
                continue

            # Convert to GameplayData
            gd = controller_manager_pb2.GameplayData(
                serial=controller.serial,
                move_num=i,
                battery=controller.battery,
                team=controller.team,
                color=controller.color,
                accel=controller.accel,
                gyro=controller.gyro,
            )
            gameplay_data_list.append(gd)

        await asyncio.sleep(1.0 / 60.0)  # 60 FPS
        return controller_manager_pb2.GameplayDataUpdate(
            controllers=gameplay_data_list, timestamp=int(time.time() * 1000)
        )


class MockControllerManagerService:
    """Mock ControllerManager gRPC service for testing."""

    def __init__(self, num_controllers: int = 3, death_schedule=None, infinite=False):
        """
        Initialize mock controller manager.

        Args:
            num_controllers: Number of mock controllers to simulate
            death_schedule: Dict mapping time offset to controller index for deaths
            infinite: If True, stream indefinitely (for force_end tests)
        """
        self.num_controllers = num_controllers
        self.controllers = []
        self.death_schedule = death_schedule or {2.0: 1, 3.0: 2}
        self.infinite = infinite
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
                team=0,
                color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                accel=controller_manager_pb2.Vector3(x=0.0, y=0.0, z=1.0),
                gyro=controller_manager_pb2.Vector3(x=0.0, y=0.0, z=0.0),
            )
            self.controllers.append(controller)

    def StreamGameplayDataDynamic(self):
        """
        Return a mock bidirectional stream for gameplay data.

        Games call this to get the stream, then:
        - await stream.write(config) to configure
        - async for update in stream: to receive data
        """
        return MockBidirectionalStream(self, self.death_schedule, self.infinite)

    async def SetControllerColor(self, request):
        """Mock SetControllerColor RPC."""
        return controller_manager_pb2.SetControllerColorResponse(success=True)


class MockSettingsService:
    """Mock Settings gRPC service for testing."""

    def __init__(self):
        """Initialize mock settings."""
        self.settings = {
            "sensitivity": "MEDIUM",
            "play_audio": "false",  # Disable audio in tests
            "color_lock": "false",
            "random_teams": "false",
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
    return MockControllerManagerService(num_controllers=3)


@pytest.fixture
def mock_settings():
    """Fixture providing mock Settings service."""
    return MockSettingsService()


@pytest.fixture
def event_collector():
    """Fixture providing event collector."""
    return EventCollector()


@pytest.mark.asyncio
async def test_ffa_game_full_lifecycle(mock_controller_manager, mock_settings, event_collector):
    """
    Test full FFA game lifecycle:
    - Game starts
    - Players initialized
    - Countdown runs
    - Game loop processes controller states
    - Players die when accelerating too much
    - Winner determined
    - Game ends
    """
    # Create initial players from mock controllers
    initial_players = [
        game_coordinator_pb2.Player(serial=c.serial, team=0, alive=True, score=0)
        for c in mock_controller_manager.controllers
    ]

    # Create FFA game with mock services
    game = ffa.FFAGame(
        controller_manager_client=mock_controller_manager,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_1",
        initial_players=initial_players,
    )

    # Run the game
    await game.run()

    # Verify game completed
    assert game.state == ffa.GameState.ENDED

    # Verify events were published
    assert event_collector.count_events_of_type("game_starting") == 1
    assert event_collector.count_events_of_type("players_initialized") == 1
    assert event_collector.count_events_of_type("countdown_start") == 1
    assert event_collector.count_events_of_type("countdown_end") == 1
    assert event_collector.count_events_of_type("game_started") == 1

    # Verify players were initialized
    players_init_events = event_collector.get_events_of_type("players_initialized")
    assert len(players_init_events) == 1
    assert players_init_events[0]["player_count"] == 3

    # Verify deaths occurred (2 players should die)
    death_events = event_collector.get_events_of_type("player_death")
    assert len(death_events) == 2, f"Expected 2 deaths, got {len(death_events)}"

    # Verify winner was determined
    winner_events = event_collector.get_events_of_type("game_winner")
    assert len(winner_events) == 1, f"Expected 1 winner, got {len(winner_events)}"

    # Winner should be controller 0 (the only one that didn't die)
    assert winner_events[0]["serial"] == "mock_controller_0"

    # Verify game ended
    assert event_collector.count_events_of_type("game_ended") == 1

    print(f"\n✅ Test passed! Total events: {len(event_collector.events)}")
    print("Events timeline:")
    for event_type, data in event_collector.events:
        print(f"  - {event_type}: {data}")


@pytest.mark.asyncio
async def test_ffa_game_with_two_players(mock_settings, event_collector):
    """Test FFA game with minimum 2 players."""
    # Create mock controller manager with 2 controllers and quick death
    mock_cm = MockControllerManagerService(
        num_controllers=2,
        death_schedule={0.1: 1},  # Controller 1 dies quickly (at 0.1s)
    )

    # Create and run game
    game = ffa.FFAGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_2",
    )

    await game.run()

    # Verify game completed successfully
    assert game.state == ffa.GameState.ENDED

    # Verify exactly 1 death
    death_events = event_collector.get_events_of_type("player_death")
    assert len(death_events) == 1

    # Verify winner
    winner_events = event_collector.get_events_of_type("game_winner")
    assert len(winner_events) == 1
    assert winner_events[0]["serial"] == "mock_controller_0"

    print("✅ Two-player test passed!")


@pytest.mark.asyncio
async def test_ffa_game_settings_loaded(mock_controller_manager, mock_settings, event_collector):
    """Test that game loads settings from Settings service."""
    # Customize settings
    mock_settings.settings["sensitivity"] = "FAST"
    mock_settings.settings["play_audio"] = "true"

    # Create game
    game = ffa.FFAGame(
        controller_manager_client=mock_controller_manager,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_3",
    )

    # Load settings (called internally by run(), but we can test separately)
    await game._load_settings()

    # Verify settings were loaded
    assert game.sensitivity == ffa.Sensitivity.FAST
    assert game.play_audio is True

    print("✅ Settings loading test passed!")


@pytest.mark.asyncio
async def test_ffa_game_force_end(mock_settings, event_collector):
    """Test that force_end() stops the game."""
    # Create mock controller manager that streams forever (no deaths)
    mock_cm = MockControllerManagerService(
        num_controllers=3,
        death_schedule={},  # No deaths
        infinite=True,  # Stream indefinitely until force_end
    )

    # Create game
    game = ffa.FFAGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_4",
    )

    # Start game in background task
    game_task = asyncio.create_task(game.run())

    # Wait a bit, then force end
    await asyncio.sleep(0.5)
    game.force_end()

    # Wait for game to finish
    try:
        await asyncio.wait_for(game_task, timeout=2.0)
    except TimeoutError:
        pytest.fail("Game did not end after force_end() was called")

    # Verify game stopped
    assert game.running is False

    print("✅ Force end test passed!")


if __name__ == "__main__":
    """Run tests directly with pytest."""
    import subprocess

    print("Running FFA integration tests...")
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
