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
from typing import TYPE_CHECKING

from opentelemetry.context import Context

from lib.colors import Colors
from lib.telemetry import extract_trace_context, get_tracer
from proto import controller_manager_pb2
from services.controller_manager import metrics
from services.controller_manager.effects_base import ControllerEffectsBase

if TYPE_CHECKING:
    from services.controller_manager.backend import ControllerBackend

logger = logging.getLogger(__name__)

# Lazy telemetry initialization - defers OTLP setup until first span
tracer = get_tracer(__name__)


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
    ):
        """
        Initialize feedback manager.

        Args:
            backend: Controller backend for hardware control
            tracked_controllers: Shared dict of tracked controller info
        """
        super().__init__()  # Initialize ControllerEffectsBase

        self.backend = backend
        self.tracked_controllers = tracked_controllers

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
            if serial not in self.tracked_controllers:
                logger.warning(f"Controller {serial} not found for vibration")
                return False

            success = await self.backend.set_rumble(serial, intensity)
            if success:
                logger.debug(f"Set vibration on {serial}: intensity={intensity}")

                # Schedule vibration stop if duration is specified
                if duration_ms > 0 and intensity > 0:
                    # Cancel any existing vibration task for this controller
                    if serial in self.vibration_tasks:
                        self.vibration_tasks[serial].cancel()
                    # Store task reference to prevent garbage collection
                    self.vibration_tasks[serial] = asyncio.create_task(
                        self._delayed_stop_vibration(serial, duration_ms)
                    )
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
        existing_task = None
        async with self.effect_lock:
            if serial in self.active_effects:
                existing_task = self.active_effects[serial]
                existing_task.cancel()
                del self.active_effects[serial]
        # Await cancelled task outside lock to avoid deadlock with task's finally block
        if existing_task:
            with contextlib.suppress(asyncio.CancelledError):
                await existing_task

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
                # Remove from active_effects so new base colors can be applied immediately
                async with self.effect_lock:
                    self.active_effect_types.pop(serial, None)
                    self.active_effects.pop(serial, None)
                # Use current base_colors (may have changed during effect) if restore requested
                current_restore = self.base_colors.get(serial) if restore_color else None
                if current_restore:
                    await self._set_led_color(serial, current_restore)

        task = asyncio.create_task(effect_with_restore())
        async with self.effect_lock:
            self.active_effects[serial] = task

    # =========================================================================
    # Individual effect handlers
    # =========================================================================

    async def _effect_none(self, serial: str, **_kwargs) -> None:
        """No-op - clear tracking."""
        # Note: async kept for interface consistency with other effect handlers
        async with self.effect_lock:
            self.active_effect_types.pop(serial, None)

    async def _effect_player_warning(
        self, serial: str, restore_color: tuple | None, trace_context: Context | None = None, **_kwargs
    ) -> None:
        """White flash + vibrate, restore to base color.

        Always pass truthy value to ensure restoration to base_colors at effect end.
        """
        with tracer.start_as_current_span("effect_player_warning", context=trace_context) as span:
            span.set_attribute("controller.serial", serial)

            span.add_event("flash_start", {"color": "white", "duration_ms": 200})
            await self.play_effect_with_restore(serial, "flash", Colors.White.value, 200, 5, restore_color or True)

            span.add_event("vibration", {"intensity": 100, "duration_ms": 200})
            await self.set_vibration(serial, 100, 200)

    async def _effect_player_death(self, serial: str, trace_context: Context | None = None, **_kwargs) -> None:
        """Red + vibrate, then fade to off to signal player is out.

        Improved transition: short sharp rumble + solid red briefly + fade to black.
        This feels more immediate and satisfying than slow blinking.
        """
        with tracer.start_as_current_span("effect_player_death", context=trace_context) as span:
            span.set_attribute("controller.serial", serial)

            # Cancel any active effect (e.g., warning flash) immediately for clean transition
            span.add_event("cancel_existing_effect")
            await self.cancel_effect(serial)

            # Short, sharp rumble (150ms feels snappier than 250ms)
            span.add_event("vibration", {"intensity": 255, "duration_ms": 150})
            await self.set_vibration(serial, 255, 150)

            # Solid red briefly (300ms) then fade to black (700ms) - total 1000ms
            # This replaces the awkward slow blink (1Hz over 1500ms)
            span.add_event("led_red")
            await self._set_led_color(serial, Colors.Red.value)
            await asyncio.sleep(0.3)

            span.add_event("fade_to_black", {"duration_ms": 700})
            await self.play_effect_with_restore(serial, "fade_out", Colors.Red.value, 700, 1, Colors.Black.value)
            self.base_colors[serial] = Colors.Black.value

    async def _effect_player_respawn(self, serial: str, **_kwargs) -> None:
        """White during spawn protection."""
        async with self.effect_lock:
            self.active_effect_types.pop(serial, None)
        await self.set_controller_color(serial, Colors.White.value)
        self.base_colors[serial] = Colors.White.value

    async def _effect_winner_rainbow(
        self, serial: str, restore_color: tuple | None, trace_context: Context | None = None, **_kwargs
    ) -> None:
        """Rainbow effect, restore to base color.

        Always pass truthy value to ensure restoration to base_colors at effect end.
        (base_colors may be updated DURING the effect, e.g., menu sends lobby color)
        """
        duration_ms = get_winner_rainbow_duration_ms()
        with tracer.start_as_current_span("effect_winner_rainbow", context=trace_context) as span:
            span.set_attribute("controller.serial", serial)
            span.set_attribute("effect.duration_ms", duration_ms)

            span.add_event("rainbow_start", {"duration_ms": duration_ms})
            await self.play_effect_with_restore(
                serial, "rainbow", Colors.White.value, duration_ms, 1, restore_color or True
            )
            span.add_event("rainbow_end")

    async def _effect_countdown(
        self,
        serial: str,
        restore_color: tuple | None,
        trace_context: Context | None = None,
        duration_ms: int = 0,
        **_kwargs,
    ) -> None:
        """Full countdown sequence: Red → Yellow → Green."""
        # Use provided duration or default to 750ms per phase
        phase_duration_ms = duration_ms if duration_ms > 0 else 750
        task = asyncio.create_task(self._countdown_sequence(serial, restore_color, trace_context, phase_duration_ms))
        async with self.effect_lock:
            self.active_effects[serial] = task

    async def _effect_admin_enter(self, serial: str, **_kwargs) -> None:
        """White flash, then persistent white."""
        self.base_colors[serial] = Colors.White.value
        await self.play_effect_with_restore(serial, "flash", Colors.White.value, 600, 5, Colors.White.value)

    async def _effect_admin_exit(self, serial: str, restore_color: tuple | None, **_kwargs) -> None:
        """Restore to base color (instant)."""
        async with self.effect_lock:
            self.active_effect_types.pop(serial, None)
        if restore_color:
            await self.set_controller_color(serial, restore_color)

    async def _effect_low_battery(self, serial: str, restore_color: tuple | None, **_kwargs) -> None:
        """Red flash 2x warning."""
        for _ in range(2):
            await self.set_controller_color(serial, Colors.Red.value)
            await asyncio.sleep(0.15)
            await self.set_controller_color(serial, Colors.Red20.value)
            await asyncio.sleep(0.15)
        async with self.effect_lock:
            self.active_effect_types.pop(serial, None)
        if restore_color:
            await self.set_controller_color(serial, restore_color)

    async def _effect_force_start_charge(self, serial: str, **_kwargs) -> None:
        """Fade from white to dim over 2s."""
        await self.play_effect_with_restore(serial, "fade_out", Colors.White.value, 2000, 5, None)

    async def _effect_show_battery(self, serial: str, restore_color: tuple | None, **_kwargs) -> None:
        """Show battery level for 1 second, then restore.

        Always pass truthy value to ensure restoration to base_colors at effect end.
        """
        battery = self.tracked_controllers.get(serial, {}).get("battery", 0)
        battery_color = self._get_battery_color(battery)
        await self.play_effect_with_restore(serial, "flash", battery_color, 1000, 1, restore_color or True)
        logger.debug(f"Battery display: {serial} level={battery}% color={battery_color}")

    async def _effect_rumble(self, serial: str, duration_ms: int = 0, speed: int = 0, **_kwargs) -> None:
        """Vibrate only (for secret signaling like traitor/werewolf)."""
        effect_duration = duration_ms if duration_ms > 0 else 2000
        effect_speed = speed if speed > 0 else 5
        intensity = min(255, effect_speed * 50)
        await self.set_vibration(serial, intensity, effect_duration)
        async with self.effect_lock:
            self.active_effect_types.pop(serial, None)

    async def _game_effect_pulse(
        self,
        serial: str,
        restore_color: tuple | None,
        color: tuple | None = None,
        duration_ms: int = 0,
        speed: int = 0,
        **_kwargs,
    ) -> None:
        """Pulse with color, restore to base."""
        effect_color = color if color else Colors.White.value
        effect_duration = duration_ms if duration_ms > 0 else 600
        effect_speed = speed if speed > 0 else 3
        await self.play_effect_with_restore(serial, "pulse", effect_color, effect_duration, effect_speed, restore_color)

    async def _game_effect_flash(
        self,
        serial: str,
        restore_color: tuple | None,
        color: tuple | None = None,
        duration_ms: int = 0,
        speed: int = 0,
        **_kwargs,
    ) -> None:
        """Brief flash with color, restore to base."""
        effect_color = color if color else Colors.White.value
        effect_duration = duration_ms if duration_ms > 0 else 400
        effect_speed = speed if speed > 0 else 5
        await self.play_effect_with_restore(serial, "flash", effect_color, effect_duration, effect_speed, restore_color)

    # =========================================================================
    # Effect dispatch
    # =========================================================================

    # Map GameEffect enum to handler method
    _EFFECT_HANDLERS: dict = {}  # Populated in __init__ or lazily

    def _get_effect_handlers(self) -> dict:
        """Get mapping of GameEffect enum to handler methods."""
        return {
            controller_manager_pb2.GAME_EFFECT_NONE: self._effect_none,
            controller_manager_pb2.GAME_EFFECT_PLAYER_WARNING: self._effect_player_warning,
            controller_manager_pb2.GAME_EFFECT_PLAYER_DEATH: self._effect_player_death,
            controller_manager_pb2.GAME_EFFECT_PLAYER_RESPAWN: self._effect_player_respawn,
            controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW: self._effect_winner_rainbow,
            controller_manager_pb2.GAME_EFFECT_COUNTDOWN: self._effect_countdown,
            controller_manager_pb2.GAME_EFFECT_ADMIN_ENTER: self._effect_admin_enter,
            controller_manager_pb2.GAME_EFFECT_ADMIN_EXIT: self._effect_admin_exit,
            controller_manager_pb2.GAME_EFFECT_LOW_BATTERY: self._effect_low_battery,
            controller_manager_pb2.GAME_EFFECT_FORCE_START_CHARGE: self._effect_force_start_charge,
            controller_manager_pb2.GAME_EFFECT_SHOW_BATTERY: self._effect_show_battery,
            controller_manager_pb2.GAME_EFFECT_RUMBLE: self._effect_rumble,
            controller_manager_pb2.GAME_EFFECT_PULSE: self._game_effect_pulse,
            controller_manager_pb2.GAME_EFFECT_FLASH: self._game_effect_flash,
        }

    async def handle_game_effect(
        self,
        serial: str,
        effect: int,
        _subscriber_id: str = "",
        color: tuple[int, int, int] | None = None,
        duration_ms: int = 0,
        speed: int = 0,
        trace_parent: str = "",
        trace_state: str = "",
    ) -> bool:
        """
        Handle semantic game effect with auto-restore to base color.

        Args:
            serial: Controller serial (empty = all controllers for broadcast)
            effect: GameEffect enum value
            subscriber_id: For logging
            color: Optional override color (r, g, b) for effects that support it
            duration_ms: Optional override duration (0 = use default)
            speed: Optional override speed (0 = use default)
            trace_parent: W3C traceparent for distributed tracing
            trace_state: W3C tracestate for distributed tracing

        Returns:
            True if successful, False otherwise
        """
        try:
            # Extract trace context if provided
            parent_context = None
            if trace_parent:
                parent_context = extract_trace_context(trace_parent, trace_state)

            # Determine target controllers
            if serial:
                serials = [serial] if serial in self.tracked_controllers else []
            else:
                serials = list(self.tracked_controllers.keys())

            if not serials:
                logger.warning("No controllers found for game effect")
                return False

            handlers = self._get_effect_handlers()
            handler = handlers.get(effect)

            if not handler:
                effect_name = controller_manager_pb2.GameEffect.Name(effect)
                logger.warning(f"Unknown game effect: {effect_name}")
                return False

            for target_serial in serials:
                restore_color = self.base_colors.get(target_serial)
                async with self.effect_lock:
                    self.active_effect_types[target_serial] = effect

                await handler(
                    serial=target_serial,
                    restore_color=restore_color,
                    color=color,
                    duration_ms=duration_ms,
                    speed=speed,
                    trace_context=parent_context,
                )

            return True

        except Exception as e:
            logger.error(f"Error handling game effect: {e}", exc_info=True)
            return False

    async def cancel_effect(self, serial: str) -> None:
        """Cancel any active effect on a controller."""
        task = None
        async with self.effect_lock:
            if serial in self.active_effects:
                task = self.active_effects[serial]
                task.cancel()
                del self.active_effects[serial]
                self.active_effect_types.pop(serial, None)
                self.backend.set_effect_active(serial, False)
        # Await cancelled task outside lock to avoid deadlock with task's finally block
        if task:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def cancel_if_cancellable(self, serial: str) -> bool:
        """
        Cancel effect only if it's marked as cancellable.

        Args:
            serial: Controller serial

        Returns:
            True if effect was cancelled, False otherwise
        """
        task = None
        async with self.effect_lock:
            if serial in self.active_effects:
                effect_type = self.active_effect_types.get(serial)
                if effect_type in self.cancellable_effects:
                    task = self.active_effects[serial]
                    task.cancel()
                    del self.active_effects[serial]
                    self.active_effect_types.pop(serial, None)
                    self.backend.set_effect_active(serial, False)
                    logger.debug(f"Cancelled cancellable effect for {serial}")
        # Await cancelled task outside lock to avoid deadlock with task's finally block
        if task:
            with contextlib.suppress(asyncio.CancelledError):
                await task
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
            return Colors.Green.value  # Green - full
        if battery_percent >= 80:
            return Colors.Turquoise.value  # Turquoise - 80%
        if battery_percent >= 60:
            return Colors.Blue.value  # Blue - 60%
        if battery_percent >= 40:
            return Colors.Yellow.value  # Yellow - 40%
        return Colors.Red.value  # Red - low battery

    async def _countdown_sequence(
        self,
        serial: str,
        restore_color: tuple[int, int, int] | None,
        trace_context: Context | None = None,
        phase_duration_ms: int = 750,
    ) -> None:
        """
        Run the full countdown sequence on a single controller.

        Red → Yellow → Green → restore to base color

        Args:
            serial: Controller serial
            restore_color: Color to restore to after sequence (base color)
            trace_context: Optional trace context for distributed tracing
            phase_duration_ms: Duration of each phase in milliseconds (default 750ms)
        """
        phase_duration_sec = phase_duration_ms / 1000.0

        with tracer.start_as_current_span("effect_countdown", context=trace_context) as span:
            span.set_attribute("controller.serial", serial)

            try:
                # Mark effect as active (polling skips LED refresh)
                self.backend.set_effect_active(serial, True)

                # Red - "3"
                span.add_event("countdown_red", {"phase": 3, "duration_ms": phase_duration_ms})
                await self.set_controller_color(serial, Colors.Red.value)
                await asyncio.sleep(phase_duration_sec)

                # Yellow - "2"
                span.add_event("countdown_yellow", {"phase": 2, "duration_ms": phase_duration_ms})
                await self.set_controller_color(serial, Colors.Yellow.value)
                await asyncio.sleep(phase_duration_sec)

                # Green - "1" / GO!
                span.add_event("countdown_green", {"phase": 1, "duration_ms": phase_duration_ms})
                await self.set_controller_color(serial, Colors.Green.value)
                await asyncio.sleep(phase_duration_sec)

                span.add_event("countdown_complete")

            except asyncio.CancelledError:
                span.add_event("countdown_cancelled")
                raise
            finally:
                # Clear effect active flag and tracking
                self.backend.set_effect_active(serial, False)
                # Remove from active_effects so new base colors can be applied immediately
                async with self.effect_lock:
                    self.active_effect_types.pop(serial, None)
                    self.active_effects.pop(serial, None)
                # Restore to base color
                current_restore = self.base_colors.get(serial) if restore_color else None
                if current_restore:
                    await self._set_led_color(serial, current_restore)
