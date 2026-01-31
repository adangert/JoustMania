"""Settings utilities for the Menu service."""

import logging

import grpc.aio

from lib.types import Games

logger = logging.getLogger(__name__)


# Game modes available in the menu (from Games enum, excluding Random which is meta)
GAME_MODES: list[str] = [g.name for g in Games if g != Games.Random]

DEFAULT_GAME_MODE: Games = Games.JoustFFA
DEFAULT_VOICE_ACTOR: str = "ivy"


class SettingsHelper:
    """
    Manages settings for the Menu service.

    Provides methods for loading and saving menu-related settings.
    """

    def __init__(self, settings_channel: grpc.aio.Channel):
        """
        Initialize settings helper.

        Args:
            settings_channel: gRPC channel to Settings service
        """
        self.settings_channel = settings_channel

    async def get_setting(self, key: str) -> str | None:
        """
        Get a setting value.

        Args:
            key: Setting key

        Returns:
            Setting value or None if not found
        """
        try:
            from proto import settings_pb2, settings_pb2_grpc

            stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
            response = await stub.GetSetting(settings_pb2.GetSettingRequest(key=key))
            return response.value if response.value else None
        except Exception as e:
            logger.debug(f"Could not get setting {key}: {e}")
            return None

    async def set_setting(self, key: str, value: str, source: str = "menu") -> bool:
        """
        Set a setting value.

        Args:
            key: Setting key
            value: Setting value
            source: Source identifier for the change

        Returns:
            True if successful
        """
        try:
            from proto import settings_pb2, settings_pb2_grpc

            stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
            await stub.UpdateSetting(
                settings_pb2.UpdateSettingRequest(
                    key=key,
                    value=value,
                    source=source,
                )
            )
            logger.debug(f"Set setting {key}={value}")
            return True
        except Exception as e:
            logger.debug(f"Could not set setting {key}: {e}")
            return False

    async def load_voice_actor(self) -> str:
        """
        Load voice actor preference from settings.

        Returns:
            Voice actor name ("aaron" or "ivy")
        """
        value = await self.get_setting("menu_voice")
        if value in ("aaron", "ivy"):
            logger.info(f"Voice actor set to: {value}")
            return value
        logger.debug(f"Voice actor setting not found or invalid, using default: {DEFAULT_VOICE_ACTOR}")
        return DEFAULT_VOICE_ACTOR

    async def load_current_game(self) -> Games:
        """
        Load current game mode from settings.

        Returns:
            Games enum value
        """
        value = await self.get_setting("current_game")
        if value:
            # Try to resolve to a valid game mode
            game = Games.from_name(value)
            if game and game.name in GAME_MODES:
                logger.info(f"Loaded current game mode: {game.name}")
                return game
        logger.debug(f"Current game setting not found, using default: {DEFAULT_GAME_MODE.name}")
        return DEFAULT_GAME_MODE

    async def save_current_game(self, game_mode: Games) -> bool:
        """
        Save current game mode to settings.

        Args:
            game_mode: Games enum value

        Returns:
            True if successful
        """
        success = await self.set_setting("current_game", game_mode.name)
        if success:
            logger.debug(f"Saved current game mode: {game_mode.name}")
        return success

    def get_next_game_mode(self, current: Games, forward: bool = True) -> Games:
        """
        Get the next game mode in the cycle.

        Args:
            current: Games enum value
            forward: True to cycle forward, False to cycle backward

        Returns:
            Next Games enum value
        """
        current_name = current.name
        current_index = GAME_MODES.index(current_name) if current_name in GAME_MODES else 0

        if forward:
            next_name = GAME_MODES[(current_index + 1) % len(GAME_MODES)]
        else:
            next_name = GAME_MODES[(current_index - 1) % len(GAME_MODES)]

        # Convert back to Games enum
        return Games.from_name(next_name) or DEFAULT_GAME_MODE

    def is_valid_game_mode(self, game_mode: Games) -> bool:
        """
        Check if a game mode is valid.

        Args:
            game_mode: Games enum value

        Returns:
            True if valid
        """
        return game_mode.name in GAME_MODES
