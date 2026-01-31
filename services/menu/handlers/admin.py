"""
Admin mode handler for Menu service.

Manages the admin mode state, commands, and visual feedback when a controller
holds all 4 face buttons (Cross + Circle + Square + Triangle) simultaneously.

Button mappings in admin mode:
- Cross: Cycle game mode (flash color + voice)
- Circle: Cycle sensitivity (unchanged)
- Square: Toggle instructions (unchanged)
- Triangle: Show battery (unchanged)
- Move: Cycle between options (num_teams / force_all_start)
- Trigger: Hold 3s = Force start game (LED dims during hold)
- Select: Increase current option value
- Start: Decrease current option value
- PS: Exit admin mode (unchanged)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Protocol

from opentelemetry import trace

from lib.colors import Colors
from lib.controller_constants import ButtonTrackingKey
from lib.telemetry import SpanAttr
from lib.types import Sound
from services.menu.handlers.base import ButtonDebouncer, ControllerState

if TYPE_CHECKING:
    from services.menu.state_manager import StateManager

logger = logging.getLogger(__name__)


class AdminModeCallbacks(Protocol):
    """Protocol defining Menu-specific callbacks that AdminModeHandler needs."""

    def set_menu_state(self, state) -> None:
        """Set the menu state (for game starting)."""
        ...

    def get_game_options(self) -> list[str]:
        """Get list of available game options."""
        ...


class AdminModeHandler:
    """
    Handles admin mode state and commands.

    Admin mode is activated by pressing all 4 face buttons simultaneously
    (Cross + Circle + Square + Triangle). While active, buttons perform
    administrative actions.

    Implements the ControllerHandler protocol for StateManager integration.
    """

    def __init__(
        self,
        controller_channel,
        tracer: trace.Tracer,
        callbacks: AdminModeCallbacks,
        metrics,
    ):
        """
        Initialize the admin mode handler.

        Args:
            controller_channel: gRPC channel to Controller Manager service
            tracer: OpenTelemetry tracer for span creation
            callbacks: Menu-specific callbacks (set_menu_state, get_game_options)
            metrics: Prometheus metrics module
        """
        self.controller_channel = controller_channel
        self.tracer = tracer
        self.callbacks = callbacks
        self.metrics = metrics

        # StateManager reference (set via set_state_manager)
        self._state_manager: StateManager | None = None

        # Admin mode state
        self.active = False
        self.controller_serial: str | None = None
        self.entry_time: float = 0
        self.combo_shown = False

        # Tracing state
        self.session_span: trace.Span | None = None
        self.session_span_context = None

        # Admin option navigation
        # Options cycle through all game settings configurable via admin mode
        self.current_option = 0
        self.option_names = [
            "sensitivity",  # 0-4 (Ultra Slow to Ultra Fast)
            "num_teams",  # 2-6 teams (for Teams, RandomTeams, Traitor)
            "random_assignment",  # True/False for Teams mode
            "nonstop_time_limit",  # 0=unlimited, 60-300 seconds
            "invincibility",  # 2.0-8.0 seconds (Tournament, FightClub)
            "fight_club_min_rounds",  # 5-20 rounds
            "werewolf_reveal_time",  # 20.0-60.0 seconds
            "force_all_start",  # True/False
        ]
        self.option_colors = [
            Colors.Blue,  # sensitivity
            Colors.Turquoise,  # num_teams
            Colors.Magenta,  # random_assignment
            Colors.Yellow,  # nonstop_time_limit
            Colors.Green,  # invincibility
            Colors.Orange,  # fight_club_min_rounds
            Colors.Purple,  # werewolf_reveal_time
            Colors.Orange,  # force_all_start
        ]

        # Button debouncing (300ms for admin mode)
        self._debouncer = ButtonDebouncer(default_interval=0.3)

        # Background tasks (to prevent garbage collection)
        self._pending_tasks: set[asyncio.Task] = set()

        # Timeout task for auto-exit after 60 seconds
        self._timeout_task: asyncio.Task | None = None
        self._timeout_seconds = 60

        # Trigger hold tracking for force start
        self._trigger_press_time: float | None = None
        self._trigger_hold_task: asyncio.Task | None = None
        self._force_start_threshold = 3.0  # seconds

    # ControllerHandler protocol methods

    @property
    def state(self) -> ControllerState:
        """The state this handler manages."""
        return ControllerState.ADMIN

    def set_state_manager(self, manager: StateManager) -> None:
        """Set the state manager reference."""
        self._state_manager = manager

    async def handle_button(self, serial: str, button: str) -> None:
        """
        Handle a button press event (ControllerHandler protocol).

        Delegates to the existing handle_button_event method.

        Args:
            serial: Controller serial number
            button: Button name
        """
        await self.handle_button_event(serial, button)

    async def on_enter(self, serial: str) -> None:
        """
        Called when a controller enters admin mode (ControllerHandler protocol).

        Delegates to the existing enter method.

        Args:
            serial: Controller serial number
        """
        await self.enter(serial)

    async def on_exit(self, _serial: str) -> None:
        """
        Called when a controller exits admin mode (ControllerHandler protocol).

        Delegates to the existing exit method.

        Args:
            serial: Controller serial number (unused - uses internal state)
        """
        await self.exit()

    # Helper properties for StateManager access

    @property
    def _settings_channel(self):
        """Get settings channel from StateManager."""
        if self._state_manager is None:
            raise RuntimeError("StateManager not set")
        return self._state_manager.settings.settings_channel

    @property
    def _connected_controllers(self) -> set[str]:
        """Get connected controllers from StateManager."""
        if self._state_manager is None:
            return set()
        return self._state_manager.connected_controllers

    @property
    def _ready_controllers(self) -> set[str]:
        """Get ready controllers from StateManager."""
        if self._state_manager is None:
            return set()
        return self._state_manager.ready_controllers

    @property
    def _current_game_mode(self) -> str:
        """Get current game mode name from StateManager."""
        if self._state_manager is None:
            return "JoustFFA"
        return self._state_manager.current_game_mode.name

    async def _send_game_effect(
        self,
        serial: str,
        effect: int,
        color: tuple[int, int, int] | None = None,
        duration_ms: int = 0,
        speed: int = 0,
    ) -> bool:
        """Send game effect via StateManager's LED controller."""
        if self._state_manager is None:
            return False
        return await self._state_manager.led.send_game_effect(
            serial, effect, color=color, duration_ms=duration_ms, speed=speed
        )

    async def _send_base_color(self, serial: str, color: tuple[int, int, int]) -> bool:
        """Send base color via StateManager's LED controller."""
        if self._state_manager is None:
            return False
        return await self._state_manager.led.send_base_color(serial, color)

    async def _publish_event(self, event_type: str, data: dict) -> None:
        """Publish event via StateManager."""
        if self._state_manager is None:
            return
        await self._state_manager.publish_event(event_type, data)

    async def _play_voice(self, sound: Sound) -> None:
        """Play voice via StateManager's audio helper."""
        if self._state_manager is None:
            return
        await self._state_manager.audio.play_voice(sound)

    async def _play_sound(self, sound: Sound) -> None:
        """Play sound effect via StateManager's audio helper."""
        if self._state_manager is None:
            return
        await self._state_manager.audio.play_sound(sound)

    # Original properties

    @property
    def is_active(self) -> bool:
        """Check if admin mode is currently active."""
        return self.active

    @property
    def admin_controller(self) -> str | None:
        """Get the serial of the controller in admin mode."""
        return self.controller_serial

    def is_admin_controller(self, serial: str) -> bool:
        """Check if the given serial is the admin controller."""
        return self.active and serial == self.controller_serial

    def check_combo_from_state(self, button_state: dict[str, bool]) -> bool:
        """
        Check if admin combo is being held based on button state dict.

        Args:
            button_state: Dictionary with button names as keys and pressed state as values

        Returns:
            True if all 4 face buttons (Cross + Circle + Square + Triangle) are pressed
        """
        return (
            button_state.get("cross", False)
            and button_state.get("circle", False)
            and button_state.get("square", False)
            and button_state.get("triangle", False)
        )

    def check_combo_from_controller(self, controller) -> bool:
        """
        Check if admin combo is being held based on controller object.

        Args:
            controller: Controller protobuf message with button fields

        Returns:
            True if all 4 face buttons (Cross + Circle + Square + Triangle) are pressed
        """
        return (
            controller.cross_pressed
            and controller.circle_pressed
            and controller.square_pressed
            and controller.triangle_pressed
        )

    def _get_span_context(self):
        """Get the admin mode span context for child spans."""
        return self.session_span_context if self.session_span_context else None

    async def enter(self, serial: str) -> None:
        """
        Enter admin mode.

        Creates a parent admin_mode_session span that encompasses all admin actions.
        The span is ended when exit() is called.

        Args:
            serial: Controller serial number
        """
        from proto import controller_manager_pb2

        self.metrics.button_presses_total.labels(button="admin_combo", action="hold").inc()

        # Create parent span for entire admin mode session (ended in exit)
        self.session_span = self.tracer.start_span("admin_mode_session")
        self.session_span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)
        self.session_span_context = trace.set_span_in_context(self.session_span)

        # Create child span for the entry operation
        with self.tracer.start_as_current_span("enter_admin_mode", context=self.session_span_context) as span:
            span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)

            self.active = True
            self.controller_serial = serial
            self.entry_time = time.time()
            self.current_option = 0  # Reset to first option (team_size)

            # Send admin enter effect via stream
            if await self._send_game_effect(serial, controller_manager_pb2.GAME_EFFECT_ADMIN_ENTER):
                logger.info(f"Admin mode entered by controller {serial}")
                span.add_event("admin_mode_entered")
            else:
                logger.warning(f"Failed to signal admin mode entry for {serial} - stream not available")

            # Start timeout task to auto-exit after 60 seconds
            self._start_timeout_task(serial)

    def _start_timeout_task(self, serial: str) -> None:
        """Start background task to auto-exit admin mode after timeout."""
        # Cancel existing timeout task if any
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

        async def timeout_exit():
            try:
                await asyncio.sleep(self._timeout_seconds)
                if self.active and self.controller_serial == serial:
                    logger.info(f"Admin mode auto-exit after {self._timeout_seconds}s timeout")
                    await self._exit_to_connected(serial)
            except asyncio.CancelledError:
                pass  # Normal cancellation when exiting early

        self._timeout_task = asyncio.create_task(timeout_exit())

    async def exit(self) -> None:
        """
        Exit admin mode and restore lobby color.

        Ends the admin_mode_session parent span.
        """
        if not self.active:
            return

        # Cancel timeout task
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            self._timeout_task = None

        from proto import controller_manager_pb2

        duration = time.time() - self.entry_time

        # Create child span for exit operation (under admin_mode_session)
        with self.tracer.start_as_current_span("exit_admin_mode", context=self.session_span_context) as span:
            span.set_attribute(SpanAttr.CONTROLLER_SERIAL, self.controller_serial)
            span.set_attribute("duration_seconds", duration)

            logger.info(f"Admin mode exited by controller {self.controller_serial}")

            # Send exit effect via stream
            serial = self.controller_serial
            if await self._send_game_effect(serial, controller_manager_pb2.GAME_EFFECT_ADMIN_EXIT):
                logger.debug(f"Admin exit effect sent via stream for {serial}")
            else:
                logger.warning(f"Failed to send admin exit effect for {serial} - stream not available")

            # Clear admin mode state
            self.active = False
            self.controller_serial = None
            self.entry_time = 0
            span.add_event("admin_mode_exited")

        # End the parent admin_mode_session span
        if self.session_span:
            self.session_span.set_attribute("session.duration_seconds", duration)
            self.session_span.end()
            self.session_span = None
            self.session_span_context = None

    async def handle_button_event(self, serial: str, button: str) -> None:
        """
        Handle button press in admin mode.

        Args:
            serial: Controller serial number
            button: Button name (trigger, move, cross, circle, square, triangle, ps)
        """
        # Check for admin mode timeout (60 seconds)
        if time.time() - self.entry_time > 60:
            logger.info("Admin mode timed out after 60 seconds")
            await self._exit_to_connected(serial)
            return

        if not self._debouncer.should_process(serial, button):
            return

        match button:
            case ButtonTrackingKey.MOVE:
                await self.handle_cycle_option(serial)
            case ButtonTrackingKey.TRIGGER:
                await self._start_trigger_hold_tracking(serial)
            case ButtonTrackingKey.SELECT:
                await self.handle_increase_value(serial)
            case ButtonTrackingKey.START:
                await self.handle_decrease_value(serial)
            case ButtonTrackingKey.CROSS:
                await self.handle_game_mode(serial)
            case ButtonTrackingKey.CIRCLE:
                await self.handle_sensitivity(serial)
            case ButtonTrackingKey.TRIANGLE:
                await self.handle_battery(serial)
            case ButtonTrackingKey.SQUARE:
                await self.handle_instructions(serial)
            case ButtonTrackingKey.PS:
                await self._exit_to_connected(serial)

    async def _exit_to_connected(self, serial: str) -> None:
        """
        Exit admin mode and transition back to CONNECTED state.

        Uses StateManager to properly transition states.

        Args:
            serial: Controller serial number
        """
        if self._state_manager is not None:
            await self._state_manager.transition_to(serial, ControllerState.CONNECTED)
        else:
            # Fallback if StateManager not set
            await self.exit()

    async def _start_trigger_hold_tracking(self, serial: str) -> None:
        """
        Start tracking trigger hold for force start.

        Begins 3-second timer with LED dim effect. If trigger is held
        for full duration, triggers force start.

        Args:
            serial: Controller serial number
        """
        # Cancel any existing hold task
        if self._trigger_hold_task and not self._trigger_hold_task.done():
            self._trigger_hold_task.cancel()

        self._trigger_press_time = time.time()

        # Start the dimming effect
        await self.start_force_start_effect(serial)

        # Create task to fire force start after threshold
        async def trigger_hold_timer():
            try:
                await asyncio.sleep(self._force_start_threshold)
                # If we get here, trigger was held long enough
                if self.active and serial == self.controller_serial:
                    logger.info(f"Trigger hold completed, triggering force start for {serial}")
                    await self.handle_force_start(serial)
            except asyncio.CancelledError:
                pass  # Normal cancellation when trigger released early

        self._trigger_hold_task = asyncio.create_task(trigger_hold_timer())
        self._pending_tasks.add(self._trigger_hold_task)
        self._trigger_hold_task.add_done_callback(self._pending_tasks.discard)

    async def handle_trigger_release(self, serial: str) -> None:
        """
        Handle trigger release in admin mode.

        Cancels force start if trigger released before 3 seconds.

        Args:
            serial: Controller serial number
        """
        if not self.is_admin_controller(serial):
            return

        # Cancel hold task if running
        if self._trigger_hold_task and not self._trigger_hold_task.done():
            self._trigger_hold_task.cancel()
            self._trigger_hold_task = None
            logger.debug(f"Trigger released early, cancelled force start for {serial}")

            # Cancel the dimming effect and restore white
            await self.cancel_force_start_effect(serial)

        self._trigger_press_time = None

    async def handle_game_mode(self, serial: str) -> None:
        """
        Handle game mode cycling (Cross button).

        Cycles through game modes forward, shows game color flash and plays voice.

        Args:
            serial: Controller serial number
        """
        from proto import controller_manager_pb2
        from services.menu.utils.led import GAME_MODE_COLORS

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_game_mode", context=ctx) as span:
            span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)

            try:
                game_options = self.callbacks.get_game_options()
                current_selection = self._current_game_mode

                if not game_options:
                    logger.warning("No game options available for mode change")
                    return

                # Find current index
                try:
                    current_idx = game_options.index(current_selection)
                except ValueError:
                    current_idx = 0

                # Cycle forward
                new_idx = (current_idx + 1) % len(game_options)
                new_selection = game_options[new_idx]

                span.set_attribute("old_selection", current_selection)
                span.set_attribute("new_selection", new_selection)

                # Publish selection change
                await self._publish_event(
                    "game_selection_changed",
                    {"game_name": new_selection, "source": "admin_mode", "serial": serial},
                )

                # Visual feedback: flash game mode color
                game_color = GAME_MODE_COLORS.get(new_selection, (255, 165, 0))  # Default orange
                await self._send_game_effect(
                    serial,
                    controller_manager_pb2.GAME_EFFECT_PULSE,
                    color=game_color,
                    duration_ms=600,
                    speed=6,
                )

                # Play game mode voice announcement
                if self._state_manager is not None:
                    await self._state_manager.audio.play_game_mode_voice(new_selection)

                span.add_event(
                    "game_mode_changed",
                    {"old_selection": current_selection, "new_selection": new_selection},
                )
                logger.info(f"Game mode changed by admin {serial}: {current_selection} -> {new_selection}")

            except Exception as e:
                logger.error(f"Error changing game mode: {e}", exc_info=True)

    async def handle_game_mode_change(self, serial: str, forward: bool = True) -> None:
        """
        Change game mode from admin mode.

        Only available in admin mode to prevent accidental game changes.

        Args:
            serial: Controller serial number
            forward: True to go forward through modes, False to go backward
        """
        from proto import controller_manager_pb2

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_game_mode_change", context=ctx) as span:
            span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)
            span.set_attribute("direction", "forward" if forward else "backward")

            try:
                game_options = self.callbacks.get_game_options()
                current_selection = self._current_game_mode

                if not game_options:
                    logger.warning("No game options available for mode change")
                    return

                # Find current index
                try:
                    current_idx = game_options.index(current_selection)
                except ValueError:
                    current_idx = 0

                # Calculate new index
                new_idx = (current_idx + 1) % len(game_options) if forward else (current_idx - 1) % len(game_options)

                new_selection = game_options[new_idx]

                span.set_attribute("old_selection", current_selection)
                span.set_attribute("new_selection", new_selection)

                # Publish selection change
                await self._publish_event(
                    "game_selection_changed",
                    {"game_name": new_selection, "source": "admin_mode", "serial": serial},
                )

                # Visual feedback: brief color pulse (green for forward, blue for backward)
                # GAME_EFFECT_PULSE restores to base color automatically
                pulse_color = (0, 255, 0) if forward else (0, 0, 255)
                await self._send_game_effect(
                    serial,
                    controller_manager_pb2.GAME_EFFECT_PULSE,
                    color=pulse_color,
                    duration_ms=400,
                    speed=6,
                )

            except Exception as e:
                logger.error(f"Error changing game mode: {e}", exc_info=True)

    async def handle_force_start(self, serial: str) -> None:
        """
        Force start the game from admin mode.

        Triggered when admin holds trigger for 2 seconds.
        Starts the game with currently ready controllers (or all if force_all_start=true).

        Args:
            serial: Controller serial number
        """
        from proto import controller_manager_pb2

        if self._state_manager is None:
            return

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_force_start", context=ctx) as span:
            span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)
            span.set_attribute("game.name", self._current_game_mode)

            try:
                # Check force_all_start from local game settings
                force_all = bool(self._state_manager.game_settings.get("force_all_start", False))
                span.set_attribute("force_all_start", force_all)

                # Determine which controllers to include
                if force_all:
                    # Use all connected controllers
                    controllers = list(self._connected_controllers)
                else:
                    # Use ready controllers, but include admin if not already ready
                    controllers = list(self._ready_controllers)
                    if serial not in controllers:
                        controllers.append(serial)

                span.set_attribute("controller.count", len(controllers))

                # Visual feedback: White flash before starting
                await self._send_game_effect(
                    serial,
                    controller_manager_pb2.GAME_EFFECT_FLASH,
                    color=(255, 255, 255),
                    duration_ms=500,
                    speed=10,
                )

                # Exit admin mode
                await self.exit()

                # Small delay for visual feedback
                await asyncio.sleep(0.3)

                # Start the game
                from proto import menu_pb2

                self.callbacks.set_menu_state(menu_pb2.MenuState.GAME_STARTING)
                await self._publish_event(
                    "game_requested",
                    {
                        "game_name": self._current_game_mode,
                        "source": "admin_force_start",
                        "serial": serial,
                        "controllers": json.dumps(controllers),
                    },
                )

                span.add_event(
                    "force_start_triggered",
                    {
                        "game": self._current_game_mode,
                        "player_count": len(controllers),
                    },
                )
                logger.info(
                    f"Force starting game '{self._current_game_mode}' via admin controller {serial} "
                    f"with {len(controllers)} players"
                )

            except Exception as e:
                logger.error(f"Error force starting game: {e}", exc_info=True)

    async def start_force_start_effect(self, serial: str) -> None:
        """
        Start the fade-out effect for force start countdown.

        Sends GAME_EFFECT_FORCE_START_CHARGE via bidirectional stream.
        LED fades white to dim over 2s.

        Args:
            serial: Controller serial number
        """
        from proto import controller_manager_pb2

        try:
            if await self._send_game_effect(serial, controller_manager_pb2.GAME_EFFECT_FORCE_START_CHARGE):
                logger.debug(f"Started force start fade effect for {serial}")
            else:
                logger.warning(f"Could not start force start effect for {serial} - stream not available")
        except Exception as e:
            logger.error(f"Error starting force start effect: {e}")

    async def cancel_force_start_effect(self, serial: str) -> None:
        """
        Cancel the force start effect and restore admin mode white color.

        Sends base color via bidirectional stream to cancel effect and restore white.

        Args:
            serial: Controller serial number
        """
        try:
            if await self._send_base_color(serial, (255, 255, 255)):
                logger.debug(f"Cancelled force start effect for {serial}")
            else:
                logger.warning(f"Could not cancel force start effect for {serial} - stream not available")
        except Exception as e:
            logger.error(f"Error cancelling force start effect: {e}")

    async def handle_sensitivity(self, serial: str) -> None:
        """
        Handle sensitivity cycling in admin mode.

        Cycles through all 5 levels:
        Ultra Slow (0) -> Slow (1) -> Medium (2) -> Fast (3) -> Ultra Fast (4) -> Ultra Slow

        Uses state_manager.game_settings for local storage.

        Args:
            serial: Controller serial number
        """
        from proto import controller_manager_pb2

        if self._state_manager is None:
            return

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_sensitivity", context=ctx) as span:
            span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)

            try:
                settings = self._state_manager.game_settings
                current = int(settings.get("sensitivity", 2))

                # Validate current value is in range (0-4)
                if current < 0 or current > 4:
                    logger.warning(f"Invalid sensitivity value {current}, resetting to 2")
                    current = 2

                # Cycle through all 5 levels: 0 -> 1 -> 2 -> 3 -> 4 -> 0
                new_value = (current + 1) % 5

                # Update local setting
                settings["sensitivity"] = new_value

                # Visual feedback: Color by sensitivity level (5 distinct colors)
                sensitivity_colors = [
                    Colors.Blue,  # Ultra Slow (0)
                    Colors.Turquoise,  # Slow (1)
                    Colors.Green,  # Medium (2)
                    Colors.Orange,  # Fast (3)
                    Colors.Red,  # Ultra Fast (4)
                ]
                color = sensitivity_colors[new_value].value

                # Show sensitivity color (GAME_EFFECT_PULSE restores to base automatically)
                await self._send_game_effect(
                    serial,
                    controller_manager_pb2.GAME_EFFECT_PULSE,
                    color=color,
                    duration_ms=800,
                    speed=5,
                )

                # Play voice for sensitivity level (matches original JoustMania)
                # Note: "ultra_high" = ultra-high sensitivity (detects slow movement)
                sensitivity_voices = [
                    Sound.MENU_VOX_SENSITIVITY_ULTRA_HIGH,  # ULTRA_SLOW (0)
                    Sound.MENU_VOX_SENSITIVITY_HIGH,  # SLOW (1)
                    Sound.MENU_VOX_SENSITIVITY_MEDIUM,  # MEDIUM (2)
                    Sound.MENU_VOX_SENSITIVITY_LOW,  # FAST (3)
                    Sound.MENU_VOX_SENSITIVITY_ULTRA_LOW,  # ULTRA_FAST (4)
                ]
                await self._play_voice(sensitivity_voices[new_value])

                span.add_event(
                    "sensitivity_changed",
                    {"old_value": current, "new_value": new_value},
                )
                logger.info(f"Sensitivity changed by admin controller {serial}: {current} -> {new_value}")

            except Exception as e:
                logger.error(f"Error changing sensitivity: {e}", exc_info=True)

    async def handle_battery(self, serial: str) -> None:
        """
        Handle battery display in admin mode (triangle press).

        Sends GAME_EFFECT_SHOW_BATTERY to controller_manager which shows
        battery levels on ALL connected controllers using color-coded LEDs
        for 1 second, then auto-restores to previous colors.

        Color scheme (from original JoustMania):
        - 100%: Green
        - 80%: Turquoise
        - 60%: Blue
        - 40%: Yellow
        - <40%: Red

        Args:
            serial: Controller serial number
        """
        from proto import controller_manager_pb2

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_battery_display", context=ctx) as span:
            span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)

            try:
                # Send SHOW_BATTERY effect with empty serial to affect all controllers
                if await self._send_game_effect("", controller_manager_pb2.GAME_EFFECT_SHOW_BATTERY):
                    logger.info(f"Battery display triggered by admin controller {serial}")
                    span.add_event("battery_display_triggered")
                else:
                    logger.warning("Could not trigger battery display - stream not available")

            except Exception as e:
                logger.error(f"Error triggering battery display: {e}", exc_info=True)

    async def handle_instructions(self, serial: str) -> None:
        """
        Handle instruction toggle in admin mode.

        Toggles instruction display on/off.

        Args:
            serial: Controller serial number
        """
        from proto import (
            controller_manager_pb2,
            settings_pb2,
            settings_pb2_grpc,
        )

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_instructions", context=ctx) as span:
            span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)

            try:
                settings_stub = settings_pb2_grpc.SettingsServiceStub(self._settings_channel)

                # Get current instruction state
                get_request = settings_pb2.GetSettingRequest(key="instructions")
                get_response = await settings_stub.GetSetting(get_request)
                current = get_response.value if get_response.value else "true"

                # Toggle: true <-> false
                new_value = "false" if current == "true" else "true"

                # Update setting
                update_request = settings_pb2.UpdateSettingRequest(
                    key="instructions", value=new_value, source="admin_mode"
                )
                await settings_stub.UpdateSetting(update_request)

                # Visual feedback: Green (enabled) or Red (disabled)
                # GAME_EFFECT_PULSE restores to base color automatically
                pulse_color = (0, 255, 0) if new_value == "true" else (255, 0, 0)
                await self._send_game_effect(
                    serial,
                    controller_manager_pb2.GAME_EFFECT_PULSE,
                    color=pulse_color,
                    duration_ms=800,
                    speed=5,
                )

                # Play instructions toggle voice announcement
                voice = Sound.MENU_VOX_INSTRUCTIONS_ON if new_value == "true" else Sound.MENU_VOX_INSTRUCTIONS_OFF
                await self._play_voice(voice)

                span.add_event(
                    "instructions_toggled",
                    {"old_value": current, "new_value": new_value, "enabled": new_value == "true"},
                )
                logger.info(f"Instructions toggled by admin controller {serial}: {current} -> {new_value}")

            except Exception as e:
                logger.error(f"Error toggling instructions: {e}", exc_info=True)

    async def handle_cycle_option(self, serial: str) -> None:
        """
        Cycle through admin options.

        Options: num_teams -> force_all_start -> num_teams

        Args:
            serial: Controller serial number
        """
        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_cycle_option", context=ctx) as span:
            span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)

            # Cycle to next option
            self.current_option = (self.current_option + 1) % len(self.option_names)
            option_name = self.option_names[self.current_option]
            option_color = self.option_colors[self.current_option]

            span.set_attribute(SpanAttr.ADMIN_OPTION, option_name)

            try:
                # Show option color for 1 second
                await self._send_base_color(serial, option_color.value)

                # Restore white after option color finishes
                async def restore_white():
                    await asyncio.sleep(1.1)
                    if self.active and serial == self.controller_serial:
                        await self._send_base_color(serial, Colors.White.value)

                # Track task to prevent garbage collection
                task = asyncio.create_task(restore_white())
                self._pending_tasks.add(task)
                task.add_done_callback(self._pending_tasks.discard)

                span.add_event(
                    "admin_option_changed",
                    {"option": option_name, "option_index": self.current_option},
                )
                logger.info(f"Admin option changed to {option_name} by controller {serial}")

            except Exception as e:
                logger.error(f"Error cycling admin option: {e}", exc_info=True)

    async def handle_increase_value(self, serial: str) -> None:
        """
        Increase the value of the current admin option.

        Uses state_manager.game_settings for local storage.

        Args:
            serial: Controller serial number
        """
        if self._state_manager is None:
            return

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_increase_value", context=ctx) as span:
            span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)

            option_name = self.option_names[self.current_option]
            span.set_attribute(SpanAttr.ADMIN_OPTION, option_name)

            try:
                settings = self._state_manager.game_settings
                current_value = settings.get(option_name)

                # Calculate new value using pattern matching
                match option_name:
                    case "sensitivity":
                        # Cycle: 0 -> 1 -> 2 -> 3 -> 4 -> 0
                        current = int(current_value) if current_value is not None else 2
                        new_value = (current + 1) % 5

                    case "num_teams":
                        # Cycle: 2 -> 3 -> 4 -> 5 -> 6 -> 2
                        current = int(current_value) if current_value is not None else 2
                        new_value = current + 1 if current < 6 else 2

                    case "random_assignment" | "force_all_start":
                        # Toggle boolean
                        new_value = not bool(current_value)

                    case "nonstop_time_limit":
                        # Cycle: 0 -> 60 -> 120 -> 180 -> 240 -> 300 -> 0
                        current = int(current_value) if current_value is not None else 0
                        steps = [0, 60, 120, 180, 240, 300]
                        idx = (steps.index(current) + 1) % len(steps) if current in steps else 0
                        new_value = steps[idx]

                    case "invincibility":
                        # Increment: 2.0 -> 3.0 -> 4.0 -> ... -> 8.0 -> 2.0
                        current = float(current_value) if current_value is not None else 4.0
                        new_value = current + 1.0 if current < 8.0 else 2.0

                    case "fight_club_min_rounds":
                        # Increment: 5 -> 10 -> 15 -> 20 -> 5
                        current = int(current_value) if current_value is not None else 10
                        steps = [5, 10, 15, 20]
                        idx = (steps.index(current) + 1) % len(steps) if current in steps else 1
                        new_value = steps[idx]

                    case "werewolf_reveal_time":
                        # Increment: 20 -> 25 -> 30 -> 35 -> 40 -> 45 -> 50 -> 55 -> 60 -> 20
                        current = float(current_value) if current_value is not None else 35.0
                        new_value = current + 5.0 if current < 60.0 else 20.0

                    case _:
                        new_value = current_value

                # Update local setting
                settings[option_name] = new_value

                # Visual feedback
                await self._show_value_feedback(serial, option_name, new_value)

                # Voice feedback
                await self._play_value_voice(option_name, new_value)

                span.add_event(
                    "admin_value_increased",
                    {"option": option_name, "old_value": str(current_value), "new_value": str(new_value)},
                )
                logger.info(f"Admin increased {option_name}: {current_value} -> {new_value}")

            except Exception as e:
                logger.error(f"Error increasing admin value: {e}", exc_info=True)

    async def handle_decrease_value(self, serial: str) -> None:
        """
        Decrease the value of the current admin option.

        Uses state_manager.game_settings for local storage.

        Args:
            serial: Controller serial number
        """
        if self._state_manager is None:
            return

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_decrease_value", context=ctx) as span:
            span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)

            option_name = self.option_names[self.current_option]
            span.set_attribute(SpanAttr.ADMIN_OPTION, option_name)

            try:
                settings = self._state_manager.game_settings
                current_value = settings.get(option_name)

                # Calculate new value using pattern matching
                match option_name:
                    case "sensitivity":
                        # Cycle backward: 0 -> 4 -> 3 -> 2 -> 1 -> 0
                        current = int(current_value) if current_value is not None else 2
                        new_value = (current - 1) % 5

                    case "num_teams":
                        # Cycle backward: 2 -> 6 -> 5 -> 4 -> 3 -> 2
                        current = int(current_value) if current_value is not None else 2
                        new_value = current - 1 if current > 2 else 6

                    case "random_assignment" | "force_all_start":
                        # Toggle boolean (same as increase)
                        new_value = not bool(current_value)

                    case "nonstop_time_limit":
                        # Cycle backward: 0 -> 300 -> 240 -> 180 -> 120 -> 60 -> 0
                        current = int(current_value) if current_value is not None else 0
                        steps = [0, 60, 120, 180, 240, 300]
                        idx = (steps.index(current) - 1) % len(steps) if current in steps else 0
                        new_value = steps[idx]

                    case "invincibility":
                        # Decrement: 2.0 -> 8.0 -> 7.0 -> ... -> 3.0 -> 2.0
                        current = float(current_value) if current_value is not None else 4.0
                        new_value = current - 1.0 if current > 2.0 else 8.0

                    case "fight_club_min_rounds":
                        # Decrement: 5 -> 20 -> 15 -> 10 -> 5
                        current = int(current_value) if current_value is not None else 10
                        steps = [5, 10, 15, 20]
                        idx = (steps.index(current) - 1) % len(steps) if current in steps else 1
                        new_value = steps[idx]

                    case "werewolf_reveal_time":
                        # Decrement: 20 -> 60 -> 55 -> 50 -> ... -> 25 -> 20
                        current = float(current_value) if current_value is not None else 35.0
                        new_value = current - 5.0 if current > 20.0 else 60.0

                    case _:
                        new_value = current_value

                # Update local setting
                settings[option_name] = new_value

                # Visual feedback
                await self._show_value_feedback(serial, option_name, new_value)

                # Voice feedback
                await self._play_value_voice(option_name, new_value)

                span.add_event(
                    "admin_value_decreased",
                    {"option": option_name, "old_value": str(current_value), "new_value": str(new_value)},
                )
                logger.info(f"Admin decreased {option_name}: {current_value} -> {new_value}")

            except Exception as e:
                logger.error(f"Error decreasing admin value: {e}", exc_info=True)

    async def _show_value_feedback(self, serial: str, option_name: str, value: int | float | bool) -> None:
        """
        Show visual feedback for admin value change.

        Args:
            serial: Controller serial number
            option_name: Name of the option that changed
            value: New value (typed)
        """
        from proto import controller_manager_pb2

        try:
            # Determine feedback color using pattern matching
            match option_name:
                case "sensitivity":
                    # 5-color gradient for sensitivity levels (0-4)
                    sensitivity_colors = [
                        Colors.Blue,  # Ultra Slow (0)
                        Colors.Turquoise,  # Slow (1)
                        Colors.Green,  # Medium (2)
                        Colors.Orange,  # Fast (3)
                        Colors.Red,  # Ultra Fast (4)
                    ]
                    pulse_color = sensitivity_colors[int(value)].value

                case "num_teams":
                    # Gradient from green (2 teams) to red (6 teams)
                    num = int(value)
                    r = int(255 * (num - 2) / 4)
                    g = int(255 * (6 - num) / 4)
                    pulse_color = (r, g, 0)

                case "random_assignment" | "force_all_start":
                    # Green for True, red for False
                    pulse_color = Colors.Green.value if value else Colors.Red.value

                case "nonstop_time_limit":
                    # Purple intensity based on time (0=dim, 300=bright)
                    intensity = int(255 * int(value) / 300) if int(value) > 0 else 50
                    pulse_color = (intensity, 0, intensity)

                case "invincibility":
                    # Green intensity based on duration (2s=dim, 8s=bright)
                    intensity = int(255 * (float(value) - 2.0) / 6.0)
                    pulse_color = (0, intensity + 50, 0)

                case "fight_club_min_rounds":
                    # Orange intensity based on rounds (5=dim, 20=bright)
                    intensity = int(255 * (int(value) - 5) / 15)
                    pulse_color = (255, intensity + 50, 0)

                case "werewolf_reveal_time":
                    # Purple intensity based on time (20s=dim, 60s=bright)
                    intensity = int(255 * (float(value) - 20.0) / 40.0)
                    pulse_color = (intensity + 50, 0, 255)

                case _:
                    pulse_color = Colors.White.value

            # Show feedback color (GAME_EFFECT_PULSE restores to base automatically)
            await self._send_game_effect(
                serial,
                controller_manager_pb2.GAME_EFFECT_PULSE,
                color=pulse_color,
                duration_ms=600,
                speed=6,
            )

        except Exception as e:
            logger.error(f"Error showing value feedback: {e}", exc_info=True)

    async def _play_value_voice(self, option_name: str, value: str) -> None:
        """
        Play voice feedback for admin option value change.

        Args:
            option_name: Name of the option that changed
            value: New value
        """
        try:
            if option_name == "num_teams":
                # Play number voice (adminop_2 through adminop_6)
                num_teams_voices = {
                    "2": Sound.MENU_VOX_ADMINOP_2,
                    "3": Sound.MENU_VOX_ADMINOP_3,
                    "4": Sound.MENU_VOX_ADMINOP_4,
                    "5": Sound.MENU_VOX_ADMINOP_5,
                    "6": Sound.MENU_VOX_ADMINOP_6,
                }
                voice = num_teams_voices.get(value)
                if voice:
                    await self._play_voice(voice)
            elif option_name == "force_all_start":
                # Play true/false voice
                voice = Sound.MENU_VOX_ADMINOP_TRUE if value == "true" else Sound.MENU_VOX_ADMINOP_FALSE
                await self._play_voice(voice)
        except Exception as e:
            logger.error(f"Error playing value voice: {e}", exc_info=True)

    def reset_on_disconnect(self, serial: str) -> None:
        """
        Reset admin mode state when the admin controller disconnects.

        Args:
            serial: Serial of the disconnected controller
        """
        if self.active and serial == self.controller_serial:
            logger.info(f"Admin controller {serial} disconnected, resetting admin mode")

            # Cancel timeout task
            if self._timeout_task and not self._timeout_task.done():
                self._timeout_task.cancel()
                self._timeout_task = None

            self.active = False
            self.controller_serial = None
            self.entry_time = 0

            # End span if active
            if self.session_span:
                self.session_span.set_attribute("disconnect", True)
                self.session_span.end()
                self.session_span = None
                self.session_span_context = None
