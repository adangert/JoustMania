"""
Unit tests for menu lobby feedback (Phase 39).

Tests controller LED feedback in the lobby:
- Game-mode-specific colors
- Dim/bright state transitions
- Admin mode white LED
- First connection green flash
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from proto import menu_pb2


class MockControllerState:
    """Mock ControllerState for testing."""

    def __init__(self, serial, trigger_pressed=False, move_pressed=False):
        self.serial = serial
        self.trigger_pressed = trigger_pressed
        self.move_pressed = move_pressed
        self.cross_pressed = False
        self.circle_pressed = False
        self.square_pressed = False
        self.triangle_pressed = False
        self.ps_pressed = False


@pytest.fixture
def menu_servicer():
    """Create MenuServicer instance for testing."""
    # Patch gRPC channels to avoid actual network connections
    with patch("grpc.aio.insecure_channel"):
        from services.menu.server import MenuServicer

        servicer = MenuServicer()
        servicer.state = menu_pb2.MenuState.RUNNING
        return servicer


class TestGameModeColors:
    """Test game mode color mappings."""

    def test_all_game_modes_have_colors(self, menu_servicer):
        """All game modes should have defined colors."""
        game_modes = ["JoustFFA", "JoustTeams", "Tournament", "Werewolf", "NonstopJoust"]

        for mode in game_modes:
            assert mode in menu_servicer.GAME_MODE_COLORS
            color = menu_servicer.GAME_MODE_COLORS[mode]
            assert len(color) == 3
            assert all(0 <= c <= 255 for c in color)

    def test_ffa_is_orange(self, menu_servicer):
        """FFA should use orange color."""
        color = menu_servicer.GAME_MODE_COLORS["JoustFFA"]
        assert color == (255, 140, 0)

    def test_teams_is_blue(self, menu_servicer):
        """Teams should use blue color."""
        color = menu_servicer.GAME_MODE_COLORS["JoustTeams"]
        assert color == (0, 100, 255)

    def test_all_colors_are_distinct(self, menu_servicer):
        """Each game mode should have a distinct color."""
        colors = list(menu_servicer.GAME_MODE_COLORS.values())
        assert len(colors) == len(set(colors))


class TestLobbyFeedback:
    """Test lobby feedback state transitions."""

    @pytest.mark.asyncio
    async def test_first_connection_green_flash(self, menu_servicer):
        """First connection should trigger green flash."""
        controller = MockControllerState("test_serial_1")
        mock_stub = AsyncMock()

        await menu_servicer._update_lobby_feedback(controller, mock_stub)

        # Should send green flash
        mock_stub.SetControllerColor.assert_called_once()
        call_args = mock_stub.SetControllerColor.call_args
        request = call_args[0][0]

        assert request.serial == "test_serial_1"
        assert request.color.r == 0
        assert request.color.g == 255
        assert request.color.b == 0
        assert request.duration_ms == 300

    @pytest.mark.asyncio
    async def test_connected_state_dim_color(self, menu_servicer):
        """Connected but not ready should show dim color."""
        controller = MockControllerState("test_serial_2")
        mock_stub = AsyncMock()

        # First connection (green flash)
        await menu_servicer._update_lobby_feedback(controller, mock_stub)
        mock_stub.reset_mock()

        # Second update (should show dim color)
        await menu_servicer._update_lobby_feedback(controller, mock_stub)

        # Should set dim orange (50% of 255, 140, 0)
        call_args = mock_stub.SetControllerColor.call_args
        request = call_args[0][0]

        assert request.color.r == 127  # int(255 * 0.5)
        assert request.color.g == 70  # int(140 * 0.5)
        assert request.color.b == 0
        assert request.duration_ms == 0  # Persistent

    @pytest.mark.asyncio
    async def test_trigger_press_marks_ready(self, menu_servicer):
        """Pressing trigger should mark controller as ready with bright color."""
        controller = MockControllerState("test_serial_3", trigger_pressed=False)
        mock_stub = AsyncMock()

        # Initialize button state tracking
        menu_servicer.controller_button_states["test_serial_3"] = {"trigger": False}

        # First connection
        await menu_servicer._update_lobby_feedback(controller, mock_stub)
        mock_stub.reset_mock()

        # Second update - connected state
        await menu_servicer._update_lobby_feedback(controller, mock_stub)
        mock_stub.reset_mock()

        # Trigger press
        controller.trigger_pressed = True
        await menu_servicer._update_lobby_feedback(controller, mock_stub)

        # Should set bright orange (100% of 255, 140, 0)
        call_args = mock_stub.SetControllerColor.call_args
        request = call_args[0][0]

        assert request.color.r == 255
        assert request.color.g == 140
        assert request.color.b == 0
        assert request.duration_ms == 0

        # Should be marked as ready
        assert "test_serial_3" in menu_servicer.ready_controllers

    @pytest.mark.asyncio
    async def test_ready_state_persists_after_releasing_trigger(self, menu_servicer):
        """Ready state should persist after releasing trigger."""
        controller = MockControllerState("test_serial_4", trigger_pressed=False)
        mock_stub = AsyncMock()

        # Initialize button state
        menu_servicer.controller_button_states["test_serial_4"] = {"trigger": False}

        # First connection
        await menu_servicer._update_lobby_feedback(controller, mock_stub)

        # Mark as ready
        menu_servicer.ready_controllers.add("test_serial_4")
        menu_servicer.controller_lobby_state["test_serial_4"] = "ready"
        mock_stub.reset_mock()

        # Release trigger (should stay ready)
        controller.trigger_pressed = False
        menu_servicer.controller_button_states["test_serial_4"]["trigger"] = True  # Was pressed
        await menu_servicer._update_lobby_feedback(controller, mock_stub)

        # Should NOT update color (stays ready)
        assert "test_serial_4" in menu_servicer.ready_controllers

    @pytest.mark.asyncio
    async def test_rate_limiting(self, menu_servicer):
        """Color updates should be rate limited to max 2/sec per controller."""
        controller = MockControllerState("test_serial_5")
        mock_stub = AsyncMock()

        # Initialize
        menu_servicer.controller_button_states["test_serial_5"] = {"trigger": False}
        await menu_servicer._update_lobby_feedback(controller, mock_stub)
        menu_servicer.controller_lobby_state["test_serial_5"] = "connected"
        menu_servicer.last_lobby_feedback_update["test_serial_5"] = 1000.0

        # Try to update immediately
        with patch("time.time", return_value=1000.1):  # Only 0.1s later
            controller.trigger_pressed = True
            await menu_servicer._update_lobby_feedback(controller, mock_stub)

        # Should be rate limited (no new call after first connection)
        assert mock_stub.SetControllerColor.call_count == 1  # Only initial green flash


class TestGameModeSwitch:
    """Test color updates when switching game modes."""

    @pytest.mark.asyncio
    async def test_game_mode_change_updates_colors(self, menu_servicer):
        """Changing game mode should update all controller colors."""
        menu_servicer.current_selection = "JoustFFA"
        controller = MockControllerState("test_serial_6")
        mock_stub = AsyncMock()

        # Initialize button state
        menu_servicer.controller_button_states["test_serial_6"] = {"trigger": False}

        # Connect and get FFA color
        await menu_servicer._update_lobby_feedback(controller, mock_stub)
        menu_servicer.controller_lobby_state["test_serial_6"] = "connected"
        mock_stub.reset_mock()

        # Change to Teams mode
        menu_servicer.current_selection = "JoustTeams"
        menu_servicer.controller_lobby_state.clear()
        menu_servicer.last_lobby_feedback_update.clear()

        # Update feedback
        await menu_servicer._update_lobby_feedback(controller, mock_stub)

        # Should use Teams color (blue)
        call_args = mock_stub.SetControllerColor.call_args
        request = call_args[0][0]

        assert request.color.r == 0  # int(0 * 0.5) = 0
        assert request.color.g == 50  # int(100 * 0.5) = 50
        assert request.color.b == 127  # int(255 * 0.5) = 127


class TestAdminMode:
    """Test admin mode visual feedback."""

    @pytest.mark.asyncio
    async def test_admin_mode_white_flash(self, menu_servicer):
        """Entering admin mode should trigger white flash."""
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await menu_servicer._enter_admin_mode("test_admin")

        assert menu_servicer.admin_mode_active
        assert menu_servicer.admin_mode_controller == "test_admin"
        assert "test_admin" in menu_servicer.controller_lobby_state
        assert menu_servicer.controller_lobby_state["test_admin"] == "admin"

    @pytest.mark.asyncio
    async def test_admin_mode_skips_lobby_feedback(self, menu_servicer):
        """Admin mode controllers should skip normal lobby feedback."""
        menu_servicer.admin_mode_active = True
        menu_servicer.admin_mode_controller = "test_admin"

        controller = MockControllerState("test_admin")
        mock_stub = AsyncMock()

        await menu_servicer._update_lobby_feedback(controller, mock_stub)

        # Should not update color (admin controller skipped)
        mock_stub.SetControllerColor.assert_not_called()

    @pytest.mark.asyncio
    async def test_exit_admin_restores_lobby_color(self, menu_servicer):
        """Exiting admin mode should restore lobby color."""
        menu_servicer.admin_mode_active = True
        menu_servicer.admin_mode_controller = "test_admin"
        menu_servicer.current_selection = "JoustFFA"
        menu_servicer.controller_lobby_state["test_admin"] = "admin"

        await menu_servicer._exit_admin_mode()

        assert not menu_servicer.admin_mode_active
        assert menu_servicer.admin_mode_controller is None
        assert "test_admin" not in menu_servicer.controller_lobby_state

    @pytest.mark.asyncio
    async def test_exit_admin_restores_ready_state(self, menu_servicer):
        """Exiting admin mode should restore ready state if controller was ready."""
        menu_servicer.admin_mode_active = True
        menu_servicer.admin_mode_controller = "test_admin_ready"
        menu_servicer.ready_controllers.add("test_admin_ready")
        menu_servicer.current_selection = "JoustFFA"

        await menu_servicer._exit_admin_mode()

        # Should still be in ready_controllers
        assert "test_admin_ready" in menu_servicer.ready_controllers


class TestReadyControllerTracking:
    """Test ready controller count tracking."""

    @pytest.mark.asyncio
    async def test_ready_count_increments(self, menu_servicer):
        """Ready controller count should increment when controller becomes ready."""
        controller = MockControllerState("test_serial_7", trigger_pressed=False)
        mock_stub = AsyncMock()

        # Initialize
        menu_servicer.controller_button_states["test_serial_7"] = {"trigger": False}
        await menu_servicer._update_lobby_feedback(controller, mock_stub)
        menu_servicer.controller_lobby_state["test_serial_7"] = "connected"

        initial_count = menu_servicer.ready_controller_count

        # Mark as ready
        controller.trigger_pressed = True
        await menu_servicer._update_lobby_feedback(controller, mock_stub)

        assert menu_servicer.ready_controller_count == initial_count + 1

    @pytest.mark.asyncio
    async def test_stop_menu_clears_lobby_state(self, menu_servicer):
        """Stopping menu should clear all lobby state."""
        # Set up some state
        menu_servicer.ready_controllers.add("test1")
        menu_servicer.connected_controllers.add("test1")
        menu_servicer.controller_lobby_state["test1"] = "ready"
        menu_servicer.last_lobby_feedback_update["test1"] = 123.0

        # Stop menu (Phase 58: now async)
        context = MagicMock()
        await menu_servicer.StopMenu(None, context)

        assert len(menu_servicer.ready_controllers) == 0
        assert len(menu_servicer.connected_controllers) == 0
        assert len(menu_servicer.controller_lobby_state) == 0
        assert len(menu_servicer.last_lobby_feedback_update) == 0
        assert menu_servicer.ready_controller_count == 0


class TestControllerDisconnection:
    """Test controller disconnection handling (Phase 58)."""

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self, menu_servicer):
        """Disconnected controllers should have state cleared."""
        serial = "test_disconnect_1"

        # Set up connected controller state
        menu_servicer.connected_controllers.add(serial)
        menu_servicer.ready_controllers.add(serial)
        menu_servicer.controller_button_states[serial] = {"trigger": True}
        menu_servicer.last_button_press_time[serial] = {"trigger": 123.0}
        menu_servicer.controller_lobby_state[serial] = "ready"
        menu_servicer.last_lobby_feedback_update[serial] = 123.0
        menu_servicer.ready_controller_count = 1

        # Simulate disconnection
        await menu_servicer._handle_controller_disconnect(serial)

        # Verify all state cleared
        assert serial not in menu_servicer.connected_controllers
        assert serial not in menu_servicer.ready_controllers
        assert serial not in menu_servicer.controller_button_states
        assert serial not in menu_servicer.last_button_press_time
        assert serial not in menu_servicer.controller_lobby_state
        assert serial not in menu_servicer.last_lobby_feedback_update
        assert menu_servicer.ready_controller_count == 0

    @pytest.mark.asyncio
    async def test_admin_mode_exits_on_disconnect(self, menu_servicer):
        """Admin mode should exit when admin controller disconnects."""
        serial = "test_admin_disconnect"

        # Enter admin mode
        menu_servicer.admin_mode_active = True
        menu_servicer.admin_mode_controller = serial
        menu_servicer.admin_mode_entry_time = 123.0
        menu_servicer.connected_controllers.add(serial)

        # Simulate disconnection
        await menu_servicer._handle_controller_disconnect(serial)

        # Verify admin mode exited
        assert not menu_servicer.admin_mode_active
        assert menu_servicer.admin_mode_controller is None
        assert menu_servicer.admin_mode_entry_time == 0


class TestProcessInput:
    """Test ProcessInput RPC (Phase 59)."""

    @pytest.mark.asyncio
    async def test_button_press_trigger_starts_game(self, menu_servicer):
        """Trigger button press should start game."""
        menu_servicer.state = menu_pb2.MenuState.RUNNING
        menu_servicer.current_selection = "JoustFFA"

        request = menu_pb2.ProcessInputRequest(input_type="button_press", data={"button": "trigger"})
        context = MagicMock()

        response = await menu_servicer.ProcessInput(request, context)

        assert response.success
        assert menu_servicer.state == menu_pb2.MenuState.GAME_STARTING

    @pytest.mark.asyncio
    async def test_button_press_select_cycles_game(self, menu_servicer):
        """Select button press should cycle game mode."""
        menu_servicer.state = menu_pb2.MenuState.RUNNING
        menu_servicer.current_selection = "JoustFFA"

        request = menu_pb2.ProcessInputRequest(input_type="button_press", data={"button": "select"})
        context = MagicMock()

        response = await menu_servicer.ProcessInput(request, context)

        assert response.success
        assert menu_servicer.current_selection == "JoustTeams"

    @pytest.mark.asyncio
    async def test_web_command_start_game(self, menu_servicer):
        """Web command should start game."""
        menu_servicer.state = menu_pb2.MenuState.RUNNING

        request = menu_pb2.ProcessInputRequest(input_type="web_command", data={"command": "start_game"})
        context = MagicMock()

        response = await menu_servicer.ProcessInput(request, context)

        assert response.success
        assert menu_servicer.state == menu_pb2.MenuState.GAME_STARTING

    @pytest.mark.asyncio
    async def test_web_command_select_game(self, menu_servicer):
        """Web command should select specific game mode."""
        menu_servicer.state = menu_pb2.MenuState.RUNNING
        menu_servicer.current_selection = "JoustFFA"

        request = menu_pb2.ProcessInputRequest(
            input_type="web_command", data={"command": "select_game", "game_name": "Tournament"}
        )
        context = MagicMock()

        response = await menu_servicer.ProcessInput(request, context)

        assert response.success
        assert menu_servicer.current_selection == "Tournament"

    @pytest.mark.asyncio
    async def test_web_command_select_invalid_game(self, menu_servicer):
        """Web command with invalid game should not change selection."""
        menu_servicer.state = menu_pb2.MenuState.RUNNING
        menu_servicer.current_selection = "JoustFFA"

        request = menu_pb2.ProcessInputRequest(
            input_type="web_command", data={"command": "select_game", "game_name": "InvalidGame"}
        )
        context = MagicMock()

        response = await menu_servicer.ProcessInput(request, context)

        assert response.success  # Still succeeds, just logs warning
        assert menu_servicer.current_selection == "JoustFFA"  # Unchanged

    @pytest.mark.asyncio
    async def test_reset_menu_cancels_game_start(self, menu_servicer):
        """Reset menu should cancel GAME_STARTING state."""
        menu_servicer.state = menu_pb2.MenuState.GAME_STARTING

        request = menu_pb2.ProcessInputRequest(input_type="reset_menu", data={})
        context = MagicMock()

        response = await menu_servicer.ProcessInput(request, context)

        assert response.success
        assert menu_servicer.state == menu_pb2.MenuState.RUNNING


class TestGameModesConstant:
    """Test GAME_MODES constant (Phase 59)."""

    def test_game_modes_constant_exists(self, menu_servicer):
        """GAME_MODES constant should exist."""
        assert hasattr(menu_servicer, "GAME_MODES")
        assert len(menu_servicer.GAME_MODES) == 5

    def test_all_game_modes_have_colors(self, menu_servicer):
        """All game modes in constant should have colors defined."""
        for mode in menu_servicer.GAME_MODES:
            assert mode in menu_servicer.GAME_MODE_COLORS

    def test_game_modes_order(self, menu_servicer):
        """Game modes should be in expected order."""
        expected = ["JoustFFA", "JoustTeams", "Tournament", "Werewolf", "NonstopJoust"]
        assert expected == menu_servicer.GAME_MODES


class TestAdminModeTimeout:
    """Test admin mode timeout (Phase 58)."""

    @pytest.mark.asyncio
    async def test_admin_mode_times_out(self, menu_servicer):
        """Admin mode should exit after 60 seconds."""
        menu_servicer.admin_mode_active = True
        menu_servicer.admin_mode_controller = "test_serial"
        menu_servicer.admin_mode_entry_time = 0  # Set to epoch (will be > 60s ago)

        # Create mock controller state
        controller = MockControllerState("test_serial")

        menu_servicer.controller_button_states["test_serial"] = {
            "trigger": False,
            "move": False,
            "cross": False,
            "circle": False,
            "square": False,
            "triangle": False,
            "ps": False,
        }
        menu_servicer.last_button_press_time["test_serial"] = {}

        await menu_servicer._process_button_state(controller)

        assert not menu_servicer.admin_mode_active
        assert menu_servicer.admin_mode_controller is None
