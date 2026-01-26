"""
Unit tests for ControllerManagerServicer.

Tests the gRPC servicer methods that can be tested in isolation:
- RenameController RPC
- Vibration scheduling
- Basic initialization

Note: Streaming methods (StreamButtonEvents, StreamGameplayData) require
extensive mocking of discovery loop, backends, etc. and are covered by
integration tests.

Issue #209: Improve test coverage for critical game flow
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Setup paths for imports
test_dir = Path(__file__).parent
service_dir = test_dir.parent
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(test_dir))

from proto import controller_manager_pb2  # noqa: E402


class MockGrpcContext:
    """Mock gRPC context for testing."""

    def __init__(self):
        self._cancelled = False

    def cancelled(self):
        return self._cancelled


class MockBackend:
    """Mock backend for testing without hardware."""

    def __init__(self):
        self.controllers = {}
        self.led_colors = {}
        self.rumble_values = {}
        self.effect_active = {}

    def initialize(self):
        pass

    def discover(self):
        return list(self.controllers.keys())

    def poll(self, serial):
        return self.controllers.get(serial, {})

    def set_led(self, serial, r, g, b):
        self.led_colors[serial] = (r, g, b)

    async def set_rumble(self, serial, intensity):
        self.rumble_values[serial] = intensity

    def set_effect_active(self, serial, active):
        self.effect_active[serial] = active

    def cleanup(self):
        pass


class TestRenameController:
    """Tests for RenameController RPC."""

    @pytest.fixture
    def servicer_components(self):
        """Create mock components for servicer testing."""
        # Mock the backend and discovery loop to avoid hardware initialization
        with (
            patch("services.controller_manager.servicer.create_backend") as mock_create_backend,
            patch("services.controller_manager.servicer.DiscoveryLoop") as mock_discovery_loop,
        ):
            mock_backend = MockBackend()
            mock_create_backend.return_value = mock_backend

            mock_loop = MagicMock()
            mock_loop.start = MagicMock()
            mock_loop.stop = MagicMock()
            mock_loop.join = MagicMock()
            mock_discovery_loop.return_value = mock_loop

            from services.controller_manager.servicer import ControllerManagerServicer

            servicer = ControllerManagerServicer()
            yield servicer, mock_backend

    @pytest.mark.asyncio
    async def test_rename_controller_success(self, servicer_components):
        """RenameController should succeed with valid serial and name."""
        servicer, _ = servicer_components
        context = MockGrpcContext()

        # Add a tracked controller
        servicer.tracked_controllers["test_serial"] = {"battery": 80}

        request = controller_manager_pb2.RenameControllerRequest(serial="test_serial", name="Player 1")

        response = await servicer.RenameController(request, context)

        assert response.success is True
        assert response.error == ""
        # Check name was stored
        assert servicer.name_manager.get_name("test_serial") == "Player 1"

    @pytest.mark.asyncio
    async def test_rename_controller_updates_tracked(self, servicer_components):
        """RenameController should update tracked_controllers if connected."""
        servicer, _ = servicer_components
        context = MockGrpcContext()

        # Add a tracked controller
        from lib.controller_constants import ControllerInfoKey

        servicer.tracked_controllers["test_serial"] = {
            ControllerInfoKey.BATTERY: 80,
            ControllerInfoKey.NAME: "Old Name",
        }

        request = controller_manager_pb2.RenameControllerRequest(serial="test_serial", name="New Name")

        await servicer.RenameController(request, context)

        assert servicer.tracked_controllers["test_serial"][ControllerInfoKey.NAME] == "New Name"

    @pytest.mark.asyncio
    async def test_rename_controller_empty_serial(self, servicer_components):
        """RenameController should fail with empty serial."""
        servicer, _ = servicer_components
        context = MockGrpcContext()

        request = controller_manager_pb2.RenameControllerRequest(serial="", name="Player 1")

        response = await servicer.RenameController(request, context)

        assert response.success is False
        assert "serial" in response.error.lower()

    @pytest.mark.asyncio
    async def test_rename_controller_empty_name(self, servicer_components):
        """RenameController should fail with empty name."""
        servicer, _ = servicer_components
        context = MockGrpcContext()

        request = controller_manager_pb2.RenameControllerRequest(serial="test_serial", name="")

        response = await servicer.RenameController(request, context)

        assert response.success is False
        assert "name" in response.error.lower()

    @pytest.mark.asyncio
    async def test_rename_controller_not_connected(self, servicer_components):
        """RenameController should succeed even if controller not connected."""
        servicer, _ = servicer_components
        context = MockGrpcContext()

        # Don't add controller to tracked_controllers
        request = controller_manager_pb2.RenameControllerRequest(serial="unknown_serial", name="Player 1")

        response = await servicer.RenameController(request, context)

        # Should still succeed - name is stored for when controller connects
        assert response.success is True
        assert servicer.name_manager.get_name("unknown_serial") == "Player 1"


class TestVibrationScheduling:
    """Tests for vibration task scheduling."""

    @pytest.fixture
    def servicer_components(self):
        """Create mock components for servicer testing."""
        with (
            patch("services.controller_manager.servicer.create_backend") as mock_create_backend,
            patch("services.controller_manager.servicer.DiscoveryLoop") as mock_discovery_loop,
        ):
            mock_backend = MagicMock()
            mock_backend.set_rumble = AsyncMock()
            mock_create_backend.return_value = mock_backend

            mock_loop = MagicMock()
            mock_loop.start = MagicMock()
            mock_loop.stop = MagicMock()
            mock_loop.join = MagicMock()
            mock_discovery_loop.return_value = mock_loop

            from services.controller_manager.servicer import ControllerManagerServicer

            servicer = ControllerManagerServicer()
            yield servicer, mock_backend

    @pytest.mark.asyncio
    async def test_schedule_vibration_stop_creates_task(self, servicer_components):
        """_schedule_vibration_stop should create an asyncio task."""
        servicer, mock_backend = servicer_components

        # Add a tracked controller
        servicer.tracked_controllers["test_serial"] = {}

        await servicer._schedule_vibration_stop("test_serial", 100)

        assert "test_serial" in servicer.vibration_tasks
        assert isinstance(servicer.vibration_tasks["test_serial"], asyncio.Task)

        # Cancel the task to clean up
        servicer.vibration_tasks["test_serial"].cancel()

    @pytest.mark.asyncio
    async def test_schedule_vibration_stop_cancels_previous(self, servicer_components):
        """_schedule_vibration_stop should cancel existing task for same controller."""
        servicer, mock_backend = servicer_components

        servicer.tracked_controllers["test_serial"] = {}

        # Schedule first task
        await servicer._schedule_vibration_stop("test_serial", 1000)
        first_task = servicer.vibration_tasks["test_serial"]

        # Schedule second task (should cancel first)
        await servicer._schedule_vibration_stop("test_serial", 1000)
        second_task = servicer.vibration_tasks["test_serial"]

        assert first_task.cancelled() or first_task.done()
        assert second_task is not first_task

        # Cancel to clean up
        second_task.cancel()

    @pytest.mark.asyncio
    async def test_schedule_vibration_stop_calls_backend(self, servicer_components):
        """_schedule_vibration_stop should call backend.set_rumble(0) after delay."""
        servicer, mock_backend = servicer_components

        servicer.tracked_controllers["test_serial"] = {}

        # Use short duration for test
        await servicer._schedule_vibration_stop("test_serial", 50)

        # Wait for task to complete
        await asyncio.sleep(0.1)

        # Backend should have been called with rumble=0
        mock_backend.set_rumble.assert_called_with("test_serial", 0)


class TestServicerInitialization:
    """Tests for servicer initialization."""

    @pytest.fixture
    def servicer(self):
        """Create servicer with mocked dependencies."""
        with (
            patch("services.controller_manager.servicer.create_backend") as mock_create_backend,
            patch("services.controller_manager.servicer.DiscoveryLoop") as mock_discovery_loop,
        ):
            mock_backend = MockBackend()
            mock_create_backend.return_value = mock_backend

            mock_loop = MagicMock()
            mock_loop.start = MagicMock()
            mock_loop.stop = MagicMock()
            mock_loop.join = MagicMock()
            mock_discovery_loop.return_value = mock_loop

            from services.controller_manager.servicer import ControllerManagerServicer

            servicer = ControllerManagerServicer()
            yield servicer

    def test_init_creates_empty_tracked_controllers(self, servicer):
        """Servicer should start with empty tracked_controllers."""
        assert servicer.tracked_controllers == {}

    def test_init_creates_empty_controller_states(self, servicer):
        """Servicer should start with empty controller_states."""
        assert servicer.controller_states == {}

    def test_init_creates_empty_subscribers(self, servicer):
        """Servicer should start with empty subscribers."""
        assert servicer.stream_subscribers == {}
        assert servicer.button_event_subscribers == {}

    def test_init_starts_discovery_loop(self, servicer):
        """Servicer should start discovery loop on init."""
        servicer.discovery_loop.start.assert_called_once()


class TestServicerShutdown:
    """Tests for servicer shutdown."""

    @pytest.fixture
    def servicer(self):
        """Create servicer with mocked dependencies."""
        with (
            patch("services.controller_manager.servicer.create_backend") as mock_create_backend,
            patch("services.controller_manager.servicer.DiscoveryLoop") as mock_discovery_loop,
        ):
            mock_backend = MockBackend()
            mock_create_backend.return_value = mock_backend

            mock_loop = MagicMock()
            mock_loop.start = MagicMock()
            mock_loop.stop = MagicMock()
            mock_loop.join = MagicMock()
            mock_discovery_loop.return_value = mock_loop

            from services.controller_manager.servicer import ControllerManagerServicer

            servicer = ControllerManagerServicer()
            yield servicer

    def test_shutdown_stops_discovery_loop(self, servicer):
        """Shutdown should stop discovery loop."""
        servicer.shutdown()

        servicer.discovery_loop.stop.assert_called_once()
        servicer.discovery_loop.join.assert_called_once()

    def test_shutdown_terminates_controller_processes(self, servicer):
        """Shutdown should terminate controller processes."""
        # Add mock process
        mock_proc = MagicMock()
        mock_proc.is_alive.return_value = True
        servicer.controller_processes["test_serial"] = mock_proc

        servicer.shutdown()

        mock_proc.terminate.assert_called_once()
        mock_proc.join.assert_called_once()

    def test_shutdown_skips_dead_processes(self, servicer):
        """Shutdown should skip already-dead processes."""
        mock_proc = MagicMock()
        mock_proc.is_alive.return_value = False
        servicer.controller_processes["test_serial"] = mock_proc

        servicer.shutdown()

        mock_proc.terminate.assert_not_called()
