"""
Teams Game Mode - gRPC-based implementation

Players are divided into teams and compete against other teams.
Last team standing wins.

Phase 36b: Refactored to extend TeamsGameBase, eliminating ~500 lines of duplicate code.
"""

import asyncio
import logging

from services.game_coordinator.games.base import Phase, Player
from services.game_coordinator.games.teams_base import TeamsGameBase

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

        Args:
            controllers: List of controller protobuf messages from GetReadyControllers
        """
        # Assign players to teams (round-robin)
        for idx, controller in enumerate(controllers):
            team_num = idx % self.num_teams
            team_color = self.team_colors[team_num]["rgb"]

            player = Player(serial=controller.serial, team=team_num, alive=True, color=team_color)
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

    def _get_additional_phases(self) -> list:
        """
        Return phases to execute before countdown.

        Teams mode has no additional phases - team colors are shown at game start
        (after countdown), matching original JoustMania behavior.
        """
        return []
