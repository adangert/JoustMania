"""Unit tests for controller state handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.menu.handlers.base import ControllerState
from services.menu.handlers.connected import ConnectedHandler
from services.menu.handlers.ready import ReadyHandler


class TestConnectedHandler:
    """Tests for ConnectedHandler."""

    @pytest.fixture
    def handler(self):
        """Create ConnectedHandler instance."""
        return ConnectedHandler()

    @pytest.fixture
    def mock_state_manager(self):
        """Create mock StateManager."""
        manager = MagicMock()
        manager.led = MagicMock()
        manager.led.set_connected_color = AsyncMock()
        manager.audio = MagicMock()
        manager.audio.play_sound = AsyncMock()
        manager.audio.play_game_mode_voice = AsyncMock()
        manager.settings = MagicMock()
        manager.settings.get_next_game_mode = MagicMock(return_value="JoustTeams")
        manager.settings.save_current_game = AsyncMock()
        manager.publish_event = AsyncMock()
        manager.transition_to = AsyncMock()
        manager.current_game_mode = "JoustFFA"
        return manager

    def test_state_property(self, handler):
        """Handler should return CONNECTED state."""
        assert handler.state == ControllerState.CONNECTED

    @pytest.mark.asyncio
    async def test_on_enter_sets_dim_color(self, handler, mock_state_manager):
        """on_enter should set dim LED color."""
        handler.set_state_manager(mock_state_manager)

        await handler.on_enter("serial1")

        mock_state_manager.led.set_connected_color.assert_called_once_with("serial1", "JoustFFA")

    @pytest.mark.asyncio
    @patch("services.menu.handlers.connected.time")
    async def test_handle_button_trigger(self, mock_time, handler, mock_state_manager):
        """Trigger press should transition to READY."""
        mock_time.time.return_value = 100.0
        handler.set_state_manager(mock_state_manager)

        await handler.handle_button("serial1", "trigger")

        mock_state_manager.transition_to.assert_called_once_with("serial1", ControllerState.READY)

    @pytest.mark.asyncio
    @patch("services.menu.handlers.connected.time")
    async def test_handle_button_move_cycles_game(self, mock_time, handler, mock_state_manager):
        """Move press should cycle game modes."""
        mock_time.time.return_value = 100.0
        handler.set_state_manager(mock_state_manager)

        await handler.handle_button("serial1", "move")

        mock_state_manager.settings.get_next_game_mode.assert_called_once()
        mock_state_manager.settings.save_current_game.assert_called_once()

    @pytest.mark.asyncio
    @patch("services.menu.handlers.connected.time")
    async def test_handle_button_debounce(self, mock_time, handler, mock_state_manager):
        """Rapid button presses should be debounced."""
        handler.set_state_manager(mock_state_manager)

        mock_time.time.return_value = 100.0
        await handler.handle_button("serial1", "trigger")

        mock_time.time.return_value = 100.05  # 50ms later
        await handler.handle_button("serial1", "trigger")

        assert mock_state_manager.transition_to.call_count == 1


class TestReadyHandler:
    """Tests for ReadyHandler."""

    @pytest.fixture
    def start_game_callback(self):
        """Create mock start game callback."""
        return AsyncMock()

    @pytest.fixture
    def handler(self, start_game_callback):
        """Create ReadyHandler instance."""
        return ReadyHandler(start_game_callback)

    @pytest.fixture
    def mock_state_manager(self):
        """Create mock StateManager."""
        manager = MagicMock()
        manager.led = MagicMock()
        manager.led.set_ready_color = AsyncMock()
        manager.transition_to = AsyncMock()
        manager.current_game_mode = "JoustFFA"
        manager.all_ready = MagicMock(return_value=False)
        manager.get_ready_count = MagicMock(return_value=1)
        manager.get_connected_count = MagicMock(return_value=2)
        return manager

    def test_state_property(self, handler):
        """Handler should return READY state."""
        assert handler.state == ControllerState.READY

    @pytest.mark.asyncio
    async def test_on_enter_sets_bright_color(self, handler, mock_state_manager):
        """on_enter should set bright LED color."""
        handler.set_state_manager(mock_state_manager)

        await handler.on_enter("serial1")

        mock_state_manager.led.set_ready_color.assert_called_once_with("serial1", "JoustFFA")

    @pytest.mark.asyncio
    async def test_on_enter_starts_game_when_all_ready(self, handler, mock_state_manager, start_game_callback):
        """on_enter should start game when all controllers are ready."""
        mock_state_manager.all_ready.return_value = True
        handler.set_state_manager(mock_state_manager)

        await handler.on_enter("serial1")

        start_game_callback.assert_called_once_with("serial1")

    @pytest.mark.asyncio
    @patch("services.menu.handlers.ready.time")
    async def test_handle_button_move_unreadies(self, mock_time, handler, mock_state_manager):
        """Move press should transition back to CONNECTED."""
        mock_time.time.return_value = 100.0
        handler.set_state_manager(mock_state_manager)

        await handler.handle_button("serial1", "move")

        mock_state_manager.transition_to.assert_called_once_with("serial1", ControllerState.CONNECTED)
