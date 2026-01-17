"""
BaseGameMode - Abstract base class for all game modes

Phase 36b: Extracts common patterns from FFA, Teams, Random Teams, and Nonstop Joust.
Provides consistent span hierarchy orchestration and common game operations.

Uses Template Method pattern:
- run() orchestrates the entire game lifecycle with spans
- Concrete methods implement shared behavior (settings, countdown, game loop)
- Abstract methods define game-specific behavior (team assignment, win conditions, etc.)

Phase 70: Added dynamic music tempo system.
"""

import asyncio
import contextlib
import logging
import math
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from opentelemetry import trace

from lib.types import GameEvent
from services.game_coordinator import metrics
from services.game_coordinator.runtime_config import get_config_manager

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

# Game constants (Phase 43: Now uses runtime config for dynamic adjustment)
# Phase 72: Increased from 30Hz to 60Hz for better responsiveness
UPDATE_FREQUENCY = 60  # Hz - default, overridden by runtime config
COUNTDOWN_DURATION = 3  # seconds

# Phase 70: Music tempo constants (from original JoustMania)
SLOW_MUSIC_SPEED = 1.0  # Normal playback
FAST_MUSIC_SPEED = 1.3  # 30% faster
MUSIC_TRANSITION_DURATION = 1.5  # Seconds to smoothly transition

# Music timing intervals (seconds) - how long before next tempo change
MIN_MUSIC_FAST_TIME = 4  # Minimum time at fast speed
MAX_MUSIC_FAST_TIME = 8  # Maximum time at fast speed
MIN_MUSIC_SLOW_TIME = 10  # Minimum time at slow speed
MAX_MUSIC_SLOW_TIME = 23  # Maximum time at slow speed

# End game timing (more frequent changes as game progresses)
END_MIN_MUSIC_FAST_TIME = 6
END_MAX_MUSIC_FAST_TIME = 10
END_MIN_MUSIC_SLOW_TIME = 8
END_MAX_MUSIC_SLOW_TIME = 12

# Volume levels
GAME_VOLUME = 0.7


# Sensitivity thresholds (in raw accelerometer units, ~4096 = 1g)
# PSMove accelerometer returns raw values where gravity alone = ~4096
# Thresholds are in raw units to avoid per-frame division
class Sensitivity(Enum):
    SLOW = (5300, 6100)  # ~1.3g warning, ~1.5g death
    MEDIUM = (6500, 7400)  # ~1.6g warning, ~1.8g death
    FAST = (7800, 11500)  # ~1.9g warning, ~2.8g death


# Warning feedback duration (seconds) - flash + rumble time
# This is purely visual feedback, NOT protection (player can still die during warning)
WARNING_DURATION = 0.5

# Grace periods - no death or warning during these times (matches original JoustMania)
GAME_START_GRACE_PERIOD = 2.0  # seconds of invincibility at game start
DEATH_GRACE_PERIOD = 0.5  # seconds of invincibility after death (for respawn modes)

# Log at import time to verify correct version is deployed
logger.info(f"base.py loaded: WARNING_DURATION={WARNING_DURATION}s, GAME_START_GRACE={GAME_START_GRACE_PERIOD}s")


@dataclass
class Player:
    """Represents a player in the game."""

    serial: str
    team: int = 0
    alive: bool = True
    color: tuple = (255, 255, 255)
    last_accel_mag: float = 0.0
    # Exponential moving average of acceleration (from original JoustMania)
    # EMA smooths sensor noise and prevents false positives from single-frame spikes
    smoothed_accel: float = 0.0
    span: trace.Span | None = None  # OpenTelemetry span for this player's lifecycle
    # Grace period: no death or warning checks until this timestamp
    # Set at game start (2s) and after death (0.5s) - matches original JoustMania
    grace_until: float = 0.0
    # Warning state: when > 0, player is in warning feedback (flash + rumble)
    # This is purely visual - player CAN still die during warning (matches original)
    warning_until: float = 0.0


@dataclass
class Phase:
    """Represents a game phase with a name and execution method."""

    name: str
    execute: callable


class GameState(Enum):
    """Game lifecycle states."""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    ENDING = "ending"
    ENDED = "ended"


def get_game_display_name(mode: str) -> str:
    """
    Convert game mode identifier to human-readable display name.

    Phase 36: Standardized human-readable names for spans.
    """
    mapping = {
        "FFA": "Free-For-All",
        "Teams": "Teams",
        "Random Teams": "Random Teams",
        "Nonstop Joust": "Nonstop Joust",
    }
    return mapping.get(mode, mode)


class BaseGameMode(ABC):
    """
    Abstract base class for all game modes.

    Provides:
    - Template method run() for consistent game lifecycle orchestration
    - Concrete methods for shared operations (settings, countdown, controller processing)
    - Abstract methods for game-specific behavior (team assignment, win conditions, etc.)
    - Consistent OpenTelemetry span hierarchy across all game modes

    Subclasses must implement:
    - get_game_name() - return game mode identifier
    - _initialize_players_impl() - assign players to teams
    - _create_player_spans() - create lifecycle spans (flat vs hierarchical)
    - _check_win_condition() - determine if game should end
    - _kill_player_impl() - handle player death (stay dead vs respawn)
    - _get_additional_phases() - return extra phases (e.g., team_formation)
    - _end_game_impl() - cleanup and declare winner
    """

    def __init__(
        self,
        controller_manager_client: Any,  # controller_manager_pb2_grpc.ControllerManagerServiceStub
        settings_client: Any,  # settings_pb2_grpc.SettingsServiceStub
        event_publisher: Callable[[str, dict[str, str]], None],
        audio_client: Any | None = None,  # audio_pb2_grpc.AudioServiceStub
        game_id: str = "",
        initial_players: list | None = None,  # List of Player protobuf messages
    ) -> None:
        """
        Initialize base game mode (Phase 33 - added type hints).

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events (event_type, data)
            audio_client: gRPC stub for Audio service (Phase 29)
            initial_players: Optional list of Player protobuf messages from StartGame RPC
            game_id: Unique identifier for this game instance
        """
        self.controller_client = controller_manager_client
        self.settings_client = settings_client
        self.event_publisher = event_publisher
        self.audio_client = audio_client

        # Game ID - subclasses can override with mode-specific prefix
        if not game_id:
            mode_prefix = self.get_game_name().lower().replace(" ", "_")
            game_id = f"{mode_prefix}_{int(time.time())}"
        self.game_id = game_id

        # Game state
        self.state = GameState.IDLE
        self.players: dict[str, Player] = {}
        self.initial_players = initial_players  # Players from StartGame RPC
        self.start_time = None
        self.running = False
        self.gameplay_stream = None  # Phase 46: Bidirectional stream for feedback commands

        # Settings (will be fetched from Settings service)
        self.sensitivity = Sensitivity.MEDIUM
        self.play_audio = True
        self.settings = {}  # Store raw settings dict

        # Phase 70: Music tempo control state
        self.music_track_id = None
        self.music_speed = SLOW_MUSIC_SPEED
        self.speed_up = True  # True = next change will speed up, False = slow down
        self.change_time = 0.0  # Time of next tempo change
        self.music_loop_task = None
        self.dead_count = 0  # Track deaths for tempo timing

        logger.info(f"{self.get_game_name()} game initialized: {self.game_id}")

    # ========================================================================
    # Abstract Methods - Subclasses MUST implement these
    # ========================================================================

    @abstractmethod
    def get_game_name(self) -> str:
        """
        Return game mode identifier for logging and span naming.

        Returns:
            Game mode name (e.g., "FFA", "Teams", "Nonstop Joust")
        """
        pass

    @abstractmethod
    async def _initialize_players_impl(self, controllers: list):
        """
        Initialize players with game-specific logic (team assignment, etc.).

        Args:
            controllers: List of controller protobuf messages from GetReadyControllers

        Subclass responsibilities:
        - Create Player objects and add to self.players
        - Assign teams (FFA uses team=0 for all, Teams uses round-robin, etc.)
        - Set controller colors
        """
        pass

    @abstractmethod
    def _create_player_spans(self, game_context):
        """
        Create player/team lifecycle spans with game-specific hierarchy.

        Args:
            game_context: Parent span context for proper hierarchy

        FFA: Flat hierarchy - player spans directly under gameplay_phase
        Teams/Random Teams: Hierarchical - team spans → player spans
        Nonstop Joust: Flat hierarchy like FFA
        """
        pass

    @abstractmethod
    def _check_win_condition(self) -> bool:
        """
        Check if game should end.

        Returns:
            True if game should end, False otherwise

        FFA: Last player standing (len(alive_players) <= 1)
        Teams: Last team standing (len(alive_teams) <= 1)
        Nonstop Joust: Time limit reached
        """
        pass

    @abstractmethod
    async def _kill_player_impl(self, serial: str, accel_mag: float):
        """
        Handle player death with game-specific logic.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death

        FFA/Teams: Player stays dead, end their lifecycle span
        Nonstop Joust: Player respawns, add death event but keep span open
        """
        pass

    @abstractmethod
    def _get_additional_phases(self) -> list:
        """
        Return extra phases to execute before countdown (e.g., team_formation).

        Returns:
            List of phase objects with name and execute() method

        FFA/Teams/Nonstop: return []
        Random Teams: return [TeamFormationPhase]
        """
        pass

    @abstractmethod
    async def _end_game_impl(self):
        """
        Handle game ending with game-specific logic.

        Responsibilities:
        - Close any remaining player/team lifecycle spans
        - Determine and declare winner
        - Set controller colors/effects for winner
        - Publish game_ended event
        """
        pass

    # ========================================================================
    # Concrete Methods - Shared implementation used by all subclasses
    # ========================================================================

    async def _load_settings(self):
        """Fetch game settings from Settings service."""
        try:
            from proto import settings_pb2

            response = await self.settings_client.GetSettings(settings_pb2.GetSettingsRequest())

            if response.success:
                self.settings = dict(response.settings)
                logger.info(f"Loaded settings: {len(self.settings)} keys")

                # Parse sensitivity
                sens_str = self.settings.get("sensitivity", "MEDIUM").upper()
                if sens_str in Sensitivity.__members__:
                    self.sensitivity = Sensitivity[sens_str]

                # Parse audio setting
                self.play_audio = self.settings.get("play_audio", "true").lower() == "true"

            else:
                logger.warning(f"Failed to load settings: {response.error}")

        except Exception as e:
            logger.error(f"Error loading settings: {e}", exc_info=True)
            # Use defaults

    async def _initialize_players(self):
        """Get ready controllers and initialize players via subclass implementation."""
        try:
            from proto import controller_manager_pb2

            # If initial_players were provided (from StartGame RPC), use them
            if self.initial_players:
                # Convert protobuf Player messages to controller-like objects for _initialize_players_impl
                # _initialize_players_impl expects controllers with .serial attribute
                class ControllerStub:
                    def __init__(self, serial):
                        self.serial = serial

                controllers = [ControllerStub(p.serial) for p in self.initial_players]
                await self._initialize_players_impl(controllers)

                logger.info(f"Initialized {len(self.players)} players from StartGame RPC")
            else:
                # Fall back to querying controller manager
                response = await self.controller_client.GetReadyControllers(
                    controller_manager_pb2.GetReadyControllersRequest()
                )

                if response.success:
                    # Call subclass-specific initialization
                    await self._initialize_players_impl(list(response.controllers))

                    logger.info(f"Initialized {len(self.players)} players from controller manager")
                else:
                    logger.error(f"Failed to get controllers: {response.error}")
                    raise RuntimeError(f"Failed to get controllers: {response.error}")

            # Publish event
            self.event_publisher(
                GameEvent.PLAYERS_INITIALIZED,
                {
                    "player_count": len(self.players),
                    "serials": list(self.players.keys()),
                },
            )

        except Exception as e:
            logger.error(f"Error initializing players: {e}", exc_info=True)
            raise

    async def _countdown(self):
        """Run countdown before game starts."""
        from proto import controller_manager_pb2

        logger.info("Starting countdown...")
        self.event_publisher(GameEvent.COUNTDOWN_START, {"duration": COUNTDOWN_DURATION})

        # Countdown colors: Red -> Yellow -> Green (matches original JoustMania)
        # High contrast sequence that's unmistakable
        countdown_colors = [
            (80, 0, 0),  # Red (3) - dimmed to match original
            (70, 100, 0),  # Orange-Yellow (2)
            (0, 70, 0),  # Green (1 - GO!) - dimmed to match original
        ]

        for _i, (r, g, b) in enumerate(countdown_colors):
            if not self.running:
                logger.info("Countdown interrupted by force_end")
                return

            # Play countdown beep (Phase 29)
            await self._play_sound("Joust/sounds/beep_loud.wav", priority=2)

            # Set color on all controllers
            color_request = controller_manager_pb2.SetControllerColorRequest(
                serial="",  # Empty = all controllers
                color=controller_manager_pb2.RGB(r=r, g=g, b=b),
                duration_ms=0,  # Permanent until next color
            )
            await self.controller_client.SetControllerColor(color_request)

            # Wait 0.75 seconds (matches original JoustMania timing)
            for _ in range(15):  # 15 * 50ms = 750ms
                if not self.running:
                    logger.info("Countdown interrupted by force_end")
                    return
                await asyncio.sleep(0.05)

        # Play start sound (Phase 29 - GO!)
        await self._play_sound("Joust/sounds/start3.wav", priority=2)

        self.event_publisher(GameEvent.COUNTDOWN_END, {})
        logger.info("Countdown complete")

    async def _start_gameplay_stream(self):
        """
        Create and configure the gameplay stream.

        Called before countdown to allow EMA warmup during countdown phase.
        The stream is stored in self.gameplay_stream for use by _game_loop().
        """
        from proto import controller_manager_pb2

        # Get runtime config
        config = get_config_manager().get_config()
        update_frequency_hz = config.update_frequency_hz

        logger.info(f"Creating gameplay stream at {update_frequency_hz}Hz...")

        # Create bidirectional stream
        self.gameplay_stream = self.controller_client.StreamGameplayDataDynamic()

        # Build player colors for stream init
        player_colors = []
        for serial, player in self.players.items():
            player_colors.append(
                controller_manager_pb2.ControllerColorConfig(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=player.color[0], g=player.color[1], b=player.color[2]),
                )
            )

        # Send initial configuration
        initial_config = controller_manager_pb2.GameplayStreamControl(
            config=controller_manager_pb2.GameplayStreamConfig(
                update_frequency_hz=update_frequency_hz,
                colors=player_colors,
            )
        )
        await self.gameplay_stream.write(initial_config)
        logger.info(f"Gameplay stream started with {len(player_colors)} players")

    async def _game_loop(self):
        """Main game loop - processes controller states and checks for deaths."""
        logger.info("Starting game loop...")

        try:
            from proto import controller_manager_pb2

            # Create player lifecycle spans (subclass-specific: flat vs hierarchical)
            # Pass None to use current active span context (we're inside gameplay_phase)
            self._create_player_spans(None)

            # Get runtime config (Phase 43: Dynamic Hz adjustment)
            config = get_config_manager().get_config()
            update_frequency_hz = config.update_frequency_hz

            # Emit configured Hz metric (Phase 43)
            metrics.configured_update_frequency_hz.set(update_frequency_hz)

            logger.info(f"Starting game loop at {update_frequency_hz}Hz (stream already started)")

            # Stream was already created in _start_gameplay_stream() before countdown
            # EMA filter was primed during countdown by _warmup_ema()

            # Track current alive set for detecting changes
            last_alive_serials = {p.serial for p in self.players.values() if p.alive}
            logger.info(f"Initial alive players: {len(last_alive_serials)}")

            # Track loop timing for actual Hz calculation (Phase 43)
            loop_start_time = time.time()
            loop_iterations = 0
            last_iteration_time = loop_start_time

            # Safety timeout: maximum 5 minutes per game
            max_game_duration = 300  # seconds

            # Stream gameplay data and process game logic
            logger.info("Starting gameplay data stream loop, waiting for first update...")
            async for gameplay_update in self.gameplay_stream:
                if loop_iterations == 0:
                    logger.info("✅ Received first gameplay update from stream!")
                    # Set start_time here, not before game_loop, so grace period is accurate
                    self.start_time = time.time()

                    # Set grace period for all players (2 seconds at game start)
                    # Matches original JoustMania: no_rumble = time.time() + 2
                    grace_end = self.start_time + GAME_START_GRACE_PERIOD
                    for player in self.players.values():
                        player.grace_until = grace_end
                    logger.info(f"Set {GAME_START_GRACE_PERIOD}s grace period for {len(self.players)} players")

                if not self.running:
                    logger.info("Game running=False, breaking loop")
                    break

                # Safety check: timeout if game runs too long
                if (time.time() - loop_start_time) > max_game_duration:
                    logger.error(f"Game exceeded maximum duration of {max_game_duration}s, forcing end")
                    break

                # Process each controller's gameplay data
                for gameplay_data in gameplay_update.controllers:
                    await self._process_controller_state(gameplay_data)

                # Check if alive players changed (Phase 45 - dynamic filtering)
                current_alive_serials = {p.serial for p in self.players.values() if p.alive}

                if current_alive_serials != last_alive_serials:
                    # Send filter update to server
                    filter_msg = controller_manager_pb2.GameplayStreamControl(
                        filter_update=controller_manager_pb2.FilterUpdate(serials=list(current_alive_serials))
                    )
                    await self.gameplay_stream.write(filter_msg)

                    logger.info(
                        f"Updated controller filter: {len(last_alive_serials)} → "
                        f"{len(current_alive_serials)} alive players"
                    )

                    # Emit filter metrics (Phase 45)
                    metrics.filter_updates_total.labels(game_mode=self.get_game_name()).inc()
                    metrics.active_controllers.set(len(current_alive_serials))
                    metrics.filtered_controllers.set(len(self.players) - len(current_alive_serials))

                    last_alive_serials = current_alive_serials

                # Check win condition
                if self._check_win_condition():
                    # Keep game running for 1 second to clearly show winner in traces
                    logger.info("Win condition met, keeping game active for 1 second to show winner")
                    await asyncio.sleep(1.0)
                    break

                # Check if config changed (Phase 43: Live Hz adjustment)
                current_hz = get_config_manager().get_config().update_frequency_hz
                if current_hz != update_frequency_hz:
                    logger.info(
                        f"Update frequency changed: {update_frequency_hz}Hz → {current_hz}Hz (will apply on next game)"
                    )

                # Emit metrics (Phase 43)
                loop_iterations += 1
                iteration_end = time.time()
                iteration_latency_ms = (iteration_end - last_iteration_time) * 1000

                metrics.game_loop_iterations_total.labels(mode=self.get_game_name()).inc()
                metrics.game_loop_latency_ms.labels(mode=self.get_game_name()).observe(iteration_latency_ms)

                # Calculate actual Hz every 10 iterations
                if loop_iterations % 10 == 0:
                    elapsed = time.time() - loop_start_time
                    actual_hz = loop_iterations / elapsed if elapsed > 0 else 0
                    metrics.actual_update_frequency_hz.set(actual_hz)

                last_iteration_time = iteration_end

                # Small sleep to maintain tick rate
                await asyncio.sleep(1.0 / update_frequency_hz)

        except Exception as e:
            logger.error(f"Game loop error: {e}", exc_info=True)
            raise
        finally:
            # Cleanup stream reference (Phase 46)
            self.gameplay_stream = None

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

        # Calculate acceleration magnitude (raw units, ~4096 = 1g)
        # Thresholds are scaled to match, avoiding per-frame division
        accel = controller_state.accel
        accel_mag = math.sqrt(accel.x**2 + accel.y**2 + accel.z**2)

        # Apply exponential moving average filter (from original JoustMania)
        # Formula: smoothed = (smoothed * 4 + raw) / 5
        # This gives 80% weight to previous value, 20% to current - smooths sensor noise
        # Phase 73: Initialize with first reading to prevent false deaths at game start
        if player.smoothed_accel == 0.0:
            player.smoothed_accel = accel_mag  # Prime filter with first real reading
        else:
            player.smoothed_accel = (player.smoothed_accel * 4 + accel_mag) / 5
        player.last_accel_mag = player.smoothed_accel

        # Get thresholds
        warn_threshold, death_threshold = self.sensitivity.value

        # Phase 70: Scale thresholds based on music speed
        # When music is fast (1.3x), increase thresholds to make players harder to kill
        # This creates the classic JoustMania gameplay dynamic
        speed_factor = self.music_speed / SLOW_MUSIC_SPEED
        effective_warn = warn_threshold * speed_factor
        effective_death = death_threshold * speed_factor

        smoothed = player.smoothed_accel
        current_time = time.time()

        # Check grace period first - no death or warning during grace period
        # Matches original JoustMania: if time.time() > no_rumble
        if current_time < player.grace_until:
            return  # In grace period, skip all checks

        # Death and warning checks (matches original JoustMania logic)
        # Key: warning is just feedback, NOT protection - player can die during warning!
        if smoothed > effective_death:
            # Player exceeded death threshold - kill them
            await self._kill_player(serial, smoothed)
        elif smoothed > effective_warn and current_time >= player.warning_until:
            # Player exceeded warning threshold and not already in warning state
            # Start warning feedback (flash + rumble)
            await self._warn_player(serial, smoothed)

    async def _warn_player(self, serial: str, accel_mag: float):
        """
        Warn a player that they're moving too much.

        This is purely visual/haptic feedback (flash + rumble) - NOT protection!
        Player can still die immediately if they exceed death threshold.
        Matches original JoustMania where warning was just feedback.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that triggered warning
        """
        from proto import controller_manager_pb2

        player = self.players.get(serial)
        if not player or not player.alive:
            return

        # Set warning feedback duration (prevents repeated warnings during flash)
        # This is NOT protection - player can still die during this time!
        player.warning_until = time.time() + WARNING_DURATION

        # Add warning event to player's lifecycle span
        if player.span:
            player.span.add_event(
                "death_warning",
                attributes={
                    "accel_magnitude": accel_mag,
                    "threshold": self.sensitivity.value[0],
                },
            )
        logger.info(f"Player {serial} triggered warning (accel: {accel_mag:.2f})")

        # Send warning effect via stream (white flash + vibrate, auto-restore)
        if self.gameplay_stream:
            effect_cmd = controller_manager_pb2.GameplayStreamControl(
                game_effect=controller_manager_pb2.GameEffectCommand(
                    serial=serial,
                    effect=controller_manager_pb2.GAME_EFFECT_PLAYER_WARNING,
                )
            )
            await self.gameplay_stream.write(effect_cmd)

    async def _kill_player(self, serial: str, accel_mag: float):
        """
        Kill a player (template method calling subclass implementation).

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        player = self.players.get(serial)
        if not player or not player.alive:
            return

        alive_count_before = len([p for p in self.players.values() if p.alive])
        logger.info(f"Player died: {serial}, {alive_count_before - 1} players remaining")

        # Phase 70: Track deaths for music tempo timing
        self.dead_count += 1

        # Play death explosion sound (Phase 29)
        await self._play_sound("Joust/sounds/Explosion34.wav", priority=2)

        # Call subclass-specific death handling
        await self._kill_player_impl(serial, accel_mag)

        # Phase XX: Send death effect via stream (red + vibrate, no restore)
        from proto import controller_manager_pb2

        if self.gameplay_stream:
            effect_cmd = controller_manager_pb2.GameplayStreamControl(
                game_effect=controller_manager_pb2.GameEffectCommand(
                    serial=serial,
                    effect=controller_manager_pb2.GAME_EFFECT_PLAYER_DEATH,
                )
            )
            await self.gameplay_stream.write(effect_cmd)

    def force_end(self):
        """Force the game to end (called externally)."""
        logger.info("Force ending game...")
        self.running = False

    # ========================================================================
    # Template Method - Orchestrates entire game lifecycle with spans
    # ========================================================================

    async def run(self):
        """
        Main entry point to run the game (Template Method).

        Orchestrates all game phases with consistent span hierarchy:
        1. initialization_phase
        2. Additional phases (e.g., team_formation)
        3. countdown_phase
        4. gameplay_phase
        5. teardown_phase

        Phase spans are automatically children of the current game span.
        """
        try:
            # State transitions
            self.state = GameState.STARTING
            self.running = True  # Set early to allow force_end during countdown
            self.event_publisher(GameEvent.GAME_STARTING, {"game_id": self.game_id})

            # Phase 1: Initialization
            with tracer.start_as_current_span("initialization_phase") as init_span:
                init_span.set_attribute("game.id", self.game_id)
                init_span.set_attribute("game.mode", self.get_game_name())

                # Load settings
                await self._load_settings()

                # Initialize players
                await self._initialize_players()

                # Validate player count
                if len(self.players) < 2:
                    raise ValueError(f"Need at least 2 players, got {len(self.players)}")

                init_span.set_attribute("player_count", len(self.players))

            # Phase 2+: Additional phases (e.g., team_formation for Random Teams)
            for phase in self._get_additional_phases():
                with tracer.start_as_current_span(phase.name):
                    await phase.execute()

            # Phase 3: Countdown
            with tracer.start_as_current_span("countdown_phase"):
                await self._countdown()

            # Start gameplay stream after countdown
            # EMA will be primed with first readings in game loop
            await self._start_gameplay_stream()

            # Phase 4: Game starts
            self.state = GameState.RUNNING
            # Note: self.start_time is set in _game_loop when first data is received
            self.event_publisher(GameEvent.GAME_STARTED, {"game_id": self.game_id, "player_count": len(self.players)})

            # Phase 70: Start game music
            await self._start_game_music()

            # Phase 5: Gameplay (with music loop running alongside)
            with tracer.start_as_current_span("gameplay_phase"):
                # Start music loop as background task
                self.music_loop_task = asyncio.create_task(self._music_loop())

                try:
                    await self._game_loop()
                finally:
                    # Stop music loop
                    if self.music_loop_task:
                        self.music_loop_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await self.music_loop_task

            # Phase 70: Stop game music
            await self._stop_game_music()

            # Phase 6: Teardown
            with tracer.start_as_current_span("teardown_phase"):
                await self._end_game_impl()

        except Exception as e:
            logger.error(f"{self.get_game_name()} game error: {e}", exc_info=True)
            self.state = GameState.ENDED
            self.event_publisher(GameEvent.GAME_ERROR, {"game_id": self.game_id, "error": str(e)})
            raise

        finally:
            self.running = False
            logger.info(f"{self.get_game_name()} game finished: {self.game_id}")

    # ========================================================================
    # Helper Methods - Span creation utilities
    # ========================================================================

    def _create_player_lifecycle_span(self, serial: str, context=None) -> trace.Span:
        """
        Create a player lifecycle span.

        Args:
            serial: Controller serial number
            context: Parent span context (None to use current active span)

        Returns:
            Started span (caller is responsible for ending it)
        """
        player = self.players[serial]

        # If context is provided, use it; otherwise use current active span context
        if context is None:
            # Get current context from active span
            from opentelemetry import context as otel_context

            context = otel_context.get_current()

        return tracer.start_span(
            "player_lifecycle",  # Consistent name for all players (OpenTelemetry best practice)
            context=context,
            attributes={
                "player.serial": serial,
                "player.team": player.team,
                "player.color": str(player.color),
                "game.mode": self.get_game_name(),
            },
        )

    async def _play_sound(self, sound_path: str, priority: int = 2):
        """
        Play sound via Audio service (Phase 29).

        Args:
            sound_path: Relative path to sound file (e.g., "Joust/sounds/Explosion34.wav")
            priority: Audio priority (0=LOW, 1=MEDIUM, 2=HIGH, 3=CRITICAL)
        """
        if not self.play_audio or not self.audio_client:
            return

        try:
            from proto import audio_pb2

            # Send relative path - audio service resolves to its assets directory
            request = audio_pb2.PlaySoundRequest(file_path=sound_path, volume=1.0, priority=priority)

            # Fire-and-forget - don't wait for response
            await self.audio_client.PlaySound(request)
            logger.debug(f"Playing sound: {sound_path}")
        except Exception as e:
            logger.warning(f"Failed to play sound {sound_path}: {e}")

    # ========================================================================
    # Phase 70: Music Tempo Control
    # ========================================================================

    def _lerp(self, a: float, b: float, t: float) -> float:
        """Linear interpolation between a and b by t (0.0 to 1.0)."""
        return a * (1 - t) + b * t

    async def _start_game_music(self):
        """
        Start game music with tempo control (Phase 70).

        Sets volume higher than lobby and starts music at normal speed.
        """
        if not self.play_audio or not self.audio_client:
            return

        try:
            from proto import audio_pb2

            # Set game volume (louder than lobby)
            await self.audio_client.SetVolume(audio_pb2.SetVolumeRequest(volume=GAME_VOLUME))

            # Start game music
            response = await self.audio_client.PlayMusic(
                audio_pb2.PlayMusicRequest(
                    file_pattern="Joust/music/*.wav",
                    loop=True,
                    tempo=SLOW_MUSIC_SPEED,
                    priority=audio_pb2.AudioPriority.MEDIUM,
                )
            )

            if response.success:
                self.music_track_id = response.track_id
                self.music_speed = SLOW_MUSIC_SPEED
                self.speed_up = True
                self.change_time = self._get_music_change_time()
                next_change = self.change_time - time.time()
                logger.info(f"Game music started: {response.track_id}, next change at +{next_change:.1f}s")
            else:
                logger.warning(f"Failed to start game music: {response.error}")

        except Exception as e:
            logger.warning(f"Failed to start game music: {e}")

    async def _stop_game_music(self):
        """Stop game music (Phase 70)."""
        if not self.audio_client:
            return

        try:
            from proto import audio_pb2

            await self.audio_client.StopMusic(audio_pb2.StopMusicRequest(track_id=""))
            self.music_track_id = None
            logger.info("Game music stopped")

        except Exception as e:
            logger.warning(f"Failed to stop game music: {e}")

    def _get_music_change_time(self) -> float:
        """
        Calculate time of next tempo change based on game progression.

        As more players die, tempo changes become more frequent.
        Returns absolute time (time.time() + delay).
        """
        # Calculate game progression (0.0 = start, 1.0 = near end)
        min_moves = len(self.players) - 2
        if min_moves <= 0:
            min_moves = 1
        game_percent = min(1.0, self.dead_count / min_moves)

        # Interpolate between normal and end-game timing
        if self.speed_up:
            # Currently slow, will speed up - use slow timing
            min_t = self._lerp(MIN_MUSIC_SLOW_TIME, END_MIN_MUSIC_SLOW_TIME, game_percent)
            max_t = self._lerp(MAX_MUSIC_SLOW_TIME, END_MAX_MUSIC_SLOW_TIME, game_percent)
        else:
            # Currently fast, will slow down - use fast timing
            min_t = self._lerp(MIN_MUSIC_FAST_TIME, END_MIN_MUSIC_FAST_TIME, game_percent)
            max_t = self._lerp(MAX_MUSIC_FAST_TIME, END_MAX_MUSIC_FAST_TIME, game_percent)

        delay = random.uniform(min_t, max_t)
        return time.time() + delay

    async def _check_music_speed(self):
        """
        Check and update music tempo (Phase 70).

        Called periodically from music loop. Handles smooth transitions
        between slow and fast tempos.
        """
        if not self.audio_client or not self.music_track_id:
            return

        now = time.time()

        # Check if it's time for a tempo change
        if now >= self.change_time:
            try:
                from proto import audio_pb2

                # Determine target tempo
                target_tempo = FAST_MUSIC_SPEED if self.speed_up else SLOW_MUSIC_SPEED

                # Request tempo transition
                await self.audio_client.ChangeTempo(
                    audio_pb2.ChangeTempoRequest(
                        track_id=self.music_track_id,
                        new_tempo=target_tempo,
                        transition_duration=MUSIC_TRANSITION_DURATION,
                    )
                )

                logger.info(f"Music tempo changing: {self.music_speed:.2f} -> {target_tempo:.2f}")

                # Update state
                self.music_speed = target_tempo
                self.speed_up = not self.speed_up
                self.change_time = self._get_music_change_time()

                logger.debug(f"Next tempo change at +{self.change_time - now:.1f}s")

            except Exception as e:
                logger.warning(f"Failed to change music tempo: {e}")

    async def _music_loop(self):
        """
        Background task to manage music tempo changes (Phase 70).

        Runs alongside the main game loop and periodically checks
        if tempo should change based on game progression.
        """
        logger.info("Music loop started")

        try:
            while self.running:
                await self._check_music_speed()
                await asyncio.sleep(0.1)  # Check every 100ms
        except asyncio.CancelledError:
            logger.info("Music loop cancelled")
        except Exception as e:
            logger.warning(f"Music loop error: {e}")
        finally:
            logger.info("Music loop ended")
