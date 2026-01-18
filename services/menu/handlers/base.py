"""Base handler protocol for controller state handlers."""

from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from services.menu.state_manager import StateManager


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
