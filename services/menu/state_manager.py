"""Controller state manager for the Menu service."""

import logging
from collections.abc import Callable, Coroutine

from lib.controller_constants import ButtonTrackingKey
from services.menu import metrics
from services.menu.handlers.base import ControllerHandler, ControllerState
from services.menu.utils import AudioHelper, LedController, SettingsHelper

logger = logging.getLogger(__name__)


class StateManager:
    """
    Central coordinator for controller states in the menu.

    Tracks which state each controller is in and dispatches button events
    to the appropriate handler. Manages state transitions with proper
    callbacks to handlers.
    """

    def __init__(
        self,
        led: LedController,
        audio: AudioHelper,
        settings: SettingsHelper,
        publish_event: Callable[[str, dict], Coroutine],
    ):
        """
        Initialize state manager.

        Args:
            led: LED controller utility
            audio: Audio helper utility
            settings: Settings helper utility
            publish_event: Async function to publish events
        """
        self.led = led
        self.audio = audio
        self.settings = settings
        self.publish_event = publish_event

        # Controller state tracking - single source of truth
        # Keys = connected controllers, values = their current state
        self.controller_states: dict[str, ControllerState] = {}

        # Battery level tracking (0-5 scale, updated from button events)
        self.battery_levels: dict[str, int] = {}

        # Button state tracking (for combo detection)
        self.button_states: dict[str, dict[str, bool]] = {}

        # Handlers for each state
        self._handlers: dict[ControllerState, ControllerHandler] = {}

        # Current game mode (for LED colors)
        self.current_game_mode: str = "JoustFFA"

    @property
    def connected_controllers(self) -> set[str]:
        """All connected controller serials (computed from controller_states)."""
        return set(self.controller_states.keys())

    @property
    def ready_controllers(self) -> set[str]:
        """Controller serials in READY state (computed from controller_states)."""
        return {serial for serial, state in self.controller_states.items() if state == ControllerState.READY}

    def register_handler(self, handler: ControllerHandler) -> None:
        """
        Register a handler for a controller state.

        Args:
            handler: Handler instance implementing ControllerHandler protocol
        """
        handler.set_state_manager(self)
        self._handlers[handler.state] = handler
        logger.debug(f"Registered handler for state: {handler.state.value}")

    def get_handler(self, state: ControllerState) -> ControllerHandler | None:
        """
        Get the handler for a state.

        Args:
            state: Controller state

        Returns:
            Handler instance or None if not registered
        """
        return self._handlers.get(state)

    def get_controller_state(self, serial: str) -> ControllerState:
        """
        Get the current state of a controller.

        Args:
            serial: Controller serial number

        Returns:
            Current state (defaults to CONNECTED for unknown controllers)
        """
        return self.controller_states.get(serial, ControllerState.CONNECTED)

    async def handle_button_event(self, serial: str, button: str, is_press: bool) -> None:
        """
        Handle a button event for a controller.

        Dispatches to the appropriate handler based on current state.

        Args:
            serial: Controller serial number
            button: Button name
            is_press: True if press, False if release
        """
        # Track controller as connected
        if serial not in self.connected_controllers:
            await self.on_controller_connected(serial)

        # Update button state
        if serial not in self.button_states:
            self.button_states[serial] = {
                "trigger": False,
                "move": False,
                "cross": False,
                "circle": False,
                "square": False,
                "triangle": False,
                "ps": False,
                "select": False,
                "start": False,
            }
        self.button_states[serial][button] = is_press

        # Handle release events - forward trigger releases in admin mode
        if not is_press:
            if button == ButtonTrackingKey.TRIGGER:
                state = self.get_controller_state(serial)
                if state == ControllerState.ADMIN:
                    handler = self._handlers.get(state)
                    if handler and hasattr(handler, "handle_trigger_release"):
                        await handler.handle_trigger_release(serial)
            return

        # Dispatch to appropriate handler
        # Note: Admin mode is handled externally by AdminModeHandler
        state = self.get_controller_state(serial)
        handler = self._handlers.get(state)
        if handler:
            await handler.handle_button(serial, button)
        else:
            logger.warning(f"No handler for state {state.value}")

    async def transition_to(self, serial: str, new_state: ControllerState) -> None:
        """
        Transition a controller to a new state.

        Calls on_exit on old handler and on_enter on new handler.

        Args:
            serial: Controller serial number
            new_state: State to transition to
        """
        old_state = self.controller_states.get(serial, ControllerState.CONNECTED)

        if old_state == new_state:
            return

        # Call exit handler
        old_handler = self._handlers.get(old_state)
        if old_handler:
            await old_handler.on_exit(serial)

        # Update state
        self.controller_states[serial] = new_state

        # Emit metrics for ready state changes
        if new_state == ControllerState.READY:
            metrics.player_ready.labels(serial=serial).set(1)
        elif old_state == ControllerState.READY:
            # Only set to 0 if transitioning FROM ready
            metrics.player_ready.labels(serial=serial).set(0)

        # Call enter handler
        new_handler = self._handlers.get(new_state)
        if new_handler:
            await new_handler.on_enter(serial)

        logger.info(f"Controller {serial} transitioned: {old_state.value} -> {new_state.value}")

    async def on_controller_connected(self, serial: str) -> None:
        """
        Handle a new controller connection.

        Args:
            serial: Controller serial number
        """
        self.controller_states[serial] = ControllerState.CONNECTED

        # Call enter handler for CONNECTED state
        handler = self._handlers.get(ControllerState.CONNECTED)
        if handler:
            await handler.on_enter(serial)

        logger.info(f"Controller {serial} connected")

    async def on_controller_disconnected(self, serial: str) -> None:
        """
        Handle a controller disconnection.

        Args:
            serial: Controller serial number
        """
        # Call exit handler for current state
        state = self.controller_states.get(serial, ControllerState.CONNECTED)
        handler = self._handlers.get(state)
        if handler:
            await handler.on_exit(serial)

        # Clear ready metric if player was ready
        if state == ControllerState.READY:
            metrics.player_ready.labels(serial=serial).set(0)

        # Clean up state (removing from controller_states also removes from computed properties)
        self.controller_states.pop(serial, None)
        self.button_states.pop(serial, None)
        self.battery_levels.pop(serial, None)

        logger.info(f"Controller {serial} disconnected")

    def update_battery(self, serial: str, battery: int) -> None:
        """
        Update battery level for a controller.

        Args:
            serial: Controller serial number
            battery: Battery level (0-5 scale from psmove)
        """
        self.battery_levels[serial] = battery

    def get_ready_count(self) -> int:
        """Get number of ready controllers."""
        return len(self.ready_controllers)

    def get_connected_count(self) -> int:
        """Get number of connected controllers."""
        return len(self.connected_controllers)

    def all_ready(self) -> bool:
        """Check if all connected controllers are ready (minimum 2)."""
        return len(self.ready_controllers) >= 2 and len(self.ready_controllers) == len(self.connected_controllers)

    def set_game_mode(self, game_mode: str) -> None:
        """
        Set the current game mode.

        Args:
            game_mode: Game mode name
        """
        self.current_game_mode = game_mode

    async def reset(self) -> list[str]:
        """
        Reset all controller states (e.g., after game ends).

        Re-registers all previously connected controllers, triggering on_enter
        handlers to set appropriate lobby colors.

        Returns:
            List of controller serials that were re-registered
        """
        # Remember which controllers were connected before clearing
        serials = list(self.controller_states.keys())

        # Clear all state (controller_states is the single source of truth)
        self.controller_states.clear()
        self.button_states.clear()

        # Clear all player ready metrics
        metrics.player_ready.clear()

        # Reset ready handler's game start flag (Issue #230)
        ready_handler = self._handlers.get(ControllerState.READY)
        if ready_handler and hasattr(ready_handler, "reset_game_start_flag"):
            ready_handler.reset_game_start_flag()

        # Re-register each controller as CONNECTED (triggers on_enter → sets colors)
        for serial in serials:
            await self.on_controller_connected(serial)

        logger.info(f"StateManager reset, re-registered {len(serials)} controllers")
        return serials
