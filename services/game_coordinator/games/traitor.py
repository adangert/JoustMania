"""
Traitor Game Mode - gRPC-based implementation

Players are divided into teams, but some are secretly traitors working
for the opposing team. Traitors appear as their visible team but win
with their secret team.

Original JoustMania behavior preserved.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from proto import controller_manager_pb2
from services.game_coordinator.games.base import Player
from services.game_coordinator.games.teams_base import TeamsGameBase

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class TraitorPlayer(Player):
    """Extended Player class with traitor information."""

    is_traitor: bool = False
    secret_team: int = -1  # The team the traitor actually wins with (-1 = not a traitor)


class TraitorGame(TeamsGameBase):
    """
    Traitor game mode using gRPC communication.

    Players are divided into teams, but some players are secretly traitors.
    Traitors:
    - Appear as their visible team color
    - Rumble during countdown to know they're traitors
    - Win with the opposing team (their secret_team)

    Traitor count based on player count:
    - 4-5 players: 1 traitor
    - 6-8 players: 2 traitors
    - 9-11 players: 3 traitors
    - 12+ players: num_players // 3 traitors

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
        Initialize Traitor game.

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events
            audio_client: gRPC stub for Audio service
            game_id: Unique identifier for this game instance
            initial_players: Optional list of Player protobuf messages
        """
        # Determine number of teams based on player count
        num_players = len(initial_players) if initial_players else 4
        num_teams = 2 if num_players < 9 else min(3, max(2, num_players // 3))

        super().__init__(
            controller_manager_client=controller_manager_client,
            settings_client=settings_client,
            event_publisher=event_publisher,
            audio_client=audio_client,
            game_id=game_id,
            num_teams=num_teams,
            initial_players=initial_players,
        )

        self.traitor_serials: list[str] = []

    def get_game_name(self) -> str:
        """Return game mode identifier."""
        return "Traitor"

    def _get_traitor_count(self, num_players: int) -> int:
        """
        Determine number of traitors based on player count.

        Args:
            num_players: Total number of players

        Returns:
            Number of traitors to assign
        """
        if num_players <= 5:
            return 1
        if num_players <= 8:
            return 2
        if num_players <= 11:
            return 3
        return num_players // 3

    async def _initialize_players_impl(self, controllers: list):
        """
        Initialize players with teams and assign traitors.

        Args:
            controllers: List of controller protobuf messages
        """
        num_players = len(controllers)
        num_traitors = self._get_traitor_count(num_players)

        # First, assign players to visible teams (round-robin)
        player_list = []
        for idx, controller in enumerate(controllers):
            team_num = idx % self.num_teams
            team_color = self.team_colors[team_num]["rgb"]

            player = TraitorPlayer(
                serial=controller.serial,
                team=team_num,
                alive=True,
                color=team_color,
                is_traitor=False,
                secret_team=team_num,  # Default: loyal to visible team
            )
            self.players[controller.serial] = player
            player_list.append(player)
            logger.debug(f"Added player: {controller.serial} to team {team_num}")

        # Select traitors - try to distribute evenly across teams
        available_by_team: dict[int, list[TraitorPlayer]] = {i: [] for i in range(self.num_teams)}
        for player in player_list:
            available_by_team[player.team].append(player)

        # Select traitors from each team in rotation
        traitors_assigned = 0
        team_idx = 0
        while traitors_assigned < num_traitors:
            team_players = available_by_team[team_idx]
            if team_players:
                # Pick a random player from this team to be a traitor
                traitor = random.choice(team_players)
                team_players.remove(traitor)

                # Assign secret team (the opposing team they'll win with)
                # For 2 teams: secret_team is the other team
                # For 3+ teams: pick a random different team
                possible_secret_teams = [t for t in range(self.num_teams) if t != traitor.team]
                traitor.secret_team = random.choice(possible_secret_teams)
                traitor.is_traitor = True
                self.traitor_serials.append(traitor.serial)

                logger.info(
                    f"Traitor assigned: {traitor.serial} - visible team {traitor.team}, "
                    f"secret team {traitor.secret_team}"
                )
                traitors_assigned += 1

            team_idx = (team_idx + 1) % self.num_teams

        logger.info(f"Initialized {num_players} players across {self.num_teams} teams with {num_traitors} traitors")

        # Publish event with team assignments (not revealing traitors)
        team_assignments = {serial: player.team for serial, player in self.players.items()}
        self.event_publisher(
            "players_initialized",
            {
                "player_count": num_players,
                "num_teams": self.num_teams,
                "traitor_count": num_traitors,
                "team_assignments": str(team_assignments),
                "serials": list(self.players.keys()),
            },
        )

    def _get_additional_phases(self) -> list:
        """Return traitor signal phase before countdown."""
        from services.game_coordinator.games.base import Phase

        return [Phase(name="traitor_signal", execute=self._traitor_signal_phase)]

    async def _traitor_signal_phase(self):
        """
        Signal traitors with rumble during team color display.

        Traitors feel a rumble so they know their secret role.
        Other players just see their team colors.
        """
        logger.info("Starting traitor signal phase...")

        self.event_publisher(
            "traitor_signal_start",
            {"traitor_count": len(self.traitor_serials)},
        )

        # Show team colors to all players
        await self._set_team_colors(pulse_effect=True, duration_ms=5000)

        # Rumble traitors to signal their role
        for serial in self.traitor_serials:
            if self.gameplay_stream:
                rumble_cmd = controller_manager_pb2.GameplayStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=serial,
                        effect=controller_manager_pb2.GAME_EFFECT_RUMBLE,
                    )
                )
                await self.gameplay_stream.write(rumble_cmd)
            else:
                # Fallback to direct RPC
                await self.controller_client.PlayControllerEffect(
                    controller_manager_pb2.PlayControllerEffectRequest(
                        serial=serial,
                        effect=controller_manager_pb2.EFFECT_RUMBLE,
                        duration_ms=2000,
                        speed=5,
                    )
                )

        logger.info(f"Signaled {len(self.traitor_serials)} traitors with rumble")

        # Play traitor intro sound
        await self._play_sound("Joust/sounds/traitor_intro.wav", priority=2)

        # Wait for signal phase (interruptible)
        for _ in range(50):  # 5 seconds
            if not self.running:
                logger.info("Traitor signal interrupted")
                return
            await asyncio.sleep(0.1)

        # Set persistent team colors
        await self._set_team_colors(pulse_effect=False)

        self.event_publisher("traitor_signal_end", {})
        logger.info("Traitor signal phase complete")

    def _check_win_condition(self) -> bool:
        """
        Check if a team has won, accounting for traitors.

        Win condition: Only one "effective team" has players remaining.
        A player's effective team is their secret_team (which equals their
        visible team for non-traitors).

        Returns:
            True if game should end, False otherwise
        """
        # Count alive players by their secret team (what they actually win with)
        alive_by_secret_team: dict[int, list[str]] = {i: [] for i in range(self.num_teams)}

        for serial, player in self.players.items():
            if player.alive:
                traitor_player = player  # Type hint for IDE
                alive_by_secret_team[traitor_player.secret_team].append(serial)

        # Find teams with alive players
        alive_teams = [team for team, players in alive_by_secret_team.items() if players]

        if len(alive_teams) <= 1:
            # Game over - we have a winning team
            if len(alive_teams) == 1:
                winning_team = alive_teams[0]
                winners = alive_by_secret_team[winning_team]
                team_name = self.team_colors[winning_team]["name"]

                logger.info(f"Team {winning_team} ({team_name}) wins with {len(winners)} players!")

                # Identify which winners were traitors
                traitor_winners = [s for s in winners if s in self.traitor_serials]
                loyal_winners = [s for s in winners if s not in self.traitor_serials]

                self.event_publisher(
                    "traitor_winner",
                    {
                        "team": winning_team,
                        "team_name": team_name,
                        "winners": winners,
                        "traitor_winners": traitor_winners,
                        "loyal_winners": loyal_winners,
                    },
                )

            else:
                logger.info("No winner - all players died")
                self.event_publisher("game_tie", {})

            return True

        return False

    def _get_alive_teams(self) -> set[int]:
        """
        Get set of secret teams with alive players.

        Override to use secret_team instead of visible team.

        Returns:
            Set of secret team numbers with at least one alive player
        """
        alive_teams = set()
        for player in self.players.values():
            if player.alive:
                traitor_player = player
                alive_teams.add(traitor_player.secret_team)
        return alive_teams

    async def _kill_player_impl(self, serial: str, accel_mag: float):
        """
        Handle player death with traitor-aware team elimination detection.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        player = self.players[serial]
        player.alive = False

        alive_count = len([p for p in self.players.values() if p.alive])
        alive_teams = self._get_alive_teams()

        # Check if this death eliminated the player's secret team
        traitor_player = player
        team_eliminated = traitor_player.secret_team not in alive_teams

        logger.info(
            f"Player died: {serial} (visible team {player.team}, "
            f"secret team {traitor_player.secret_team}, traitor={traitor_player.is_traitor}), "
            f"{alive_count} players remaining"
        )

        # Add death event to player's lifecycle span
        if player.span:
            player.span.add_event(
                "player_death",
                attributes={
                    "accel_magnitude": accel_mag,
                    "sensitivity": self.sensitivity.name,
                    "alive_count": alive_count,
                    "team_eliminated": team_eliminated,
                    "is_traitor": traitor_player.is_traitor,
                    "visible_team": player.team,
                    "secret_team": traitor_player.secret_team,
                },
            )
            player.span.set_status(Status(StatusCode.OK))
            player.span.end()

        # If secret team eliminated, end team span
        # Note: Team spans are based on visible teams, so this might not align perfectly
        # We'll end the visible team's span if all its loyal members are dead
        visible_team = self.teams[player.team]
        visible_team_alive = any(p.alive and p.team == player.team for p in self.players.values())

        if not visible_team_alive and visible_team.span:
            visible_team.span.add_event(
                "team_eliminated",
                attributes={
                    "last_player": serial,
                    "was_traitor": traitor_player.is_traitor,
                },
            )
            visible_team.span.set_status(Status(StatusCode.OK))
            visible_team.span.end()
            logger.info(f"Visible team {visible_team.name} eliminated")

    async def _end_game_impl(self):
        """Handle game ending for Traitor mode."""
        logger.info("Ending Traitor game...")
        self.state = self.state.__class__.ENDING

        # Determine winning team (by secret team)
        alive_teams = self._get_alive_teams()
        winning_team = list(alive_teams)[0] if len(alive_teams) == 1 else None

        # Show rainbow effect on winners
        if winning_team is not None:
            for serial, player in self.players.items():
                traitor_player = player
                if player.alive and traitor_player.secret_team == winning_team:
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

            # Play victory sound
            # TODO: Use voice setting from settings service instead of hardcoded path
            await self._play_sound("Joust/vox/aaron/traitor win.wav", priority=2)

        # Wait for celebration
        for _ in range(20):  # 2 seconds
            if not self.running:
                break
            await asyncio.sleep(0.1)

        # End all player spans
        for _serial, player in self.players.items():
            if player.span and player.alive:
                traitor_player = player
                is_winner = winning_team is not None and traitor_player.secret_team == winning_team
                player.span.add_event(
                    "game_ended",
                    attributes={
                        "winner": is_winner,
                        "visible_team": player.team,
                        "secret_team": traitor_player.secret_team,
                        "is_traitor": traitor_player.is_traitor,
                    },
                )
                player.span.set_status(Status(StatusCode.OK))
                player.span.end()

        # End remaining team spans
        for _team_num, team in self.teams.items():
            if team.span:
                team.span.set_status(Status(StatusCode.OK))
                team.span.end()

        self.state = self.state.__class__.ENDED
        self.event_publisher(
            "game_ended",
            {
                "game_id": self.game_id,
                "duration": time.time() - self.start_time if self.start_time else 0,
                "winning_team": winning_team if winning_team is not None else -1,
                "traitor_count": len(self.traitor_serials),
            },
        )

        logger.info("Traitor game ended")
