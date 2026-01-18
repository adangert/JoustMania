"""Settings utilities for the Menu service."""

import logging

import grpc.aio

logger = logging.getLogger(__name__)


# Game modes available in the menu (single source of truth)
GAME_MODES: list[str] = [
    "JoustFFA",
    "JoustTeams",
    "JoustRandomTeams",
    "Swapper",
    "Werewolf",
    "Traitor",
    "Zombie",
    "Commander",
    "FightClub",
    "Tournament",
    "NonstopJoust",
    "SpeedBomb",
]

DEFAULT_GAME_MODE: str = "JoustFFA"
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

    async def load_current_game(self) -> str:
        """
        Load current game mode from settings.

        Returns:
            Game mode name
        """
        value = await self.get_setting("current_game")
        if value and value in GAME_MODES:
            logger.info(f"Loaded current game mode: {value}")
            return value
        logger.debug(f"Current game setting not found, using default: {DEFAULT_GAME_MODE}")
        return DEFAULT_GAME_MODE

    async def save_current_game(self, game_mode: str) -> bool:
        """
        Save current game mode to settings.

        Args:
            game_mode: Game mode name

        Returns:
            True if successful
        """
        success = await self.set_setting("current_game", game_mode)
        if success:
            logger.debug(f"Saved current game mode: {game_mode}")
        return success

    def get_next_game_mode(self, current: str, forward: bool = True) -> str:
        """
        Get the next game mode in the cycle.

        Args:
            current: Current game mode name
            forward: True to cycle forward, False to cycle backward

        Returns:
            Next game mode name
        """
        current_index = GAME_MODES.index(current) if current in GAME_MODES else 0

        if forward:
            return GAME_MODES[(current_index + 1) % len(GAME_MODES)]
        return GAME_MODES[(current_index - 1) % len(GAME_MODES)]

    def is_valid_game_mode(self, game_mode: str) -> bool:
        """
        Check if a game mode is valid.

        Args:
            game_mode: Game mode name

        Returns:
            True if valid
        """
        return game_mode in GAME_MODES
