"""
Admin mode handler for Menu service.

Manages the admin mode state, commands, and visual feedback when a controller
holds all 4 face buttons (Cross + Circle + Square + Triangle) simultaneously.

Admin mode allows changing settings like:
- Sensitivity level (Circle button)
- Battery display (Triangle button)
- Instructions toggle (Square button)
- Game mode selection (L1/R1 or Cross for backward)
- Force start game (Trigger hold for 2 seconds)
- Cycle options / adjust values (Move button / Trigger / Cross)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Protocol

from opentelemetry import trace

from lib.types import Sound
from services.menu.handlers.base import ControllerState

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
        self.current_option = 0  # 0=num_teams, 1=force_all_start
        self.option_names = ["num_teams", "force_all_start"]
        self.option_colors = [
            (0, 255, 255),  # Cyan for num_teams
            (255, 165, 0),  # Orange for force_all_start
        ]

        # Button debouncing
        self.last_button_time: dict[str, float] = {}
        self.button_debounce_interval = 0.3  # seconds

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

    async def on_exit(self, serial: str) -> None:  # noqa: ARG002
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
        """Get current game mode from StateManager."""
        if self._state_manager is None:
            return "JoustFFA"
        return self._state_manager.current_game_mode

    async def _send_game_effect(self, serial: str, effect: int) -> bool:
        """Send game effect via StateManager's LED controller."""
        if self._state_manager is None:
            return False
        return await self._state_manager.led.send_game_effect(serial, effect)

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

    def _should_process_button(self, serial: str, button: str, current_time: float) -> bool:
        """
        Check if a button press should be processed (debouncing).

        Args:
            serial: Controller serial
            button: Button name
            current_time: Current timestamp

        Returns:
            True if button should be processed
        """
        key = f"{serial}:{button}"
        last_time = self.last_button_time.get(key, 0)

        if current_time - last_time < self.button_debounce_interval:
            return False

        self.last_button_time[key] = current_time
        return True

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
        self.session_span.set_attribute("controller.serial", serial)
        self.session_span_context = trace.set_span_in_context(self.session_span)

        # Create child span for the entry operation
        with self.tracer.start_as_current_span("enter_admin_mode", context=self.session_span_context) as span:
            span.set_attribute("controller.serial", serial)

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

    async def exit(self) -> None:
        """
        Exit admin mode and restore lobby color.

        Ends the admin_mode_session parent span.
        """
        if not self.active:
            return

        from proto import controller_manager_pb2

        duration = time.time() - self.entry_time

        # Create child span for exit operation (under admin_mode_session)
        with self.tracer.start_as_current_span("exit_admin_mode", context=self.session_span_context) as span:
            span.set_attribute("controller.serial", self.controller_serial)
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
        current_time = time.time()

        # Check for admin mode timeout (60 seconds)
        if current_time - self.entry_time > 60:
            logger.info("Admin mode timed out after 60 seconds")
            await self._exit_to_connected(serial)
            return

        if not self._should_process_button(serial, button, current_time):
            return

        if button == "move":
            await self.handle_cycle_option(serial)
        elif button == "trigger":
            await self.handle_increase_value(serial)
        elif button == "cross":
            await self.handle_decrease_value(serial)
        elif button == "circle":
            await self.handle_sensitivity(serial)
        elif button == "triangle":
            await self.handle_battery(serial)
        elif button == "square":
            await self.handle_instructions(serial)
        elif button == "ps":
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

    async def handle_game_mode_change(self, serial: str, forward: bool = True) -> None:
        """
        Change game mode from admin mode.

        Only available in admin mode to prevent accidental game changes.

        Args:
            serial: Controller serial number
            forward: True to go forward through modes, False to go backward
        """
        from proto import controller_manager_pb2, controller_manager_pb2_grpc

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_game_mode_change", context=ctx) as span:
            span.set_attribute("controller.serial", serial)
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

                # Visual feedback: brief color flash
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                # Flash green for forward, blue for backward
                if forward:
                    color = controller_manager_pb2.RGB(r=0, g=255, b=0)
                else:
                    color = controller_manager_pb2.RGB(r=0, g=0, b=255)

                effect_request = controller_manager_pb2.PlayControllerEffectRequest(
                    serial=serial,
                    effect=controller_manager_pb2.ControllerEffect.EFFECT_PULSE,
                    color=color,
                    duration_ms=400,
                    speed=6,
                )
                await stub.PlayControllerEffect(effect_request)

                # Restore white after flash
                async def restore_white():
                    await asyncio.sleep(0.5)
                    if self.active and serial == self.controller_serial:
                        await self._send_base_color(serial, (255, 255, 255))

                asyncio.create_task(restore_white())

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
        from proto import (
            controller_manager_pb2,
            controller_manager_pb2_grpc,
            settings_pb2,
            settings_pb2_grpc,
        )

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_force_start", context=ctx) as span:
            span.set_attribute("controller.serial", serial)
            span.set_attribute("game.name", self._current_game_mode)

            try:
                # Check force_all_start setting
                settings_stub = settings_pb2_grpc.SettingsServiceStub(self._settings_channel)
                force_all_response = await settings_stub.GetSetting(
                    settings_pb2.GetSettingRequest(key="force_all_start")
                )
                force_all = force_all_response.value == "true"
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
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)
                effect_request = controller_manager_pb2.PlayControllerEffectRequest(
                    serial=serial,
                    effect=controller_manager_pb2.ControllerEffect.EFFECT_FLASH,
                    color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                    duration_ms=500,
                    speed=10,
                )
                await stub.PlayControllerEffect(effect_request)

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

        Args:
            serial: Controller serial number
        """
        from proto import (
            controller_manager_pb2,
            controller_manager_pb2_grpc,
            settings_pb2,
            settings_pb2_grpc,
        )

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_sensitivity", context=ctx) as span:
            span.set_attribute("controller.serial", serial)

            try:
                settings_stub = settings_pb2_grpc.SettingsServiceStub(self._settings_channel)

                # Get current sensitivity
                get_request = settings_pb2.GetSettingRequest(key="sensitivity")
                get_response = await settings_stub.GetSetting(get_request)
                current = int(get_response.value) if get_response.value else 2

                # Validate current value is in range (0-4)
                if current < 0 or current > 4:
                    logger.warning(f"Invalid sensitivity value {current}, resetting to 2")
                    current = 2

                # Cycle through all 5 levels: 0 -> 1 -> 2 -> 3 -> 4 -> 0
                new_value = str((current + 1) % 5)

                # Update setting
                update_request = settings_pb2.UpdateSettingRequest(
                    key="sensitivity", value=new_value, source="admin_mode"
                )
                await settings_stub.UpdateSetting(update_request)

                # Visual feedback: Color by sensitivity level (5 distinct colors)
                sensitivity_colors = [
                    (0, 0, 255),  # Blue - Ultra Slow (0)
                    (0, 255, 255),  # Cyan - Slow (1)
                    (0, 255, 0),  # Green - Medium (2)
                    (255, 165, 0),  # Orange - Fast (3)
                    (255, 0, 0),  # Red - Ultra Fast (4)
                ]
                color = sensitivity_colors[int(new_value)]

                controller_stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                # Show sensitivity color
                effect_request = controller_manager_pb2.PlayControllerEffectRequest(
                    serial=serial,
                    effect=controller_manager_pb2.ControllerEffect.EFFECT_PULSE,
                    color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
                    duration_ms=800,
                    speed=5,
                )
                await controller_stub.PlayControllerEffect(effect_request)

                # Play voice for sensitivity level (matches original JoustMania)
                # Note: "ultra_high" = ultra-high sensitivity (detects slow movement)
                sensitivity_voices = [
                    Sound.MENU_VOX_SENSITIVITY_ULTRA_HIGH,  # ULTRA_SLOW (0)
                    Sound.MENU_VOX_SENSITIVITY_HIGH,  # SLOW (1)
                    Sound.MENU_VOX_SENSITIVITY_MEDIUM,  # MEDIUM (2)
                    Sound.MENU_VOX_SENSITIVITY_LOW,  # FAST (3)
                    Sound.MENU_VOX_SENSITIVITY_ULTRA_LOW,  # ULTRA_FAST (4)
                ]
                await self._play_voice(sensitivity_voices[int(new_value)])

                # Restore white after feedback
                async def restore_white():
                    await asyncio.sleep(1.0)
                    if self.active and serial == self.controller_serial:
                        await self._send_base_color(serial, (255, 255, 255))

                asyncio.create_task(restore_white())

                span.add_event(
                    "sensitivity_changed",
                    {"old_value": current, "new_value": int(new_value)},
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
            span.set_attribute("controller.serial", serial)

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
            controller_manager_pb2_grpc,
            settings_pb2,
            settings_pb2_grpc,
        )

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_instructions", context=ctx) as span:
            span.set_attribute("controller.serial", serial)

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
                if new_value == "true":
                    color = controller_manager_pb2.RGB(r=0, g=255, b=0)  # Green - enabled
                else:
                    color = controller_manager_pb2.RGB(r=255, g=0, b=0)  # Red - disabled

                controller_stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                # Show color pulse
                effect_request = controller_manager_pb2.PlayControllerEffectRequest(
                    serial=serial,
                    effect=controller_manager_pb2.ControllerEffect.EFFECT_PULSE,
                    color=color,
                    duration_ms=800,
                    speed=5,
                )
                await controller_stub.PlayControllerEffect(effect_request)

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
            span.set_attribute("controller.serial", serial)

            # Cycle to next option
            self.current_option = (self.current_option + 1) % len(self.option_names)
            option_name = self.option_names[self.current_option]
            option_color = self.option_colors[self.current_option]

            span.set_attribute("admin.option", option_name)

            try:
                # Show option color for 1 second
                await self._send_base_color(serial, option_color)

                # Restore white after option color finishes
                async def restore_white():
                    await asyncio.sleep(1.1)
                    if self.active and serial == self.controller_serial:
                        await self._send_base_color(serial, (255, 255, 255))

                asyncio.create_task(restore_white())

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

        Args:
            serial: Controller serial number
        """
        from proto import settings_pb2, settings_pb2_grpc

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_increase_value", context=ctx) as span:
            span.set_attribute("controller.serial", serial)

            option_name = self.option_names[self.current_option]
            span.set_attribute("admin.option", option_name)

            try:
                stub = settings_pb2_grpc.SettingsServiceStub(self._settings_channel)

                # Get current value
                get_request = settings_pb2.GetSettingRequest(key=option_name)
                get_response = await stub.GetSetting(get_request)
                current_value = get_response.value

                # Calculate new value based on option type
                if option_name == "num_teams":
                    # Cycle: 2 -> 3 -> 4 -> 5 -> 6 -> 2
                    current = int(current_value) if current_value else 2
                    # Validate range
                    if current < 2 or current > 6:
                        logger.warning(f"Invalid num_teams value {current}, resetting to 2")
                        current = 2
                    new_value = str((current % 6) + 1) if current < 6 else "2"
                elif option_name == "force_all_start":
                    # Toggle: true <-> false
                    if current_value not in ["true", "false"]:
                        logger.warning(f"Invalid force_all_start value {current_value}, resetting to false")
                        current_value = "false"
                    new_value = "true" if current_value == "false" else "false"
                else:
                    new_value = current_value

                # Update setting
                update_request = settings_pb2.UpdateSettingRequest(
                    key=option_name, value=new_value, source="admin_mode"
                )
                await stub.UpdateSetting(update_request)

                # Visual feedback
                await self._show_value_feedback(serial, option_name, new_value)

                span.add_event(
                    "admin_value_increased",
                    {"option": option_name, "old_value": current_value, "new_value": new_value},
                )
                logger.info(f"Admin increased {option_name}: {current_value} -> {new_value}")

            except Exception as e:
                logger.error(f"Error increasing admin value: {e}", exc_info=True)

    async def handle_decrease_value(self, serial: str) -> None:
        """
        Decrease the value of the current admin option.

        Args:
            serial: Controller serial number
        """
        from proto import settings_pb2, settings_pb2_grpc

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_decrease_value", context=ctx) as span:
            span.set_attribute("controller.serial", serial)

            option_name = self.option_names[self.current_option]
            span.set_attribute("admin.option", option_name)

            try:
                stub = settings_pb2_grpc.SettingsServiceStub(self._settings_channel)

                # Get current value
                get_request = settings_pb2.GetSettingRequest(key=option_name)
                get_response = await stub.GetSetting(get_request)
                current_value = get_response.value

                # Calculate new value based on option type
                if option_name == "num_teams":
                    # Cycle backward: 2 -> 6 -> 5 -> 4 -> 3 -> 2
                    current = int(current_value) if current_value else 2
                    # Validate range
                    if current < 2 or current > 6:
                        logger.warning(f"Invalid num_teams value {current}, resetting to 2")
                        current = 2
                    new_value = str(current - 1) if current > 2 else "6"
                elif option_name == "force_all_start":
                    # Toggle: true <-> false (same as increase)
                    if current_value not in ["true", "false"]:
                        logger.warning(f"Invalid force_all_start value {current_value}, resetting to false")
                        current_value = "false"
                    new_value = "true" if current_value == "false" else "false"
                else:
                    new_value = current_value

                # Update setting
                update_request = settings_pb2.UpdateSettingRequest(
                    key=option_name, value=new_value, source="admin_mode"
                )
                await stub.UpdateSetting(update_request)

                # Visual feedback
                await self._show_value_feedback(serial, option_name, new_value)

                span.add_event(
                    "admin_value_decreased",
                    {"option": option_name, "old_value": current_value, "new_value": new_value},
                )
                logger.info(f"Admin decreased {option_name}: {current_value} -> {new_value}")

            except Exception as e:
                logger.error(f"Error decreasing admin value: {e}", exc_info=True)

    async def _show_value_feedback(self, serial: str, option_name: str, value: str) -> None:
        """
        Show visual feedback for admin value change.

        Args:
            serial: Controller serial number
            option_name: Name of the option that changed
            value: New value
        """
        from proto import controller_manager_pb2, controller_manager_pb2_grpc

        try:
            stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

            # Determine feedback color based on option and value
            if option_name == "num_teams":
                # Color intensity based on team count (2-6)
                num = int(value)
                # Gradient from green (2 teams) to red (6 teams)
                r = int(255 * (num - 2) / 4)
                g = int(255 * (6 - num) / 4)
                color = controller_manager_pb2.RGB(r=r, g=g, b=0)
            elif option_name == "force_all_start":
                # Green for true, red for false
                if value == "true":
                    color = controller_manager_pb2.RGB(r=0, g=255, b=0)
                else:
                    color = controller_manager_pb2.RGB(r=255, g=0, b=0)
            else:
                color = controller_manager_pb2.RGB(r=255, g=255, b=255)

            # Show feedback color
            effect_request = controller_manager_pb2.PlayControllerEffectRequest(
                serial=serial,
                effect=controller_manager_pb2.ControllerEffect.EFFECT_PULSE,
                color=color,
                duration_ms=600,
                speed=6,
            )
            await stub.PlayControllerEffect(effect_request)

            # Restore white after feedback
            async def restore_white():
                await asyncio.sleep(0.7)
                if self.active and serial == self.controller_serial:
                    await self._send_base_color(serial, (255, 255, 255))

            asyncio.create_task(restore_white())

        except Exception as e:
            logger.error(f"Error showing value feedback: {e}", exc_info=True)

    def reset_on_disconnect(self, serial: str) -> None:
        """
        Reset admin mode state when the admin controller disconnects.

        Args:
            serial: Serial of the disconnected controller
        """
        if self.active and serial == self.controller_serial:
            logger.info(f"Admin controller {serial} disconnected, resetting admin mode")
            self.active = False
            self.controller_serial = None
            self.entry_time = 0

            # End span if active
            if self.session_span:
                self.session_span.set_attribute("disconnect", True)
                self.session_span.end()
                self.session_span = None
                self.session_span_context = None
