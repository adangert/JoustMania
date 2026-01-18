"""
Admin mode handler for Menu service.

Manages the admin mode state, commands, and visual feedback when a controller
holds the admin combo (Move + Trigger + PS for 3 seconds).

Admin mode allows changing settings like:
- Sensitivity level (Circle button)
- Battery display (Triangle button)
- Instructions toggle (Square button)
- Game mode selection (L1/R1 or Cross for backward)
- Force start game (Trigger hold for 2 seconds)
- Cycle options / adjust values (Move button / Trigger / Cross)
"""

import asyncio
import logging
import time
from typing import Protocol

from opentelemetry import trace

from lib.types import Sound

logger = logging.getLogger(__name__)


class AdminModeCallbacks(Protocol):
    """Protocol defining callbacks that AdminModeHandler needs from Menu."""

    async def play_voice(self, sound: Sound) -> None:
        """Play a voice announcement."""
        ...

    async def send_game_effect(self, serial: str, effect: int) -> bool:
        """Send a game effect to a controller."""
        ...

    async def send_base_color(self, serial: str, color: tuple[int, int, int]) -> bool:
        """Send a base color to a controller."""
        ...

    async def publish_event(self, event_type: str, data: dict) -> None:
        """Publish an event to subscribers."""
        ...

    def get_current_selection(self) -> str:
        """Get the currently selected game mode."""
        ...

    def get_connected_controllers(self) -> set[str]:
        """Get set of connected controller serials."""
        ...

    def get_ready_controllers(self) -> set[str]:
        """Get set of ready controller serials."""
        ...

    def set_menu_state(self, state) -> None:
        """Set the menu state (for game starting)."""
        ...

    def get_game_options(self) -> list[str]:
        """Get list of available game options."""
        ...


class AdminModeHandler:
    """
    Handles admin mode state and commands.

    Admin mode is activated by holding Move + Trigger + PS for 3 seconds.
    While active, face buttons perform administrative actions.
    """

    def __init__(
        self,
        controller_channel,
        settings_channel,
        tracer: trace.Tracer,
        callbacks: AdminModeCallbacks,
        metrics,
    ):
        """
        Initialize the admin mode handler.

        Args:
            controller_channel: gRPC channel to Controller Manager service
            settings_channel: gRPC channel to Settings service
            tracer: OpenTelemetry tracer for span creation
            callbacks: Callbacks to Menu service methods
            metrics: Prometheus metrics module
        """
        self.controller_channel = controller_channel
        self.settings_channel = settings_channel
        self.tracer = tracer
        self.callbacks = callbacks
        self.metrics = metrics

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
            True if Move + Trigger + PS are all pressed
        """
        return button_state.get("move", False) and button_state.get("trigger", False) and button_state.get("ps", False)

    def check_combo_from_controller(self, controller) -> bool:
        """
        Check if admin combo is being held based on controller object.

        Args:
            controller: Controller protobuf message with button fields

        Returns:
            True if Move + Trigger + PS are all pressed
        """
        return controller.move_pressed and controller.trigger_pressed and controller.ps_pressed

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
        from proto import controller_manager_pb2, controller_manager_pb2_grpc

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

            # Try bidirectional stream first (Phase XX)
            if await self.callbacks.send_game_effect(serial, controller_manager_pb2.GAME_EFFECT_ADMIN_ENTER):
                logger.info(f"Admin mode entered by controller {serial} (via stream)")
                span.add_event("admin_mode_entered")
            else:
                # Fallback to unary RPC
                try:
                    stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)
                    effect_request = controller_manager_pb2.PlayControllerEffectRequest(
                        serial=serial,
                        effect=controller_manager_pb2.ControllerEffect.EFFECT_PULSE,
                        color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                        duration_ms=500,
                        speed=8,
                    )
                    await stub.PlayControllerEffect(effect_request)

                    # Set to persistent white for admin mode
                    color_request = controller_manager_pb2.SetControllerColorRequest(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                        duration_ms=0,
                    )
                    await stub.SetControllerColor(color_request)

                    logger.info(f"Admin mode entered by controller {serial} (via unary)")
                    span.add_event("admin_mode_entered")

                except Exception as e:
                    logger.error(f"Failed to signal admin mode entry: {e}")

    async def exit(self) -> None:
        """
        Exit admin mode and restore lobby color.

        Ends the admin_mode_session parent span.
        """
        if not self.active:
            return

        from proto import controller_manager_pb2, controller_manager_pb2_grpc

        duration = time.time() - self.entry_time

        # Create child span for exit operation (under admin_mode_session)
        with self.tracer.start_as_current_span("exit_admin_mode", context=self.session_span_context) as span:
            span.set_attribute("controller.serial", self.controller_serial)
            span.set_attribute("duration_seconds", duration)

            logger.info(f"Admin mode exited by controller {self.controller_serial}")

            # Send exit effect via stream
            serial = self.controller_serial
            if await self.callbacks.send_game_effect(serial, controller_manager_pb2.GAME_EFFECT_ADMIN_EXIT):
                logger.debug(f"Admin exit effect sent via stream for {serial}")
            else:
                # Fallback to unary RPC
                try:
                    stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                    # Flash effect for exit
                    effect_request = controller_manager_pb2.PlayControllerEffectRequest(
                        serial=serial,
                        effect=controller_manager_pb2.ControllerEffect.EFFECT_FLASH,
                        color=controller_manager_pb2.RGB(r=0, g=255, b=0),
                        duration_ms=300,
                        speed=10,
                    )
                    await stub.PlayControllerEffect(effect_request)

                    # Restore dim lobby color
                    await asyncio.sleep(0.4)
                    color_request = controller_manager_pb2.SetControllerColorRequest(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=40, g=40, b=40),
                        duration_ms=0,
                    )
                    await stub.SetControllerColor(color_request)

                except Exception as e:
                    logger.error(f"Failed to restore lobby color: {e}")

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
            await self.exit()
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
                current_selection = self.callbacks.get_current_selection()

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
                await self.callbacks.publish_event(
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
                        try:
                            white_request = controller_manager_pb2.SetControllerColorRequest(
                                serial=serial,
                                color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                                duration_ms=0,
                            )
                            await stub.SetControllerColor(white_request)
                        except Exception:
                            pass

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
            span.set_attribute("game.name", self.callbacks.get_current_selection())

            try:
                # Check force_all_start setting
                settings_stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
                force_all_response = await settings_stub.GetSetting(
                    settings_pb2.GetSettingRequest(key="force_all_start")
                )
                force_all = force_all_response.value == "true"
                span.set_attribute("force_all_start", force_all)

                # Determine which controllers to include
                if force_all:
                    # Use all connected controllers
                    controllers = list(self.callbacks.get_connected_controllers())
                else:
                    # Use ready controllers, but include admin if not already ready
                    controllers = list(self.callbacks.get_ready_controllers())
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
                await self.callbacks.publish_event(
                    "game_requested",
                    {
                        "game_name": self.callbacks.get_current_selection(),
                        "source": "admin_force_start",
                        "serial": serial,
                        "controllers": controllers,
                    },
                )

                span.add_event(
                    "force_start_triggered",
                    {
                        "game": self.callbacks.get_current_selection(),
                        "player_count": len(controllers),
                    },
                )
                logger.info(
                    f"Force starting game '{self.callbacks.get_current_selection()}' via admin controller {serial} "
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
            if await self.callbacks.send_game_effect(serial, controller_manager_pb2.GAME_EFFECT_FORCE_START_CHARGE):
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
            if await self.callbacks.send_base_color(serial, (255, 255, 255)):
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
                settings_stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)

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

                # Play voice announcement for sensitivity level
                sensitivity_sounds = [
                    Sound.MENU_VOX_ULTRA_SLOW,
                    Sound.MENU_VOX_SLOW,
                    Sound.MENU_VOX_MEDIUM,
                    Sound.MENU_VOX_FAST,
                    Sound.MENU_VOX_ULTRA_FAST,
                ]
                await self.callbacks.play_voice(sensitivity_sounds[int(new_value)])

                # Restore white after feedback
                async def restore_white():
                    await asyncio.sleep(1.0)
                    if self.active and serial == self.controller_serial:
                        try:
                            white_request = controller_manager_pb2.SetControllerColorRequest(
                                serial=serial,
                                color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                                duration_ms=0,
                            )
                            await controller_stub.SetControllerColor(white_request)
                        except Exception as e:
                            logger.debug(f"Could not restore white LED: {e}")

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
        Handle battery display in admin mode.

        Shows battery level via LED color:
        - Green: >66%
        - Yellow: 33-66%
        - Red: <33%

        Args:
            serial: Controller serial number
        """
        from proto import controller_manager_pb2, controller_manager_pb2_grpc

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_battery", context=ctx) as span:
            span.set_attribute("controller.serial", serial)

            try:
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                # Get all controllers to show battery levels
                controllers_request = controller_manager_pb2.GetControllersRequest()
                controllers_response = await stub.GetControllers(controllers_request)

                # Show battery for each controller
                for ctrl in controllers_response.controllers:
                    battery_percent = ctrl.battery

                    # Determine color based on battery level
                    if battery_percent > 66:
                        color = controller_manager_pb2.RGB(r=0, g=255, b=0)  # Green
                    elif battery_percent > 33:
                        color = controller_manager_pb2.RGB(r=255, g=255, b=0)  # Yellow
                    else:
                        color = controller_manager_pb2.RGB(r=255, g=0, b=0)  # Red

                    # Show battery color for 2 seconds
                    color_request = controller_manager_pb2.SetControllerColorRequest(
                        serial=ctrl.serial, color=color, duration_ms=2000
                    )
                    await stub.SetControllerColor(color_request)

                    span.add_event(
                        "battery_displayed",
                        {"controller.serial": ctrl.serial, "battery.percent": battery_percent},
                    )

                logger.info(f"Battery levels displayed by admin controller {serial}")

            except Exception as e:
                logger.error(f"Error displaying battery: {e}", exc_info=True)

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
                settings_stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)

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
                await self.callbacks.play_voice(voice)

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
        from proto import controller_manager_pb2, controller_manager_pb2_grpc

        ctx = self._get_span_context()
        with self.tracer.start_as_current_span("admin_cycle_option", context=ctx) as span:
            span.set_attribute("controller.serial", serial)

            # Cycle to next option
            self.current_option = (self.current_option + 1) % len(self.option_names)
            option_name = self.option_names[self.current_option]
            option_color = self.option_colors[self.current_option]

            span.set_attribute("admin.option", option_name)

            try:
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                # Show option color for 1 second
                color_request = controller_manager_pb2.SetControllerColorRequest(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=option_color[0], g=option_color[1], b=option_color[2]),
                    duration_ms=1000,
                )
                await stub.SetControllerColor(color_request)

                # Restore white after option color finishes
                async def restore_white():
                    await asyncio.sleep(1.1)
                    if self.active and serial == self.controller_serial:
                        try:
                            white_request = controller_manager_pb2.SetControllerColorRequest(
                                serial=serial,
                                color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                                duration_ms=0,
                            )
                            await stub.SetControllerColor(white_request)
                        except Exception as e:
                            logger.debug(f"Could not restore white LED: {e}")

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
                stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)

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
                stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)

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
                    try:
                        white_request = controller_manager_pb2.SetControllerColorRequest(
                            serial=serial,
                            color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                            duration_ms=0,
                        )
                        await stub.SetControllerColor(white_request)
                    except Exception as e:
                        logger.debug(f"Could not restore white LED: {e}")

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
