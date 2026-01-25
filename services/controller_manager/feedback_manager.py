"""
Feedback manager for ControllerManager.

Handles LED colors, vibration, and visual effects on controllers.
Provides both internal methods and effect management with auto-restore.

Phase 46: Internal feedback methods.
Phase 57: Backend abstraction for platform independence.
"""

import asyncio
import contextlib
import logging
import os
import threading
from typing import TYPE_CHECKING

from proto import controller_manager_pb2
from services.controller_manager import metrics
from services.controller_manager.effects_base import ControllerEffectsBase

if TYPE_CHECKING:
    from services.controller_manager.backend import ControllerBackend

logger = logging.getLogger(__name__)


def get_winner_rainbow_duration_ms() -> int:
    """Get winner rainbow duration from env var, defaults to 3000ms."""
    try:
        return int(os.environ.get("WINNER_RAINBOW_DURATION_MS", "3000"))
    except ValueError:
        return 3000


class FeedbackManager(ControllerEffectsBase):
    """
    Manages LED colors, vibration, and visual effects on controllers.

    Inherits from ControllerEffectsBase for effect animation methods.
    """

    def __init__(
        self,
        backend: "ControllerBackend",
        tracked_controllers: dict[str, dict],
        state_lock: threading.RLock,
    ):
        """
        Initialize feedback manager.

        Args:
            backend: Controller backend for hardware control
            tracked_controllers: Shared dict of tracked controller info
            state_lock: RLock for thread-safe controller access
        """
        super().__init__()  # Initialize ControllerEffectsBase

        self.backend = backend
        self.tracked_controllers = tracked_controllers
        self.state_lock = state_lock

        # Effect lock for async effect management
        self.effect_lock = asyncio.Lock()

        # Base colors per controller (for auto-restore after effects)
        self.base_colors: dict[str, tuple[int, int, int]] = {}

        # Track which GameEffect type is active per controller (for cancellability check)
        self.active_effect_types: dict[str, int] = {}

        # Effects that can be cancelled by a base_color message
        self.cancellable_effects: set[int] = {
            controller_manager_pb2.GAME_EFFECT_FORCE_START_CHARGE,
        }

        # Vibration duration tasks
        self.vibration_tasks: dict[str, asyncio.Task] = {}

    async def _set_led_color(self, serial: str, color: tuple[int, int, int]) -> None:
        """
        Set LED color on a controller (implements abstract from ControllerEffectsBase).

        Args:
            serial: Controller serial number
            color: RGB tuple (0-255, 0-255, 0-255)
        """
        if serial not in self.tracked_controllers:
            return

        try:
            await self.backend.set_led_color(serial, color[0], color[1], color[2])
            # Update color metrics for Grafana dashboard
            metrics.controller_color_r.labels(serial=serial).set(color[0])
            metrics.controller_color_g.labels(serial=serial).set(color[1])
            metrics.controller_color_b.labels(serial=serial).set(color[2])
            hex_color = (color[0] << 16) | (color[1] << 8) | color[2]
            metrics.controller_color_hex.labels(serial=serial).set(hex_color)
        except Exception as e:
            logger.error(f"Error setting LED color on {serial}: {e}", exc_info=True)

    async def set_controller_color(self, serial: str, color_rgb: tuple[int, int, int]) -> bool:
        """
        Set controller color (internal method).

        Can be called from both SetControllerColor RPC and stream-based ColorCommand.

        Args:
            serial: Controller serial number
            color_rgb: RGB color tuple (r, g, b)

        Returns:
            True if successful, False otherwise
        """
        try:
            if serial not in self.tracked_controllers:
                logger.warning(f"Controller {serial} not found for color change")
                return False

            success = await self.backend.set_led_color(serial, color_rgb[0], color_rgb[1], color_rgb[2])
            if success:
                logger.debug(f"Set color on {serial}: RGB{color_rgb}")
                # Emit color metrics for Grafana dashboard (Phase 75)
                metrics.controller_color_r.labels(serial=serial).set(color_rgb[0])
                metrics.controller_color_g.labels(serial=serial).set(color_rgb[1])
                metrics.controller_color_b.labels(serial=serial).set(color_rgb[2])
                # Combined hex for single-panel color display
                hex_color = (color_rgb[0] << 16) | (color_rgb[1] << 8) | color_rgb[2]
                metrics.controller_color_hex.labels(serial=serial).set(hex_color)
            else:
                logger.warning(f"Failed to set color on {serial}")
            return success

        except Exception as e:
            logger.error(f"Error setting color on {serial}: {e}", exc_info=True)
            return False

    async def set_vibration(self, serial: str, intensity: int, duration_ms: int) -> bool:
        """
        Set controller vibration (internal method).

        Called from stream-based VibrationCommand.

        Args:
            serial: Controller serial number
            intensity: Vibration intensity (0-255)
            duration_ms: Duration in milliseconds

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.state_lock:
                controller_exists = serial in self.tracked_controllers
            if not controller_exists:
                logger.warning(f"Controller {serial} not found for vibration")
                return False

            success = await self.backend.set_rumble(serial, intensity)
            if success:
                logger.debug(f"Set vibration on {serial}: intensity={intensity}")

                # Schedule vibration stop if duration is specified
                if duration_ms > 0 and intensity > 0:
                    asyncio.create_task(self._delayed_stop_vibration(serial, duration_ms))
            else:
                logger.warning(f"Failed to set vibration on {serial}")
            return success

        except Exception as e:
            logger.error(f"Error setting vibration on {serial}: {e}", exc_info=True)
            return False

    async def _delayed_stop_vibration(self, serial: str, duration_ms: int) -> None:
        """Stop vibration on a controller after async delay."""
        try:
            await asyncio.sleep(duration_ms / 1000.0)
            await self.backend.set_rumble(serial, 0)
            logger.debug(f"Vibration stopped on {serial} (duration expired)")
        except Exception as e:
            logger.error(f"Error in delayed vibration stop for {serial}: {e}")

    async def play_effect(
        self,
        serial: str,
        effect: int,
        color_rgb: tuple[int, int, int] = (255, 255, 255),
        duration_ms: int = 1000,
        speed: int = 5,
    ) -> bool:
        """
        Play a visual effect on a controller.

        Args:
            serial: Controller serial number
            effect: Effect enum value
            color_rgb: RGB color tuple for effect
            duration_ms: Effect duration in milliseconds
            speed: Effect speed (1-10)

        Returns:
            True if successful, False otherwise
        """
        try:
            if serial not in self.tracked_controllers:
                logger.warning(f"Controller {serial} not found for effect")
                return False

            # Cancel any existing effect on this controller
            async with self.effect_lock:
                if serial in self.active_effects:
                    self.active_effects[serial].cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self.active_effects[serial]
                    del self.active_effects[serial]

            # Start the appropriate effect
            if effect == controller_manager_pb2.EFFECT_NONE:
                await self._set_led_color(serial, color_rgb)

            elif effect == controller_manager_pb2.EFFECT_FLASH:
                task = asyncio.create_task(self._effect_flash(serial, color_rgb, duration_ms, speed))
                async with self.effect_lock:
                    self.active_effects[serial] = task

            elif effect == controller_manager_pb2.EFFECT_PULSE:
                task = asyncio.create_task(self._effect_pulse(serial, color_rgb, duration_ms, speed))
                async with self.effect_lock:
                    self.active_effects[serial] = task

            elif effect == controller_manager_pb2.EFFECT_RAINBOW:
                task = asyncio.create_task(self._effect_rainbow(serial, duration_ms, speed))
                async with self.effect_lock:
                    self.active_effects[serial] = task

            elif effect == controller_manager_pb2.EFFECT_FADE_OUT:
                task = asyncio.create_task(self._effect_fade_out(serial, color_rgb, duration_ms))
                async with self.effect_lock:
                    self.active_effects[serial] = task

            elif effect == controller_manager_pb2.EFFECT_FADE_IN:
                task = asyncio.create_task(self._effect_fade_in(serial, color_rgb, duration_ms))
                async with self.effect_lock:
                    self.active_effects[serial] = task

            else:
                effect_name = controller_manager_pb2.ControllerEffect.Name(effect)
                logger.warning(f"Unknown effect: {effect_name}")
                return False

            logger.debug(f"Playing effect {effect} on {serial}")
            return True

        except Exception as e:
            logger.error(f"Error playing effect on {serial}: {e}", exc_info=True)
            return False

    async def play_effect_with_restore(
        self,
        serial: str,
        effect_type: str,
        color: tuple[int, int, int],
        duration_ms: int,
        speed: int,
        restore_color: tuple[int, int, int] | None,
    ) -> None:
        """
        Play an effect and restore to base color when done.

        Args:
            serial: Controller serial
            effect_type: "flash", "pulse", "rainbow", "fade_out", "fade_in"
            color: RGB color for effect
            duration_ms: Effect duration
            speed: Effect speed (1-10)
            restore_color: Color to restore to after effect (None = no restore)
        """
        # Cancel any existing effect
        async with self.effect_lock:
            if serial in self.active_effects:
                self.active_effects[serial].cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.active_effects[serial]
                del self.active_effects[serial]

        # Mark effect as active (polling skips LED refresh)
        self.backend.set_effect_active(serial, True)

        # Create wrapper that restores color after effect
        async def effect_with_restore():
            try:
                if effect_type == "flash":
                    await self._effect_flash(serial, color, duration_ms, speed)
                elif effect_type == "pulse":
                    await self._effect_pulse(serial, color, duration_ms, speed)
                elif effect_type == "rainbow":
                    await self._effect_rainbow(serial, duration_ms, speed)
                elif effect_type == "fade_out":
                    await self._effect_fade_out(serial, color, duration_ms)
                elif effect_type == "fade_in":
                    await self._effect_fade_in(serial, color, duration_ms)
            except asyncio.CancelledError:
                raise
            finally:
                # Clear effect active flag and effect type tracking
                self.backend.set_effect_active(serial, False)
                self.active_effect_types.pop(serial, None)
                # Remove from active_effects so new base colors can be applied immediately
                async with self.effect_lock:
                    self.active_effects.pop(serial, None)
                # Use current base_colors (may have changed during effect) if restore requested
                current_restore = self.base_colors.get(serial) if restore_color else None
                if current_restore:
                    await self._set_led_color(serial, current_restore)

        task = asyncio.create_task(effect_with_restore())
        async with self.effect_lock:
            self.active_effects[serial] = task

    async def handle_game_effect(self, serial: str, effect: int, _subscriber_id: str = "") -> bool:
        """
        Handle semantic game effect with auto-restore to base color.

        This method interprets game-level effects (warning, death, winner, etc.)
        and translates them to LED animations with appropriate restore behavior.

        Args:
            serial: Controller serial (empty = all controllers for broadcast)
            effect: GameEffect enum value
            subscriber_id: For logging

        Returns:
            True if successful, False otherwise
        """
        try:
            # Determine target controllers
            if serial:
                serials = [serial] if serial in self.tracked_controllers else []
            else:
                serials = list(self.tracked_controllers.keys())

            if not serials:
                logger.warning("No controllers found for game effect")
                return False

            for target_serial in serials:
                restore_color = self.base_colors.get(target_serial)

                # Track effect type for cancellability check
                self.active_effect_types[target_serial] = effect

                if effect == controller_manager_pb2.GAME_EFFECT_NONE:
                    # No-op - clear tracking
                    self.active_effect_types.pop(target_serial, None)

                elif effect == controller_manager_pb2.GAME_EFFECT_PLAYER_WARNING:
                    # White flash + vibrate, restore to base color
                    await self.play_effect_with_restore(
                        target_serial,
                        effect_type="flash",
                        color=(255, 255, 255),
                        duration_ms=200,
                        speed=5,
                        restore_color=restore_color,
                    )
                    await self.set_vibration(target_serial, 100, 200)

                elif effect == controller_manager_pb2.GAME_EFFECT_PLAYER_DEATH:
                    # Red + vibrate, then LED off to signal player is out
                    await self.set_vibration(target_serial, 255, 250)
                    await self.play_effect_with_restore(
                        target_serial,
                        effect_type="flash",
                        color=(255, 0, 0),
                        duration_ms=1500,
                        speed=1,
                        restore_color=(0, 0, 0),
                    )
                    self.base_colors[target_serial] = (0, 0, 0)

                elif effect == controller_manager_pb2.GAME_EFFECT_PLAYER_RESPAWN:
                    # White during spawn protection
                    self.active_effect_types.pop(target_serial, None)
                    await self.set_controller_color(target_serial, (255, 255, 255))
                    self.base_colors[target_serial] = (255, 255, 255)

                elif effect == controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW:
                    # Rainbow at slow speed, restore to base color
                    # Duration configurable via WINNER_RAINBOW_DURATION_MS (default 3000ms)
                    await self.play_effect_with_restore(
                        target_serial,
                        effect_type="rainbow",
                        color=(255, 255, 255),
                        duration_ms=get_winner_rainbow_duration_ms(),
                        speed=1,
                        restore_color=restore_color,
                    )

                elif effect == controller_manager_pb2.GAME_EFFECT_COUNTDOWN:
                    # Full countdown sequence: Red(750ms) → Yellow(750ms) → Green(750ms)
                    # Controller manager handles all timing internally
                    task = asyncio.create_task(self._countdown_sequence(target_serial, restore_color))
                    async with self.effect_lock:
                        self.active_effects[target_serial] = task

                elif effect == controller_manager_pb2.GAME_EFFECT_ADMIN_ENTER:
                    # White flash 3x, then persistent white
                    await self.play_effect(
                        target_serial,
                        controller_manager_pb2.EFFECT_FLASH,
                        (255, 255, 255),
                        600,
                        5,
                    )
                    await asyncio.sleep(0.7)
                    self.active_effect_types.pop(target_serial, None)
                    await self.set_controller_color(target_serial, (255, 255, 255))
                    self.base_colors[target_serial] = (255, 255, 255)

                elif effect == controller_manager_pb2.GAME_EFFECT_ADMIN_EXIT:
                    # Restore to base color (instant)
                    self.active_effect_types.pop(target_serial, None)
                    if restore_color:
                        await self.set_controller_color(target_serial, restore_color)

                elif effect == controller_manager_pb2.GAME_EFFECT_LOW_BATTERY:
                    # Red flash 2x warning
                    for _ in range(2):
                        await self.set_controller_color(target_serial, (255, 0, 0))
                        await asyncio.sleep(0.15)
                        await self.set_controller_color(target_serial, (50, 0, 0))
                        await asyncio.sleep(0.15)
                    self.active_effect_types.pop(target_serial, None)
                    if restore_color:
                        await self.set_controller_color(target_serial, restore_color)

                elif effect == controller_manager_pb2.GAME_EFFECT_FORCE_START_CHARGE:
                    # Fade from white to dim over 2s
                    await self.play_effect_with_restore(
                        target_serial,
                        effect_type="fade_out",
                        color=(255, 255, 255),
                        duration_ms=2000,
                        speed=5,
                        restore_color=None,
                    )

                elif effect == controller_manager_pb2.GAME_EFFECT_SHOW_BATTERY:
                    # Show battery level on this controller for 1 second, then restore
                    battery = self.tracked_controllers.get(target_serial, {}).get("battery", 0)
                    color = self._get_battery_color(battery)
                    await self.play_effect_with_restore(
                        target_serial,
                        effect_type="flash",
                        color=color,
                        duration_ms=1000,
                        speed=1,  # Steady (no flashing)
                        restore_color=restore_color,
                    )
                    logger.debug(f"Battery display: {target_serial} level={battery}% color={color}")

                else:
                    effect_name = controller_manager_pb2.GameEffect.Name(effect)
                    logger.warning(f"Unknown game effect: {effect_name}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error handling game effect: {e}", exc_info=True)
            return False

    async def cancel_effect(self, serial: str) -> None:
        """Cancel any active effect on a controller."""
        async with self.effect_lock:
            if serial in self.active_effects:
                self.active_effects[serial].cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.active_effects[serial]
                del self.active_effects[serial]
                self.active_effect_types.pop(serial, None)
                self.backend.set_effect_active(serial, False)

    async def cancel_if_cancellable(self, serial: str) -> bool:
        """
        Cancel effect only if it's marked as cancellable.

        Args:
            serial: Controller serial

        Returns:
            True if effect was cancelled, False otherwise
        """
        async with self.effect_lock:
            if serial in self.active_effects:
                effect_type = self.active_effect_types.get(serial)
                if effect_type in self.cancellable_effects:
                    self.active_effects[serial].cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self.active_effects[serial]
                    del self.active_effects[serial]
                    self.active_effect_types.pop(serial, None)
                    self.backend.set_effect_active(serial, False)
                    logger.debug(f"Cancelled cancellable effect for {serial}")
                    return True
        return False

    def clear_controller(self, serial: str) -> None:
        """Clear feedback state for a disconnected controller."""
        # Note: Keep base_colors[serial] so we can restore on reconnect
        self.active_effect_types.pop(serial, None)

    def _get_battery_color(self, battery_percent: int) -> tuple[int, int, int]:
        """
        Get LED color for battery level.

        Color scheme matches original JoustMania:
        - 100%: Green
        - 80%: Turquoise
        - 60%: Blue
        - 40%: Yellow
        - <40%: Red

        Args:
            battery_percent: Battery level as percentage (0-100)

        Returns:
            RGB tuple for battery indicator color
        """
        if battery_percent >= 100:
            return (0, 255, 0)  # Green - full
        if battery_percent >= 80:
            return (6, 194, 172)  # Turquoise - 80%
        if battery_percent >= 60:
            return (0, 0, 255)  # Blue - 60%
        if battery_percent >= 40:
            return (255, 255, 20)  # Yellow - 40%
        return (255, 0, 0)  # Red - low battery

    async def _countdown_sequence(self, serial: str, restore_color: tuple[int, int, int] | None) -> None:
        """
        Run the full countdown sequence on a single controller.

        Red (750ms) → Yellow (750ms) → Green (750ms) → restore to base color

        Args:
            serial: Controller serial
            restore_color: Color to restore to after sequence (base color)
        """
        try:
            # Mark effect as active (polling skips LED refresh)
            self.backend.set_effect_active(serial, True)

            # Red - "3"
            await self.set_controller_color(serial, (255, 0, 0))
            await asyncio.sleep(0.75)

            # Yellow - "2"
            await self.set_controller_color(serial, (255, 255, 0))
            await asyncio.sleep(0.75)

            # Green - "1" / GO!
            await self.set_controller_color(serial, (0, 255, 0))
            await asyncio.sleep(0.75)

        except asyncio.CancelledError:
            raise
        finally:
            # Clear effect active flag and tracking
            self.backend.set_effect_active(serial, False)
            self.active_effect_types.pop(serial, None)
            # Remove from active_effects so new base colors can be applied immediately
            async with self.effect_lock:
                self.active_effects.pop(serial, None)
            # Restore to base color
            current_restore = self.base_colors.get(serial) if restore_color else None
            if current_restore:
                await self._set_led_color(serial, current_restore)
