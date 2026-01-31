"""Unit tests for StateManager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.menu.handlers.base import ControllerState
from services.menu.state_manager import StateManager


@pytest.fixture
def mock_led():
    """Create mock LedController."""
    led = MagicMock()
    led.set_connected_color = AsyncMock()
    led.set_ready_color = AsyncMock()
    return led


@pytest.fixture
def mock_audio():
    """Create mock AudioHelper."""
    return MagicMock()


@pytest.fixture
def mock_settings():
    """Create mock SettingsHelper."""
    return MagicMock()


@pytest.fixture
def mock_publish_event():
    """Create mock publish_event function."""
    return AsyncMock()


@pytest.fixture
def state_manager(mock_led, mock_audio, mock_settings, mock_publish_event):
    """Create StateManager instance."""
    return StateManager(mock_led, mock_audio, mock_settings, mock_publish_event)


class TestStateManagerInit:
    """Test StateManager initialization."""

    def test_initialization(self, state_manager):
        """StateManager should initialize correctly."""
        assert state_manager.controller_states == {}
        assert state_manager.connected_controllers == set()
        assert state_manager.ready_controllers == set()
        from lib.types import Games

        assert state_manager.current_game_mode == Games.JoustFFA


class TestStateManagerHandlerRegistration:
    """Test handler registration."""

    def test_register_handler(self, state_manager):
        """Handler should be registered for its state."""
        handler = MagicMock()
        handler.state = ControllerState.CONNECTED

        state_manager.register_handler(handler)

        handler.set_state_manager.assert_called_once_with(state_manager)
        assert state_manager.get_handler(ControllerState.CONNECTED) is handler


class TestStateManagerConnection:
    """Test controller connection handling."""

    @pytest.mark.asyncio
    async def test_on_controller_connected(self, state_manager):
        """Connecting a controller should add it to connected set."""
        handler = MagicMock()
        handler.state = ControllerState.CONNECTED
        handler.on_enter = AsyncMock()
        state_manager.register_handler(handler)

        await state_manager.on_controller_connected("serial1")

        assert "serial1" in state_manager.connected_controllers
        assert state_manager.controller_states["serial1"] == ControllerState.CONNECTED

    @pytest.mark.asyncio
    async def test_on_controller_disconnected(self, state_manager):
        """Disconnecting a controller should clean up state."""
        state_manager.connected_controllers.add("serial1")
        state_manager.controller_states["serial1"] = ControllerState.CONNECTED

        handler = MagicMock()
        handler.state = ControllerState.CONNECTED
        handler.on_exit = AsyncMock()
        state_manager.register_handler(handler)

        await state_manager.on_controller_disconnected("serial1")

        assert "serial1" not in state_manager.connected_controllers
        assert "serial1" not in state_manager.controller_states


class TestStateManagerTransition:
    """Test state transitions."""

    @pytest.mark.asyncio
    @patch("services.menu.state_manager.metrics")
    async def test_transition_to_ready(self, mock_metrics, state_manager):
        """Transitioning to READY should update ready_controllers."""
        state_manager.connected_controllers.add("serial1")
        state_manager.controller_states["serial1"] = ControllerState.CONNECTED

        old_handler = MagicMock()
        old_handler.state = ControllerState.CONNECTED
        old_handler.on_exit = AsyncMock()
        state_manager.register_handler(old_handler)

        new_handler = MagicMock()
        new_handler.state = ControllerState.READY
        new_handler.on_enter = AsyncMock()
        state_manager.register_handler(new_handler)

        await state_manager.transition_to("serial1", ControllerState.READY)

        assert "serial1" in state_manager.ready_controllers
        assert state_manager.controller_states["serial1"] == ControllerState.READY

    @pytest.mark.asyncio
    async def test_transition_to_same_state(self, state_manager):
        """Transitioning to same state should be a no-op."""
        state_manager.controller_states["serial1"] = ControllerState.CONNECTED

        handler = MagicMock()
        handler.state = ControllerState.CONNECTED
        handler.on_exit = AsyncMock()
        handler.on_enter = AsyncMock()
        state_manager.register_handler(handler)

        await state_manager.transition_to("serial1", ControllerState.CONNECTED)

        handler.on_exit.assert_not_called()
        handler.on_enter.assert_not_called()


class TestStateManagerHelpers:
    """Test helper methods."""

    def test_update_battery(self, state_manager):
        """update_battery should store battery level."""
        state_manager.update_battery("serial1", 4)
        assert state_manager.battery_levels["serial1"] == 4

    def test_all_ready_true(self, state_manager):
        """all_ready should return True when all connected are ready (min 2)."""
        state_manager.controller_states = {"s1": ControllerState.READY, "s2": ControllerState.READY}
        assert state_manager.all_ready() is True

    def test_all_ready_false_not_enough(self, state_manager):
        """all_ready should return False when less than 2 ready."""
        state_manager.controller_states = {"s1": ControllerState.READY}
        assert state_manager.all_ready() is False

    def test_set_game_mode(self, state_manager):
        """set_game_mode should update current game mode."""
        from lib.types import Games

        state_manager.set_game_mode(Games.Werewolf)
        assert state_manager.current_game_mode == Games.Werewolf

    @pytest.mark.asyncio
    @patch("services.menu.state_manager.metrics")
    async def test_reset(self, mock_metrics, state_manager):
        """reset should clear ready state and re-register controllers."""
        # Set up state via controller_states (single source of truth)
        state_manager.controller_states = {"s1": ControllerState.READY, "s2": ControllerState.CONNECTED}
        state_manager.button_states = {"s1": {"trigger": True}}

        re_registered = await state_manager.reset()

        # Controllers from controller_states should be re-registered
        assert set(re_registered) == {"s1", "s2"}
        # Re-registered controllers should be in connected set
        assert state_manager.connected_controllers == {"s1", "s2"}
        # All controllers should be in CONNECTED state (not READY)
        assert state_manager.controller_states == {"s1": ControllerState.CONNECTED, "s2": ControllerState.CONNECTED}
        # Ready controllers should be cleared
        assert state_manager.ready_controllers == set()
        # Button states should be cleared
        assert state_manager.button_states == {}
