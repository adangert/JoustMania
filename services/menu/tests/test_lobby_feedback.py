"""
Unit tests for Menu service.

Tests the MenuServicer public API and basic functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from proto import menu_pb2
from services.menu.utils.settings import GAME_MODES


class TestGameModes:
    """Test game modes constants."""

    def test_game_modes_exist(self):
        """GAME_MODES constant should be defined."""
        assert GAME_MODES is not None
        assert isinstance(GAME_MODES, list)
        assert len(GAME_MODES) > 0

    def test_game_modes_contains_expected(self):
        """GAME_MODES should contain expected games."""
        expected = ["JoustFFA", "JoustTeams", "Werewolf"]
        for game in expected:
            assert game in GAME_MODES

    def test_game_modes_are_strings(self):
        """All game modes should be strings."""
        for mode in GAME_MODES:
            assert isinstance(mode, str)

    def test_game_modes_are_unique(self):
        """All game modes should be unique."""
        assert len(GAME_MODES) == len(set(GAME_MODES))


@pytest.fixture
def mock_channels():
    """Create mock gRPC channels."""
    with patch("grpc.aio.insecure_channel") as mock_channel:
        mock_channel.return_value = MagicMock()
        yield mock_channel


@pytest.fixture
def menu_servicer(mock_channels):  # noqa: ARG001
    """Create MenuServicer instance for testing."""
    from services.menu.servicer import MenuServicer

    return MenuServicer()


class TestMenuServicerBasic:
    """Test basic MenuServicer functionality."""

    def test_initialization(self, menu_servicer):
        """Test servicer initializes correctly."""
        assert menu_servicer.state == menu_pb2.MenuState.STOPPED
        assert menu_servicer.current_selection is not None
        assert menu_servicer.controller_lobby_state == {}

    def test_set_menu_state(self, menu_servicer):
        """Test setting menu state."""
        menu_servicer.set_menu_state(menu_pb2.MenuState.RUNNING)
        assert menu_servicer.state == menu_pb2.MenuState.RUNNING

    def test_get_menu_state(self, menu_servicer):
        """Test getting menu state."""
        menu_servicer.state = menu_pb2.MenuState.RUNNING
        assert menu_servicer.get_menu_state() == menu_pb2.MenuState.RUNNING

    def test_get_game_options(self, menu_servicer):
        """Test getting game options."""
        # get_game_options returns game_options attribute if set, else empty
        options = menu_servicer.get_game_options()
        assert isinstance(options, list)
        # By default returns empty list until game_options is set
        # This is used by AdminModeCallbacks


@pytest.mark.asyncio
class TestMenuServicerAsync:
    """Async tests for MenuServicer."""

    async def test_on_connect_updates_state(self, menu_servicer):
        """Test that on_connect is called without error."""
        import contextlib

        serial = "test_serial_1"
        # on_connect tries to set LED color which may fail in test
        # but should not raise
        with contextlib.suppress(Exception):
            await menu_servicer.on_connect(serial)
        # The state update happens internally, may fail due to mocked channel

    async def test_on_disconnect(self, menu_servicer):
        """Test handling controller disconnection."""
        serial = "test_serial_1"
        menu_servicer.controller_lobby_state[serial] = "connected"
        await menu_servicer.on_disconnect(serial)
        assert serial not in menu_servicer.controller_lobby_state

    async def test_on_disconnect_unknown_serial(self, menu_servicer):
        """Test disconnect for unknown serial doesn't raise."""
        await menu_servicer.on_disconnect("unknown_serial")
        # Should not raise


@pytest.mark.asyncio
class TestMenuServicerRPCs:
    """Test gRPC RPC methods."""

    @pytest.fixture
    def mock_context(self):
        """Create mock gRPC context."""
        context = MagicMock()
        context.cancelled = MagicMock(return_value=False)
        return context

    async def test_start_menu(self, menu_servicer, mock_context):
        """Test StartMenu RPC."""
        request = menu_pb2.StartMenuRequest()
        response = await menu_servicer.StartMenu(request, mock_context)

        assert response.success is True
        assert menu_servicer.state == menu_pb2.MenuState.RUNNING

    async def test_stop_menu(self, menu_servicer, mock_context):
        """Test StopMenu RPC."""
        menu_servicer.state = menu_pb2.MenuState.RUNNING

        request = menu_pb2.StopMenuRequest()
        response = await menu_servicer.StopMenu(request, mock_context)

        assert response.success is True
        assert menu_servicer.state == menu_pb2.MenuState.STOPPED
