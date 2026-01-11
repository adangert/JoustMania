"""
TeamsGameBase - Abstract base class for team-based game modes

Phase 36b: Extracts common team logic from Teams and Random Teams.
Provides hierarchical span management (team → player) and team-based win conditions.

Subclasses:
- SimpleTeamsGame (Teams): Round-robin team assignment
- RandomTeamsGame (Random Teams): Random team assignment with team_formation_phase
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from services.game_coordinator.games.base import BaseGameMode

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)


# Team colors (from utils/colors.py - first 8 colors)
TEAM_COLORS = [
    {"name": "Pink", "rgb": (255, 108, 108)},
    {"name": "Magenta", "rgb": (255, 0, 192)},
    {"name": "Orange", "rgb": (255, 64, 0)},
    {"name": "Yellow", "rgb": (255, 255, 0)},
    {"name": "Green", "rgb": (0, 255, 0)},
    {"name": "Turquoise", "rgb": (0, 255, 255)},
    {"name": "Blue", "rgb": (0, 0, 255)},
    {"name": "Purple", "rgb": (96, 0, 255)},
]


@dataclass
class Team:
    """Represents a team in the game."""

    team_num: int
    name: str
    color: tuple
    span: trace.Span | None = None  # OpenTelemetry span for team lifecycle


class TeamsGameBase(BaseGameMode):
    """
    Abstract base class for team-based game modes.

    Provides:
    - Team management (teams dict, team colors)
    - Hierarchical span creation (team spans → player spans)
    - Team-based win condition checking
    - Team elimination detection

    Subclasses must implement:
    - get_game_name() - return "Teams" or "Random Teams"
    - _initialize_players_impl() - assign players to teams (round-robin vs random)
    - _get_additional_phases() - return [] for Teams, [TeamFormationPhase] for Random Teams
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
        Initialize team-based game mode.

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events
            game_id: Unique identifier for this game instance
            num_teams: Number of teams (default 2)
        """
        super().__init__(
            controller_manager_client=controller_manager_client,
            settings_client=settings_client,
            event_publisher=event_publisher,
            game_id=game_id,
        )

        self.num_teams = num_teams
        self.teams: dict[int, Team] = {}

        # Team tracking
        self.team_colors = TEAM_COLORS[:num_teams]

        # Initialize team objects
        for i in range(num_teams):
            self.teams[i] = Team(
                team_num=i, name=self.team_colors[i]["name"], color=self.team_colors[i]["rgb"]
            )

        logger.info(f"{self.get_game_name()} game initialized with {num_teams} teams")

    # ========================================================================
    # Concrete Methods - Team-specific implementation
    # ========================================================================

    def _create_player_spans(self, game_context):
        """
        Create hierarchical team → player lifecycle spans.

        Team spans are created first, then player spans are created as children
        of their respective team spans.

        Args:
            game_context: Parent span context for proper hierarchy
        """
        # Create team lifecycle spans first
        for team_num, team in self.teams.items():
            team_span = tracer.start_span(
                f"team_{team_num}_{team.name}_lifecycle",
                attributes={
                    "team.number": team_num,
                    "team.name": team.name,
                    "team.color": str(team.color),
                    "game.mode": self.get_game_name(),
                },
            )
            team.span = team_span
            logger.debug(f"Started lifecycle span for team {team_num} ({team.name})")

        # Create player lifecycle spans as children of their team spans
        for serial, player in self.players.items():
            team = self.teams[player.team]

            # Create player span as child of team span using context
            ctx = trace.set_span_in_context(team.span)

            player_span = tracer.start_span(
                f"player_{serial}_lifecycle",
                context=ctx,
                attributes={
                    "player.serial": serial,
                    "player.team": player.team,
                    "player.team_name": team.name,
                    "player.color": str(player.color),
                    "game.mode": self.get_game_name(),
                },
            )
            player.span = player_span
            logger.debug(f"Started lifecycle span for player {serial} (Team {team.name})")

    async def _set_team_colors(self, pulse_effect: bool = False, duration_ms: int = 0):
        """
        Set controller LED colors to match team assignments (Phase 39 - Task 3).

        Args:
            pulse_effect: If True, use pulse effect for emphasis (good for team announcements)
            duration_ms: Duration of the color/effect. 0 = persistent until changed
        """
        from proto import controller_manager_pb2

        try:
            for serial, player in self.players.items():
                team_color = self.team_colors[player.team]["rgb"]

                if pulse_effect:
                    # Use pulse effect for team announcement
                    await self.controller_manager_client.PlayControllerEffect(
                        controller_manager_pb2.PlayControllerEffectRequest(
                            serial=serial,
                            effect=controller_manager_pb2.ControllerEffect.EFFECT_PULSE,
                            color=controller_manager_pb2.RGB(
                                r=team_color[0], g=team_color[1], b=team_color[2]
                            ),
                            duration_ms=duration_ms,
                            speed=3,  # Medium pulse speed
                        )
                    )
                    logger.debug(
                        f"Set {serial} to team {player.team} ({self.team_colors[player.team]['name']}) with pulse"
                    )
                else:
                    # Set persistent team color
                    await self.controller_manager_client.SetControllerColor(
                        controller_manager_pb2.SetControllerColorRequest(
                            serial=serial,
                            color=controller_manager_pb2.RGB(
                                r=team_color[0], g=team_color[1], b=team_color[2]
                            ),
                            duration_ms=duration_ms,
                        )
                    )
                    logger.debug(
                        f"Set {serial} to team {player.team} ({self.team_colors[player.team]['name']}) color"
                    )

            logger.info(
                f"Set team colors for {len(self.players)} players "
                f"({'pulsing' if pulse_effect else 'persistent'})"
            )

        except Exception as e:
            logger.error(f"Failed to set team colors: {e}", exc_info=True)

    def _get_alive_teams(self) -> set[int]:
        """
        Get set of teams that still have alive players.

        Returns:
            Set of team numbers with at least one alive player
        """
        alive_teams = set()
        for player in self.players.values():
            if player.alive:
                alive_teams.add(player.team)
        return alive_teams

    def _check_win_condition(self) -> bool:
        """
        Check if a team has won.

        Returns:
            True if game should end (<=1 team remaining), False otherwise
        """
        alive_teams = self._get_alive_teams()

        if len(alive_teams) <= 1:
            # Game over - we have a winning team (or tie if 0)
            if len(alive_teams) == 1:
                winning_team = list(alive_teams)[0]
                team_name = self.team_colors[winning_team]["name"]

                # Get winning players
                winners = [
                    p.serial for p in self.players.values() if p.alive and p.team == winning_team
                ]

                logger.info(f"Team {winning_team} ({team_name}) wins with {len(winners)} players!")

                self.event_publisher(
                    "team_winner",
                    {
                        "team": winning_team,
                        "team_name": team_name,
                        "team_color": str(self.team_colors[winning_team]["rgb"]),
                        "winning_players": winners,
                        "winner_count": len(winners),
                    },
                )

            elif len(alive_teams) == 0:
                logger.info("No winner - all players died simultaneously")
                self.event_publisher("game_tie", {})

            return True

        return False

    async def _kill_player_impl(self, serial: str, accel_mag: float):
        """
        Handle player death with team elimination detection.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        player = self.players[serial]
        player.alive = False
        team = self.teams[player.team]

        alive_count = len([p for p in self.players.values() if p.alive])
        alive_teams = self._get_alive_teams()

        # Check if this death eliminated the team
        team_eliminated = player.team not in alive_teams

        logger.info(
            f"Player died: {serial} (Team {player.team}), {alive_count} players remaining on {len(alive_teams)} teams"
        )

        # Add death event to player's lifecycle span and end it
        if player.span:
            player.span.add_event(
                "player_death",
                attributes={
                    "accel_magnitude": accel_mag,
                    "threshold": self.sensitivity.value[1],
                    "alive_count": alive_count,
                    "team_eliminated": team_eliminated,
                },
            )
            player.span.set_status(Status(StatusCode.OK))
            player.span.end()
            logger.debug(f"Ended lifecycle span for player {serial}")

        # If team eliminated, end team span
        if team_eliminated and team.span:
            team.span.add_event(
                "team_eliminated",
                attributes={"last_player": serial, "alive_teams_count": len(alive_teams)},
            )
            team.span.set_status(Status(StatusCode.OK))
            team.span.end()
            logger.info(f"Team {team.name} eliminated! Ended team lifecycle span")

    async def _end_game_impl(self):
        """Handle game ending for team-based games."""
        logger.info("Ending game...")
        self.state = self.state.__class__.ENDING

        # Determine winning team
        alive_teams = self._get_alive_teams()
        winning_team_num = list(alive_teams)[0] if len(alive_teams) == 1 else None

        # End spans for any surviving players
        for serial, player in self.players.items():
            if player.span and player.alive:
                is_winner = winning_team_num is not None and player.team == winning_team_num
                player.span.add_event(
                    "player_survived",
                    attributes={
                        "game_duration": time.time() - self.start_time
                        if self.start_time
                        else 0,
                        "winner": is_winner,
                        "team": player.team,
                    },
                )
                player.span.set_status(Status(StatusCode.OK))
                player.span.end()
                logger.debug(f"Ended lifecycle span for surviving player {serial}")

        # End spans for any surviving teams (winning team)
        for team_num, team in self.teams.items():
            if team.span and team_num in alive_teams:
                is_winning_team = winning_team_num is not None and team_num == winning_team_num
                team.span.add_event(
                    "team_victory" if is_winning_team else "team_survived",
                    attributes={
                        "game_duration": time.time() - self.start_time
                        if self.start_time
                        else 0,
                        "winner": is_winning_team,
                    },
                )
                team.span.set_status(Status(StatusCode.OK))
                team.span.end()
                logger.info(
                    f"Ended lifecycle span for team {team.name} ({'WINNER' if is_winning_team else 'survived'})"
                )

        # TODO: Show rainbow effect on winning team's controllers
        # TODO: Play victory sound via Audio service

        # Show winner for a bit (interruptible by force_end)
        for _ in range(20):  # 2 seconds in 0.1s increments
            if not self.running:
                logger.info("End game interrupted by force_end")
                break
            await asyncio.sleep(0.1)

        self.state = self.state.__class__.ENDED
        self.event_publisher(
            "game_ended",
            {
                "game_id": self.game_id,
                "duration": time.time() - self.start_time if self.start_time else 0,
            },
        )

        logger.info("Game ended")
