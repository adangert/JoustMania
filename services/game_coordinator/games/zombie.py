"""
Zombie Game Mode - gRPC-based implementation

Humans vs Zombies asymmetric gameplay. When zombies "kill" humans,
they become zombies. Humans win if they survive the time limit,
zombies win if all humans are converted.

Note: Weapon system (trigger button to shoot zombies) requires button
event support in gameplay stream - not yet implemented.

Original JoustMania behavior preserved (minus weapon system).
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
INITIAL_ZOMBIES = 2  # Number of starting zombies
ZOMBIE_RESPAWN_MIN = 2.0  # Minimum respawn delay for zombies
ZOMBIE_RESPAWN_MAX = 10.0  # Maximum respawn delay for zombies

# Colors
HUMAN_COLOR = (255, 255, 255)  # White for humans
ZOMBIE_COLOR = (80, 80, 120)  # Blue-gray for zombies

# Zombie thresholds - zombies are harder to kill
ZOMBIE_THRESHOLDS = {
    Sensitivity.ULTRA_SLOW: (1.4, 1.6),
    Sensitivity.SLOW: (1.7, 1.9),
    Sensitivity.MEDIUM: (2.1, 2.6),
    Sensitivity.FAST: (2.9, 3.9),
    Sensitivity.ULTRA_FAST: (3.5, 4.5),
}


def calculate_game_duration(num_players: int) -> float:
    """
    Calculate game duration based on player count.

    Scales from ~3 minutes for 4 players to ~6.75 minutes for 12 players.

    Args:
        num_players: Total number of players

    Returns:
        Game duration in seconds
    """
    return ((num_players * 3) / 16) * 60


@dataclass
class ZombiePlayer(Player):
    """Extended Player class with zombie information."""

    is_zombie: bool = False
    respawn_until: float = 0.0  # Time when zombie can respawn (0 = not respawning)


class ZombieGame(BaseGameMode):
    """
    Zombie game mode using gRPC communication.

    Asymmetric gameplay:
    - 2 players start as zombies (blue-gray)
    - Rest are humans (white)
    - When a human "dies" (exceeds threshold), they become a zombie
    - Zombies have higher thresholds (harder to kill)
    - Zombies respawn after a delay when killed
    - Humans win if time expires with at least one human alive
    - Zombies win if all humans are converted

    Note: Weapon system not implemented (requires button events in gameplay stream).
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
        Initialize Zombie game.

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

        self.zombie_serials: list[str] = []
        self.human_serials: list[str] = []
        self.game_duration: float = 180.0  # Will be calculated based on player count
        self.time_remaining: float = 0.0
        self.timer_task: asyncio.Task | None = None
        self.game_span: trace.Span | None = None

    def get_game_name(self) -> str:
        """Return game mode identifier."""
        return "Zombie"

    async def _initialize_players_impl(self, controllers: list):
        """
        Initialize players and assign initial zombies.

        Args:
            controllers: List of controller protobuf messages
        """
        num_players = len(controllers)
        self.game_duration = calculate_game_duration(num_players)
        self.time_remaining = self.game_duration

        # Randomly select initial zombies
        serials = [c.serial for c in controllers]
        num_zombies = min(INITIAL_ZOMBIES, num_players - 1)  # At least 1 human
        zombie_serials = set(random.sample(serials, num_zombies))

        for controller in controllers:
            is_zombie = controller.serial in zombie_serials
            color = ZOMBIE_COLOR if is_zombie else HUMAN_COLOR

            player = ZombiePlayer(
                serial=controller.serial,
                team=1 if is_zombie else 0,  # Team 0 = humans, Team 1 = zombies
                alive=True,
                color=color,
                is_zombie=is_zombie,
            )
            self.players[controller.serial] = player

            if is_zombie:
                self.zombie_serials.append(controller.serial)
            else:
                self.human_serials.append(controller.serial)

            logger.debug(f"Added player: {controller.serial} ({'zombie' if is_zombie else 'human'})")

        logger.info(
            f"Initialized {num_players} players: {len(self.human_serials)} humans, "
            f"{len(self.zombie_serials)} zombies. Game duration: {self.game_duration:.0f}s"
        )

        self.event_publisher(
            "players_initialized",
            {
                "player_count": num_players,
                "zombie_count": len(self.zombie_serials),
                "human_count": len(self.human_serials),
                "game_duration": self.game_duration,
                "serials": list(self.players.keys()),
            },
        )

    def _create_player_spans(self):
        """Create flat player lifecycle spans, parented to game span."""
        if not self.game_span:
            logger.warning("No game_span available, creating orphan player spans")
            for serial, player in self.players.items():
                zombie_player = player
                player.span = tracer.start_span(
                    "player_lifecycle",
                    attributes={
                        "player.serial": serial,
                        "player.is_zombie": zombie_player.is_zombie,
                        "player.team": "zombie" if zombie_player.is_zombie else "human",
                        "game.mode": self.get_game_name(),
                    },
                )
            return

        # Create player spans as children of game span
        with trace.use_span(self.game_span, end_on_exit=False):
            for serial, player in self.players.items():
                zombie_player = player
                player.span = tracer.start_span(
                    "player_lifecycle",
                    attributes={
                        "player.serial": serial,
                        "player.is_zombie": zombie_player.is_zombie,
                        "player.team": "zombie" if zombie_player.is_zombie else "human",
                        "game.mode": self.get_game_name(),
                    },
                )
                logger.debug(f"Created span for player {serial}")

    def _get_additional_phases(self) -> list:
        """Return zombie intro phase."""
        return [Phase(name="zombie_intro", execute=self._zombie_intro_phase)]

    async def _zombie_intro_phase(self):
        """
        Zombie introduction phase.

        Show players their roles with appropriate colors.
        """
        logger.info("Starting zombie intro phase...")

        self.event_publisher(
            "zombie_intro_start",
            {
                "zombie_count": len(self.zombie_serials),
                "human_count": len(self.human_serials),
            },
        )

        # Set initial colors
        for serial, player in self.players.items():
            zombie_player = player
            color = ZOMBIE_COLOR if zombie_player.is_zombie else HUMAN_COLOR

            base_color_cmd = controller_manager_pb2.GameplayStreamControl(
                base_color=controller_manager_pb2.ControllerColorConfig(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
                )
            )
            await self.gameplay_stream.write(base_color_cmd)

        # Play intro sound (use start sound - no dedicated zombie intro exists)
        await self._play_sound(Sound.SFX_START3, priority=2)

        # Wait for intro
        for _ in range(30):  # 3 seconds
            if not self.running:
                return
            await asyncio.sleep(0.1)

        self.event_publisher("zombie_intro_end", {})
        logger.info("Zombie intro phase complete")

    def _get_effective_thresholds(self, player: Player) -> tuple[float, float]:
        """
        Get death thresholds for a player.

        Zombies have higher thresholds.
        """
        zombie_player = player
        if zombie_player.is_zombie:
            return ZOMBIE_THRESHOLDS.get(self.sensitivity, (2.1, 2.6))
        return self.sensitivity.value

    async def _game_timer(self):
        """
        Track game time and announce remaining time.

        Runs as a background task during gameplay.
        """
        announcements = [180, 60, 30, 10]  # Seconds remaining to announce

        while self.running and self.time_remaining > 0:
            await asyncio.sleep(1.0)
            self.time_remaining -= 1.0

            # Check for time announcements
            for seconds in announcements:
                if abs(self.time_remaining - seconds) < 0.5:
                    logger.info(f"Time announcement: {seconds} seconds remaining")
                    self.event_publisher("time_announcement", {"seconds_remaining": seconds})
                    # Play time announcement sound (Zombie/vox/ directory)
                    if seconds == 60:
                        await self._play_sound(Sound.VOX_ZOMBIE_ONE_MINUTE, priority=2)
                    elif seconds == 30:
                        await self._play_sound(Sound.VOX_ZOMBIE_THIRTY_SECONDS, priority=2)
                    elif seconds == 10:
                        await self._play_sound(Sound.VOX_ZOMBIE_TEN_SECONDS, priority=2)
                    break

        # Time's up - humans win if any survive
        if self.running and self.time_remaining <= 0:
            logger.info("Time's up! Checking for human survivors...")

    def _check_win_condition(self) -> bool:
        """
        Check if the game should end.

        Zombies win if all humans are converted.
        Humans win if time expires with at least one human alive.
        """
        # Count alive humans (not counting converting players)
        alive_humans = [s for s in self.human_serials if self.players[s].alive and not self.players[s].is_zombie]

        # Check if all humans converted
        if len(alive_humans) == 0:
            logger.info("All humans converted! Zombies win!")
            self.event_publisher(
                "zombie_winner",
                {
                    "winner": "zombies",
                    "zombie_count": len(self.zombie_serials),
                },
            )
            return True

        # Check if time expired
        if self.time_remaining <= 0:
            logger.info(f"Time's up! Humans win with {len(alive_humans)} survivors!")
            self.event_publisher(
                "zombie_winner",
                {
                    "winner": "humans",
                    "survivors": alive_humans,
                    "survivor_count": len(alive_humans),
                },
            )
            return True

        return False

    async def _kill_player_impl(self, serial: str, accel_mag: float):
        """
        Handle player death/conversion.

        - Humans become zombies when killed
        - Zombies respawn after a delay

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        player = self.players[serial]
        zombie_player = player

        if zombie_player.is_zombie:
            # Zombie killed - set respawn timer
            zombie_player.alive = False
            respawn_delay = random.uniform(ZOMBIE_RESPAWN_MIN, ZOMBIE_RESPAWN_MAX)
            zombie_player.respawn_until = time.time() + respawn_delay

            logger.info(f"Zombie {serial} killed, respawning in {respawn_delay:.1f}s")

            # Start respawn task
            asyncio.create_task(self._respawn_zombie(serial, respawn_delay))

            if player.span:
                player.span.add_event(
                    "zombie_killed",
                    attributes={
                        "accel_magnitude": accel_mag,
                        "respawn_delay": respawn_delay,
                    },
                )
        else:
            # Human killed - convert to zombie!
            zombie_player.alive = True  # Stays alive as zombie
            zombie_player.is_zombie = True
            zombie_player.color = ZOMBIE_COLOR
            zombie_player.team = 1

            # Update lists
            if serial in self.human_serials:
                self.human_serials.remove(serial)
            if serial not in self.zombie_serials:
                self.zombie_serials.append(serial)

            logger.info(f"Human {serial} converted to zombie! {len(self.human_serials)} humans remain")

            # Update color to zombie - death flash then zombie color
            flash_cmd = controller_manager_pb2.GameplayStreamControl(
                game_effect=controller_manager_pb2.GameEffectCommand(
                    serial=serial,
                    effect=controller_manager_pb2.GAME_EFFECT_PLAYER_DEATH,
                )
            )
            await self.gameplay_stream.write(flash_cmd)

            await asyncio.sleep(0.5)

            base_color_cmd = controller_manager_pb2.GameplayStreamControl(
                base_color=controller_manager_pb2.ControllerColorConfig(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=ZOMBIE_COLOR[0], g=ZOMBIE_COLOR[1], b=ZOMBIE_COLOR[2]),
                )
            )
            await self.gameplay_stream.write(base_color_cmd)

            # Play conversion sound (use zombie death sound for conversion)
            await self._play_sound(Sound.VOX_ZOMBIE_DEATH, priority=2)

            if player.span:
                player.span.add_event(
                    "human_converted",
                    attributes={
                        "accel_magnitude": accel_mag,
                        "remaining_humans": len(self.human_serials),
                    },
                )

            self.event_publisher(
                "human_converted",
                {
                    "serial": serial,
                    "remaining_humans": len(self.human_serials),
                    "total_zombies": len(self.zombie_serials),
                },
            )

    async def _respawn_zombie(self, serial: str, delay: float):
        """
        Respawn a zombie after the delay.

        Args:
            serial: Controller serial number
            delay: Respawn delay in seconds
        """
        await asyncio.sleep(delay)

        if not self.running:
            return

        player = self.players.get(serial)
        if player and player.is_zombie:
            zombie_player = player
            zombie_player.alive = True
            zombie_player.respawn_until = 0.0
            zombie_player.grace_until = time.time() + 2.0  # Grace period after respawn

            logger.info(f"Zombie {serial} respawned!")

            # Flash to indicate respawn
            if self.gameplay_stream:
                flash_cmd = controller_manager_pb2.GameplayStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=serial,
                        effect=controller_manager_pb2.GAME_EFFECT_FLASH,
                    )
                )
                await self.gameplay_stream.write(flash_cmd)

            if player.span:
                player.span.add_event("zombie_respawned", {})

    async def _end_game_impl(self):
        """Handle game ending."""
        logger.info("Ending Zombie game...")
        self.state = self.state.__class__.ENDING

        # Cancel timer task
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()

        # Determine winner
        alive_humans = [s for s in self.human_serials if self.players[s].alive]

        if self.time_remaining <= 0 and len(alive_humans) > 0:
            winner = "humans"
            winner_serials = alive_humans
        else:
            winner = "zombies"
            winner_serials = self.zombie_serials

        # Show rainbow effect on winners
        if self.gameplay_stream:
            for serial in winner_serials:
                player = self.players.get(serial)
                if player and player.alive:
                    effect_cmd = controller_manager_pb2.GameplayStreamControl(
                        game_effect=controller_manager_pb2.GameEffectCommand(
                            serial=serial,
                            effect=controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW,
                        )
                    )
                    await self.gameplay_stream.write(effect_cmd)

        # Play victory sound (Zombie/vox/ directory)
        if winner == "humans":
            await self._play_sound(Sound.VOX_HUMAN_VICTORY, priority=2)
        else:
            await self._play_sound(Sound.VOX_ZOMBIE_VICTORY, priority=2)

        # Wait for celebration
        for _ in range(20):  # 2 seconds
            if not self.running:
                break
            await asyncio.sleep(0.1)

        # End all player spans
        for serial, player in self.players.items():
            if player.span:
                zombie_player = player
                is_winner = serial in winner_serials
                player.span.add_event(
                    "game_ended",
                    attributes={
                        "winner": is_winner,
                        "is_zombie": zombie_player.is_zombie,
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
                "time_remaining": self.time_remaining,
            },
        )

        logger.info("Zombie game ended")

    async def run(self):
        """
        Run the zombie game with timer.

        Override to start the game timer during gameplay.
        """
        from services.game_coordinator.games.base import GameState

        with tracer.start_as_current_span("zombie_game") as game_span:
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

                # Additional phases (zombie intro)
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

                # Start game timer as background task
                self.timer_task = asyncio.create_task(self._game_timer())

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
                if self.timer_task and not self.timer_task.done():
                    self.timer_task.cancel()
