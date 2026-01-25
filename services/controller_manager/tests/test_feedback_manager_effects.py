"""
Unit tests for FeedbackManager effect + base_color interaction.

Tests the critical behavior where base_color is updated DURING an effect,
and verifies that the effect restores to the NEW base_color, not the old one.
"""

import asyncio
import threading
from unittest.mock import patch

import pytest

from proto import controller_manager_pb2
from services.controller_manager.feedback_manager import FeedbackManager


class MockBackend:
    """Mock backend that tracks LED color changes."""

    def __init__(self):
        self.colors: dict[str, tuple[int, int, int]] = {}
        self.effect_active: dict[str, bool] = {}
        self.rumble: dict[str, int] = {}

    async def set_led_color(self, serial: str, r: int, g: int, b: int) -> bool:
        """Track color changes (async, matches real backend interface)."""
        self.colors[serial] = (r, g, b)
        return True

    async def set_rumble(self, serial: str, intensity: int) -> bool:
        """Track rumble/vibration (async, matches real backend interface)."""
        self.rumble[serial] = intensity
        return True

    def set_effect_active(self, serial: str, active: bool):
        """Track effect active state."""
        self.effect_active[serial] = active

    def get_current_color(self, serial: str) -> tuple[int, int, int]:
        """Get current color for verification."""
        return self.colors.get(serial, (0, 0, 0))


@pytest.fixture
def mock_backend():
    """Create mock backend."""
    return MockBackend()


@pytest.fixture
def feedback_manager(mock_backend):
    """Create FeedbackManager with mock backend."""
    state_lock = threading.RLock()
    return FeedbackManager(
        backend=mock_backend,
        tracked_controllers={
            "test_ctrl": {"name": "Test Controller"},
        },
        state_lock=state_lock,
    )


class TestBaseColorDuringEffect:
    """Test base_color updates during active effects."""

    @pytest.mark.asyncio
    async def test_base_color_updated_during_rainbow_is_restored(self, feedback_manager, mock_backend):
        """
        Critical test: When base_color is changed DURING a rainbow effect,
        the effect should restore to the NEW base_color when it completes.

        This simulates the real-world scenario:
        1. Game sets team color as base_color (e.g., Yellow)
        2. Winner rainbow effect starts
        3. Menu sends new base_color (lobby color, e.g., Cyan)
        4. Rainbow effect completes
        5. Controller should show Cyan (new base_color), NOT Yellow (old)
        """
        serial = "test_ctrl"
        team_color = (255, 255, 0)  # Yellow team color
        lobby_color = (0, 60, 76)  # Cyan lobby color (dimmed)

        # 1. Set initial team color as base_color
        feedback_manager.base_colors[serial] = team_color
        await feedback_manager.set_controller_color(serial, team_color)
        assert mock_backend.get_current_color(serial) == team_color

        # 2. Start rainbow effect (short duration for test)
        # This will capture restore_color = team_color at the START
        with patch("services.controller_manager.feedback_manager.get_winner_rainbow_duration_ms", return_value=100):
            # Start the game effect (this schedules a background task)
            await feedback_manager.handle_game_effect(
                serial,
                controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW,
                "test_stream",
            )

            # Get the actual background task that's running the effect
            effect_task = feedback_manager.active_effects.get(serial)
            assert effect_task is not None, "Effect task should be running"

            # Give effect time to start
            await asyncio.sleep(0.02)

            # 3. Menu updates base_color to lobby color DURING effect
            feedback_manager.base_colors[serial] = lobby_color

            # 4. Wait for the actual effect task to complete
            await effect_task

        # 5. Verify controller shows NEW base_color (lobby), not old (team)
        final_color = mock_backend.get_current_color(serial)
        assert final_color == lobby_color, (
            f"Expected lobby color {lobby_color}, got {final_color}. "
            f"Effect should restore to CURRENT base_color, not the one captured at effect start."
        )

    @pytest.mark.asyncio
    async def test_base_color_not_set_initially_still_restores(self, feedback_manager, mock_backend):
        """
        When base_color was NOT set when effect started, but IS set during effect,
        the effect should still restore to the new base_color.
        """
        serial = "test_ctrl"
        lobby_color = (0, 60, 76)

        # 1. NO initial base_color (simulates controller just connected during game)
        assert serial not in feedback_manager.base_colors

        # 2. Start effect
        with patch("services.controller_manager.feedback_manager.get_winner_rainbow_duration_ms", return_value=100):
            await feedback_manager.handle_game_effect(
                serial,
                controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW,
                "test_stream",
            )

            # Get the actual background task
            effect_task = feedback_manager.active_effects.get(serial)
            assert effect_task is not None, "Effect task should be running"

            await asyncio.sleep(0.02)

            # 3. Menu sets base_color during effect
            feedback_manager.base_colors[serial] = lobby_color

            # 4. Wait for the actual effect task to complete
            await effect_task

        # 5. Should restore to the base_color that was set during effect
        final_color = mock_backend.get_current_color(serial)
        assert final_color == lobby_color, (
            f"Expected {lobby_color}, got {final_color}. "
            f"Even when base_color wasn't set initially, setting it during effect should work."
        )

    @pytest.mark.asyncio
    async def test_death_effect_then_lobby_reset(self, feedback_manager, mock_backend):
        """
        Simulate player death -> game end -> lobby color reset.

        1. Player has team color
        2. Player dies (death effect sets base_color to black)
        3. Game ends
        4. Menu resets base_color to lobby color
        5. Controller should show lobby color
        """
        serial = "test_ctrl"
        team_color = (255, 255, 0)
        lobby_color = (0, 60, 76)

        # 1. Set team color
        feedback_manager.base_colors[serial] = team_color
        await feedback_manager.set_controller_color(serial, team_color)

        # 2. Death effect (this sets base_color to black after completion)
        # Use short duration for test
        with patch.object(
            feedback_manager, "play_effect_with_restore", wraps=feedback_manager.play_effect_with_restore
        ):
            await feedback_manager.handle_game_effect(
                serial,
                controller_manager_pb2.GAME_EFFECT_PLAYER_DEATH,
                "test_stream",
            )

            # Get the actual background task
            effect_task = feedback_manager.active_effects.get(serial)
            if effect_task:
                await effect_task

        # After death, base_color should be black
        assert feedback_manager.base_colors[serial] == (0, 0, 0)
        assert mock_backend.get_current_color(serial) == (0, 0, 0)

        # 3 & 4. Menu resets to lobby color (no effect running now)
        feedback_manager.base_colors[serial] = lobby_color
        await feedback_manager.set_controller_color(serial, lobby_color)

        # 5. Should show lobby color
        assert mock_backend.get_current_color(serial) == lobby_color


class TestEffectRestoreLogic:
    """Test the restore_color logic in play_effect_with_restore."""

    @pytest.mark.asyncio
    async def test_restore_uses_current_base_colors(self, feedback_manager, mock_backend):
        """
        The effect restore should always use the CURRENT base_colors value,
        not the value captured when the effect started.
        """
        serial = "test_ctrl"
        old_color = (255, 0, 0)  # Red
        new_color = (0, 255, 0)  # Green

        feedback_manager.base_colors[serial] = old_color

        # Start effect (this schedules a background task and returns immediately)
        await feedback_manager.play_effect_with_restore(
            serial,
            effect_type="flash",
            color=(255, 255, 255),
            duration_ms=50,
            speed=10,
            restore_color=old_color,  # Initial restore_color
        )

        # Get the actual background task
        effect_task = feedback_manager.active_effects.get(serial)
        assert effect_task is not None, "Effect task should be running"

        # Update base_colors during effect
        await asyncio.sleep(0.02)
        feedback_manager.base_colors[serial] = new_color

        # Wait for effect to complete
        await effect_task

        # Should have restored to NEW color (read from base_colors at effect end)
        final_color = mock_backend.get_current_color(serial)
        assert final_color == new_color
