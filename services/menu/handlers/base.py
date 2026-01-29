"""Base handler protocol for controller state handlers."""

import time
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from services.menu.state_manager import StateManager


class ButtonDebouncer:
    """
    Utility class for debouncing button presses.

    Tracks the last press time for each button on each controller and
    filters out presses that occur too quickly (within the debounce interval).
    """

    def __init__(self, default_interval: float = 0.1):
        """
        Initialize the debouncer.

        Args:
            default_interval: Default debounce interval in seconds (default 100ms)
        """
        self._last_press: dict[str, dict[str, float]] = {}
        self.default_interval = default_interval

    def should_process(self, serial: str, button: str, interval: float | None = None) -> bool:
        """
        Check if a button press should be processed.

        Args:
            serial: Controller serial number
            button: Button name
            interval: Optional override for debounce interval

        Returns:
            True if the button press should be processed, False if debounced
        """
        interval = interval if interval is not None else self.default_interval
        current_time = time.time()

        if serial not in self._last_press:
            self._last_press[serial] = {}

        last_press = self._last_press[serial].get(button, 0)
        if current_time - last_press < interval:
            return False

        self._last_press[serial][button] = current_time
        return True

    def clear(self, serial: str | None = None) -> None:
        """
        Clear debounce state.

        Args:
            serial: If provided, clear only for this controller.
                   If None, clear all state.
        """
        if serial is None:
            self._last_press.clear()
        else:
            self._last_press.pop(serial, None)


class ControllerState(Enum):
    """Controller states in the menu."""

    CONNECTED = "connected"  # Connected but not ready (dim LED)
    READY = "ready"  # Ready to play (bright LED)
    ADMIN = "admin"  # In admin mode (white LED)


class ControllerHandler(Protocol):
    """
    Protocol for controller state handlers.

    Each handler processes button events for controllers in a specific state.
    """

    @property
    def state(self) -> ControllerState:
        """The state this handler manages."""
        ...

    async def handle_button(self, serial: str, button: str) -> None:
        """
        Handle a button press event.

        Args:
            serial: Controller serial number
            button: Button name (trigger, move, cross, circle, square, triangle, ps, select, start)
        """
        ...

    async def on_enter(self, serial: str) -> None:
        """
        Called when a controller enters this state.

        Args:
            serial: Controller serial number
        """
        ...

    async def on_exit(self, serial: str) -> None:
        """
        Called when a controller exits this state.

        Args:
            serial: Controller serial number
        """
        ...

    def set_state_manager(self, manager: "StateManager") -> None:
        """
        Set the state manager reference for state transitions.

        Args:
            manager: StateManager instance
        """
        ...
