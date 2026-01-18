"""
Swapper Game Mode - gRPC-based implementation

Players switch teams when they die. Last team standing wins,
but the last player to die is excluded from winners.

Original JoustMania behavior preserved.
"""

import asyncio
import logging
import time

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from lib.types import Sound
from proto import controller_manager_pb2
from services.game_coordinator.games.base import Player
from services.game_coordinator.games.teams_base import TEAM_WIN_SOUNDS, TeamsGameBase

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class SwapperGame(TeamsGameBase):
    """
    Swapper game mode using gRPC communication.

    Players switch teams when they die instead of being eliminated.
    When all players end up on the same team, the game ends.
    The last player to die is excluded from the winners.

    Extends TeamsGameBase for team management and hierarchical spans.
    """

    def __init__(
        self,
        controller_manager_client,
        settings_client,
        event_publisher,
        audio_client=None,
        game_id: str = "",
        initial_players: list | None = None,
    ):
        """
        Initialize Swapper game.

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events
            audio_client: gRPC stub for Audio service
            game_id: Unique identifier for this game instance
            initial_players: Optional list of Player protobuf messages
        """
        # Swapper always uses 2 teams
        super().__init__(
            controller_manager_client=controller_manager_client,
            settings_client=settings_client,
            event_publisher=event_publisher,
            audio_client=audio_client,
            game_id=game_id,
            num_teams=2,  # Force 2 teams for swapper
            initial_players=initial_players,
        )

        # Track the last player to die (excluded from winners)
        self.last_death_serial: str | None = None

    def get_game_name(self) -> str:
        """Return game mode identifier."""
        return "Swapper"

    async def _initialize_players_impl(self, controllers: list):
        """
        Initialize players with round-robin team assignment.

        Args:
            controllers: List of controller protobuf messages
        """
        for idx, controller in enumerate(controllers):
            team_num = idx % self.num_teams
            team_color = self.team_colors[team_num]["rgb"]

            player = Player(
                serial=controller.serial,
                team=team_num,
                alive=True,
                color=team_color,
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

    def _get_additional_phases(self) -> list:
        """No additional phases for Swapper."""
        return []

    async def _kill_player_impl(self, serial: str, accel_mag: float):
        """
        Handle player death by switching their team.

        Instead of dying, players switch to the opposing team.
        The player is given a brief grace period on their new team.

        Span handling:
        - End the player's span under the old team with "team_swap_out" event
        - Create a new span under the new team with "team_swap_in" event

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        player = self.players[serial]
        old_team = player.team
        old_team_obj = self.teams[old_team]

        # Switch teams
        new_team = 1 - old_team  # Toggle between 0 and 1
        new_team_obj = self.teams[new_team]
        player.team = new_team
        player.color = self.team_colors[new_team]["rgb"]

        # Track last death for winner exclusion
        self.last_death_serial = serial

        # Give grace period on new team
        player.grace_until = time.time() + 2.0

        # Log the swap
        swap_count = getattr(player, "swap_count", 0) + 1
        player.swap_count = swap_count
        logger.info(
            f"Player {serial} swapped (#{swap_count}): Team {old_team} ({self.team_colors[old_team]['name']}) "
            f"-> Team {new_team} ({self.team_colors[new_team]['name']})"
        )

        # End old span with swap event, create new span under new team
        if player.span:
            player.span.add_event(
                "team_swap_out",
                attributes={
                    "accel_magnitude": accel_mag,
                    "old_team": old_team,
                    "new_team": new_team,
                    "old_team_name": self.team_colors[old_team]["name"],
                    "new_team_name": self.team_colors[new_team]["name"],
                    "swap_count": swap_count,
                },
            )
            player.span.set_status(Status(StatusCode.OK))
            player.span.end()
            logger.debug(f"Ended player {serial} span under team {old_team}")

        # Create new span under new team
        if new_team_obj.span:
            with trace.use_span(new_team_obj.span, end_on_exit=False):
                new_span = tracer.start_span(
                    "player_lifecycle",
                    context=otel_context.get_current(),
                    attributes={
                        "player.serial": serial,
                        "player.team": new_team,
                        "player.team_name": new_team_obj.name,
                        "player.color": str(player.color),
                        "player.swap_count": swap_count,
                        "game.mode": self.get_game_name(),
                    },
                )
                new_span.add_event(
                    "team_swap_in",
                    attributes={
                        "from_team": old_team,
                        "from_team_name": old_team_obj.name,
                        "swap_count": swap_count,
                    },
                )
                player.span = new_span
                logger.debug(f"Created new player {serial} span under team {new_team}")

        # Update controller LED to new team color
        if self.gameplay_stream:
            color_cmd = controller_manager_pb2.GameplayStreamControl(
                game_effect=controller_manager_pb2.GameEffectCommand(
                    serial=serial,
                    effect=controller_manager_pb2.GAME_EFFECT_DEATH,
                )
            )
            await self.gameplay_stream.write(color_cmd)

            # After death flash, set new team color
            await asyncio.sleep(0.5)
            await self._set_player_color(serial, player.color)
        else:
            # Fallback to direct RPC
            await self.controller_client.SetControllerColor(
                controller_manager_pb2.SetControllerColorRequest(
                    serial=serial,
                    color=controller_manager_pb2.RGB(
                        r=player.color[0],
                        g=player.color[1],
                        b=player.color[2],
                    ),
                    duration_ms=0,
                )
            )

        # Publish swap event
        self.event_publisher(
            "player_swapped",
            {
                "serial": serial,
                "old_team": old_team,
                "new_team": new_team,
                "teams_count": str(self._get_team_counts()),
            },
        )

        # Play swap sound
        await self._play_sound("Joust/sounds/beep.wav", priority=1)

    async def _set_player_color(self, serial: str, color: tuple):
        """Set a player's controller LED color."""
        if self.gameplay_stream:
            # Use gameplay stream for color update
            color_cmd = controller_manager_pb2.GameplayStreamControl(
                color_update=controller_manager_pb2.ColorUpdate(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
                )
            )
            await self.gameplay_stream.write(color_cmd)
        else:
            await self.controller_client.SetControllerColor(
                controller_manager_pb2.SetControllerColorRequest(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
                    duration_ms=0,
                )
            )

    def _get_team_counts(self) -> dict[int, int]:
        """Get count of players on each team."""
        counts = {0: 0, 1: 0}
        for player in self.players.values():
            counts[player.team] = counts.get(player.team, 0) + 1
        return counts

    def _check_win_condition(self) -> bool:
        """
        Check if all players are on the same team.

        Returns:
            True if all players are on one team, False otherwise
        """
        teams = self._get_alive_teams()

        if len(teams) <= 1:
            # All players on one team
            winning_team = list(teams)[0] if teams else 0

            # Get winners (excluding last player to swap)
            winners = []
            for serial, player in self.players.items():
                if player.team == winning_team and serial != self.last_death_serial:
                    winners.append(serial)

            team_name = self.team_colors[winning_team]["name"]
            logger.info(
                f"Team {winning_team} ({team_name}) wins! Winners: {len(winners)}, Excluded: {self.last_death_serial}"
            )

            self.event_publisher(
                "swapper_winner",
                {
                    "team": winning_team,
                    "team_name": team_name,
                    "winners": winners,
                    "excluded_serial": self.last_death_serial or "",
                },
            )

            return True

        return False

    def _get_alive_teams(self) -> set[int]:
        """
        Get set of teams with players.

        In Swapper, all players are always "alive" - they just switch teams.
        We check which teams have players.

        Returns:
            Set of team numbers that have at least one player
        """
        teams = set()
        for player in self.players.values():
            teams.add(player.team)
        return teams

    async def _end_game_impl(self):
        """Handle game ending for Swapper."""
        logger.info("Ending Swapper game...")
        self.state = self.state.__class__.ENDING

        # Determine winning team
        teams = self._get_alive_teams()
        winning_team = list(teams)[0] if teams else 0

        # Show rainbow effect on winners (excluding last swapper)
        for serial, player in self.players.items():
            if player.team == winning_team and serial != self.last_death_serial:
                if self.gameplay_stream:
                    effect_cmd = controller_manager_pb2.GameplayStreamControl(
                        game_effect=controller_manager_pb2.GameEffectCommand(
                            serial=serial,
                            effect=controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW,
                        )
                    )
                    await self.gameplay_stream.write(effect_cmd)
                else:
                    rainbow_request = controller_manager_pb2.PlayControllerEffectRequest(
                        serial=serial,
                        effect=controller_manager_pb2.EFFECT_RAINBOW,
                        color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                        duration_ms=3000,
                        speed=1,  # Slow rainbow (1 cycle/second)
                    )
                    await self.controller_client.PlayControllerEffect(rainbow_request)

        # Show loser effect on excluded player (dim gray color)
        if self.last_death_serial and self.gameplay_stream:
            color_cmd = controller_manager_pb2.GameplayStreamControl(
                color_update=controller_manager_pb2.ColorUpdate(
                    serial=self.last_death_serial,
                    color=controller_manager_pb2.RGB(r=50, g=50, b=50),  # Dim gray
                )
            )
            await self.gameplay_stream.write(color_cmd)

        # Play team victory sound (audio service handles voice selection)
        winning_team_obj = self.teams.get(winning_team)
        if winning_team_obj:
            sound = TEAM_WIN_SOUNDS.get(winning_team_obj.name, Sound.VOX_CONGRATULATIONS)
            await self._play_sound(sound, priority=2)

        # Wait for celebration (interruptible)
        for _ in range(20):  # 2 seconds
            if not self.running:
                break
            await asyncio.sleep(0.1)

        # End all player spans
        for serial, player in self.players.items():
            if player.span:
                is_winner = player.team == winning_team and serial != self.last_death_serial
                player.span.add_event(
                    "game_ended",
                    attributes={
                        "winner": is_winner,
                        "team": player.team,
                        "excluded": serial == self.last_death_serial,
                    },
                )
                player.span.set_status(Status(StatusCode.OK))
                player.span.end()

        # End team spans
        for team_num, team in self.teams.items():
            if team.span:
                is_winning_team = team_num == winning_team
                team.span.add_event(
                    "game_ended",
                    attributes={"winner": is_winning_team},
                )
                team.span.set_status(Status(StatusCode.OK))
                team.span.end()

        self.state = self.state.__class__.ENDED
        self.event_publisher(
            "game_ended",
            {
                "game_id": self.game_id,
                "duration": time.time() - self.start_time if self.start_time else 0,
                "winning_team": winning_team,
            },
        )

        logger.info("Swapper game ended")
