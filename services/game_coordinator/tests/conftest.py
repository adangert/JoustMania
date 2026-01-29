"""
Shared fixtures and mocks for game coordinator tests.

Provides MockControllerManagerService, MockSettingsService, and EventCollector
for testing game modes without real hardware or gRPC services.
"""

import asyncio
import sys
import time
from pathlib import Path

import pytest

# Setup paths for imports
test_dir = Path(__file__).parent
service_dir = test_dir.parent
project_root = service_dir.parent.parent

# Add paths for imports
sys.path.insert(0, str(project_root))

# Disable OpenTelemetry for tests - must be done before importing service modules
from lib.otel_metrics import disable_metrics_for_tests  # noqa: E402
from lib.telemetry import disable_telemetry_for_tests  # noqa: E402

disable_telemetry_for_tests()
disable_metrics_for_tests()

# Import protobufs from proto package (must be after path setup)
from proto import controller_manager_pb2, settings_pb2  # noqa: E402


class MockBidirectionalStream:
    """Mock bidirectional gRPC stream for StreamGameplayData."""

    def __init__(self, controller_manager, death_schedule=None, infinite=False, max_duration=5.0):
        """
        Initialize mock bidirectional stream.

        Args:
            controller_manager: Parent MockControllerManagerService
            death_schedule: Dict mapping time offset to controller index for deaths
            infinite: If True, stream indefinitely (for force_end tests)
            max_duration: Maximum stream duration in seconds (default 5.0)
        """
        self.controller_manager = controller_manager
        self.death_schedule = death_schedule or {}
        self.start_time = None
        self.running = True
        self.filter_serials = None
        self.infinite = infinite
        self.max_duration = max_duration

    async def write(self, message):
        """Handle client messages (config, filter updates, effects)."""
        if message.HasField("config"):
            self.start_time = time.time()
        elif message.HasField("filter_update"):
            self.filter_serials = set(message.filter_update.serials) if message.filter_update.serials else None
        elif message.HasField("game_effect"):
            # Game effects (countdown, death, etc.) - just log in mock
            pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        """Yield next gameplay data update."""
        if not self.running:
            raise StopAsyncIteration

        if self.start_time is None:
            await asyncio.sleep(0.01)
            return controller_manager_pb2.GameplayDataUpdate(controllers=[], timestamp=int(time.time() * 1000))

        elapsed = time.time() - self.start_time

        if not self.infinite and elapsed > self.max_duration:
            self.running = False
            raise StopAsyncIteration

        gameplay_data_list = []
        for i, controller in enumerate(self.controller_manager.controllers):
            died = False
            for death_time, death_index in self.death_schedule.items():
                if elapsed > death_time and i == death_index:
                    controller.accel.x = 5.0 + i
                    controller.accel.y = 3.0 + i
                    controller.accel.z = 4.0
                    died = True
                    break

            if not died:
                controller.accel.x = 0.1
                controller.accel.y = 0.0
                controller.accel.z = 1.0

            if self.filter_serials is not None and controller.serial not in self.filter_serials:
                continue

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

        await asyncio.sleep(1.0 / 60.0)
        return controller_manager_pb2.GameplayDataUpdate(
            controllers=gameplay_data_list, timestamp=int(time.time() * 1000)
        )


class MockControllerManagerService:
    """Mock ControllerManager gRPC service for testing."""

    def __init__(
        self,
        num_controllers: int = 4,
        death_schedule: dict | None = None,
        infinite: bool = False,
        max_duration: float = 5.0,
    ):
        """
        Initialize mock controller manager.

        Args:
            num_controllers: Number of mock controllers to simulate
            death_schedule: Dict mapping time offset to controller index for deaths
            infinite: If True, stream indefinitely (for force_end tests)
            max_duration: Maximum stream duration in seconds
        """
        self.num_controllers = num_controllers
        self.controllers = []
        self.death_schedule = death_schedule or {}
        self.infinite = infinite
        self.max_duration = max_duration
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

    def StreamGameplayData(self):  # noqa: N802 - matches gRPC naming
        """Return a mock bidirectional stream for gameplay data."""
        return MockBidirectionalStream(self, self.death_schedule, self.infinite, self.max_duration)

    async def SetControllerColor(self, request):  # noqa: N802 - matches gRPC naming
        """Mock SetControllerColor RPC."""
        return controller_manager_pb2.SetControllerColorResponse(success=True)


class MockSettingsService:
    """Mock Settings gRPC service for testing."""

    def __init__(self):
        """Initialize mock settings."""
        self.settings = {
            "sensitivity": "MEDIUM",
            "play_audio": "false",
            "color_lock": "false",
            "random_teams": "false",
        }

    def GetSettings(self, request):  # noqa: N802 - matches gRPC naming
        """Mock GetSettings RPC."""
        return settings_pb2.GetSettingsResponse(settings=self.settings, success=True, error="")


class EventCollector:
    """Collects events published by the game."""

    def __init__(self):
        self.events: list[tuple] = []

    def publish(self, event_type: str, data: dict):
        """Collect published event."""
        self.events.append((event_type, data))

    def get_events_of_type(self, event_type: str) -> list[dict]:
        """Get all events of a specific type."""
        return [data for et, data in self.events if et == event_type]

    def count_events_of_type(self, event_type: str) -> int:
        """Count events of a specific type."""
        return len(self.get_events_of_type(event_type))

    def clear(self):
        """Clear all collected events."""
        self.events.clear()


# Fixtures


@pytest.fixture
def mock_controller_manager():
    """Fixture providing mock ControllerManager service with default death schedule."""
    return MockControllerManagerService(
        num_controllers=3,
        death_schedule={2.0: 1, 3.0: 2},  # Controllers 1 and 2 die
    )


@pytest.fixture
def mock_settings():
    """Fixture providing mock Settings service."""
    return MockSettingsService()


@pytest.fixture
def event_collector():
    """Fixture providing event collector."""
    return EventCollector()
