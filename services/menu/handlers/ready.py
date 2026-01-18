"""Handler for controllers in the ready state."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from services.menu.handlers.base import ControllerState

if TYPE_CHECKING:
    from services.menu.state_manager import StateManager

logger = logging.getLogger(__name__)


class ReadyHandler:
    """
    Handles button events for controllers in the ready state.

    Controllers in this state have pressed trigger and are ready to play.
    They have bright LED colors based on the current game mode.

    Button mappings:
    - Trigger: Start game (if all controllers are ready)
    - Move: Transition back to connected state (un-ready)
    """

    def __init__(self, start_game_callback):
        """
        Initialize ready handler.

        Args:
            start_game_callback: Async function to call when game should start.
                                Signature: async (serial: str) -> None
        """
        self._state_manager: StateManager | None = None
        self._start_game_callback = start_game_callback

        # Debounce tracking
        self._last_button_press: dict[str, dict[str, float]] = {}

    @property
    def state(self) -> ControllerState:
        """The state this handler manages."""
        return ControllerState.READY

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

        elif button == "move":
            if not self._should_process_button(serial, "move", current_time):
                return
            await self._handle_move(serial)

    async def on_enter(self, serial: str) -> None:
        """
        Called when a controller enters the ready state.

        Sets the LED to bright game mode color and checks if all are ready.
        """
        if self._state_manager is None:
            return

        # Set bright LED color
        await self._state_manager.led.set_ready_color(
            serial,
            self._state_manager.current_game_mode,
        )

        logger.info(
            f"Controller {serial} ready "
            f"({self._state_manager.get_ready_count()}/{self._state_manager.get_connected_count()})"
        )

        # Check if all ready - auto start with feedback delay
        if self._state_manager.all_ready():
            logger.info("All controllers ready - showing feedback before game start")
            # Brief delay so last player sees their LED go bright
            await asyncio.sleep(0.3)
            logger.info("Starting game after feedback delay")
            await self._start_game_callback(serial)

    async def on_exit(self, serial: str) -> None:
        """
        Called when a controller exits the ready state.
        """
        logger.debug(f"Controller {serial} exiting ready state")

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
        Handle trigger press - start game if all ready.

        Args:
            serial: Controller serial number
        """
        if self._state_manager is None:
            return

        # Check if all ready
        if self._state_manager.all_ready():
            logger.info(f"All ready, starting game via trigger from {serial}")
            await self._start_game_callback(serial)
        else:
            logger.debug(
                f"Trigger press from {serial} but not all ready "
                f"({self._state_manager.get_ready_count()}/{self._state_manager.get_connected_count()})"
            )

    async def _handle_move(self, serial: str) -> None:
        """
        Handle move press - un-ready (transition back to connected).

        Args:
            serial: Controller serial number
        """
        if self._state_manager is None:
            return

        logger.info(f"Controller {serial} un-ready via Move button")

        # Transition back to connected state
        await self._state_manager.transition_to(serial, ControllerState.CONNECTED)
