"""
Random Teams Game Mode - gRPC-based implementation

Players are randomly assigned to teams and compete against other teams.
Team colors are shown before the game starts so players know their teams.
Last team standing wins.

Phase 36b: Refactored to extend TeamsGameBase, eliminating ~550 lines of duplicate code.
"""

import asyncio
import logging
import random

from services.game_coordinator.games.base import Phase, Player
from services.game_coordinator.games.teams_base import TEAM_COLORS, TeamsGameBase

logger = logging.getLogger(__name__)

# Game constants
TEAM_FORMATION_DURATION = 5  # seconds - time to show team colors


class RandomTeamsGame(TeamsGameBase):
    """
    Random Teams game mode using gRPC communication.

    Players are randomly assigned to teams. Before the game starts, team colors
    are shown so players can identify their teammates. Last team standing wins.

    Phase 36b: Extends TeamsGameBase to inherit:
    - Team management (teams dict, team colors, TEAM_COLORS)
    - Hierarchical span creation (team → player)
    - Team-based win condition checking
    - Team elimination detection

    Implements Random Teams-specific behavior:
    - Random team assignment (shuffled team pool)
    - Random team colors (shuffled from TEAM_COLORS)
    - team_formation_phase before countdown (show team colors)
    """

    def __init__(
        self,
        controller_manager_client,
        settings_client,
        event_publisher,
        game_id: str = "",
        num_teams: int = 2,
    ):
        """
        Initialize Random Teams game.

        Note: Random colors are generated during player initialization,
        not in __init__, to ensure fresh randomization each game.

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events
            game_id: Unique identifier for this game instance
            num_teams: Number of teams (default 2)
        """
        # Call parent init first
        super().__init__(
            controller_manager_client=controller_manager_client,
            settings_client=settings_client,
            event_publisher=event_publisher,
            game_id=game_id,
            num_teams=num_teams,
        )

    def get_game_name(self) -> str:
        """Return game mode identifier."""
        return "Random Teams"

    def _generate_random_team_colors(self):
        """Generate random team colors (shuffled from available colors)."""
        available_colors = TEAM_COLORS.copy()
        random.shuffle(available_colors)
        self.team_colors = available_colors[: self.num_teams]

        # Update team objects with random colors
        for i in range(self.num_teams):
            self.teams[i].name = self.team_colors[i]["name"]
            self.teams[i].color = self.team_colors[i]["rgb"]

        logger.info(f"Generated random team colors: {[c['name'] for c in self.team_colors]}")

    def _assign_random_teams(self, player_serials: list[str]) -> dict[str, int]:
        """
        Randomly assign players to teams.

        Args:
            player_serials: List of player serial numbers

        Returns:
            Dictionary mapping serial to team number
        """
        # Create a pool of team numbers
        num_players = len(player_serials)
        teams_per_player = (num_players // self.num_teams) + 1
        team_pool = list(range(self.num_teams)) * teams_per_player

        # Shuffle the pool
        random.shuffle(team_pool)

        # Assign teams
        assignments = {}
        for idx, serial in enumerate(player_serials):
            assignments[serial] = team_pool[idx]

        logger.info(f"Random team assignments: {assignments}")
        return assignments

    async def _initialize_players_impl(self, controllers: list):
        """
        Initialize players with random team assignment.

        Args:
            controllers: List of controller protobuf messages from GetReadyControllers
        """
        player_serials = [c.serial for c in controllers]

        # Generate random team colors (do this BEFORE assigning teams)
        self._generate_random_team_colors()

        # Randomly assign players to teams
        team_assignments = self._assign_random_teams(player_serials)

        # Create player objects
        for controller in controllers:
            team_num = team_assignments[controller.serial]
            team_color = self.team_colors[team_num]["rgb"]

            player = Player(serial=controller.serial, team=team_num, alive=True, color=team_color)
            self.players[controller.serial] = player
            logger.debug(
                f"Added player: {controller.serial} to team {team_num} ({self.team_colors[team_num]['name']})"
            )

        logger.info(
            f"Initialized {len(self.players)} players across {self.num_teams} teams (random assignment)"
        )

        # Publish event with team assignments
        self.event_publisher(
            "players_initialized",
            {
                "player_count": len(self.players),
                "num_teams": self.num_teams,
                "team_assignments": str(team_assignments),
                "team_colors": str([c["name"] for c in self.team_colors]),
                "serials": list(self.players.keys()),
            },
        )

    async def _team_formation(self):
        """
        Team formation phase - show team colors to players (Phase 39 - Task 3).

        This gives players time to see who's on their team before the game starts.
        Players' controllers pulse with their team color for emphasis.
        """
        logger.info("Starting team formation phase...")

        self.event_publisher(
            "team_formation_start",
            {
                "duration": TEAM_FORMATION_DURATION,
                "team_colors": str([c["name"] for c in self.team_colors]),
            },
        )

        # Set controller colors to team colors with pulse effect (Phase 39)
        await self._set_team_colors(pulse_effect=True, duration_ms=TEAM_FORMATION_DURATION * 1000)

        # TODO: Play "teams form" audio

        # Use shorter sleeps to allow force_end to interrupt
        for _ in range(TEAM_FORMATION_DURATION * 10):
            if not self.running:
                logger.info("Team formation interrupted by force_end")
                return
            await asyncio.sleep(0.1)

        # Set persistent team colors after pulse completes
        await self._set_team_colors(pulse_effect=False, duration_ms=0)

        self.event_publisher("team_formation_end", {})
        logger.info("Team formation complete")

    def _get_additional_phases(self) -> list:
        """
        Return team_formation phase to execute before countdown.

        Returns:
            List containing TeamFormationPhase
        """
        return [Phase(name="team_formation_phase", execute=self._team_formation)]
