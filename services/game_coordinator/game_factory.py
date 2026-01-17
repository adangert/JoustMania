"""
Game Factory - Creates game instances based on game mode name.

Centralizes game instantiation logic with:
- Name alias resolution (e.g., "ffa" -> "FFA", "joust teams" -> "Teams")
- Consistent argument passing
- Clear error messages for unknown modes

Usage:
    from services.game_coordinator.game_factory import GameFactory

    game = GameFactory.create_game(
        game_name="FFA",
        controller_manager_client=cm_client,
        settings_client=settings_client,
        event_publisher=publish_fn,
        audio_client=audio_client,
        game_id="game_123",
        initial_players=players,
    )
    await game.run()
"""

import logging
from collections.abc import Callable

from services.game_coordinator.games import ffa, nonstop_joust, random_teams, swapper, teams, traitor
from services.game_coordinator.games.base import BaseGameMode

logger = logging.getLogger(__name__)


# Game mode name mappings (lowercase -> canonical name)
GAME_MODE_ALIASES: dict[str, str] = {
    # FFA (Free-for-All)
    "ffa": "ffa",
    "free-for-all": "ffa",
    "joust free-for-all": "ffa",
    "joustffa": "ffa",  # Menu service name
    # Teams
    "teams": "teams",
    "joust teams": "teams",
    "joustteams": "teams",  # Menu service name
    # Random Teams
    "random teams": "random_teams",
    "joust random teams": "random_teams",
    "random_teams": "random_teams",
    # Nonstop Joust
    "nonstop": "nonstop_joust",
    "nonstop joust": "nonstop_joust",
    "nonstopjoust": "nonstop_joust",  # Menu service name
    # Swapper
    "swapper": "swapper",
    # Traitor
    "traitor": "traitor",
}


class GameFactory:
    """
    Factory for creating game instances.

    Supports all JoustMania game modes with flexible name matching.
    """

    @staticmethod
    def create_game(
        game_name: str,
        controller_manager_client,
        settings_client,
        event_publisher: Callable[[str, dict], None],
        audio_client,
        game_id: str,
        initial_players: list,
        game_settings: dict[str, str] | None = None,
    ) -> BaseGameMode:
        """
        Create a game instance based on game mode name.

        Args:
            game_name: Game mode name (case-insensitive, supports aliases)
            controller_manager_client: gRPC stub for controller manager service
            settings_client: gRPC stub for settings service
            event_publisher: Callback for publishing game events
            audio_client: gRPC stub for audio service
            game_id: Unique game identifier
            initial_players: List of Player protobuf messages from StartGame RPC
            game_settings: Optional game-specific settings dict

        Returns:
            Initialized game instance (call .run() to start)

        Raises:
            ValueError: If game mode is not recognized
        """
        game_settings = game_settings or {}
        canonical_name = GAME_MODE_ALIASES.get(game_name.lower())

        if canonical_name is None:
            raise ValueError(f"Unknown game mode: '{game_name}'")

        # Common arguments for all game types
        common_args = {
            "controller_manager_client": controller_manager_client,
            "settings_client": settings_client,
            "event_publisher": event_publisher,
            "audio_client": audio_client,
            "game_id": game_id,
            "initial_players": initial_players,
        }

        if canonical_name == "ffa":
            logger.info("Creating FFA game")
            return ffa.FFAGame(**common_args)

        if canonical_name == "teams":
            num_teams = int(game_settings.get("num_teams", "2"))
            logger.info(f"Creating Teams game with {num_teams} teams")
            return teams.SimpleTeamsGame(num_teams=num_teams, **common_args)

        if canonical_name == "random_teams":
            num_teams = int(game_settings.get("num_teams", "2"))
            logger.info(f"Creating Random Teams game with {num_teams} teams")
            return random_teams.RandomTeamsGame(num_teams=num_teams, **common_args)

        if canonical_name == "nonstop_joust":
            logger.info("Creating Nonstop Joust game")
            return nonstop_joust.NonstopJoustGame(**common_args)

        if canonical_name == "swapper":
            logger.info("Creating Swapper game")
            return swapper.SwapperGame(**common_args)

        if canonical_name == "traitor":
            logger.info("Creating Traitor game")
            return traitor.TraitorGame(**common_args)

        # Should never reach here due to alias check above
        raise ValueError(f"Game mode '{canonical_name}' not implemented")

    @staticmethod
    def get_supported_modes() -> list[str]:
        """
        Get list of canonical game mode names.

        Returns:
            List of unique canonical mode names (e.g., ["ffa", "teams", ...])
        """
        return sorted(set(GAME_MODE_ALIASES.values()))

    @staticmethod
    def get_all_aliases() -> dict[str, str]:
        """
        Get all supported game name aliases.

        Returns:
            Dict mapping alias -> canonical name
        """
        return dict(GAME_MODE_ALIASES)

    @staticmethod
    def is_valid_mode(game_name: str) -> bool:
        """
        Check if a game mode name is valid.

        Args:
            game_name: Game mode name to check (case-insensitive)

        Returns:
            True if the name is a valid game mode or alias
        """
        return game_name.lower() in GAME_MODE_ALIASES

    @staticmethod
    def get_canonical_name(game_name: str) -> str | None:
        """
        Get the canonical name for a game mode.

        Args:
            game_name: Game mode name or alias (case-insensitive)

        Returns:
            Canonical name or None if not found
        """
        return GAME_MODE_ALIASES.get(game_name.lower())
