"""
Werewolf Game Mode - gRPC-based implementation

Some players are secretly werewolves. All players appear the same initially,
but after 35 seconds the werewolves are revealed. Last team standing wins.

Original JoustMania behavior preserved.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from lib.types import Sound
from proto import controller_manager_pb2
from services.game_coordinator.games.base import BaseGameMode, Phase, Player, Sensitivity

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Game constants
REVEAL_TIME = 35.0  # Seconds until werewolves are revealed
HUMAN_COLOR = (255, 255, 0)  # Yellow for humans (and all players before reveal)
WEREWOLF_COLOR = (0, 100, 255)  # Blue for werewolves after reveal

# Werewolf thresholds - slightly harder to kill than humans
# Format: (warn_threshold, death_threshold)
WEREWOLF_THRESHOLDS = {
    Sensitivity.ULTRA_SLOW: (1.4, 1.6),
    Sensitivity.SLOW: (1.7, 1.9),
    Sensitivity.MEDIUM: (2.1, 2.6),
    Sensitivity.FAST: (2.9, 3.9),
    Sensitivity.ULTRA_FAST: (3.5, 4.5),
}


@dataclass
class WerewolfPlayer(Player):
    """Extended Player class with werewolf information."""

    is_werewolf: bool = False
    revealed: bool = False  # Whether identity has been revealed


class WerewolfGame(BaseGameMode):
    """
    Werewolf game mode using gRPC communication.

    About 44% of players are secretly werewolves:
    - All players start appearing as yellow (human color)
    - Werewolves rumble during intro to know their role
    - After 35 seconds, werewolves are revealed (turn blue)
    - Last team (humans or werewolves) standing wins
    - Werewolves have slightly higher thresholds (harder to kill)

    This is a FFA-style game with two hidden teams.
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
        Initialize Werewolf game.

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

        self.werewolf_serials: list[str] = []
        self.human_serials: list[str] = []
        self.revealed = False
        self.reveal_task: asyncio.Task | None = None
        self.game_span: trace.Span | None = None

    def get_game_name(self) -> str:
        """Return game mode identifier."""
        return "Werewolf"

    async def _initialize_players_impl(self, controllers: list):
        """
        Initialize players and assign werewolf roles.

        About 44% of players become werewolves.

        Args:
            controllers: List of controller protobuf messages
        """
        num_players = len(controllers)
        num_werewolves = max(1, int(num_players * 0.44))  # ~44% are werewolves, minimum 1

        # Randomly select werewolves
        serials = [c.serial for c in controllers]
        werewolf_serials = set(random.sample(serials, num_werewolves))

        for controller in controllers:
            is_wolf = controller.serial in werewolf_serials

            player = WerewolfPlayer(
                serial=controller.serial,
                team=1 if is_wolf else 0,  # Team 0 = humans, Team 1 = werewolves
                alive=True,
                color=HUMAN_COLOR,  # Everyone starts yellow
                is_werewolf=is_wolf,
                revealed=False,
            )
            self.players[controller.serial] = player

            if is_wolf:
                self.werewolf_serials.append(controller.serial)
            else:
                self.human_serials.append(controller.serial)

            logger.debug(f"Added player: {controller.serial} ({'werewolf' if is_wolf else 'human'})")

        logger.info(
            f"Initialized {num_players} players: {len(self.human_serials)} humans, "
            f"{len(self.werewolf_serials)} werewolves"
        )

        # Publish event (not revealing who is werewolf)
        self.event_publisher(
            "players_initialized",
            {
                "player_count": num_players,
                "werewolf_count": len(self.werewolf_serials),
                "human_count": len(self.human_serials),
                "serials": list(self.players.keys()),
            },
        )

    def _create_player_spans(self):
        """Create flat player lifecycle spans (FFA-style), parented to game span."""
        if not self.game_span:
            logger.warning("No game_span available, creating orphan player spans")
            for serial, player in self.players.items():
                wolf_player = player
                player.span = tracer.start_span(
                    "player_lifecycle",
                    attributes={
                        "player.serial": serial,
                        "player.is_werewolf": wolf_player.is_werewolf,
                        "player.team": "werewolf" if wolf_player.is_werewolf else "human",
                        "game.mode": self.get_game_name(),
                    },
                )
            return

        # Create player spans as children of game span
        with trace.use_span(self.game_span, end_on_exit=False):
            for serial, player in self.players.items():
                wolf_player = player
                player.span = tracer.start_span(
                    "player_lifecycle",
                    attributes={
                        "player.serial": serial,
                        "player.is_werewolf": wolf_player.is_werewolf,
                        "player.team": "werewolf" if wolf_player.is_werewolf else "human",
                        "game.mode": self.get_game_name(),
                    },
                )
                logger.debug(f"Created span for player {serial}")

    def _get_additional_phases(self) -> list:
        """Return werewolf intro phase."""
        return [Phase(name="werewolf_intro", execute=self._werewolf_intro_phase)]

    async def _werewolf_intro_phase(self):
        """
        Werewolf introduction phase.

        All players see yellow. Werewolves get a rumble to know their role.
        """
        logger.info("Starting werewolf intro phase...")

        self.event_publisher(
            "werewolf_intro_start",
            {"werewolf_count": len(self.werewolf_serials)},
        )

        # Set all controllers to human color (yellow)
        await self._set_all_colors(HUMAN_COLOR)

        # Play intro sound (Joust/vox/)
        await self._play_sound(Sound.VOX_WEREWOLF_INTRO, priority=2)

        # Rumble werewolves to signal their role
        for serial in self.werewolf_serials:
            if self.gameplay_stream:
                rumble_cmd = controller_manager_pb2.GameplayStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=serial,
                        effect=controller_manager_pb2.GAME_EFFECT_RUMBLE,
                    )
                )
                await self.gameplay_stream.write(rumble_cmd)
            else:
                await self.controller_client.PlayControllerEffect(
                    controller_manager_pb2.PlayControllerEffectRequest(
                        serial=serial,
                        effect=controller_manager_pb2.EFFECT_RUMBLE,
                        duration_ms=2000,
                        speed=5,
                    )
                )

        logger.info(f"Signaled {len(self.werewolf_serials)} werewolves with rumble")

        # Wait for intro (interruptible)
        for _ in range(30):  # 3 seconds
            if not self.running:
                return
            await asyncio.sleep(0.1)

        self.event_publisher("werewolf_intro_end", {})
        logger.info("Werewolf intro phase complete")

    async def _set_all_colors(self, color: tuple):
        """Set all controllers to the same color via stream."""
        r, g, b = color
        for serial in self.players:
            base_color_cmd = controller_manager_pb2.GameplayStreamControl(
                base_color=controller_manager_pb2.ControllerColorConfig(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=r, g=g, b=b),
                )
            )
            await self.gameplay_stream.write(base_color_cmd)

    async def _reveal_werewolves(self):
        """
        Reveal werewolves after the reveal timer.

        Called as a background task during gameplay.
        """
        # Wait for reveal time
        await asyncio.sleep(REVEAL_TIME)

        if not self.running:
            return

        logger.info("Revealing werewolves!")
        self.revealed = True

        self.event_publisher("werewolf_reveal", {"werewolf_serials": self.werewolf_serials})

        # Play reveal sound (Joust/vox/)
        await self._play_sound(Sound.VOX_WEREWOLF_REVEAL, priority=2)

        # Change werewolf colors to blue
        for serial in self.werewolf_serials:
            player = self.players.get(serial)
            if player and player.alive:
                wolf_player = player
                wolf_player.revealed = True
                wolf_player.color = WEREWOLF_COLOR

                # Flash effect then set color
                flash_cmd = controller_manager_pb2.GameplayStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=serial,
                        effect=controller_manager_pb2.GAME_EFFECT_FLASH,
                    )
                )
                await self.gameplay_stream.write(flash_cmd)

                await asyncio.sleep(0.3)

                base_color_cmd = controller_manager_pb2.GameplayStreamControl(
                    base_color=controller_manager_pb2.ControllerColorConfig(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=WEREWOLF_COLOR[0], g=WEREWOLF_COLOR[1], b=WEREWOLF_COLOR[2]),
                    )
                )
                await self.gameplay_stream.write(base_color_cmd)

        # Mark all werewolves as revealed
        for serial in self.werewolf_serials:
            player = self.players.get(serial)
            if player and player.span:
                player.span.add_event("werewolf_revealed", {"time_since_start": REVEAL_TIME})

        logger.info(f"Revealed {len(self.werewolf_serials)} werewolves")

    def _get_effective_thresholds(self, player: Player) -> tuple[float, float]:
        """
        Get death thresholds for a player.

        Werewolves have higher thresholds (harder to kill).

        Args:
            player: The player to get thresholds for

        Returns:
            Tuple of (warn_threshold, death_threshold)
        """
        wolf_player = player
        if wolf_player.is_werewolf:
            return WEREWOLF_THRESHOLDS.get(self.sensitivity, (2.1, 2.6))
        # Use standard thresholds from sensitivity
        return self.sensitivity.value

    def _check_win_condition(self) -> bool:
        """
        Check if one team has won.

        Returns:
            True if all humans or all werewolves are dead
        """
        alive_humans = [s for s in self.human_serials if self.players[s].alive]
        alive_werewolves = [s for s in self.werewolf_serials if self.players[s].alive]

        if len(alive_humans) == 0 or len(alive_werewolves) == 0:
            # One team is eliminated
            if len(alive_werewolves) > 0:
                winner = "werewolves"
                winners = alive_werewolves
            elif len(alive_humans) > 0:
                winner = "humans"
                winners = alive_humans
            else:
                winner = "none"
                winners = []

            logger.info(f"{winner.capitalize()} win! {len(winners)} survivors")

            self.event_publisher(
                "werewolf_winner",
                {
                    "winner": winner,
                    "winners": winners,
                    "alive_humans": len(alive_humans),
                    "alive_werewolves": len(alive_werewolves),
                },
            )

            return True

        return False

    async def _kill_player_impl(self, serial: str, accel_mag: float):
        """
        Handle player death.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        player = self.players[serial]
        player.alive = False

        wolf_player = player
        alive_count = len([p for p in self.players.values() if p.alive])

        logger.info(
            f"Player died: {serial} ({'werewolf' if wolf_player.is_werewolf else 'human'}), {alive_count} remaining"
        )

        if player.span:
            player.span.add_event(
                "player_death",
                attributes={
                    "accel_magnitude": accel_mag,
                    "is_werewolf": wolf_player.is_werewolf,
                    "was_revealed": wolf_player.revealed,
                    "alive_count": alive_count,
                },
            )
            player.span.set_status(Status(StatusCode.OK))
            player.span.end()

    async def _end_game_impl(self):
        """Handle game ending."""
        logger.info("Ending Werewolf game...")
        self.state = self.state.__class__.ENDING

        # Cancel reveal task if still running
        if self.reveal_task and not self.reveal_task.done():
            self.reveal_task.cancel()

        # Determine winner
        alive_humans = [s for s in self.human_serials if self.players[s].alive]
        alive_werewolves = [s for s in self.werewolf_serials if self.players[s].alive]

        if len(alive_werewolves) > 0:
            winner = "werewolves"
            winner_serials = alive_werewolves
        elif len(alive_humans) > 0:
            winner = "humans"
            winner_serials = alive_humans
        else:
            winner = "none"
            winner_serials = []

        # Show rainbow effect on winners
        for serial in winner_serials:
            if self.gameplay_stream:
                effect_cmd = controller_manager_pb2.GameplayStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=serial,
                        effect=controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW,
                    )
                )
                await self.gameplay_stream.write(effect_cmd)
            else:
                await self.controller_client.PlayControllerEffect(
                    controller_manager_pb2.PlayControllerEffectRequest(
                        serial=serial,
                        effect=controller_manager_pb2.EFFECT_RAINBOW,
                        color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                        duration_ms=3000,
                        speed=1,  # Slow rainbow (1 cycle/second)
                    )
                )

        # Play appropriate victory sound (Joust/vox/)
        if winner == "werewolves":
            await self._play_sound(Sound.VOX_WEREWOLF_WIN, priority=2)
        elif winner == "humans":
            await self._play_sound(Sound.VOX_HUMAN_WIN, priority=2)
        else:
            await self._play_sound(Sound.SFX_WOLFDOWN, priority=2)

        # Wait for celebration
        for _ in range(20):  # 2 seconds
            if not self.running:
                break
            await asyncio.sleep(0.1)

        # End surviving player spans
        for serial, player in self.players.items():
            if player.span and player.alive:
                wolf_player = player
                is_winner = serial in winner_serials
                player.span.add_event(
                    "game_ended",
                    attributes={
                        "winner": is_winner,
                        "is_werewolf": wolf_player.is_werewolf,
                        "winning_team": winner,
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
                "winner": winner,
                "revealed": self.revealed,
            },
        )

        logger.info("Werewolf game ended")

    async def run(self):
        """
        Run the werewolf game with reveal timer.

        Override to start the reveal task during gameplay.
        """
        # Start the base game flow
        # We need to hook into gameplay to start the reveal timer
        # The cleanest way is to override run() and start the task after countdown

        # Import here to avoid circular imports
        from services.game_coordinator.games.base import GameState

        with tracer.start_as_current_span("werewolf_game") as game_span:
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

                # Additional phases (werewolf intro)
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

                # Start reveal timer as background task
                self.reveal_task = asyncio.create_task(self._reveal_werewolves())

                # Start gameplay stream
                await self._start_gameplay_stream()

                # Game loop
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
                if self.reveal_task and not self.reveal_task.done():
                    self.reveal_task.cancel()
