"""
Teams Game Mode - gRPC-based implementation

Players are divided into teams and compete against other teams.
Last team standing wins.

Phase 36b: Refactored to extend TeamsGameBase, eliminating ~500 lines of duplicate code.
"""

import logging
import random
import time

from services.game_coordinator.games.analytics import PlayerAnalytics
from services.game_coordinator.games.base import Phase, Player
from services.game_coordinator.games.teams_base import TeamsGameBase
from services.game_coordinator.runtime_config import get_config_manager

logger = logging.getLogger()


class SimpleTeamsGame(TeamsGameBase):
    """
    Teams game mode using gRPC communication.

    Players are divided into teams using round-robin assignment.
    Players try to keep their controllers still while jostling opponents on other teams.
    Last team standing wins.

    Phase 36b: Extends TeamsGameBase to inherit:
    - Team management (teams dict, team colors, TEAM_COLORS)
    - Hierarchical span creation (team → player)
    - Team-based win condition checking
    - Team elimination detection

    Implements Teams-specific behavior:
    - Round-robin team assignment (player 0→team 0, player 1→team 1, player 2→team 0, etc.)
    - No additional phases (no team_formation phase)
    """

    def get_game_name(self) -> str:
        """Return game mode identifier."""
        return "Teams"

    async def _initialize_players_impl(self, controllers: list):
        """
        Initialize players with round-robin team assignment.

        Uses random_teams setting:
        - True: Randomize player order before round-robin assignment
        - False: Sequential assignment based on controller order

        Args:
            controllers: List of controller protobuf messages from GetReadyControllers
        """
        config = get_config_manager().get_config()
        game_start_time = time.time()

        # Create a list for assignment (optionally randomized)
        controller_list = list(controllers)
        if self.random_teams:
            random.shuffle(controller_list)
            logger.info("Using randomized team assignment")
        else:
            logger.info("Using sequential team assignment")

        # Assign players to teams (round-robin)
        for idx, controller in enumerate(controller_list):
            team_num = idx % self.num_teams

            # Initialize analytics if enabled
            analytics = None
            if config.analytics.enabled:
                analytics = PlayerAnalytics(
                    serial=controller.serial,
                    game_start_time=game_start_time,
                )

            player = Player(
                serial=controller.serial,
                team=team_num,
                alive=True,
                color=(255, 255, 255),  # Default white, assigned in color_assignment phase
                analytics=analytics,
            )
            self.players[controller.serial] = player
            logger.debug(f"Added player: {controller.serial} to team {team_num}")

        logger.info(f"Initialized {len(self.players)} players across {self.num_teams} teams")

        # Publish event with team assignments
        team_assignments = {serial: player.team for serial, player in self.players.items()}

        self.event_publisher(
            "players_initialized",
            {
                "player_count": len(self.players),
                "num_teams": self.num_teams,
                "team_assignments": str(team_assignments),
                "serials": list(self.players.keys()),
            },
        )

    async def _assign_team_colors(self):
        """
        Assign team colors to each player.

        Colors are assigned to player objects but NOT displayed yet.
        Players see their colors when the game starts (after countdown).
        """
        logger.info("Assigning team colors...")

        try:
            for _serial, player in self.players.items():
                team_color = self.team_colors[player.team]["rgb"]
                player.color = team_color

            logger.info(f"Assigned team colors to {len(self.players)} players")

        except Exception as e:
            logger.error(f"Failed to assign colors: {e}", exc_info=True)

    def _get_additional_phases(self) -> list:
        """
        Return phases to execute before countdown.

        Teams mode assigns team colors silently - players see them at game start
        (after countdown).
        """
        return [Phase(name="color_assignment", execute=self._assign_team_colors)]
