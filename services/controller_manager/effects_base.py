"""
Base class for controller effects - shared by real and mock controller managers.

This class contains all the animation logic for controller LED effects (FLASH, PULSE,
RAINBOW, FADE_OUT, FADE_IN). The only hardware-specific method is _set_led_color(),
which must be implemented by subclasses.

Phase 40: Refactoring to eliminate code duplication between real and mock servers.
"""

import asyncio
import colorsys
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from lib.clock import Clock, RealClock

logger = logging.getLogger(__name__)


@dataclass
class ActiveEffect:
    """Tracks an active effect task and its type for a single controller."""

    task: asyncio.Task
    effect_type: int  # GameEffect enum value


class ControllerEffectsBase(ABC):
    """Base class providing controller effect animations.

    Subclasses must implement _set_led_color() to control actual hardware or mock state.

    Args:
        clock: Optional Clock instance for time operations. Defaults to RealClock.
               Inject a FakeClock in tests to control time without patching.
    """

    def __init__(self, clock: Clock | None = None):
        """Initialize effect tracking.

        Args:
            clock: Clock instance for time/sleep operations. Defaults to RealClock.
        """
        # Track active effects per controller: {serial: ActiveEffect}
        self.active_effects: dict[str, ActiveEffect] = {}
        self._clock = clock or RealClock()

    @abstractmethod
    async def _set_led_color(self, serial: str, color: tuple[int, int, int]):
        """Set LED color on a controller (async).

        Args:
            serial: Controller serial number
            color: RGB tuple (0-255, 0-255, 0-255)

        Subclasses must implement this to control hardware or mock state.
        """
        pass

    async def _effect_flash(self, serial: str, color: tuple[int, int, int], duration_ms: int, speed: int):
        """FLASH effect: rapid on/off blinking (Phase 31).

        Args:
            serial: Controller serial
            color: RGB color to flash
            duration_ms: Total effect duration in milliseconds
            speed: Flash frequency (1-10 Hz)
        """
        interval = 1.0 / max(1, speed)  # seconds per flash cycle
        end_time = self._clock.time() + (duration_ms / 1000.0)

        try:
            while self._clock.time() < end_time:
                await self._set_led_color(serial, color)
                await self._clock.sleep(interval / 2)
                await self._set_led_color(serial, (0, 0, 0))  # Off
                await self._clock.sleep(interval / 2)
        except asyncio.CancelledError:
            logger.debug(f"FLASH effect cancelled for {serial}")
            raise
        finally:
            # Restore color at end
            await self._set_led_color(serial, color)

    async def _effect_pulse(self, serial: str, color: tuple[int, int, int], duration_ms: int, speed: int):
        """PULSE effect: smooth breathing/fade (Phase 31).

        Uses sine wave for smooth brightness transitions.

        Args:
            serial: Controller serial
            color: RGB color to pulse
            duration_ms: Total effect duration in milliseconds
            speed: Pulse frequency (1-10 Hz)
        """
        interval = 0.05  # 20 Hz update rate for smooth animation
        cycle_duration = 1.0 / max(1, speed)  # seconds per pulse cycle
        start = self._clock.time()
        end_time = start + (duration_ms / 1000.0)

        try:
            while self._clock.time() < end_time:
                elapsed = self._clock.time() - start
                # Sine wave: 0 → 1 → 0 (smooth breathing)
                brightness = (math.sin(2 * math.pi * elapsed / cycle_duration) + 1) / 2

                scaled_color = tuple(int(c * brightness) for c in color)
                await self._set_led_color(serial, scaled_color)
                await self._clock.sleep(interval)
        except asyncio.CancelledError:
            logger.debug(f"PULSE effect cancelled for {serial}")
            raise
        finally:
            # Restore full brightness at end
            await self._set_led_color(serial, color)

    async def _effect_rainbow(self, serial: str, duration_ms: int, speed: int):
        """RAINBOW effect: cycle through color spectrum (Phase 31).

        Uses HSV color space for smooth color transitions.

        Args:
            serial: Controller serial
            duration_ms: Total effect duration in milliseconds
            speed: Rotation speed (1-10 Hz)
        """
        interval = 0.05  # 20 Hz update rate
        cycle_duration = 1.0 / max(1, speed)  # seconds per full rainbow cycle
        start = self._clock.time()
        end_time = start + (duration_ms / 1000.0)

        try:
            while self._clock.time() < end_time:
                elapsed = self._clock.time() - start
                # HSV color space: rotate hue 0 → 1
                hue = (elapsed / cycle_duration) % 1.0

                rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                color = tuple(int(c * 255) for c in rgb)
                await self._set_led_color(serial, color)
                await self._clock.sleep(interval)
        except asyncio.CancelledError:
            logger.debug(f"RAINBOW effect cancelled for {serial}")
            raise

    async def _effect_fade_out(self, serial: str, color: tuple[int, int, int], duration_ms: int):
        """FADE_OUT effect: linear fade to black (Phase 31).

        Args:
            serial: Controller serial
            color: Starting RGB color
            duration_ms: Fade duration in milliseconds
        """
        interval = 0.05  # 20 Hz update rate
        steps = int((duration_ms / 1000.0) / interval)
        steps = max(1, steps)

        try:
            for step in range(steps):
                brightness = 1.0 - (step / steps)
                scaled_color = tuple(int(c * brightness) for c in color)
                await self._set_led_color(serial, scaled_color)
                await self._clock.sleep(interval)
        except asyncio.CancelledError:
            logger.debug(f"FADE_OUT effect cancelled for {serial}")
            raise
        finally:
            # End at black
            await self._set_led_color(serial, (0, 0, 0))

    async def _effect_fade_in(self, serial: str, color: tuple[int, int, int], duration_ms: int):
        """FADE_IN effect: linear fade from black to color (Phase 31).

        Args:
            serial: Controller serial
            color: Target RGB color
            duration_ms: Fade duration in milliseconds
        """
        interval = 0.05  # 20 Hz update rate
        steps = int((duration_ms / 1000.0) / interval)
        steps = max(1, steps)

        try:
            for step in range(steps + 1):
                brightness = step / steps
                scaled_color = tuple(int(c * brightness) for c in color)
                await self._set_led_color(serial, scaled_color)
                await self._clock.sleep(interval)
        except asyncio.CancelledError:
            logger.debug(f"FADE_IN effect cancelled for {serial}")
            raise
        finally:
            # End at full brightness
            await self._set_led_color(serial, color)

    def cancel_controller_effect(self, serial: str):
        """Cancel any active effect on a controller.

        Call this when a controller disconnects or is removed.

        Args:
            serial: Controller serial number
        """
        if serial in self.active_effects:
            self.active_effects[serial].task.cancel()
            del self.active_effects[serial]
            logger.debug(f"Cancelled effect for {serial}")
