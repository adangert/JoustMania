"""
Standardized error messages and constants for JoustMania services (Phase 33).

Provides consistent error messages across all services to improve
error handling and user experience.
"""

from enum import Enum


class ServiceError(Enum):
    """Common service-level errors."""

    ALREADY_RUNNING = "Service is already running"
    ALREADY_STOPPED = "Service is already stopped"
    NOT_INITIALIZED = "Service not initialized"
    INITIALIZATION_FAILED = "Service initialization failed"
    SERVICE_UNAVAILABLE = "Service temporarily unavailable"
    INTERNAL_ERROR = "Internal service error"


class GameError(Enum):
    """Game-specific errors."""

    GAME_ALREADY_RUNNING = "Game is already running"
    GAME_NOT_RUNNING = "No game is currently running"
    GAME_START_FAILED = "Failed to start game"
    GAME_STOP_FAILED = "Failed to stop game"
    INVALID_GAME_MODE = "Invalid game mode specified"
    NOT_ENOUGH_PLAYERS = "Not enough players to start game"
    TOO_MANY_PLAYERS = "Too many players for this game mode"


class ControllerError(Enum):
    """Controller-specific errors."""

    CONTROLLER_NOT_FOUND = "Controller not found"
    CONTROLLER_DISCONNECTED = "Controller disconnected"
    CONTROLLER_ALREADY_REGISTERED = "Controller already registered"
    INVALID_CONTROLLER_SERIAL = "Invalid controller serial number"
    PAIRING_FAILED = "Controller pairing failed"
    NO_CONTROLLERS_AVAILABLE = "No controllers available"


class InputError(Enum):
    """Input validation errors."""

    INVALID_INPUT = "Invalid input provided"
    MISSING_REQUIRED_FIELD = "Missing required field"
    INVALID_BUTTON_NAME = "Invalid button name"
    INVALID_COLOR = "Invalid color value"
    INVALID_RANGE = "Value out of valid range"
    INVALID_TYPE = "Invalid data type"


class SettingsError(Enum):
    """Settings-specific errors."""

    SETTING_NOT_FOUND = "Setting not found"
    INVALID_SETTING_VALUE = "Invalid setting value"
    SETTING_IMMUTABLE = "Setting cannot be changed"
    SETTING_VALIDATION_FAILED = "Setting validation failed"
    SETTINGS_LOAD_FAILED = "Failed to load settings"
    SETTINGS_SAVE_FAILED = "Failed to save settings"


class MenuError(Enum):
    """Menu-specific errors."""

    MENU_NOT_RUNNING = "Menu is not running"
    MENU_ALREADY_RUNNING = "Menu is already running"
    INVALID_SELECTION = "Invalid menu selection"
    NO_GAME_SELECTED = "No game selected"


class AudioError(Enum):
    """Audio-specific errors."""

    AUDIO_FILE_NOT_FOUND = "Audio file not found"
    AUDIO_PLAYBACK_FAILED = "Audio playback failed"
    AUDIO_SERVICE_UNAVAILABLE = "Audio service unavailable"


# Validation constants
VALID_BUTTONS = {"trigger", "move", "cross", "circle", "square", "triangle", "ps"}

VALID_GAME_MODES = {
    "JoustFFA",
    "JoustTeams",
    "JoustRandomTeams",
    "Werewolf",
    "Nonstop",
}


def format_error(error: Enum, **context) -> str:
    """
    Format an error message with optional context.

    Args:
        error: Error enum value
        **context: Additional context to include in error message

    Returns:
        Formatted error message

    Example:
        >>> format_error(ControllerError.CONTROLLER_NOT_FOUND, serial="00:11:22:33")
        'Controller not found: serial=00:11:22:33'
    """
    base_message = error.value
    if context:
        context_str = ", ".join(f"{k}={v}" for k, v in context.items())
        return f"{base_message}: {context_str}"
    return base_message


def validate_button_name(button: str) -> tuple[bool, str]:
    """
    Validate button name.

    Args:
        button: Button name to validate

    Returns:
        Tuple of (is_valid, error_message)

    Example:
        >>> validate_button_name("trigger")
        (True, "")
        >>> validate_button_name("invalid")
        (False, "Invalid button name: button=invalid")
    """
    if button in VALID_BUTTONS:
        return True, ""
    return False, format_error(InputError.INVALID_BUTTON_NAME, button=button)


def validate_game_mode(game_mode: str) -> tuple[bool, str]:
    """
    Validate game mode name.

    Args:
        game_mode: Game mode name to validate

    Returns:
        Tuple of (is_valid, error_message)

    Example:
        >>> validate_game_mode("JoustFFA")
        (True, "")
        >>> validate_game_mode("InvalidMode")
        (False, "Invalid game mode specified: mode=InvalidMode")
    """
    if game_mode in VALID_GAME_MODES:
        return True, ""
    return False, format_error(GameError.INVALID_GAME_MODE, mode=game_mode)


def validate_range(value: int, min_val: int, max_val: int, name: str = "value") -> tuple[bool, str]:
    """
    Validate that a value is within a valid range.

    Args:
        value: Value to validate
        min_val: Minimum valid value (inclusive)
        max_val: Maximum valid value (inclusive)
        name: Name of the value for error message

    Returns:
        Tuple of (is_valid, error_message)

    Example:
        >>> validate_range(5, 0, 10, "sensitivity")
        (True, "")
        >>> validate_range(15, 0, 10, "sensitivity")
        (False, "Value out of valid range: sensitivity=15, min=0, max=10")
    """
    if min_val <= value <= max_val:
        return True, ""
    return False, format_error(
        InputError.INVALID_RANGE,
        **{name: value, "min": min_val, "max": max_val}
    )
