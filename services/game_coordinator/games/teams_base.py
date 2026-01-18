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

from lib.types import GameEvent
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
        audio_client=None,
        game_id: str = "",
        num_teams: int = 2,
        initial_players: list | None = None,
    ):
        """
        Initialize team-based game mode.

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events
            audio_client: gRPC stub for Audio service (Phase 29)
            game_id: Unique identifier for this game instance
            num_teams: Number of teams (default 2)
            initial_players: Optional list of Player protobuf messages from StartGame RPC
        """
        super().__init__(
            controller_manager_client=controller_manager_client,
            settings_client=settings_client,
            event_publisher=event_publisher,
            audio_client=audio_client,
            game_id=game_id,
            initial_players=initial_players,
        )

        self.num_teams = num_teams
        self.teams: dict[int, Team] = {}

        # Team tracking
        self.team_colors = TEAM_COLORS[:num_teams]

        # Initialize team objects
        for i in range(num_teams):
            self.teams[i] = Team(team_num=i, name=self.team_colors[i]["name"], color=self.team_colors[i]["rgb"])

        logger.info(f"{self.get_game_name()} game initialized with {num_teams} teams")

    # ========================================================================
    # Concrete Methods - Team-specific implementation
    # ========================================================================

    def _create_player_spans(self, game_context):
        """
        Create hierarchical team → player lifecycle spans.

        Team spans are created first, then player spans are created as children
        of their respective team spans using trace.use_span() to register them
        with the OpenTelemetry SDK for proper export.

        Args:
            game_context: Parent span context for proper hierarchy
        """
        # Get current context if not provided
        if game_context is None:
            from opentelemetry import context as otel_context

            game_context = otel_context.get_current()

        # Create team lifecycle spans and their player children
        # Using trace.use_span() to register team spans with SDK for export
        for team_num, team in self.teams.items():
            team_span = tracer.start_span(
                "team_lifecycle",  # Consistent name for all teams (OpenTelemetry best practice)
                context=game_context,
                attributes={
                    "team.number": team_num,
                    "team.name": team.name,
                    "team.color": str(team.color),
                    "game.mode": self.get_game_name(),
                },
            )

            # FIX: Use trace.use_span() to register team span with SDK
            # end_on_exit=False prevents automatic span ending (we end manually)
            with trace.use_span(team_span, end_on_exit=False):
                team.span = team_span  # Store reference for manual .end() later

                # Create player spans while team span is current (registered with SDK)
                team_players = [(s, p) for s, p in self.players.items() if p.team == team_num]
                for serial, player in team_players:
                    # Get current context (now the registered team span)
                    from opentelemetry import context as otel_context

                    player_span = tracer.start_span(
                        "player_lifecycle",  # Consistent name for all players (OpenTelemetry best practice)
                        context=otel_context.get_current(),  # Gets team context (registered!)
                        attributes={
                            "player.serial": serial,
                            "player.team": player.team,
                            "player.team_name": team.name,
                            "player.color": str(player.color),
                            "game.mode": self.get_game_name(),
                        },
                    )
                    player.span = player_span

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
                player.color = team_color  # Phase XX: Store color for stream init

                if pulse_effect:
                    # Use pulse effect for team announcement
                    await self.controller_client.PlayControllerEffect(
                        controller_manager_pb2.PlayControllerEffectRequest(
                            serial=serial,
                            effect=controller_manager_pb2.ControllerEffect.EFFECT_PULSE,
                            color=controller_manager_pb2.RGB(r=team_color[0], g=team_color[1], b=team_color[2]),
                            duration_ms=duration_ms,
                            speed=3,  # Medium pulse speed
                        )
                    )
                    logger.debug(
                        f"Set {serial} to team {player.team} ({self.team_colors[player.team]['name']}) with pulse"
                    )
                else:
                    # Set persistent team color
                    await self.controller_client.SetControllerColor(
                        controller_manager_pb2.SetControllerColorRequest(
                            serial=serial,
                            color=controller_manager_pb2.RGB(r=team_color[0], g=team_color[1], b=team_color[2]),
                            duration_ms=duration_ms,
                        )
                    )
                    logger.debug(f"Set {serial} to team {player.team} ({self.team_colors[player.team]['name']}) color")

            logger.info(
                f"Set team colors for {len(self.players)} players ({'pulsing' if pulse_effect else 'persistent'})"
            )

        except Exception as e:
            logger.error(f"Failed to set team colors: {e}", exc_info=True)

    async def _countdown(self):
        """
        Run countdown with team colors (Phase 30 - Controller Feedback Completion).

        Team-specific countdown sequence:
        - 3 seconds: Team color (each player sees their team color)
        - 2 seconds: White flash (neutral, heightens anticipation)
        - 1 second: Green (universal GO signal)

        This overrides the base class countdown which uses Red → Yellow → Green.
        """
        from proto import controller_manager_pb2
        from services.game_coordinator.games.base import COUNTDOWN_DURATION

        logger.info("Starting team countdown...")
        self.event_publisher(GameEvent.COUNTDOWN_START, {"duration": COUNTDOWN_DURATION})

        # Countdown sequence specific to team-based games
        countdown_phases = [
            {
                "name": "team_colors",
                "duration": 1.0,
                "set_team_colors": True,  # Each player sees their team color
            },
            {
                "name": "white_flash",
                "color": (255, 255, 255),
                "duration": 1.0,
            },
            {
                "name": "green_go",
                "color": (0, 255, 0),
                "duration": 1.0,
            },
        ]

        for phase in countdown_phases:
            if not self.running:
                logger.info("Countdown interrupted by force_end")
                return

            # Play countdown beep (Phase 29)
            await self._play_sound("Joust/sounds/beep_loud.wav", priority=2)

            if phase.get("set_team_colors"):
                # Set each player to their team color
                await self._set_team_colors(pulse_effect=False, duration_ms=0)
            else:
                # Set all players to same color (broadcast)
                r, g, b = phase["color"]
                color_request = controller_manager_pb2.SetControllerColorRequest(
                    serial="",  # Empty = all controllers
                    color=controller_manager_pb2.RGB(r=r, g=g, b=b),
                    duration_ms=0,
                )
                await self.controller_client.SetControllerColor(color_request)

            # Wait 1 second (in 0.1s increments to allow interruption)
            for _ in range(10):
                if not self.running:
                    logger.info("Countdown interrupted by force_end")
                    return
                await asyncio.sleep(0.1)

        # Play start sound (Phase 29)
        await self._play_sound("Joust/sounds/start3.wav", priority=2)

        self.event_publisher(GameEvent.COUNTDOWN_END, {})
        logger.info("Team countdown complete")

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
                winners = [p.serial for p in self.players.values() if p.alive and p.team == winning_team]

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
                self.event_publisher(GameEvent.GAME_TIE, {})

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
                    "sensitivity": self.sensitivity.name,
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
        from services.game_coordinator import metrics

        logger.info("Ending game...")
        self.state = self.state.__class__.ENDING

        # Determine winning team
        alive_teams = self._get_alive_teams()
        winning_team_num = list(alive_teams)[0] if len(alive_teams) == 1 else None

        # Phase XX: Show rainbow effect on winning team's controllers via game effect
        if winning_team_num is not None:
            from proto import controller_manager_pb2

            # Play rainbow effect on all winning team members
            for serial, player in self.players.items():
                if player.alive and player.team == winning_team_num:
                    if self.gameplay_stream:
                        effect_cmd = controller_manager_pb2.GameplayStreamControl(
                            game_effect=controller_manager_pb2.GameEffectCommand(
                                serial=serial,
                                effect=controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW,
                            )
                        )
                        await self.gameplay_stream.write(effect_cmd)
                    else:
                        # Fallback to RPC
                        rainbow_request = controller_manager_pb2.PlayControllerEffectRequest(
                            serial=serial,
                            effect=controller_manager_pb2.EFFECT_RAINBOW,
                            color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                            duration_ms=3000,
                            speed=5,
                        )
                        await self.controller_client.PlayControllerEffect(rainbow_request)

            # Play victory sound (Phase 29)
            await self._play_sound("Joust/sounds/wolfdown.wav", priority=2)

        # Show winner for a bit (interruptible by force_end)
        for _ in range(20):  # 2 seconds in 0.1s increments
            if not self.running:
                logger.info("End game interrupted by force_end")
                break
            await asyncio.sleep(0.1)

        # End spans for surviving players AFTER the celebration
        # This ensures winners' spans are longer than losers'
        for serial, player in self.players.items():
            if player.span and player.alive:
                is_winner = winning_team_num is not None and player.team == winning_team_num

                # Build attributes including analytics summary if available
                survived_attrs = {
                    "game_duration": time.time() - self.start_time if self.start_time else 0,
                    "winner": is_winner,
                    "team": player.team,
                }

                # Add analytics summary to span
                if player.analytics is not None:
                    analytics_summary = player.analytics.get_summary()
                    for key, value in analytics_summary.items():
                        survived_attrs[f"analytics.{key}"] = value

                player.span.add_event("player_survived", attributes=survived_attrs)
                player.span.set_status(Status(StatusCode.OK))
                player.span.end()
                logger.debug(f"Ended lifecycle span for surviving player {serial}")

        # Publish analytics summaries for all players
        for serial, player in self.players.items():
            if player.analytics is not None:
                is_winner = winning_team_num is not None and player.team == winning_team_num
                summary = player.analytics.get_summary()
                summary["game_id"] = self.game_id
                summary["winner"] = is_winner
                summary["team"] = player.team
                summary["survival_time_ms"] = player.analytics.total_time_ms

                # Publish player analytics event
                self.event_publisher(GameEvent.PLAYER_ANALYTICS, summary)

                # Update Prometheus metrics
                metrics.game_analytics_samples_total.labels(game_mode=self.get_game_name()).inc(
                    player.analytics.sample_count
                )
                metrics.near_death_events_total.labels(serial=serial, game_mode=self.get_game_name()).inc(
                    player.analytics.near_death_count
                )

                logger.info(
                    f"Player {serial} analytics: peak={summary['peak_accel']:.2f}g, "
                    f"playstyle={summary['playstyle']}, near_deaths={summary['near_death_count']}"
                )

        # End spans for surviving teams AFTER the celebration
        for team_num, team in self.teams.items():
            if team.span and team_num in alive_teams:
                is_winning_team = winning_team_num is not None and team_num == winning_team_num
                team.span.add_event(
                    "team_victory" if is_winning_team else "team_survived",
                    attributes={
                        "game_duration": time.time() - self.start_time if self.start_time else 0,
                        "winner": is_winning_team,
                    },
                )
                team.span.set_status(Status(StatusCode.OK))
                team.span.end()
                logger.info(
                    f"Ended lifecycle span for team {team.name} ({'WINNER' if is_winning_team else 'survived'})"
                )

        self.state = self.state.__class__.ENDED
        self.event_publisher(
            GameEvent.GAME_ENDED,
            {
                "game_id": self.game_id,
                "duration": time.time() - self.start_time if self.start_time else 0,
            },
        )

        logger.info("Game ended")
