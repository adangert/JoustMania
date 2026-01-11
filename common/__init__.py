"""
Common utilities shared across JoustMania services (Phase 33).
"""

from .grpc_utils import (
    get_optimized_channel_options,
    create_channel,
    create_channel_with_custom_options,
)
from .errors import (
    ServiceError,
    GameError,
    ControllerError,
    InputError,
    SettingsError,
    MenuError,
    AudioError,
    VALID_BUTTONS,
    VALID_GAME_MODES,
    format_error,
    validate_button_name,
    validate_game_mode,
    validate_range,
)

__all__ = [
    # gRPC utilities
    "get_optimized_channel_options",
    "create_channel",
    "create_channel_with_custom_options",
    # Error constants
    "ServiceError",
    "GameError",
    "ControllerError",
    "InputError",
    "SettingsError",
    "MenuError",
    "AudioError",
    "VALID_BUTTONS",
    "VALID_GAME_MODES",
    # Error utilities
    "format_error",
    "validate_button_name",
    "validate_game_mode",
    "validate_range",
]
