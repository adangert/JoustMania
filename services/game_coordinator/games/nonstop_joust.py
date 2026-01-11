"""
Nonstop Joust Game Mode - Endless respawn with scoring

Players respawn after death, compete for highest score.
Features:
- 3-second respawn countdown
- 2-second spawn protection
- Kill/death/streak tracking
- Time-limited or manual stop

This is Phase 22 - endless action gameplay mode.
"""

import asyncio
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

# Game constants
UPDATE_FREQUENCY = 60  # Hz - game tick frequency
COUNTDOWN_DURATION = 3  # seconds
RESPAWN_DURATION = 3.0  # seconds to respawn
SPAWN_PROTECTION_DURATION = 2.0  # seconds of invulnerability after spawn


# Sensitivity thresholds
class Sensitivity(Enum):
    SLOW = (1.3, 1.5)  # (warning_threshold, death_threshold)
    MEDIUM = (1.6, 1.8)
    FAST = (1.9, 2.8)


@dataclass
class NonstopPlayer:
    """Represents a player in Nonstop Joust."""

    serial: str
    team: int = 0
    alive: bool = True
    color: tuple = (255, 255, 255)
    last_accel_mag: float = 0.0
    span: trace.Span | None = None

    # Scoring (Phase 22)
    kills: int = 0
    deaths: int = 0
    current_streak: int = 0
    best_streak: int = 0
    score: int = 0

    # Respawn state (Phase 22)
    respawn_timer: float = 0.0  # Time until respawn (seconds)
    spawn_protected: bool = False
    spawn_protection_end: float = 0.0


class GameState(Enum):
    """Game lifecycle states."""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    ENDING = "ending"
    ENDED = "ended"


class NonstopJoustGame:
    """
    Nonstop Joust game mode - endless respawn with scoring.

    Players compete for highest score in time-limited or endless matches.
    Features respawn mechanics, spawn protection, and kill tracking.
    """

    def __init__(
        self,
        controller_manager_client,
        settings_client,
        event_publisher: Callable,
        game_id: str = "",
    ):
        """
        Initialize Nonstop Joust game.

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events
            game_id: Unique identifier for this game instance
        """
        self.controller_client = controller_manager_client
        self.settings_client = settings_client
        self.event_publisher = event_publisher
        self.game_id = game_id or f"nonstop_{int(time.time())}"

        # Game state
        self.state = GameState.IDLE
        self.players: dict[str, NonstopPlayer] = {}
        self.start_time = None
        self.running = False

        # Settings
        self.sensitivity = Sensitivity.MEDIUM
        self.play_audio = True
        self.time_limit = 0  # 0 = unlimited, otherwise seconds

        logger.info(f"Nonstop Joust game initialized: {self.game_id}")

    async def run(self, game_context=None):
        """Run the Nonstop Joust game.

        Args:
            game_context: Parent game_session span context for proper hierarchy
        """
        logger.info(f"Starting Nonstop Joust game: {self.game_id}")
        self.state = GameState.STARTING
        self.running = True

        # Initialization phase (load settings + initialize players)
        with tracer.start_as_current_span("initialization_phase", context=game_context) as init_span:
            init_span.set_attribute("game.id", self.game_id)
            init_span.set_attribute("game.mode", "NonstopJoust")

            # Load settings
            await self._load_settings()

            # Add settings to init span
            init_span.set_attribute("game.time_limit", self.time_limit)
            init_span.set_attribute("game.sensitivity", self.sensitivity.name)
            init_span.set_attribute("game.play_audio", self.play_audio)

            # Initialize players
            await self._initialize_players()

            if not self.players:
                logger.error("No players available to start game")
                self.state = GameState.ENDED
                return

            init_span.set_attribute("player_count", len(self.players))

        # Countdown phase
        with tracer.start_as_current_span("countdown_phase", context=game_context):
            await self._countdown()

        # Start game loop
        self.state = GameState.RUNNING
        self.start_time = time.time()

        self.event_publisher(
            "game_started",
            {
                "game_id": self.game_id,
                "game_mode": "NonstopJoust",
                "player_count": len(self.players),
            },
        )

        logger.info("Nonstop Joust game loop starting...")

        # Gameplay phase (main game loop)
        with tracer.start_as_current_span("gameplay_phase", context=game_context):
            await self._game_loop()

        # Teardown phase (end game)
        with tracer.start_as_current_span("teardown_phase", context=game_context):
            await self._end_game()

        self.state = GameState.ENDED
        logger.info(f"Nonstop Joust game ended: {self.game_id}")

    async def stop(self):
        """Stop the game (force end)."""
        logger.info(f"Force stopping Nonstop Joust game: {self.game_id}")
        self.running = False

    async def _load_settings(self):
        """Fetch game settings from Settings service."""
        try:
            from proto import settings_pb2

            response = self.settings_client.GetSettings(settings_pb2.GetSettingsRequest())

            if response.success:
                settings = response.settings
                logger.info(f"Loaded settings: {len(settings)} keys")

                # Parse sensitivity
                sens_str = settings.get("sensitivity", "MEDIUM").upper()
                if sens_str in Sensitivity.__members__:
                    self.sensitivity = Sensitivity[sens_str]

                # Parse audio setting
                self.play_audio = settings.get("play_audio", "true").lower() == "true"

                # Parse time limit (0 = unlimited)
                self.time_limit = int(settings.get("nonstop_time_limit", "0"))

            else:
                logger.warning(f"Failed to load settings: {response.error}")

        except Exception as e:
            logger.error(f"Error loading settings: {e}", exc_info=True)

    async def _initialize_players(self):
        """Get initial controller states and create player objects."""
        try:
            from proto import controller_manager_pb2

            response = self.controller_client.GetReadyControllers(
                controller_manager_pb2.GetReadyControllersRequest()
            )

            if response.success:
                for controller in response.controllers:
                    player = NonstopPlayer(
                        serial=controller.serial, team=0, alive=True, color=(255, 255, 255)
                    )
                    self.players[controller.serial] = player
                    logger.debug(f"Added player: {controller.serial}")

                logger.info(f"Initialized {len(self.players)} players")

                self.event_publisher(
                    "players_initialized",
                    {"player_count": len(self.players), "serials": list(self.players.keys())},
                )

            else:
                logger.error(f"Failed to get controllers: {response.error}")
                raise RuntimeError(f"Failed to get controllers: {response.error}")

        except Exception as e:
            logger.error(f"Error initializing players: {e}", exc_info=True)
            raise

    async def _countdown(self):
        """Run countdown before game starts."""
        from proto import controller_manager_pb2

        logger.info("Starting countdown...")
        self.event_publisher("countdown_start", {"duration": COUNTDOWN_DURATION})

        # Countdown colors: Red -> Yellow -> Green
        countdown_colors = [
            (255, 0, 0),  # Red (3 seconds)
            (255, 255, 0),  # Yellow (2 seconds)
            (0, 255, 0),  # Green (1 second)
        ]

        for i, (r, g, b) in enumerate(countdown_colors):
            if not self.running:
                logger.info("Countdown interrupted by force_end")
                return

            # Set color on all controllers
            color_request = controller_manager_pb2.SetControllerColorRequest(
                serial="",  # Empty = all controllers
                color=controller_manager_pb2.RGB(r=r, g=g, b=b),
                duration_ms=0,
            )
            await self.controller_client.SetControllerColor(color_request)

            # Wait 1 second
            for _ in range(10):
                if not self.running:
                    logger.info("Countdown interrupted by force_end")
                    return
                await asyncio.sleep(0.1)

        self.event_publisher("countdown_end", {})
        logger.info("Countdown complete")

    async def _game_loop(self):
        """Main game loop - processes controller states, respawns, and checks victory."""
        logger.info("Starting game loop...")

        try:
            from proto import controller_manager_pb2

            # Start per-player lifecycle spans
            for serial, player in self.players.items():
                player_span = tracer.start_span(
                    f"player_{serial}_lifecycle",
                    attributes={"player.serial": serial, "game.mode": "NonstopJoust"},
                )
                player.span = player_span
                logger.debug(f"Started lifecycle span for player {serial}")

            # Start streaming controller states
            stream_request = controller_manager_pb2.StreamRequest(
                update_frequency_hz=UPDATE_FREQUENCY
            )


            # Track game progress for periodic telemetry
            last_progress_event = time.time()
            game_tick = 0

            # Stream controller states and process game logic
            async for state_update in self.controller_client.StreamControllerStates(
                stream_request
            ):
                if not self.running:
                    break

                game_tick += 1

                # Process each controller's state
                for controller_state in state_update.controllers:
                    await self._process_controller_state(controller_state)

                # Update respawn timers
                await self._update_respawn_timers()

                # Periodic progress events (every 30 seconds)
                current_time = time.time()
                if current_time - last_progress_event >= 30.0:
                    total_deaths = sum(p.deaths for p in self.players.values())
                    total_respawns = sum(
                        1 for p in self.players.values() if p.respawn_timer > 0
                    )
                    alive_count = sum(1 for p in self.players.values() if p.alive)

                    last_progress_event = current_time

                # Check time limit
                if self._check_time_limit():
                    break

                # Small sleep to maintain tick rate
                await asyncio.sleep(1.0 / UPDATE_FREQUENCY)

        except Exception as e:
            logger.error(f"Game loop error: {e}", exc_info=True)
            raise

    async def _process_controller_state(self, controller_state):
        """
        Process a single controller's state and check for death.

        Args:
            controller_state: ControllerState protobuf message
        """
        serial = controller_state.serial

        if serial not in self.players:
            return  # Unknown controller

        player = self.players[serial]

        if not player.alive:
            return  # Dead player, ignore

        # Calculate acceleration magnitude
        accel = controller_state.accel
        accel_mag = math.sqrt(accel.x**2 + accel.y**2 + accel.z**2)

        player.last_accel_mag = accel_mag

        # Skip death checks during spawn protection
        if player.spawn_protected:
            return

        # Get thresholds
        warn_threshold, death_threshold = self.sensitivity.value

        # Check for death
        if accel_mag > death_threshold:
            await self._kill_player(serial, accel_mag)

        # Check for warning (flash controller)
        elif accel_mag > warn_threshold:
            await self._warn_player(serial, accel_mag)

    async def _warn_player(self, serial: str, accel_mag: float):
        """
        Warn a player that they're moving too much.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that triggered warning
        """
        from proto import controller_manager_pb2

        player = self.players.get(serial)
        if not player or not player.alive:
            return

        # Add warning event to player's lifecycle span
        if player.span:
            player.span.add_event(
                "death_warning",
                attributes={"accel_magnitude": accel_mag, "threshold": self.sensitivity.value[0]},
            )
            logger.debug(f"Player {serial} triggered warning (accel: {accel_mag:.2f})")

        # Flash controller LED (orange warning)
        flash_request = controller_manager_pb2.SetControllerColorRequest(
            serial=serial,
            color=controller_manager_pb2.RGB(r=255, g=128, b=0),  # Orange
            duration_ms=200,
        )
        await self.controller_client.SetControllerColor(flash_request)

        # Vibrate controller briefly
        vibrate_request = controller_manager_pb2.SetControllerVibrationRequest(
            serial=serial, intensity=100, duration_ms=200
        )
        await self.controller_client.SetControllerVibration(vibrate_request)

    async def _kill_player(self, serial: str, accel_mag: float):
        """
        Kill a player and start respawn timer.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        from proto import controller_manager_pb2

        player = self.players.get(serial)
        if not player or not player.alive:
            return

        player.alive = False
        player.deaths += 1
        player.current_streak = 0
        player.respawn_timer = RESPAWN_DURATION


        logger.info(
            f"Player died: {serial} (kills: {player.kills}, deaths: {player.deaths}, score: {player.score})"
        )

        # Add death event to player's lifecycle span
        if player.span:
            player.span.add_event(
                "player_death",
                attributes={
                    "accel_magnitude": accel_mag,
                    "threshold": self.sensitivity.value[1],
                    "kills": player.kills,
                    "deaths": player.deaths,
                    "score": player.score,
                },
            )

        # Publish death event
        self.event_publisher(
            "player_death",
            {
                "serial": serial,
                "accel_magnitude": accel_mag,
                "kills": player.kills,
                "deaths": player.deaths,
                "score": player.score,
            },
        )

        # Set controller color to red (death indication)
        death_color_request = controller_manager_pb2.SetControllerColorRequest(
            serial=serial,
            color=controller_manager_pb2.RGB(r=255, g=0, b=0),  # Red
            duration_ms=0,
        )
        await self.controller_client.SetControllerColor(death_color_request)

        # Strong vibration on death
        death_vibrate_request = controller_manager_pb2.SetControllerVibrationRequest(
            serial=serial, intensity=255, duration_ms=500
        )
        await self.controller_client.SetControllerVibration(death_vibrate_request)

    async def _update_respawn_timers(self):
        """Update respawn timers and respawn players."""
        from proto import controller_manager_pb2

        current_time = time.time()

        for serial, player in self.players.items():
            # Handle respawn countdown
            if not player.alive and player.respawn_timer > 0:
                player.respawn_timer -= 1.0 / UPDATE_FREQUENCY

                # Show respawn countdown colors
                await self._show_respawn_countdown(serial, player.respawn_timer)

                # Respawn when timer reaches 0
                if player.respawn_timer <= 0:
                    await self._respawn_player(serial)

            # Check spawn protection expiration
            if player.spawn_protected and current_time >= player.spawn_protection_end:
                player.spawn_protected = False
                # Return to normal white color
                color_request = controller_manager_pb2.SetControllerColorRequest(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=255, g=255, b=255),  # White
                    duration_ms=0,
                )
                await self.controller_client.SetControllerColor(color_request)

    async def _show_respawn_countdown(self, serial: str, time_remaining: float):
        """
        Show respawn countdown colors.

        Args:
            serial: Controller serial number
            time_remaining: Seconds until respawn
        """
        from proto import controller_manager_pb2

        # Countdown colors: Gray -> Yellow -> Green
        if time_remaining > 2.0:
            color = (128, 128, 128)  # Gray (3s)
        elif time_remaining > 1.0:
            color = (255, 255, 0)  # Yellow (2s)
        else:
            color = (0, 255, 0)  # Green (1s)

        # Only update if color changed (avoid spamming)
        player = self.players[serial]
        if not hasattr(player, "_last_respawn_color") or player._last_respawn_color != color:
            player._last_respawn_color = color
            color_request = controller_manager_pb2.SetControllerColorRequest(
                serial=serial,
                color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
                duration_ms=0,
            )
            await self.controller_client.SetControllerColor(color_request)

    async def _respawn_player(self, serial: str):
        """
        Respawn a dead player.

        Args:
            serial: Controller serial number
        """
        from proto import controller_manager_pb2

        player = self.players[serial]
        player.alive = True
        player.spawn_protected = True
        player.spawn_protection_end = time.time() + SPAWN_PROTECTION_DURATION


        # Add respawn event to player's lifecycle span
        if player.span:
            player.span.add_event(
                "player_respawned",
                {"kills": player.kills, "deaths": player.deaths, "score": player.score},
            )

        logger.info(f"Player respawned: {serial} (spawn protection active)")

        # White pulsing glow during spawn protection
        # For now, just set white - can implement pulse effect later
        protection_color_request = controller_manager_pb2.SetControllerColorRequest(
            serial=serial,
            color=controller_manager_pb2.RGB(r=255, g=255, b=255),  # White
            duration_ms=0,
        )
        await self.controller_client.SetControllerColor(protection_color_request)

        # Publish respawn event
        self.event_publisher(
            "player_respawned",
            {
                "serial": serial,
                "kills": player.kills,
                "deaths": player.deaths,
                "score": player.score,
            },
        )

    def _check_time_limit(self) -> bool:
        """
        Check if time limit has been reached.

        Returns:
            True if game should end, False otherwise
        """
        if self.time_limit == 0:
            return False  # Unlimited mode

        if not self.start_time:
            return False

        elapsed = time.time() - self.start_time
        if elapsed >= self.time_limit:
            logger.info(f"Time limit reached: {elapsed:.1f}s / {self.time_limit}s")
            return True

        return False

    async def _end_game(self):
        """Handle game ending - determine winner, cleanup."""
        from proto import controller_manager_pb2

        logger.info("Ending game...")
        self.state = GameState.ENDING

        # Calculate final scores (inverse of deaths - fewer deaths = higher score)
        # Score = 100 - (deaths * 10), minimum 0
        for player in self.players.values():
            player.score = max(0, 100 - (player.deaths * 10))

        # Add final game statistics to span
        total_deaths = sum(p.deaths for p in self.players.values())
        avg_deaths = total_deaths / len(self.players) if self.players else 0
        game_duration = time.time() - self.start_time if self.start_time else 0


        # Determine winner (highest score, tie-break by fewest deaths)
        winner = max(self.players.values(), key=lambda p: (p.score, -p.deaths), default=None)

        if winner:
            logger.info(
                f"Winner: {winner.serial} with score {winner.score} (K:{winner.kills} D:{winner.deaths})"
            )

            # Show rainbow effect on winner's controller
            rainbow_request = controller_manager_pb2.PlayControllerEffectRequest(
                serial=winner.serial,
                effect=controller_manager_pb2.EFFECT_RAINBOW,
                color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                duration_ms=3000,  # 3 seconds
                speed=5,
            )
            await self.controller_client.PlayControllerEffect(rainbow_request)

            self.event_publisher(
                "game_winner",
                {
                    "serial": winner.serial,
                    "score": winner.score,
                    "kills": winner.kills,
                    "deaths": winner.deaths,
                    "best_streak": winner.best_streak,
                },
            )

        # End spans for all players
        for serial, player in self.players.items():
            if player.span:
                player.span.add_event(
                    "game_ended",
                    attributes={
                        "game_duration": time.time() - self.start_time
                        if self.start_time
                        else 0,
                        "score": player.score,
                        "kills": player.kills,
                        "deaths": player.deaths,
                        "best_streak": player.best_streak,
                        "winner": player == winner,
                    },
                )
                player.span.set_status(Status(StatusCode.OK))
                player.span.end()
                logger.debug(f"Ended lifecycle span for player {serial}")

        # Show winner for a bit
        for _ in range(30):  # 3 seconds in 0.1s increments
            if not self.running:
                logger.info("End game interrupted by force_end")
                break
            await asyncio.sleep(0.1)

        self.state = GameState.ENDED
        self.event_publisher(
            "game_ended",
            {
                "game_id": self.game_id,
                "duration": time.time() - self.start_time if self.start_time else 0,
            },
        )
