"""
Game Factory - Creates game instances based on game mode name.

Centralizes game instantiation logic with:
- Name alias resolution via Games enum (e.g., "ffa" -> Games.JoustFFA)
- Typed config parsing from StartGameConfig proto messages
- Consistent argument passing
- Clear error messages for unknown modes

Usage:
    from services.game_coordinator.game_factory import GameFactory
    from proto import game_coordinator_pb2

    config = game_coordinator_pb2.StartGameConfig(
        game_name="FFA",
        sensitivity=2,
        ffa_config=game_coordinator_pb2.FFAConfig(),
    )

    game = GameFactory.create_game(
        game_name=config.game_name,
        controller_manager_client=cm_client,
        settings_client=settings_client,
        event_publisher=publish_fn,
        audio_client=audio_client,
        game_id="game_123",
        initial_players=config.players,
        sensitivity=config.sensitivity,
        game_config=config,
    )
    await game.run()
"""

import logging
from collections.abc import Callable
from typing import Any

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


class GameFactory:
    """
    Factory for creating game instances.

    Supports all JoustMania game modes with flexible name matching
    via the Games enum. Parses typed config from StartGameConfig proto.
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
        sensitivity: int = 2,
        game_config: Any | None = None,
    ) -> BaseGameMode:
        """
        Create a game instance based on game mode name and typed config.

        Args:
            game_name: Game mode name (case-insensitive, supports aliases)
            controller_manager_client: gRPC stub for controller manager service
            settings_client: gRPC stub for settings service
            event_publisher: Callback for publishing game events
            audio_client: gRPC stub for audio service
            game_id: Unique game identifier
            initial_players: List of Player protobuf messages from StartGame RPC
            sensitivity: Sensitivity level 0-4 (from StartGameConfig)
            game_config: StartGameConfig proto message with typed game_config oneof

        Returns:
            Initialized game instance (call .run() to start)

        Raises:
            ValueError: If game mode is not recognized
        """
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
            "sensitivity": sensitivity,
        }

        # Extract mode-specific config from oneof
        mode_args = GameFactory._extract_mode_config(game_mode, game_config)

        logger.info(
            f"Creating {game_mode.pretty_name} with sensitivity={sensitivity}" + (f", {mode_args}" if mode_args else "")
        )

        return game_class(**common_args, **mode_args)

    @staticmethod
    def _extract_mode_config(game_mode: Games, config: Any | None) -> dict:
        """
        Extract mode-specific arguments from StartGameConfig oneof.

        Args:
            game_mode: Resolved Games enum value
            config: StartGameConfig proto message (may be None)

        Returns:
            Dict of mode-specific constructor arguments
        """
        if config is None:
            return {}

        # Check which oneof field is set
        which_config = config.WhichOneof("game_config")
        if which_config is None:
            return {}

        # Extract based on game mode using pattern matching
        match game_mode:
            case Games.JoustFFA | Games.Zombies | Games.Swapper:
                # These configs have no fields
                return {}

            case Games.JoustTeams if which_config == "teams_config":
                cfg = config.teams_config
                return {
                    "num_teams": cfg.num_teams if cfg.num_teams > 0 else 2,
                    "random_assignment": cfg.random_assignment,
                }

            case Games.JoustRandomTeams if which_config == "random_teams_config":
                cfg = config.random_teams_config
                return {
                    "num_teams": cfg.num_teams if cfg.num_teams > 0 else 2,
                }

            case Games.NonStop if which_config == "nonstop_config":
                cfg = config.nonstop_config
                return {
                    "time_limit_seconds": cfg.time_limit_seconds,
                }

            case Games.Tournament if which_config == "tournament_config":
                cfg = config.tournament_config
                return {
                    "invincibility_seconds": cfg.invincibility_seconds if cfg.invincibility_seconds > 0 else 4.0,
                }

            case Games.FightClub if which_config == "fight_club_config":
                cfg = config.fight_club_config
                return {
                    "invincibility_seconds": cfg.invincibility_seconds if cfg.invincibility_seconds > 0 else 4.0,
                    "min_rounds": cfg.min_rounds if cfg.min_rounds > 0 else 10,
                }

            case Games.Werewolf if which_config == "werewolf_config":
                cfg = config.werewolf_config
                return {
                    "reveal_time_seconds": cfg.reveal_time_seconds if cfg.reveal_time_seconds > 0 else 35.0,
                }

            case Games.Traitor if which_config == "traitor_config":
                cfg = config.traitor_config
                return {
                    "num_teams": cfg.num_teams,  # 0 = auto-calculate
                }

            case _:
                return {}

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
