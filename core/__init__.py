"""
JoustMania Core Infrastructure

Core components for controller state management and process tracking.

Note: This module exports types that have psmove dependencies.
For services that don't need psmove (like webui), import from core.types instead.
"""

# Only import controller_state if psmove is available
try:
    from .controller_state import ControllerState, ControllerStateManager

    CONTROLLER_STATE_AVAILABLE = True
except ImportError:
    CONTROLLER_STATE_AVAILABLE = False
    ControllerState = None
    ControllerStateManager = None

# Import common (has psmove dependencies)
try:
    from .common import *

    PSMOVE_AVAILABLE = True
except ImportError:
    # Fallback to types if psmove not available
    from .types import *

    PSMOVE_AVAILABLE = False

__all__ = [
    "ControllerState",
    "ControllerStateManager",
    # Re-export common types
    "Button",
    "Games",
    "Status",
    "Sensitivity",
    "Opts",
    "PSMOVE_AVAILABLE",
    "CONTROLLER_STATE_AVAILABLE",
]
