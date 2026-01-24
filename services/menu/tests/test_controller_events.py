"""Unit tests for ControllerEventLoop."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from proto import controller_manager_pb2
from services.menu.controller_events import BUTTON_TYPE_NAMES, ControllerEventLoop


@pytest.fixture
def mock_callbacks():
    """Create mock ControllerEventCallbacks."""
    callbacks = MagicMock()
    callbacks.on_connect = AsyncMock()
    callbacks.on_disconnect = AsyncMock()
    callbacks.on_button = AsyncMock()
    callbacks.update_battery = MagicMock()
    callbacks.get_menu_state = MagicMock(return_value=1)  # RUNNING
    return callbacks


@pytest.fixture
def mock_metrics():
    """Create mock metrics."""
    metrics = MagicMock()
    metrics.button_frames_processed_total.inc = MagicMock()
    return metrics


@pytest.fixture
def event_loop_instance(mock_callbacks, mock_metrics):
    """Create ControllerEventLoop instance."""
    return ControllerEventLoop(MagicMock(), MagicMock(), mock_callbacks, mock_metrics)


class TestControllerEventLoopInit:
    """Test ControllerEventLoop initialization."""

    def test_initialization(self, event_loop_instance):
        """ControllerEventLoop should initialize correctly."""
        assert event_loop_instance._running is False
        assert event_loop_instance._task is None


class TestControllerEventLoopLifecycle:
    """Test start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self, event_loop_instance):
        """start should set running flag."""
        event_loop_instance._run = AsyncMock()

        await event_loop_instance.start()

        assert event_loop_instance._running is True
        assert event_loop_instance._task is not None

        await event_loop_instance.stop()

    @pytest.mark.asyncio
    async def test_stop(self, event_loop_instance):
        """stop should clear running flag."""
        event_loop_instance._running = True

        async def dummy():
            await asyncio.sleep(10)

        event_loop_instance._task = asyncio.create_task(dummy())

        await event_loop_instance.stop()

        assert event_loop_instance._running is False

    def test_is_running(self, event_loop_instance):
        """is_running should return running state."""
        assert event_loop_instance.is_running is False
        event_loop_instance._running = True
        assert event_loop_instance.is_running is True


class TestControllerEventLoopDispatch:
    """Test event dispatching."""

    @pytest.mark.asyncio
    async def test_dispatch_connect_event(self, event_loop_instance, mock_callbacks, mock_metrics):
        """Connect events should call on_connect callback."""
        event = MagicMock()
        event.serial = "serial1"
        event.event_type = controller_manager_pb2.EVENT_CONNECT
        event.battery = 5

        await event_loop_instance._dispatch_event(event)

        mock_callbacks.on_connect.assert_called_once_with("serial1")
        mock_callbacks.update_battery.assert_called_once_with("serial1", 5)

    @pytest.mark.asyncio
    async def test_dispatch_disconnect_event(self, event_loop_instance, mock_callbacks, mock_metrics):
        """Disconnect events should call on_disconnect callback."""
        event = MagicMock()
        event.serial = "serial1"
        event.event_type = controller_manager_pb2.EVENT_DISCONNECT
        event.battery = 0

        await event_loop_instance._dispatch_event(event)

        mock_callbacks.on_disconnect.assert_called_once_with("serial1")

    @pytest.mark.asyncio
    async def test_dispatch_button_event_press(self, event_loop_instance, mock_callbacks):
        """Button press events should call on_button callback."""
        from proto import menu_pb2

        mock_callbacks.get_menu_state.return_value = menu_pb2.MenuState.RUNNING

        event = MagicMock()
        event.serial = "serial1"
        event.event_type = 0  # Default, button event
        event.action = controller_manager_pb2.ACTION_PRESS
        event.button = controller_manager_pb2.BUTTON_TRIGGER
        event.battery = 4

        await event_loop_instance._dispatch_event(event)

        mock_callbacks.on_button.assert_called_once_with("serial1", "trigger", True)

    @pytest.mark.asyncio
    async def test_dispatch_button_event_menu_stopped(self, event_loop_instance, mock_callbacks):
        """Button events should be ignored when menu is not running."""
        from proto import menu_pb2

        mock_callbacks.get_menu_state.return_value = menu_pb2.MenuState.STOPPED

        event = MagicMock()
        event.serial = "serial1"
        event.event_type = 0
        event.action = controller_manager_pb2.ACTION_PRESS
        event.button = controller_manager_pb2.BUTTON_TRIGGER
        event.battery = 4

        await event_loop_instance._dispatch_event(event)

        mock_callbacks.on_button.assert_not_called()


class TestButtonTypeNames:
    """Test BUTTON_TYPE_NAMES mapping."""

    def test_all_buttons_mapped(self):
        """All button types should have names."""
        expected = [
            controller_manager_pb2.BUTTON_TRIGGER,
            controller_manager_pb2.BUTTON_MOVE,
            controller_manager_pb2.BUTTON_CROSS,
            controller_manager_pb2.BUTTON_CIRCLE,
            controller_manager_pb2.BUTTON_SQUARE,
            controller_manager_pb2.BUTTON_TRIANGLE,
            controller_manager_pb2.BUTTON_PS,
            controller_manager_pb2.BUTTON_SELECT,
            controller_manager_pb2.BUTTON_START,
        ]

        for button in expected:
            assert button in BUTTON_TYPE_NAMES

    def test_button_names_are_strings(self):
        """All button names should be lowercase strings."""
        for name in BUTTON_TYPE_NAMES.values():
            assert isinstance(name, str)
            assert name == name.lower()
