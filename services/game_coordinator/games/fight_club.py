"""
Fight Club Game Mode - gRPC-based implementation

1v1 arena tournament with queue system. Players take turns fighting
the current defender. Winner stays, loser goes to back of queue.
Highest score at end wins.

Original JoustMania behavior preserved.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from proto import controller_manager_pb2
from services.game_coordinator.games.base import BaseGameMode, Phase, Player

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Game constants
ROUND_DURATION = 22.0  # Seconds per round
INVINCIBILITY_DURATION = 4.0  # Seconds of invincibility at round start
MIN_ROUNDS = 10  # Minimum rounds before game can end
COUNTDOWN_BEEPS = 3  # Beeps in last 3 seconds of round

# Colors
DEFENDER_COLOR = (255, 0, 0)  # Red for defender
FIGHTER_COLOR = (0, 255, 0)  # Green for challenger
WAITING_COLOR = (50, 50, 50)  # Dim gray for waiting


class FightState(Enum):
    """State of a player in Fight Club."""

    IN_LINE = "in_line"  # Waiting in queue
    DEFENDER = "defender"  # Current champion
    FIGHTER = "fighter"  # Challenging the defender
    FACE_OFF = "face_off"  # Tiebreaker (no time limit)


@dataclass
class FightClubPlayer(Player):
    """Extended Player class for Fight Club."""

    state: FightState = FightState.IN_LINE
    score: int = 0
    invincible_until: float = 0.0


class FightClubGame(BaseGameMode):
    """
    Fight Club game mode using gRPC communication.

    Players form a queue and fight 1v1 matches:
    - Each round has a 22 second time limit
    - First 4 seconds are invincibility period
    - Defender wins: stays, earns point, challenger goes to back of queue
    - Fighter wins: becomes defender, earns point
    - Time expires: both "die" and go to back of queue
    - Highest score after minimum rounds wins

    Special: Face-off mode for tied scores (no time limit).
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
        """Initialize Fight Club game."""
        super().__init__(
            controller_manager_client=controller_manager_client,
            settings_client=settings_client,
            event_publisher=event_publisher,
            audio_client=audio_client,
            game_id=game_id,
            initial_players=initial_players,
        )

        self.queue: list[str] = []  # Queue of player serials
        self.current_defender: str | None = None
        self.current_fighter: str | None = None
        self.round_number: int = 0
        self.round_end_time: float = 0.0
        self.round_task: asyncio.Task | None = None
        self.game_over: bool = False
        self.face_off_mode: bool = False
        self.game_span: trace.Span | None = None

    def get_game_name(self) -> str:
        """Return game mode identifier."""
        return "Fight Club"

    async def _initialize_players_impl(self, controllers: list):
        """
        Initialize players and create queue.

        Args:
            controllers: List of controller protobuf messages
        """
        # Initialize all players
        for controller in controllers:
            player = FightClubPlayer(
                serial=controller.serial,
                team=0,
                alive=True,
                color=WAITING_COLOR,
                state=FightState.IN_LINE,
                score=0,
            )
            self.players[controller.serial] = player
            self.queue.append(controller.serial)
            logger.debug(f"Added player: {controller.serial} to queue")

        logger.info(f"Initialized {len(self.players)} players in Fight Club")

        self.event_publisher(
            "players_initialized",
            {
                "player_count": len(self.players),
                "serials": list(self.players.keys()),
            },
        )

    def _create_player_spans(self):
        """Create flat player lifecycle spans, parented to game span."""
        if not self.game_span:
            logger.warning("No game_span available, creating orphan player spans")
            for serial, player in self.players.items():
                player.span = tracer.start_span(
                    "player_lifecycle",
                    attributes={
                        "player.serial": serial,
                        "game.mode": self.get_game_name(),
                    },
                )
            return

        # Create player spans as children of game span
        with trace.use_span(self.game_span, end_on_exit=False):
            for serial, player in self.players.items():
                player.span = tracer.start_span(
                    "player_lifecycle",
                    attributes={
                        "player.serial": serial,
                        "game.mode": self.get_game_name(),
                    },
                )
                logger.debug(f"Created span for player {serial}")

    def _get_additional_phases(self) -> list:
        """Return Fight Club intro phase."""
        return [Phase(name="fight_club_intro", execute=self._intro_phase)]

    async def _intro_phase(self):
        """
        Fight Club introduction phase.

        Show all players as waiting, play intro sound.
        """
        logger.info("Starting Fight Club intro phase...")

        # Set all controllers to waiting color
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
        await self._play_sound("Joust/sounds/fight_club_intro.wav", priority=2)

        # Wait for intro
        for _ in range(20):  # 2 seconds
            if not self.running:
                return
            await asyncio.sleep(0.1)

        logger.info("Fight Club intro complete")

    async def _start_round(self):
        """
        Start a new round with defender and challenger.
        """
        self.round_number += 1

        # If no defender, take first from queue
        if self.current_defender is None and self.queue:
            self.current_defender = self.queue.pop(0)

        # Get challenger from queue
        if self.queue:
            self.current_fighter = self.queue.pop(0)
        else:
            # No more challengers - game should end
            logger.info("No challengers left, ending game")
            self.game_over = True
            return

        defender = self.players[self.current_defender]
        fighter = self.players[self.current_fighter]

        # Set states
        defender.state = FightState.DEFENDER
        defender.color = DEFENDER_COLOR
        defender.alive = True
        defender.invincible_until = time.time() + INVINCIBILITY_DURATION

        fighter.state = FightState.FIGHTER
        fighter.color = FIGHTER_COLOR
        fighter.alive = True
        fighter.invincible_until = time.time() + INVINCIBILITY_DURATION

        # Set round end time
        if not self.face_off_mode:
            self.round_end_time = time.time() + ROUND_DURATION
        else:
            self.round_end_time = float("inf")  # No time limit in face-off

        logger.info(
            f"Round {self.round_number}: {self.current_defender} (defender, score={defender.score}) "
            f"vs {self.current_fighter} (fighter, score={fighter.score})"
            f"{' [FACE-OFF]' if self.face_off_mode else ''}"
        )

        # Update colors
        await self._update_player_colors()

        # Play round start sound
        await self._play_sound("Joust/sounds/beep.wav", priority=2)

        self.event_publisher(
            "round_start",
            {
                "round": self.round_number,
                "defender": self.current_defender,
                "fighter": self.current_fighter,
                "defender_score": defender.score,
                "fighter_score": fighter.score,
                "face_off": self.face_off_mode,
            },
        )

        # Start round timer task (unless face-off)
        if not self.face_off_mode:
            self.round_task = asyncio.create_task(self._round_timer())

    async def _round_timer(self):
        """
        Track round time and play countdown beeps.
        """
        while self.running:
            remaining = self.round_end_time - time.time()

            if remaining <= 0:
                # Time's up - both players lose
                logger.info("Round time expired - both players lose")
                await self._handle_timeout()
                break

            # Play beeps in last 3 seconds
            if remaining <= COUNTDOWN_BEEPS and remaining > 0:
                await self._play_sound("Joust/sounds/beep_loud.wav", priority=2)

            await asyncio.sleep(1.0)

    async def _handle_timeout(self):
        """
        Handle round timeout - both players go to back of queue.
        """
        if self.current_defender:
            defender = self.players[self.current_defender]
            defender.state = FightState.IN_LINE
            defender.color = WAITING_COLOR
            self.queue.append(self.current_defender)

        if self.current_fighter:
            fighter = self.players[self.current_fighter]
            fighter.state = FightState.IN_LINE
            fighter.color = WAITING_COLOR
            self.queue.append(self.current_fighter)

        self.current_defender = None
        self.current_fighter = None

        self.event_publisher(
            "round_timeout",
            {"round": self.round_number},
        )

        # Update colors and start next round
        await self._update_player_colors()

        if self._should_end_game():
            self.game_over = True
        else:
            await self._start_round()

    async def _update_player_colors(self):
        """Update all player colors based on their state."""
        for serial, player in self.players.items():
            fc_player = player
            color = WAITING_COLOR

            if fc_player.state == FightState.DEFENDER:
                color = DEFENDER_COLOR
            elif fc_player.state == FightState.FIGHTER:
                color = FIGHTER_COLOR

            if self.gameplay_stream:
                color_cmd = controller_manager_pb2.GameplayStreamControl(
                    color_update=controller_manager_pb2.ColorUpdate(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
                    )
                )
                await self.gameplay_stream.write(color_cmd)

    def _check_win_condition(self) -> bool:
        """Check if game should end."""
        return self.game_over

    def _should_end_game(self) -> bool:
        """
        Check if game should end after this round.

        Game ends after minimum rounds if there's a clear winner.
        """
        if self.round_number < MIN_ROUNDS:
            return False

        # Check if anyone has a clear lead
        scores = [(s, p.score) for s, p in self.players.items()]
        scores.sort(key=lambda x: x[1], reverse=True)

        if len(scores) >= 2 and scores[0][1] == scores[1][1]:
            # Top 2 are tied - continue or start face-off
            if not self.face_off_mode:
                # Start face-off between tied players
                self.face_off_mode = True
                self.current_defender = scores[0][0]
                self.current_fighter = scores[1][0]
                logger.info(f"Starting face-off: {self.current_defender} vs {self.current_fighter}")
            # In face-off, continue until winner
            return False

        return True

    async def _kill_player_impl(self, serial: str, accel_mag: float):
        """
        Handle player death in a fight.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        player = self.players[serial]
        fc_player = player

        # Check if still invincible
        if time.time() < fc_player.invincible_until:
            logger.debug(f"Player {serial} is invincible, ignoring death")
            return

        # Only process if player is in active fight
        if fc_player.state not in (FightState.DEFENDER, FightState.FIGHTER):
            return

        fc_player.alive = False

        # Cancel round timer
        if self.round_task and not self.round_task.done():
            self.round_task.cancel()

        # Determine winner
        if serial == self.current_defender:
            # Fighter wins!
            winner_serial = self.current_fighter
            loser_serial = self.current_defender
            logger.info(f"Fighter {winner_serial} defeats defender {loser_serial}!")
        else:
            # Defender wins!
            winner_serial = self.current_defender
            loser_serial = self.current_fighter
            logger.info(f"Defender {winner_serial} defeats fighter {loser_serial}!")

        winner = self.players[winner_serial]
        loser = self.players[loser_serial]

        # Update scores
        winner.score += 1

        # Winner becomes/stays defender
        winner.state = FightState.DEFENDER
        winner.color = DEFENDER_COLOR
        winner.alive = True
        self.current_defender = winner_serial

        # Loser goes to back of queue
        loser.state = FightState.IN_LINE
        loser.color = WAITING_COLOR
        loser.alive = True
        self.queue.append(loser_serial)
        self.current_fighter = None

        logger.info(f"Score update: {winner_serial}={winner.score}, {loser_serial}={loser.score}")

        # Play victory sound for round
        await self._play_sound("Joust/sounds/beep.wav", priority=1)

        if player.span:
            player.span.add_event(
                "round_lost",
                attributes={
                    "accel_magnitude": accel_mag,
                    "round": self.round_number,
                    "winner": winner_serial,
                },
            )

        self.event_publisher(
            "round_end",
            {
                "round": self.round_number,
                "winner": winner_serial,
                "loser": loser_serial,
                "winner_score": winner.score,
                "loser_score": loser.score,
            },
        )

        # Check if game should end
        if self._should_end_game():
            self.game_over = True
        else:
            # Start next round
            await asyncio.sleep(1.0)  # Brief pause between rounds
            await self._start_round()

    async def _end_game_impl(self):
        """Handle game ending."""
        logger.info("Ending Fight Club game...")
        self.state = self.state.__class__.ENDING

        # Cancel round task
        if self.round_task and not self.round_task.done():
            self.round_task.cancel()

        # Find winner (highest score)
        scores = [(s, p.score) for s, p in self.players.items()]
        scores.sort(key=lambda x: x[1], reverse=True)

        winner_serial = scores[0][0] if scores else None
        winner_score = scores[0][1] if scores else 0

        logger.info(f"Winner: {winner_serial} with score {winner_score}")

        # Show rainbow effect on winner
        if winner_serial:
            if self.gameplay_stream:
                effect_cmd = controller_manager_pb2.GameplayStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=winner_serial,
                        effect=controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW,
                    )
                )
                await self.gameplay_stream.write(effect_cmd)
            else:
                await self.controller_client.PlayControllerEffect(
                    controller_manager_pb2.PlayControllerEffectRequest(
                        serial=winner_serial,
                        effect=controller_manager_pb2.EFFECT_RAINBOW,
                        color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                        duration_ms=3000,
                        speed=1,  # Slow rainbow (1 cycle/second)
                    )
                )

        # Play victory sound
        await self._play_sound("Joust/sounds/wolfdown.wav", priority=2)

        # Wait for celebration
        for _ in range(20):  # 2 seconds
            if not self.running:
                break
            await asyncio.sleep(0.1)

        # End all player spans
        for serial, player in self.players.items():
            if player.span:
                fc_player = player
                is_winner = serial == winner_serial
                player.span.add_event(
                    "game_ended",
                    attributes={
                        "winner": is_winner,
                        "score": fc_player.score,
                        "final_rank": [s for s, _ in scores].index(serial) + 1,
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
                "winner": winner_serial,
                "winner_score": winner_score,
                "total_rounds": self.round_number,
                "final_scores": {s: p.score for s, p in self.players.items()},
            },
        )

        logger.info("Fight Club game ended")

    async def run(self):
        """
        Run the Fight Club game.

        Override to manage round-based gameplay.
        """
        from services.game_coordinator.games.base import GameState

        with tracer.start_as_current_span("fight_club_game") as game_span:
            self.game_span = game_span
            game_span.set_attribute("game.id", self.game_id)
            game_span.set_attribute("game.mode", self.get_game_name())

            try:
                self.running = True

                # Initialization phase
                with tracer.start_as_current_span("initialization_phase"):
                    await self._load_settings()
                    await self._initialize_players()
                    self._create_player_spans()

                # Additional phases (intro)
                for phase in self._get_additional_phases():
                    if not self.running:
                        break
                    with tracer.start_as_current_span(phase.name):
                        await phase.execute()

                if not self.running:
                    return

                # Countdown
                with tracer.start_as_current_span("countdown_phase"):
                    await self._countdown()

                if not self.running:
                    return

                # Start gameplay
                self.state = GameState.RUNNING
                self.start_time = time.time()

                # Start music
                await self._start_game_music()

                # Start gameplay stream
                await self._start_gameplay_stream()

                # Start first round
                await self._start_round()

                # Game loop - process controller states
                with tracer.start_as_current_span("gameplay_phase"):
                    await self._game_loop()

                # End game
                with tracer.start_as_current_span("teardown_phase"):
                    await self._end_game_impl()

                game_span.set_status(Status(StatusCode.OK))

            except Exception as e:
                logger.error(f"Game error: {e}", exc_info=True)
                game_span.record_exception(e)
                game_span.set_status(Status(StatusCode.ERROR, str(e)))
                raise
            finally:
                self.running = False
                await self._stop_game_music()
                if self.round_task and not self.round_task.done():
                    self.round_task.cancel()

    async def _process_controller_state(self, state):
        """
        Process controller state during Fight Club.

        Only process states for active fighters (defender/fighter).
        """
        serial = state.serial
        player = self.players.get(serial)

        if not player:
            return

        fc_player = player

        # Only process if player is in active fight
        if fc_player.state not in (FightState.DEFENDER, FightState.FIGHTER):
            return

        # Check invincibility
        if time.time() < fc_player.invincible_until:
            return

        # Calculate acceleration magnitude
        accel_mag = (state.accel_x**2 + state.accel_y**2 + state.accel_z**2) ** 0.5

        # Apply EMA filter
        if fc_player.smoothed_accel == 0.0:
            fc_player.smoothed_accel = accel_mag
        else:
            fc_player.smoothed_accel = (fc_player.smoothed_accel * 4 + accel_mag) / 5

        # Get thresholds
        warn_thresh, death_thresh = self.sensitivity.value

        # Check for death
        if fc_player.smoothed_accel > death_thresh:
            await self._kill_player(serial, fc_player.smoothed_accel)
        elif fc_player.smoothed_accel > warn_thresh:
            await self._warn_player(serial, fc_player.smoothed_accel, warn_thresh)
