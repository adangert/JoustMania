"""
Unit tests for ControllerEffectsBase.

Tests all effect animation methods in isolation without requiring hardware
or integration test infrastructure.
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, patch

import pytest

from services.controller_manager.effects_base import ControllerEffectsBase


class TestEffectsImplementation(ControllerEffectsBase):
    """Concrete implementation of ControllerEffectsBase for testing."""

    def __init__(self):
        super().__init__()
        self.color_calls = []  # Track all _set_led_color calls: [(serial, color), ...]

    def _set_led_color(self, serial: str, color: tuple[int, int, int]):
        """Record color changes for verification."""
        self.color_calls.append((serial, color))


@pytest.fixture
def effects():
    """Create test effects instance."""
    return TestEffectsImplementation()


class TestEffectFlash:
    """Test FLASH effect (rapid on/off blinking)."""

    @pytest.mark.asyncio
    async def test_flash_toggles_on_off(self, effects):
        """Flash effect should toggle between color and black."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ), patch("services.controller_manager.effects_base.time.time") as mock_time:
            # Simulate 0.5 seconds passing (500ms duration)
            mock_time.side_effect = [0.0, 0.0, 0.1, 0.1, 0.2, 0.2, 0.3, 0.3, 0.4, 0.4, 0.5, 0.6]

            await effects._effect_flash("test_serial", (255, 0, 0), duration_ms=500, speed=5)

            # Should alternate between red and black
            colors = [call[1] for call in effects.color_calls]

            # First few should alternate
            assert colors[0] == (255, 0, 0)  # On
            assert colors[1] == (0, 0, 0)  # Off
            assert colors[2] == (255, 0, 0)  # On
            assert colors[3] == (0, 0, 0)  # Off

            # Final color should be restored
            assert colors[-1] == (255, 0, 0)

    @pytest.mark.asyncio
    async def test_flash_speed_controls_frequency(self, effects):
        """Higher speed should mean faster flashing."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep, patch("services.controller_manager.effects_base.time.time") as mock_time:
            # Allow a few iterations before ending
            mock_time.side_effect = [0.0, 0.0, 0.01, 0.01, 0.02, 0.02, 0.2]

            await effects._effect_flash("test", (255, 0, 0), duration_ms=100, speed=10)

            # Speed=10 → interval=0.1s, so sleep should be called with 0.05s (half interval)
            calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert len(calls) > 0
            assert calls[0] == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_flash_cancellation_restores_color(self, effects):
        """Cancelling flash should restore final color."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            mock_sleep.side_effect = asyncio.CancelledError()

            with pytest.raises(asyncio.CancelledError):
                await effects._effect_flash("test", (0, 255, 0), duration_ms=1000, speed=5)

            # Should still restore color in finally block
            assert effects.color_calls[-1][1] == (0, 255, 0)


class TestEffectPulse:
    """Test PULSE effect (smooth breathing)."""

    @pytest.mark.asyncio
    async def test_pulse_uses_sine_wave(self, effects):
        """Pulse should use sine wave for smooth breathing."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ), patch("services.controller_manager.effects_base.time.time") as mock_time:
            # Simulate one full cycle at speed=1 (1 Hz = 1 second cycle)
            # Need enough time points to see variation
            times = [
                0.0,
                0.0,
                0.1,
                0.2,
                0.25,
                0.3,
                0.4,
                0.5,
                0.6,
                0.7,
                0.75,
                0.8,
                0.9,
                1.0,
                1.1,
            ]
            mock_time.side_effect = times

            await effects._effect_pulse("test", (255, 255, 255), duration_ms=1000, speed=1)

            colors = [call[1] for call in effects.color_calls[:-1]]  # Exclude final restore

            # At t=0.25: sin(2π*0.25) = sin(π/2) = 1 → brightness = 1
            # At t=0.5:  sin(2π*0.5)  = sin(π) = 0 → brightness = 0.5
            # At t=0.75: sin(2π*0.75) = sin(3π/2) = -1 → brightness = 0

            # Check that brightness varies (not all same)
            brightnesses = [sum(c) for c in colors]
            unique_brightnesses = set(brightnesses)
            assert len(unique_brightnesses) > 2  # Multiple different brightness levels

            # Min brightness should be near 0, max near 255*3
            assert min(brightnesses) < 100
            assert max(brightnesses) > 650

    @pytest.mark.asyncio
    async def test_pulse_restores_full_brightness(self, effects):
        """Pulse should restore full color at end."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ), patch("services.controller_manager.effects_base.time.time") as mock_time:
            mock_time.side_effect = [0.0, 0.0, 1.0]

            await effects._effect_pulse("test", (128, 64, 32), duration_ms=100, speed=5)

            # Final color should be full brightness
            assert effects.color_calls[-1][1] == (128, 64, 32)

    @pytest.mark.asyncio
    async def test_pulse_speed_controls_cycle_duration(self, effects):
        """Higher speed should mean faster pulse cycles."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep, patch("services.controller_manager.effects_base.time.time") as mock_time:
            # Allow a few iterations - need enough time values
            mock_time.side_effect = [
                0.0,
                0.0,
                0.01,
                0.02,
                0.03,
                0.04,
                0.05,
                0.06,
                0.2,
                0.2,
                0.2,
            ]

            await effects._effect_pulse("test", (255, 0, 0), duration_ms=100, speed=5)

            # Should sleep at 20Hz interval (0.05s)
            calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert len(calls) > 0
            assert calls[0] == pytest.approx(0.05)


class TestEffectRainbow:
    """Test RAINBOW effect (color cycling)."""

    @pytest.mark.asyncio
    async def test_rainbow_cycles_through_hues(self, effects):
        """Rainbow should cycle through HSV color space."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ), patch("services.controller_manager.effects_base.time.time") as mock_time:
            # Simulate one full cycle at speed=1
            times = [0.0, 0.0, 0.25, 0.5, 0.75, 1.0, 1.1]
            mock_time.side_effect = times

            await effects._effect_rainbow("test", duration_ms=1000, speed=1)

            colors = [call[1] for call in effects.color_calls]

            # Should have multiple different colors
            assert len(set(colors)) > 1

            # All colors should be saturated (at least one channel at 255)
            for color in colors:
                assert max(color) == 255  # Full saturation, full value

    @pytest.mark.asyncio
    async def test_rainbow_produces_varying_colors(self, effects):
        """Rainbow should produce multiple different colors over time."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ), patch("services.controller_manager.effects_base.time.time") as mock_time:
            # Simulate progression through time for color changes
            times = [0.0, 0.0, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1]
            mock_time.side_effect = times

            await effects._effect_rainbow("test", duration_ms=1000, speed=1)

            colors = [call[1] for call in effects.color_calls]

            # Should have multiple color calls
            assert len(colors) >= 5

            # Colors should vary (not all the same)
            unique_colors = set(colors)
            assert len(unique_colors) >= 3  # At least 3 different colors

            # All colors should be fully saturated (max channel = 255)
            for color in colors:
                assert max(color) == 255


class TestEffectFadeOut:
    """Test FADE_OUT effect (fade to black)."""

    @pytest.mark.asyncio
    async def test_fade_out_decreases_brightness(self, effects):
        """Fade out should progressively decrease brightness."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ):
            await effects._effect_fade_out("test", (255, 255, 255), duration_ms=200)

            colors = [call[1] for call in effects.color_calls[:-1]]  # Exclude final black
            brightnesses = [sum(c) for c in colors]

            # Brightness should decrease monotonically
            for i in range(len(brightnesses) - 1):
                assert brightnesses[i] >= brightnesses[i + 1]

    @pytest.mark.asyncio
    async def test_fade_out_ends_at_black(self, effects):
        """Fade out should end at black (0, 0, 0)."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ):
            await effects._effect_fade_out("test", (100, 200, 150), duration_ms=100)

            # Final color should be black
            assert effects.color_calls[-1][1] == (0, 0, 0)

    @pytest.mark.asyncio
    async def test_fade_out_preserves_color_ratio(self, effects):
        """Fade out should maintain RGB ratios during fade."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ):
            await effects._effect_fade_out("test", (255, 128, 64), duration_ms=200)

            colors = [call[1] for call in effects.color_calls[:-1]]  # Exclude final black

            # Check that ratios are preserved (R:G:B = 255:128:64 = 4:2:1)
            for r, g, b in colors:
                if r > 0:  # Avoid division by zero
                    assert g / r == pytest.approx(128 / 255, abs=0.01)
                    assert b / r == pytest.approx(64 / 255, abs=0.01)


class TestEffectFadeIn:
    """Test FADE_IN effect (fade from black)."""

    @pytest.mark.asyncio
    async def test_fade_in_increases_brightness(self, effects):
        """Fade in should progressively increase brightness."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ):
            await effects._effect_fade_in("test", (255, 255, 255), duration_ms=200)

            colors = [call[1] for call in effects.color_calls[:-1]]  # Exclude final restore
            brightnesses = [sum(c) for c in colors]

            # Brightness should increase monotonically
            for i in range(len(brightnesses) - 1):
                assert brightnesses[i] <= brightnesses[i + 1]

    @pytest.mark.asyncio
    async def test_fade_in_ends_at_target_color(self, effects):
        """Fade in should end at target color."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ):
            await effects._effect_fade_in("test", (200, 100, 50), duration_ms=100)

            # Final color should be target color
            assert effects.color_calls[-1][1] == (200, 100, 50)

    @pytest.mark.asyncio
    async def test_fade_in_starts_from_black(self, effects):
        """Fade in should start from black or near-black."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ):
            await effects._effect_fade_in("test", (255, 128, 64), duration_ms=200)

            # First color should be very dim
            first_brightness = sum(effects.color_calls[0][1])
            assert first_brightness < 50  # Near black


class TestEffectManagement:
    """Test effect task management."""

    @pytest.mark.asyncio
    async def test_active_effects_tracking(self, effects):
        """Active effects should be tracked in dict."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ), patch("services.controller_manager.effects_base.time.time") as mock_time:
            mock_time.side_effect = [0.0, 0.0, 1.0]

            # Create task
            task = asyncio.create_task(
                effects._effect_flash("test_serial", (255, 0, 0), duration_ms=100, speed=5)
            )
            effects.active_effects["test_serial"] = task

            await task

            # Task should have completed
            assert task.done()

    @pytest.mark.asyncio
    async def test_cancel_controller_effect(self, effects):
        """cancel_controller_effect should stop active effect."""
        # Start long-running effect (10 seconds)
        task = asyncio.create_task(
            effects._effect_pulse("test", (255, 0, 0), duration_ms=10000, speed=1)
        )
        effects.active_effects["test"] = task

        # Give it a moment to start
        await asyncio.sleep(0.01)

        # Cancel it
        effects.cancel_controller_effect("test")

        # Wait for cancellation to complete
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Task should be cancelled
        assert task.cancelled()
        assert "test" not in effects.active_effects

    def test_cancel_nonexistent_effect(self, effects):
        """Cancelling non-existent effect should not error."""
        # Should not raise
        effects.cancel_controller_effect("nonexistent_serial")


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_zero_duration_flash(self, effects):
        """Flash with 0ms duration should complete immediately."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ), patch("services.controller_manager.effects_base.time.time") as mock_time:
            mock_time.side_effect = [0.0, 1.0]  # Time already passed

            await effects._effect_flash("test", (255, 0, 0), duration_ms=0, speed=5)

            # Should restore color immediately
            assert len(effects.color_calls) >= 1

    @pytest.mark.asyncio
    async def test_very_fast_speed(self, effects):
        """Very high speed values should work."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep, patch("services.controller_manager.effects_base.time.time") as mock_time:
            mock_time.side_effect = [0.0, 0.0, 1.0]

            await effects._effect_flash("test", (255, 0, 0), duration_ms=100, speed=100)

            # Should handle very small intervals
            calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert calls[0] == pytest.approx(0.005)  # 1/100 / 2

    @pytest.mark.asyncio
    async def test_zero_speed_uses_minimum(self, effects):
        """Speed=0 should be treated as speed=1 (max() protection)."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep, patch("services.controller_manager.effects_base.time.time") as mock_time:
            mock_time.side_effect = [0.0, 0.0, 1.0]

            await effects._effect_flash("test", (255, 0, 0), duration_ms=100, speed=0)

            # Should use speed=1 (max(1, 0))
            calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert calls[0] == pytest.approx(0.5)  # 1/1 / 2

    @pytest.mark.asyncio
    async def test_effect_with_zero_color_values(self, effects):
        """Effects should handle (0, 0, 0) color input."""
        with patch(
            "services.controller_manager.effects_base.asyncio.sleep", new_callable=AsyncMock
        ), patch("services.controller_manager.effects_base.time.time") as mock_time:
            mock_time.side_effect = [0.0, 0.0, 1.0]

            await effects._effect_pulse("test", (0, 0, 0), duration_ms=100, speed=5)

            # Should complete without error
            colors = [call[1] for call in effects.color_calls]
            assert all(sum(c) == 0 for c in colors)  # All black
