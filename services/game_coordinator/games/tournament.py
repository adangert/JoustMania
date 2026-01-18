"""
Tournament Game Mode - gRPC-based implementation

Single elimination bracket tournament with 1v1 matches.
Winner advances, loser is eliminated. Handles odd player counts
with byes (automatically advance to next round).

Original JoustMania behavior preserved.
"""

import asyncio
import logging
import math
import random
import time
from dataclasses import dataclass
from enum import Enum

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from proto import controller_manager_pb2
from services.game_coordinator.games.base import BaseGameMode, Phase, Player

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


# Colors for tournament states
WAITING_COLOR = (40, 40, 40)  # Gray while waiting
MATCH_COLORS = [
    (255, 0, 0),  # Red - Player 1
    (0, 0, 255),  # Blue - Player 2
]
WINNER_COLOR = (0, 255, 0)  # Green for match winner
ELIMINATED_COLOR = (0, 0, 0)  # Off when eliminated

# Match timing
MATCH_DURATION = 22.0  # Seconds per match
INVINCIBILITY_DURATION = 4.0  # Seconds at start of match
TIME_BETWEEN_MATCHES = 5.0  # Pause between matches


class TournamentState(Enum):
    """Player state in tournament."""

    WAITING = "waiting"  # In bracket, waiting for match
    FIGHTING = "fighting"  # Currently in a match
    BYE = "bye"  # Got a bye this round
    CHAMPION = "champion"  # Won the tournament
    ELIMINATED = "eliminated"  # Lost a match


@dataclass
class TournamentPlayer(Player):
    """Extended Player class with tournament state."""

    tournament_state: TournamentState = TournamentState.WAITING
    bracket_position: int = 0  # Position in bracket
    round_number: int = 1  # Current round (advances with wins)
    invincible_until: float = 0.0  # Timestamp when invincibility ends
    wins: int = 0  # Total wins in tournament


@dataclass
class Match:
    """Represents a single match in the tournament."""

    match_id: int
    round_number: int
    player1_serial: str | None = None  # None = waiting for winner from previous match
    player2_serial: str | None = None
    winner_serial: str | None = None
    is_complete: bool = False
    is_bye: bool = False  # True if only one player (automatic advance)


class TournamentGame(BaseGameMode):
    """
    Tournament game mode using gRPC communication.

    Single elimination bracket where players compete in 1v1 matches.
    Winners advance, losers are eliminated. Last player standing wins.

    Handles odd player counts with byes (some players automatically
    advance to next round).
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
        Initialize Tournament game.

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events
            audio_client: gRPC stub for Audio service
            game_id: Unique identifier for this game instance
            initial_players: Optional list of Player protobuf messages
        """
        super().__init__(
            controller_manager_client=controller_manager_client,
            settings_client=settings_client,
            event_publisher=event_publisher,
            audio_client=audio_client,
            game_id=game_id,
            initial_players=initial_players,
        )

        self.bracket: list[Match] = []
        self.current_match: Match | None = None
        self.current_round = 1
        self.total_rounds = 0
        self.match_task: asyncio.Task | None = None
        self.match_span: trace.Span | None = None

    def get_game_name(self) -> str:
        """Return game mode identifier."""
        return "Tournament"

    def _generate_bracket(self, player_count: int) -> list[Match]:
        """
        Generate tournament bracket for given player count.

        Creates a balanced bracket with byes for non-power-of-2 counts.

        Args:
            player_count: Number of players

        Returns:
            List of Match objects representing the bracket
        """
        if player_count < 2:
            return []

        # Find next power of 2 >= player_count
        total_slots = 1
        while total_slots < player_count:
            total_slots *= 2

        self.total_rounds = int(math.log2(total_slots))
        num_byes = total_slots - player_count

        # Shuffle players for random seeding
        serials = list(self.players.keys())
        random.shuffle(serials)

        # Assign bracket positions
        for i, serial in enumerate(serials):
            player = self.players[serial]
            player.bracket_position = i

        matches = []
        match_id = 0

        # First round matches
        first_round_matches = total_slots // 2
        player_idx = 0

        for i in range(first_round_matches):
            match = Match(
                match_id=match_id,
                round_number=1,
            )
            match_id += 1

            # Assign players or byes
            if player_idx < len(serials):
                match.player1_serial = serials[player_idx]
                player_idx += 1

            if num_byes > 0 and i < num_byes:
                # This match is a bye - player1 auto-advances
                match.is_bye = True
                match.winner_serial = match.player1_serial
                match.is_complete = True
                if match.player1_serial:
                    self.players[match.player1_serial].tournament_state = TournamentState.BYE
            elif player_idx < len(serials):
                match.player2_serial = serials[player_idx]
                player_idx += 1

            matches.append(match)

        # Generate placeholder matches for subsequent rounds
        matches_in_round = first_round_matches // 2
        current_round = 2

        while matches_in_round >= 1:
            for _ in range(matches_in_round):
                match = Match(
                    match_id=match_id,
                    round_number=current_round,
                )
                matches.append(match)
                match_id += 1

            matches_in_round //= 2
            current_round += 1

        logger.info(f"Generated bracket: {len(matches)} matches, {self.total_rounds} rounds, {num_byes} byes")
        return matches

    def _get_next_match(self) -> Match | None:
        """
        Get the next incomplete match that's ready to play.

        A match is ready if both players are assigned (or it's a bye).

        Returns:
            Next match to play, or None if tournament is complete
        """
        for match in self.bracket:
            if match.is_complete:
                continue
            if match.player1_serial and match.player2_serial:
                return match
            if match.is_bye and match.player1_serial:
                return match
        return None

    def _advance_winner(self, winner_serial: str, completed_match: Match):
        """
        Advance winner to next round's match.

        Args:
            winner_serial: Serial of winning player
            completed_match: The match that was just completed
        """
        if completed_match.round_number >= self.total_rounds:
            # Tournament winner!
            return

        # Find next round match for this winner
        next_round = completed_match.round_number + 1
        next_round_matches = [m for m in self.bracket if m.round_number == next_round]

        # Determine which match and slot
        matches_in_prev_round = len([m for m in self.bracket if m.round_number == completed_match.round_number])
        match_index = completed_match.match_id % matches_in_prev_round
        next_match_index = match_index // 2

        if next_match_index < len(next_round_matches):
            next_match = next_round_matches[next_match_index]

            # Assign to first or second slot based on match position
            if match_index % 2 == 0:
                next_match.player1_serial = winner_serial
            else:
                next_match.player2_serial = winner_serial

            logger.info(f"Advanced {winner_serial} to round {next_round}, match {next_match.match_id}")

            # Update player state
            player = self.players[winner_serial]
            player.round_number = next_round
            player.tournament_state = TournamentState.WAITING

    async def _initialize_players_impl(self, controllers: list):
        """
        Initialize players for tournament.

        Args:
            controllers: List of controller protobuf messages
        """
        for controller in controllers:
            player = TournamentPlayer(
                serial=controller.serial,
                team=-1,  # No teams in tournament
                alive=True,
                color=WAITING_COLOR,
                tournament_state=TournamentState.WAITING,
            )
            self.players[controller.serial] = player
            logger.debug(f"Added player: {controller.serial}")

        # Generate bracket
        self.bracket = self._generate_bracket(len(controllers))

        logger.info(f"Initialized {len(controllers)} players for tournament")

        self.event_publisher(
            "players_initialized",
            {
                "player_count": len(controllers),
                "total_rounds": self.total_rounds,
                "bracket_size": len(self.bracket),
                "serials": list(self.players.keys()),
            },
        )

    def _create_player_spans(self, game_context):
        """Create flat player spans (no team hierarchy in tournament)."""
        # Get current context if not provided
        if game_context is None:
            from opentelemetry import context as otel_context

            game_context = otel_context.get_current()

        for serial, player in self.players.items():
            player.span = tracer.start_span(
                "player_lifecycle",
                context=game_context,
                attributes={
                    "player.serial": serial,
                    "player.bracket_position": player.bracket_position,
                    "game.mode": "Tournament",
                },
            )
            logger.debug(f"Created span for player {serial}")

    def _get_additional_phases(self) -> list:
        """Return tournament-specific phases."""
        return [Phase(name="tournament_intro", execute=self._tournament_intro_phase)]

    async def _tournament_intro_phase(self):
        """Show bracket and prepare for first matches."""
        logger.info("Starting tournament intro phase...")

        self.event_publisher(
            "tournament_intro",
            {
                "total_players": len(self.players),
                "total_rounds": self.total_rounds,
                "byes": len([m for m in self.bracket if m.is_bye]),
            },
        )

        # Set all to waiting color
        for serial in self.players:
            if self.gameplay_stream:
                color_cmd = controller_manager_pb2.GameplayStreamControl(
                    color_update=controller_manager_pb2.ColorUpdate(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=WAITING_COLOR[0], g=WAITING_COLOR[1], b=WAITING_COLOR[2]),
                    )
                )
                await self.gameplay_stream.write(color_cmd)

        # Play intro sound
        await self._play_sound("Joust/sounds/tournament_intro.wav", priority=2)

        # Wait for intro
        for _ in range(30):  # 3 seconds
            if not self.running:
                return
            await asyncio.sleep(0.1)

        logger.info("Tournament intro phase complete")

    async def _run_match(self, match: Match):
        """
        Run a single tournament match.

        Args:
            match: The match to run
        """
        if match.is_bye:
            # Auto-advance
            logger.info(f"Match {match.match_id}: {match.player1_serial} gets a bye")
            self._advance_winner(match.player1_serial, match)
            return

        p1 = self.players[match.player1_serial]
        p2 = self.players[match.player2_serial]

        # Set match states
        p1.tournament_state = TournamentState.FIGHTING
        p2.tournament_state = TournamentState.FIGHTING
        p1.alive = True
        p2.alive = True

        # Create match span (inherits current active context)
        self.match_span = tracer.start_span(
            "tournament_match",
            attributes={
                "match.id": match.match_id,
                "match.round": match.round_number,
                "player1.serial": match.player1_serial,
                "player2.serial": match.player2_serial,
            },
        )

        logger.info(f"Match {match.match_id} starting: {match.player1_serial} vs {match.player2_serial}")

        self.event_publisher(
            "match_start",
            {
                "match_id": match.match_id,
                "round": match.round_number,
                "player1": match.player1_serial,
                "player2": match.player2_serial,
            },
        )

        # Set colors
        if self.gameplay_stream:
            for serial, color in [(match.player1_serial, MATCH_COLORS[0]), (match.player2_serial, MATCH_COLORS[1])]:
                color_cmd = controller_manager_pb2.GameplayStreamControl(
                    color_update=controller_manager_pb2.ColorUpdate(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
                    )
                )
                await self.gameplay_stream.write(color_cmd)

        # Set invincibility
        invincible_until = time.time() + INVINCIBILITY_DURATION
        p1.invincible_until = invincible_until
        p2.invincible_until = invincible_until

        # Play match start sound
        await self._play_sound("Joust/sounds/fight.wav", priority=2)

        # Run match with timer
        match_start = time.time()
        while self.running and not match.is_complete:
            elapsed = time.time() - match_start

            if elapsed >= MATCH_DURATION:
                # Time's up - both survive, random winner
                match.winner_serial = random.choice([match.player1_serial, match.player2_serial])
                logger.info(f"Match {match.match_id} timeout - random winner: {match.winner_serial}")
                break

            await asyncio.sleep(0.05)

        # Finalize match
        if not match.is_complete and match.winner_serial:
            match.is_complete = True

            # Determine loser
            loser_serial = match.player2_serial if match.winner_serial == match.player1_serial else match.player1_serial

            winner = self.players[match.winner_serial]
            loser = self.players[loser_serial]

            winner.wins += 1
            winner.tournament_state = TournamentState.WAITING
            loser.tournament_state = TournamentState.ELIMINATED
            loser.alive = False

            # Show winner effect
            if self.gameplay_stream:
                effect_cmd = controller_manager_pb2.GameplayStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=match.winner_serial,
                        effect=controller_manager_pb2.GAME_EFFECT_WIN_FLASH,
                    )
                )
                await self.gameplay_stream.write(effect_cmd)

                # Turn off loser
                off_cmd = controller_manager_pb2.GameplayStreamControl(
                    color_update=controller_manager_pb2.ColorUpdate(
                        serial=loser_serial,
                        color=controller_manager_pb2.RGB(r=0, g=0, b=0),
                    )
                )
                await self.gameplay_stream.write(off_cmd)

            # End loser's span
            if loser.span:
                loser.span.add_event(
                    "eliminated",
                    attributes={
                        "match_id": match.match_id,
                        "round": match.round_number,
                        "eliminated_by": match.winner_serial,
                    },
                )
                loser.span.set_status(Status(StatusCode.OK))
                loser.span.end()

            self.event_publisher(
                "match_end",
                {
                    "match_id": match.match_id,
                    "round": match.round_number,
                    "winner": match.winner_serial,
                    "loser": loser_serial,
                },
            )

            # End match span
            if self.match_span:
                self.match_span.add_event(
                    "match_complete",
                    attributes={
                        "winner": match.winner_serial,
                        "loser": loser_serial,
                    },
                )
                self.match_span.set_status(Status(StatusCode.OK))
                self.match_span.end()
                self.match_span = None

            # Advance winner
            self._advance_winner(match.winner_serial, match)

    async def _gameplay_loop(self):
        """Run the tournament by processing matches."""
        logger.info("Tournament gameplay starting...")

        while self.running:
            # Get next match
            next_match = self._get_next_match()

            if next_match is None:
                # Check if we have a champion
                alive_players = [s for s, p in self.players.items() if p.tournament_state != TournamentState.ELIMINATED]
                if len(alive_players) <= 1:
                    logger.info("Tournament complete!")
                    break
                await asyncio.sleep(0.1)
                continue

            # Check if round changed
            if next_match.round_number > self.current_round:
                self.current_round = next_match.round_number
                logger.info(f"Starting round {self.current_round}")
                self.event_publisher(
                    "round_start",
                    {"round": self.current_round, "total_rounds": self.total_rounds},
                )
                # Play round start sound
                await self._play_sound("Joust/sounds/round_start.wav", priority=2)
                await asyncio.sleep(2)

            self.current_match = next_match
            await self._run_match(next_match)
            self.current_match = None

            # Pause between matches
            for _ in range(int(TIME_BETWEEN_MATCHES * 10)):
                if not self.running:
                    break
                await asyncio.sleep(0.1)

    def _check_win_condition(self) -> bool:
        """
        Check if tournament is complete.

        Returns:
            True if only one player remains (or all eliminated)
        """
        active_players = [s for s, p in self.players.items() if p.tournament_state != TournamentState.ELIMINATED]

        if len(active_players) <= 1:
            if len(active_players) == 1:
                champion_serial = active_players[0]
                champion = self.players[champion_serial]
                champion.tournament_state = TournamentState.CHAMPION

                logger.info(f"Tournament champion: {champion_serial} with {champion.wins} wins!")

                self.event_publisher(
                    "tournament_champion",
                    {
                        "champion": champion_serial,
                        "wins": champion.wins,
                        "rounds_played": self.current_round,
                    },
                )
            else:
                logger.info("Tournament ended with no winner")
                self.event_publisher("tournament_no_winner", {})

            return True

        return False

    async def _kill_player_impl(self, serial: str, accel_mag: float):
        """
        Handle player death during a match.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        player = self.players[serial]

        # Check if in active match
        if player.tournament_state != TournamentState.FIGHTING:
            return

        # Check invincibility
        if time.time() < player.invincible_until:
            logger.debug(f"Player {serial} is invincible")
            return

        # Only process if this player is in current match
        if not self.current_match:
            return

        if serial not in (self.current_match.player1_serial, self.current_match.player2_serial):
            return

        # Determine winner
        if serial == self.current_match.player1_serial:
            self.current_match.winner_serial = self.current_match.player2_serial
        else:
            self.current_match.winner_serial = self.current_match.player1_serial

        self.current_match.is_complete = True

        winner = self.current_match.winner_serial
        logger.info(f"Match {self.current_match.match_id}: {serial} eliminated, winner: {winner}")

        # Add death event to player span
        if player.span:
            player.span.add_event(
                "match_death",
                attributes={
                    "match_id": self.current_match.match_id,
                    "accel_magnitude": accel_mag,
                    "sensitivity": self.sensitivity.name,
                },
            )

    async def _end_game_impl(self):
        """Handle tournament ending."""
        logger.info("Ending Tournament game...")
        self.state = self.state.__class__.ENDING

        # Find champion
        champion_serial = None
        for serial, player in self.players.items():
            if player.tournament_state == TournamentState.CHAMPION:
                champion_serial = serial
                break

        # Celebrate champion
        if champion_serial:
            if self.gameplay_stream:
                effect_cmd = controller_manager_pb2.GameplayStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=champion_serial,
                        effect=controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW,
                    )
                )
                await self.gameplay_stream.write(effect_cmd)

            await self._play_sound("Joust/sounds/victory.wav", priority=2)

        # Wait for celebration
        for _ in range(30):  # 3 seconds
            if not self.running:
                break
            await asyncio.sleep(0.1)

        # End remaining spans
        for _serial, player in self.players.items():
            if player.span:
                is_champion = player.tournament_state == TournamentState.CHAMPION
                player.span.add_event(
                    "tournament_ended",
                    attributes={
                        "is_champion": is_champion,
                        "wins": player.wins,
                        "final_round": player.round_number,
                    },
                )
                player.span.set_status(Status(StatusCode.OK))
                player.span.end()

        self.state = self.state.__class__.ENDED
        self.event_publisher(
            "game_ended",
            {
                "game_id": self.game_id,
                "duration": time.time() - self.start_time if self.start_time else 0,
                "champion": champion_serial,
                "total_matches": len([m for m in self.bracket if m.is_complete and not m.is_bye]),
            },
        )

        logger.info("Tournament game ended")
