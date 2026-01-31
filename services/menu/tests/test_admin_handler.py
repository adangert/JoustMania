"""Unit tests for AdminModeHandler game settings."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lib.colors import Colors
from services.menu.handlers.admin import AdminModeHandler


@pytest.fixture
def mock_tracer():
    """Create mock tracer."""
    tracer = MagicMock()
    tracer.start_span = MagicMock(return_value=MagicMock())
    tracer.start_as_current_span = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
    return tracer


@pytest.fixture
def mock_callbacks():
    """Create mock callbacks."""
    callbacks = MagicMock()
    callbacks.get_game_options = MagicMock(return_value=["JoustFFA", "JoustTeams"])
    return callbacks


@pytest.fixture
def mock_metrics():
    """Create mock metrics."""
    metrics = MagicMock()
    metrics.button_presses_total = MagicMock()
    metrics.button_presses_total.labels = MagicMock(return_value=MagicMock())
    return metrics


@pytest.fixture
def mock_state_manager():
    """Create mock StateManager with game_settings."""
    manager = MagicMock()
    manager.game_settings = {
        "sensitivity": 2,
        "num_teams": 2,
        "random_assignment": True,
        "nonstop_time_limit": 0,
        "invincibility": 4.0,
        "fight_club_min_rounds": 10,
        "werewolf_reveal_time": 35.0,
        "force_all_start": False,
    }
    manager.led = MagicMock()
    manager.led.send_game_effect = AsyncMock(return_value=True)
    manager.led.send_base_color = AsyncMock(return_value=True)
    manager.current_game_mode = MagicMock()
    manager.current_game_mode.name = "JoustFFA"
    return manager


@pytest.fixture
def handler(mock_tracer, mock_callbacks, mock_metrics, mock_state_manager):
    """Create AdminModeHandler instance with mocks."""
    handler = AdminModeHandler(
        controller_channel=MagicMock(),
        tracer=mock_tracer,
        callbacks=mock_callbacks,
        metrics=mock_metrics,
    )
    handler.set_state_manager(mock_state_manager)
    handler.active = True
    handler.controller_serial = "test_serial"
    return handler


class TestAdminOptionNavigation:
    """Tests for admin option navigation."""

    def test_option_names_defined(self, handler):
        """All expected options should be defined."""
        expected = [
            "sensitivity",
            "num_teams",
            "random_assignment",
            "nonstop_time_limit",
            "invincibility",
            "fight_club_min_rounds",
            "werewolf_reveal_time",
            "force_all_start",
        ]
        assert handler.option_names == expected

    def test_option_colors_match_names(self, handler):
        """Each option should have a corresponding color."""
        assert len(handler.option_colors) == len(handler.option_names)

    def test_option_colors_are_colors_enum(self, handler):
        """Option colors should be Colors enum values."""
        for color in handler.option_colors:
            assert isinstance(color, Colors)

    @pytest.mark.asyncio
    async def test_cycle_option_increments(self, handler):
        """handle_cycle_option should increment current_option."""
        handler.current_option = 0
        await handler.handle_cycle_option("test_serial")
        assert handler.current_option == 1

    @pytest.mark.asyncio
    async def test_cycle_option_wraps(self, handler):
        """handle_cycle_option should wrap around to 0."""
        handler.current_option = len(handler.option_names) - 1
        await handler.handle_cycle_option("test_serial")
        assert handler.current_option == 0


class TestIncreaseValueSensitivity:
    """Tests for sensitivity increase."""

    @pytest.mark.asyncio
    async def test_sensitivity_increases(self, handler, mock_state_manager):
        """Sensitivity should increase by 1."""
        handler.current_option = 0  # sensitivity
        mock_state_manager.game_settings["sensitivity"] = 2

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["sensitivity"] == 3

    @pytest.mark.asyncio
    async def test_sensitivity_wraps_at_4(self, handler, mock_state_manager):
        """Sensitivity should wrap from 4 to 0."""
        handler.current_option = 0
        mock_state_manager.game_settings["sensitivity"] = 4

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["sensitivity"] == 0


class TestIncreaseValueNumTeams:
    """Tests for num_teams increase."""

    @pytest.mark.asyncio
    async def test_num_teams_increases(self, handler, mock_state_manager):
        """num_teams should increase by 1."""
        handler.current_option = 1  # num_teams
        mock_state_manager.game_settings["num_teams"] = 2

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["num_teams"] == 3

    @pytest.mark.asyncio
    async def test_num_teams_wraps_at_6(self, handler, mock_state_manager):
        """num_teams should wrap from 6 to 2."""
        handler.current_option = 1
        mock_state_manager.game_settings["num_teams"] = 6

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["num_teams"] == 2


class TestIncreaseValueBoolean:
    """Tests for boolean settings increase (toggle)."""

    @pytest.mark.asyncio
    async def test_random_assignment_toggles_true_to_false(self, handler, mock_state_manager):
        """random_assignment should toggle from True to False."""
        handler.current_option = 2  # random_assignment
        mock_state_manager.game_settings["random_assignment"] = True

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["random_assignment"] is False

    @pytest.mark.asyncio
    async def test_random_assignment_toggles_false_to_true(self, handler, mock_state_manager):
        """random_assignment should toggle from False to True."""
        handler.current_option = 2
        mock_state_manager.game_settings["random_assignment"] = False

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["random_assignment"] is True

    @pytest.mark.asyncio
    async def test_force_all_start_toggles(self, handler, mock_state_manager):
        """force_all_start should toggle."""
        handler.current_option = 7  # force_all_start
        mock_state_manager.game_settings["force_all_start"] = False

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["force_all_start"] is True


class TestIncreaseValueNonstopTimeLimit:
    """Tests for nonstop_time_limit increase."""

    @pytest.mark.asyncio
    async def test_nonstop_time_limit_cycles(self, handler, mock_state_manager):
        """nonstop_time_limit should cycle through steps."""
        handler.current_option = 3  # nonstop_time_limit
        mock_state_manager.game_settings["nonstop_time_limit"] = 0

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["nonstop_time_limit"] == 60

    @pytest.mark.asyncio
    async def test_nonstop_time_limit_wraps(self, handler, mock_state_manager):
        """nonstop_time_limit should wrap from 300 to 0."""
        handler.current_option = 3
        mock_state_manager.game_settings["nonstop_time_limit"] = 300

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["nonstop_time_limit"] == 0


class TestIncreaseValueInvincibility:
    """Tests for invincibility increase."""

    @pytest.mark.asyncio
    async def test_invincibility_increases(self, handler, mock_state_manager):
        """invincibility should increase by 1.0."""
        handler.current_option = 4  # invincibility
        mock_state_manager.game_settings["invincibility"] = 4.0

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["invincibility"] == 5.0

    @pytest.mark.asyncio
    async def test_invincibility_wraps_at_8(self, handler, mock_state_manager):
        """invincibility should wrap from 8.0 to 2.0."""
        handler.current_option = 4
        mock_state_manager.game_settings["invincibility"] = 8.0

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["invincibility"] == 2.0


class TestIncreaseValueFightClubMinRounds:
    """Tests for fight_club_min_rounds increase."""

    @pytest.mark.asyncio
    async def test_fight_club_min_rounds_cycles(self, handler, mock_state_manager):
        """fight_club_min_rounds should cycle through steps."""
        handler.current_option = 5  # fight_club_min_rounds
        mock_state_manager.game_settings["fight_club_min_rounds"] = 10

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["fight_club_min_rounds"] == 15

    @pytest.mark.asyncio
    async def test_fight_club_min_rounds_wraps(self, handler, mock_state_manager):
        """fight_club_min_rounds should wrap from 20 to 5."""
        handler.current_option = 5
        mock_state_manager.game_settings["fight_club_min_rounds"] = 20

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["fight_club_min_rounds"] == 5


class TestIncreaseValueWerewolfRevealTime:
    """Tests for werewolf_reveal_time increase."""

    @pytest.mark.asyncio
    async def test_werewolf_reveal_time_increases(self, handler, mock_state_manager):
        """werewolf_reveal_time should increase by 5.0."""
        handler.current_option = 6  # werewolf_reveal_time
        mock_state_manager.game_settings["werewolf_reveal_time"] = 35.0

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["werewolf_reveal_time"] == 40.0

    @pytest.mark.asyncio
    async def test_werewolf_reveal_time_wraps_at_60(self, handler, mock_state_manager):
        """werewolf_reveal_time should wrap from 60.0 to 20.0."""
        handler.current_option = 6
        mock_state_manager.game_settings["werewolf_reveal_time"] = 60.0

        await handler.handle_increase_value("test_serial")

        assert mock_state_manager.game_settings["werewolf_reveal_time"] == 20.0


class TestDecreaseValueSensitivity:
    """Tests for sensitivity decrease."""

    @pytest.mark.asyncio
    async def test_sensitivity_decreases(self, handler, mock_state_manager):
        """Sensitivity should decrease by 1."""
        handler.current_option = 0  # sensitivity
        mock_state_manager.game_settings["sensitivity"] = 2

        await handler.handle_decrease_value("test_serial")

        assert mock_state_manager.game_settings["sensitivity"] == 1

    @pytest.mark.asyncio
    async def test_sensitivity_wraps_at_0(self, handler, mock_state_manager):
        """Sensitivity should wrap from 0 to 4."""
        handler.current_option = 0
        mock_state_manager.game_settings["sensitivity"] = 0

        await handler.handle_decrease_value("test_serial")

        assert mock_state_manager.game_settings["sensitivity"] == 4


class TestDecreaseValueNumTeams:
    """Tests for num_teams decrease."""

    @pytest.mark.asyncio
    async def test_num_teams_decreases(self, handler, mock_state_manager):
        """num_teams should decrease by 1."""
        handler.current_option = 1  # num_teams
        mock_state_manager.game_settings["num_teams"] = 4

        await handler.handle_decrease_value("test_serial")

        assert mock_state_manager.game_settings["num_teams"] == 3

    @pytest.mark.asyncio
    async def test_num_teams_wraps_at_2(self, handler, mock_state_manager):
        """num_teams should wrap from 2 to 6."""
        handler.current_option = 1
        mock_state_manager.game_settings["num_teams"] = 2

        await handler.handle_decrease_value("test_serial")

        assert mock_state_manager.game_settings["num_teams"] == 6


class TestDecreaseValueInvincibility:
    """Tests for invincibility decrease."""

    @pytest.mark.asyncio
    async def test_invincibility_decreases(self, handler, mock_state_manager):
        """invincibility should decrease by 1.0."""
        handler.current_option = 4  # invincibility
        mock_state_manager.game_settings["invincibility"] = 4.0

        await handler.handle_decrease_value("test_serial")

        assert mock_state_manager.game_settings["invincibility"] == 3.0

    @pytest.mark.asyncio
    async def test_invincibility_wraps_at_2(self, handler, mock_state_manager):
        """invincibility should wrap from 2.0 to 8.0."""
        handler.current_option = 4
        mock_state_manager.game_settings["invincibility"] = 2.0

        await handler.handle_decrease_value("test_serial")

        assert mock_state_manager.game_settings["invincibility"] == 8.0


class TestShowValueFeedback:
    """Tests for visual feedback."""

    @pytest.mark.asyncio
    async def test_feedback_sends_game_effect(self, handler, mock_state_manager):
        """_show_value_feedback should send GAME_EFFECT_PULSE."""
        from proto import controller_manager_pb2

        await handler._show_value_feedback("test_serial", "sensitivity", 2)

        mock_state_manager.led.send_game_effect.assert_called_once()
        call_args = mock_state_manager.led.send_game_effect.call_args
        assert call_args[0][1] == controller_manager_pb2.GAME_EFFECT_PULSE

    @pytest.mark.asyncio
    async def test_sensitivity_feedback_uses_correct_color(self, handler, mock_state_manager):
        """Sensitivity feedback should use the correct color for each level."""
        expected_colors = [
            Colors.Blue.value,
            Colors.Turquoise.value,
            Colors.Green.value,
            Colors.Orange.value,
            Colors.Red.value,
        ]

        for level, expected_color in enumerate(expected_colors):
            mock_state_manager.led.send_game_effect.reset_mock()
            await handler._show_value_feedback("test_serial", "sensitivity", level)

            call_kwargs = mock_state_manager.led.send_game_effect.call_args[1]
            assert call_kwargs["color"] == expected_color

    @pytest.mark.asyncio
    async def test_boolean_feedback_green_for_true(self, handler, mock_state_manager):
        """Boolean True should show green feedback."""
        await handler._show_value_feedback("test_serial", "force_all_start", True)

        call_kwargs = mock_state_manager.led.send_game_effect.call_args[1]
        assert call_kwargs["color"] == Colors.Green.value

    @pytest.mark.asyncio
    async def test_boolean_feedback_red_for_false(self, handler, mock_state_manager):
        """Boolean False should show red feedback."""
        await handler._show_value_feedback("test_serial", "force_all_start", False)

        call_kwargs = mock_state_manager.led.send_game_effect.call_args[1]
        assert call_kwargs["color"] == Colors.Red.value


class TestStateManagerIntegration:
    """Tests for state_manager.game_settings integration."""

    @pytest.mark.asyncio
    async def test_uses_state_manager_not_settings_service(self, handler, mock_state_manager):
        """Handler should use state_manager.game_settings, not Settings service."""
        handler.current_option = 0  # sensitivity
        mock_state_manager.game_settings["sensitivity"] = 2

        # This should NOT make any RPC calls
        await handler.handle_increase_value("test_serial")

        # Verify setting was updated locally
        assert mock_state_manager.game_settings["sensitivity"] == 3

    @pytest.mark.asyncio
    async def test_no_state_manager_returns_early(self, handler):
        """Handler should return early if state_manager is None."""
        handler._state_manager = None

        # Should not raise
        await handler.handle_increase_value("test_serial")
        await handler.handle_decrease_value("test_serial")


class TestHandleSensitivityLocalStorage:
    """Tests for handle_sensitivity using local storage."""

    @pytest.mark.asyncio
    async def test_handle_sensitivity_uses_game_settings(self, handler, mock_state_manager):
        """handle_sensitivity should use state_manager.game_settings."""
        mock_state_manager.game_settings["sensitivity"] = 2

        await handler.handle_sensitivity("test_serial")

        assert mock_state_manager.game_settings["sensitivity"] == 3

    @pytest.mark.asyncio
    async def test_handle_sensitivity_wraps(self, handler, mock_state_manager):
        """handle_sensitivity should wrap from 4 to 0."""
        mock_state_manager.game_settings["sensitivity"] = 4

        await handler.handle_sensitivity("test_serial")

        assert mock_state_manager.game_settings["sensitivity"] == 0


class TestHandleForceStartLocalStorage:
    """Tests for handle_force_start using local storage."""

    @pytest.mark.asyncio
    async def test_handle_force_start_reads_game_settings(self, handler, mock_state_manager):
        """handle_force_start should read force_all_start from game_settings."""
        mock_state_manager.game_settings["force_all_start"] = True
        mock_state_manager.connected_controllers = {"s1", "s2"}
        mock_state_manager.ready_controllers = {"s1"}
        handler._publish_event = AsyncMock()
        handler.exit = AsyncMock()

        with patch("services.menu.handlers.admin.asyncio.sleep", new_callable=AsyncMock):
            await handler.handle_force_start("test_serial")

        # Should have used all connected controllers since force_all_start=True
        handler._publish_event.assert_called()
        call_args = handler._publish_event.call_args[0]
        assert call_args[0] == "game_requested"
