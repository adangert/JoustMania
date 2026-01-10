"""
Integration tests for FFA game mode with mock gRPC services.

Tests the full FFA game flow using mocked ControllerManager and Settings services,
verifying game logic, event publishing, and win conditions without real hardware.
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict

# Import the FFA game
import sys
import os
import importlib.util

# Setup paths
test_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(test_dir))
games_dir = os.path.join(test_dir, 'games')

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


class MockControllerManagerService:
    """Mock ControllerManager gRPC service for testing."""

    def __init__(self, num_controllers: int = 3):
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
                gyro=controller_manager_pb2.Vector3(x=0.0, y=0.0, z=0.0)
            )
            self.controllers.append(controller)

    def GetReadyControllers(self, request):
        """Mock GetReadyControllers RPC."""
        return controller_manager_pb2.GetReadyControllersResponse(
            controllers=self.controllers,
            success=True,
            error=""
        )

    async def StreamControllerStates(self, request):
        """
        Mock StreamControllerStates RPC.

        Simulates controller state updates with one controller dying after 2 seconds.
        """
        start_time = time.time()
        frame = 0

        # Simulate game for 5 seconds
        while time.time() - start_time < 5.0:
            frame += 1

            # Update controller states
            for i, controller in enumerate(self.controllers):
                # After 2 seconds, make controller 1 move violently (dies)
                if time.time() - start_time > 2.0 and i == 1:
                    controller.accel.x = 5.0  # High acceleration = death
                    controller.accel.y = 3.0
                    controller.accel.z = 4.0
                # After 3 seconds, make controller 2 move violently (dies)
                elif time.time() - start_time > 3.0 and i == 2:
                    controller.accel.x = 6.0
                    controller.accel.y = 4.0
                    controller.accel.z = 3.0
                else:
                    # Normal idle state (small movements)
                    controller.accel.x = 0.1
                    controller.accel.y = 0.0
                    controller.accel.z = 1.0

            # Yield state update
            yield controller_manager_pb2.ControllerStateUpdate(
                controllers=self.controllers,
                timestamp=int(time.time() * 1000)
            )

            # 60 FPS = ~16.67ms per frame
            await asyncio.sleep(1.0 / 60.0)


class MockSettingsService:
    """Mock Settings gRPC service for testing."""

    def __init__(self):
        """Initialize mock settings."""
        self.settings = {
            'sensitivity': 'MEDIUM',
            'play_audio': 'false',  # Disable audio in tests
            'color_lock': 'false',
            'random_teams': 'false',
        }

    def GetSettings(self, request):
        """Mock GetSettings RPC."""
        return settings_pb2.GetSettingsResponse(
            settings=self.settings,
            success=True,
            error=""
        )


class EventCollector:
    """Collects events published by the game."""

    def __init__(self):
        self.events: List[tuple] = []  # List of (event_type, data)

    def publish(self, event_type: str, data: Dict):
        """Collect published event."""
        self.events.append((event_type, data))
        print(f"Event published: {event_type} - {data}")

    def get_events_of_type(self, event_type: str) -> List[Dict]:
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
    # Create FFA game with mock services
    game = ffa.FFAGame(
        controller_manager_client=mock_controller_manager,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_1"
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
    print(f"Events timeline:")
    for event_type, data in event_collector.events:
        print(f"  - {event_type}: {data}")


@pytest.mark.asyncio
async def test_ffa_game_with_two_players(mock_settings, event_collector):
    """Test FFA game with minimum 2 players."""
    # Create mock controller manager with 2 controllers
    mock_cm = MockControllerManagerService(num_controllers=2)

    # Make controller 1 die quickly
    async def quick_death_stream(request):
        """Stream with controller 1 dying immediately."""
        for i in range(10):  # Just 10 frames
            if i > 3:  # After 3 frames, controller 1 dies
                mock_cm.controllers[1].accel.x = 10.0
                mock_cm.controllers[1].accel.y = 8.0
                mock_cm.controllers[1].accel.z = 6.0

            yield controller_manager_pb2.ControllerStateUpdate(
                controllers=mock_cm.controllers,
                timestamp=int(time.time() * 1000)
            )
            await asyncio.sleep(1.0 / 60.0)

    # Replace stream method
    mock_cm.StreamControllerStates = quick_death_stream

    # Create and run game
    game = ffa.FFAGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_2"
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

    print(f"✅ Two-player test passed!")


@pytest.mark.asyncio
async def test_ffa_game_settings_loaded(mock_controller_manager, mock_settings, event_collector):
    """Test that game loads settings from Settings service."""
    # Customize settings
    mock_settings.settings['sensitivity'] = 'FAST'
    mock_settings.settings['play_audio'] = 'true'

    # Create game
    game = ffa.FFAGame(
        controller_manager_client=mock_controller_manager,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_3"
    )

    # Load settings (called internally by run(), but we can test separately)
    await game._load_settings()

    # Verify settings were loaded
    assert game.sensitivity == ffa.Sensitivity.FAST
    assert game.play_audio == True

    print(f"✅ Settings loading test passed!")


@pytest.mark.asyncio
async def test_ffa_game_force_end(mock_settings, event_collector):
    """Test that force_end() stops the game."""
    # Create mock controller manager that streams forever
    mock_cm = MockControllerManagerService(num_controllers=3)

    async def infinite_stream(request):
        """Stream indefinitely (until force_end)."""
        while True:
            yield controller_manager_pb2.ControllerStateUpdate(
                controllers=mock_cm.controllers,
                timestamp=int(time.time() * 1000)
            )
            await asyncio.sleep(1.0 / 60.0)

    mock_cm.StreamControllerStates = infinite_stream

    # Create game
    game = ffa.FFAGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_4"
    )

    # Start game in background task
    game_task = asyncio.create_task(game.run())

    # Wait a bit, then force end
    await asyncio.sleep(0.5)
    game.force_end()

    # Wait for game to finish
    try:
        await asyncio.wait_for(game_task, timeout=2.0)
    except asyncio.TimeoutError:
        pytest.fail("Game did not end after force_end() was called")

    # Verify game stopped
    assert game.running == False

    print(f"✅ Force end test passed!")


if __name__ == "__main__":
    """Run tests directly with pytest."""
    import subprocess

    print("Running FFA integration tests...")
    result = subprocess.run([
        "pytest",
        __file__,
        "-v",
        "-s",  # Show print statements
        "--tb=short"  # Short traceback
    ])

    sys.exit(result.returncode)
