"""Handler for controllers in the connected (not ready) state."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from services.menu.handlers.base import ControllerState

if TYPE_CHECKING:
    from services.menu.state_manager import StateManager

logger = logging.getLogger(__name__)


class ConnectedHandler:
    """
    Handles button events for controllers in the connected state.

    Controllers in this state are connected but haven't pressed trigger to ready up.
    They have dim LED colors based on the current game mode.

    Button mappings:
    - Trigger: Transition to ready state
    - Select: Cycle game modes
    """

    def __init__(self):
        """Initialize connected handler."""
        self._state_manager: StateManager | None = None

        # Debounce tracking
        self._last_button_press: dict[str, dict[str, float]] = {}

    @property
    def state(self) -> ControllerState:
        """The state this handler manages."""
        return ControllerState.CONNECTED

    def set_state_manager(self, manager: StateManager) -> None:
        """Set the state manager reference."""
        self._state_manager = manager

    async def handle_button(self, serial: str, button: str) -> None:
        """
        Handle a button press event.

        Args:
            serial: Controller serial number
            button: Button name
        """
        if self._state_manager is None:
            logger.error("StateManager not set")
            return

        current_time = time.time()

        if button == "trigger":
            if not self._should_process_button(serial, "trigger", current_time):
                return
            await self._handle_trigger(serial)

        elif button == "select":
            if not self._should_process_button(serial, "select", current_time):
                return
            await self._handle_select(serial)

    async def on_enter(self, serial: str) -> None:
        """
        Called when a controller enters the connected state.

        Sets the LED to dim game mode color.
        """
        if self._state_manager is None:
            return

        await self._state_manager.led.set_connected_color(
            serial,
            self._state_manager.current_game_mode,
        )
        logger.debug(f"Controller {serial} entered connected state")

    async def on_exit(self, serial: str) -> None:
        """
        Called when a controller exits the connected state.
        """
        logger.debug(f"Controller {serial} exiting connected state")

    def _should_process_button(self, serial: str, button: str, current_time: float) -> bool:
        """
        Check if button press should be processed (debouncing).

        Args:
            serial: Controller serial number
            button: Button name
            current_time: Current timestamp

        Returns:
            True if button press should be processed
        """
        if serial not in self._last_button_press:
            self._last_button_press[serial] = {}

        last_press = self._last_button_press[serial].get(button, 0)
        if current_time - last_press < 0.1:  # 100ms debounce
            return False

        self._last_button_press[serial][button] = current_time
        return True

    async def _handle_trigger(self, serial: str) -> None:
        """
        Handle trigger press - transition to ready state.

        Args:
            serial: Controller serial number
        """
        if self._state_manager is None:
            return

        logger.info(f"Controller {serial} trigger press -> ready")

        # Play ready sound
        from lib.types import Sound

        await self._state_manager.audio.play_sound(Sound.SFX_BEEP_LOUD, volume=0.5)

        # Transition to ready state
        await self._state_manager.transition_to(serial, ControllerState.READY)

    async def _handle_select(self, serial: str) -> None:
        """
        Handle select button press - cycle game modes.

        Args:
            serial: Controller serial number
        """
        if self._state_manager is None:
            return

        # Cycle to next game mode
        next_mode = self._state_manager.settings.get_next_game_mode(
            self._state_manager.current_game_mode,
            forward=True,
        )
        self._state_manager.set_game_mode(next_mode)

        # Save setting
        await self._state_manager.settings.save_current_game(next_mode)

        # Publish event
        await self._state_manager.publish_event(
            "selection_changed",
            {"game_name": next_mode, "source": "controller", "serial": serial},
        )

        # Play voice announcement
        await self._state_manager.audio.play_game_mode_voice(next_mode)

        logger.info(f"Controller {serial} select button -> game mode: {next_mode}")
