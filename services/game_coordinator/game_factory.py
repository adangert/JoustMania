"""
Game Factory - Creates game instances based on game mode name.

Centralizes game instantiation logic with:
- Name alias resolution via Games enum (e.g., "ffa" -> Games.JoustFFA)
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

from lib.types import Games
from services.game_coordinator.games import (
    ffa,
    fight_club,
    nonstop_joust,
    random_teams,
    swapper,
    teams,
    tournament,
    traitor,
    werewolf,
    zombie,
)
from services.game_coordinator.games.base import BaseGameMode

logger = logging.getLogger(__name__)


# Mapping from Games enum to game class
_GAME_CLASSES: dict[Games, type[BaseGameMode]] = {
    Games.JoustFFA: ffa.FFAGame,
    Games.JoustTeams: teams.SimpleTeamsGame,
    Games.JoustRandomTeams: random_teams.RandomTeamsGame,
    Games.Traitor: traitor.TraitorGame,
    Games.Werewolf: werewolf.WerewolfGame,
    Games.Zombies: zombie.ZombieGame,
    Games.Swapper: swapper.SwapperGame,
    Games.FightClub: fight_club.FightClubGame,
    Games.Tournament: tournament.TournamentGame,
    Games.NonStop: nonstop_joust.NonstopJoustGame,
}

# Games that support num_teams setting
_TEAM_GAMES: set[Games] = {Games.JoustTeams, Games.JoustRandomTeams}


class GameFactory:
    """
    Factory for creating game instances.

    Supports all JoustMania game modes with flexible name matching
    via the Games enum.
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

        # Resolve name to Games enum
        game_mode = Games.from_name(game_name)
        if game_mode is None:
            raise ValueError(f"Unknown game mode: '{game_name}'")

        # Check if game mode is implemented
        game_class = _GAME_CLASSES.get(game_mode)
        if game_class is None:
            raise ValueError(f"Game mode '{game_mode.name}' not implemented")

        # Common arguments for all game types
        common_args = {
            "controller_manager_client": controller_manager_client,
            "settings_client": settings_client,
            "event_publisher": event_publisher,
            "audio_client": audio_client,
            "game_id": game_id,
            "initial_players": initial_players,
        }

        # Handle team games with num_teams setting
        if game_mode in _TEAM_GAMES:
            num_teams = int(game_settings.get("num_teams", "2"))
            logger.info(f"Creating {game_mode.pretty_name} with {num_teams} teams")
            return game_class(num_teams=num_teams, **common_args)

        logger.info(f"Creating {game_mode.pretty_name}")
        return game_class(**common_args)

    @staticmethod
    def get_supported_modes() -> list[str]:
        """
        Get list of supported game mode names.

        Returns:
            List of Games enum member names that are implemented
        """
        return [game.name for game in _GAME_CLASSES]

    @staticmethod
    def is_valid_mode(game_name: str) -> bool:
        """
        Check if a game mode name is valid and implemented.

        Args:
            game_name: Game mode name to check (case-insensitive, supports aliases)

        Returns:
            True if the name resolves to an implemented game mode
        """
        game_mode = Games.from_name(game_name)
        return game_mode is not None and game_mode in _GAME_CLASSES

    @staticmethod
    def get_game_mode(game_name: str) -> Games | None:
        """
        Resolve a game name to its Games enum member.

        Args:
            game_name: Game mode name or alias (case-insensitive)

        Returns:
            Games enum member or None if not found
        """
        return Games.from_name(game_name)
