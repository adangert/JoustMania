"""
Controller Manager Constants

Centralized string constants for controller state dict keys, button names,
and other shared values to prevent typos and key mismatches across files.
"""

from enum import Enum


class ButtonKey(str, Enum):
    """
    Button state dictionary keys.

    These are the keys used in the state dict returned by backends.
    The str inheritance allows using these directly as dict keys.
    """

    # Digital buttons
    TRIGGER = "trigger_button"  # Trigger pressed (digital)
    MOVE = "move_button"  # Large Move button
    PS = "ps_button"  # PlayStation button
    CROSS = "cross"  # Cross (X) button
    CIRCLE = "circle"  # Circle (O) button
    SQUARE = "square"  # Square button
    TRIANGLE = "triangle"  # Triangle button
    SELECT = "select_button"  # Select button
    START = "start_button"  # Start button


class StateKey(str, Enum):
    """
    Controller state dictionary keys.

    These are the keys used in the state dict returned by backends.
    """

    # Identity
    SERIAL = "serial"

    # Inputs
    TRIGGER = "trigger"  # Trigger analog value (0-255)
    BATTERY = "battery"  # Battery level (0-5)
    TEMPERATURE = "temperature"  # Controller temperature

    # Motion sensors (dicts with x, y, z)
    ACCEL = "accel"  # Accelerometer data
    GYRO = "gyro"  # Gyroscope data


class AxisKey(str, Enum):
    """Keys for motion sensor axis data."""

    X = "x"
    Y = "y"
    Z = "z"


class ControllerInfoKey(str, Enum):
    """
    Keys used in tracked_controllers info dict.

    These are metadata about tracked controllers, not hardware state.
    """

    SERIAL = "serial"
    BATTERY = "battery"
    READY = "ready"
    TEAM = "team"
    MOVE_NUM = "move_num"
    CONNECTED_AT = "connected_at"
    ADDRESS = "address"
    NAME = "name"
    PAIRED = "paired"


class LobbyState(str, Enum):
    """Controller lobby states for menu feedback."""

    FLASH = "flash"  # Initial green flash
    CONNECTED = "connected"  # Connected but not ready (dim color)
    READY = "ready"  # Ready to play (bright color)
    ADMIN = "admin"  # In admin mode (white)


# Button transition tracking keys (used in _detect_button_transitions)
# These are shorter names used for internal button state tracking
class ButtonTrackingKey(str, Enum):
    """Keys used for button transition tracking (shorter names)."""

    TRIGGER = "trigger"
    MOVE = "move"
    CROSS = "cross"
    CIRCLE = "circle"
    SQUARE = "square"
    TRIANGLE = "triangle"
    PS = "ps"


# Mapping from tracking keys to state dict keys
BUTTON_TRACKING_TO_STATE = {
    ButtonTrackingKey.TRIGGER: ButtonKey.TRIGGER,
    ButtonTrackingKey.MOVE: ButtonKey.MOVE,
    ButtonTrackingKey.CROSS: ButtonKey.CROSS,
    ButtonTrackingKey.CIRCLE: ButtonKey.CIRCLE,
    ButtonTrackingKey.SQUARE: ButtonKey.SQUARE,
    ButtonTrackingKey.TRIANGLE: ButtonKey.TRIANGLE,
    ButtonTrackingKey.PS: ButtonKey.PS,
}


# Default values
DEFAULT_BATTERY = 5
DEFAULT_ACCEL = {"x": 0.0, "y": 0.0, "z": 1.0}  # At rest (1g gravity)
DEFAULT_GYRO = {"x": 0.0, "y": 0.0, "z": 0.0}  # No rotation
