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
import statistics
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from opentelemetry import context as otel_context
from opentelemetry import trace

from lib.telemetry import inject_trace_context
from lib.types import GameEvent, Sensitivity, Sound
from services.game_coordinator import metrics
from services.game_coordinator.runtime_config import get_config_manager

if TYPE_CHECKING:
    from services.game_coordinator.games.analytics import PlayerAnalytics

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

# Game constants (Phase 43: Now uses runtime config for dynamic adjustment)
# Phase 72: Increased from 30Hz to 60Hz for better responsiveness
UPDATE_FREQUENCY = 60  # Hz - default, overridden by runtime config
COUNTDOWN_DURATION = 3  # seconds (legacy constant, use runtime config instead)

# Phase 70: Music tempo constants (from original JoustMania)
SLOW_MUSIC_SPEED = 1.0  # Normal playback
FAST_MUSIC_SPEED = 1.3  # 30% faster
MUSIC_TRANSITION_DURATION = 1.5  # Seconds to smoothly transition

# Log messages (S1192 - avoid duplicate strings)
_MSG_COUNTDOWN_INTERRUPTED = "%s"

# Threshold Scaling: LERP approach (matches original JoustMania)
# ===============================================================
# Uses linear interpolation between slow/fast threshold arrays based on music speed.
# This allows fine-tuned per-sensitivity-level behavior as music tempo changes.
#
# Formula: threshold = lerp(SLOW[sens], FAST[sens], music_speed_percent)
# Where music_speed_percent = (current_speed - SLOW_SPEED) / (FAST_SPEED - SLOW_SPEED)
#
# Example at MEDIUM (sens=2), music at 1.15x (50% between slow/fast):
#   warning = lerp(1.6, 1.9, 0.5) = 1.75g
#   death   = lerp(1.8, 2.8, 0.5) = 2.3g

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


# Threshold arrays from original JoustMania (in g-force units, 1.0 = 1g)
# PSMove accelerometer returns g-force values (standing still = ~1.0 on Z axis)
#
# Uses LERP between slow/fast thresholds based on music speed:
#   threshold = lerp(SLOW[sens], FAST[sens], music_speed_percent)
#
# Index: 0=ULTRA_SLOW, 1=SLOW, 2=MEDIUM, 3=FAST, 4=ULTRA_FAST
SLOW_WARNING = [1.2, 1.3, 1.6, 2.0, 2.5]  # Warning thresholds when music is slow
SLOW_MAX = [1.3, 1.5, 1.8, 2.5, 3.2]  # Death thresholds when music is slow
FAST_WARNING = [1.4, 1.6, 1.9, 2.7, 2.8]  # Warning thresholds when music is fast
FAST_MAX = [1.6, 1.8, 2.8, 3.2, 3.5]  # Death thresholds when music is fast


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
    # Analytics tracker for this player (initialized when game starts)
    analytics: "PlayerAnalytics | None" = None
    # Per-player sensitivity multiplier (Phase 3: Per-Player Sensitivity Infrastructure)
    # 1.0 = default, >1.0 = more sensitive (easier to die), <1.0 = less sensitive (harder to die)
    # Thresholds are divided by this factor: higher factor = lower threshold = easier to trigger
    sensitivity_factor: float = 1.0


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
        self.random_teams = True  # Randomize team assignments (vs sequential)
        self.settings = {}  # Store raw settings dict

        # Phase 70: Music tempo control state
        self.music_track_id = None
        self.music_speed = SLOW_MUSIC_SPEED
        self.speed_up = True  # True = next change will speed up, False = slow down
        self.change_time = 0.0  # Time of next tempo change
        self.music_loop_task = None
        self.dead_count = 0  # Track deaths for tempo timing
        self.gameplay_span: trace.Span | None = None  # Reference for span events
        self.gameplay_span_context = None  # Context for child spans in background tasks

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

                # Parse sensitivity (integer 0-4)
                sens_value = int(self.settings.get("sensitivity", "2"))
                if 0 <= sens_value <= 4:
                    self.sensitivity = Sensitivity(sens_value)
                else:
                    logger.warning(f"Sensitivity {sens_value} out of range, using MEDIUM")
                    self.sensitivity = Sensitivity.MEDIUM
                logger.info(f"Sensitivity: {self.sensitivity.name} ({self.sensitivity.value})")

                # Emit sensitivity metric for dashboard (Phase 80)
                metrics.game_sensitivity.set(self.sensitivity.value)

                # Parse random_teams setting (for team-based games)
                self.random_teams = self.settings.get("random_teams", "true").lower() == "true"

            else:
                logger.warning(f"Failed to load settings: {response.error}")

        except Exception as e:
            logger.error(f"Error loading settings: {e}", exc_info=True)
            # Use defaults

    async def _initialize_players(self):
        """Initialize players from StartGame RPC payload."""
        try:
            # Players must be provided via StartGame RPC (from Menu → Supervisor)
            if not self.initial_players:
                raise RuntimeError("No players provided - StartGame must include player list")

            # Convert protobuf Player messages to controller-like objects for _initialize_players_impl
            # _initialize_players_impl expects controllers with .serial attribute
            class ControllerStub:
                def __init__(self, serial):
                    self.serial = serial

            controllers = [ControllerStub(p.serial) for p in self.initial_players]
            await self._initialize_players_impl(controllers)

            # Set alive metric for all initialized players (Phase 75: filter dead from dashboard)
            for serial in self.players:
                metrics.player_alive.labels(serial=serial).set(1)

            logger.info(f"Initialized {len(self.players)} players from StartGame RPC")

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
        """Run countdown before game starts using unified countdown effect."""
        from proto import controller_manager_pb2

        # Get countdown duration from runtime config (allows override via COUNTDOWN_DURATION_SECONDS env var)
        config = get_config_manager().get_config()
        countdown_seconds = config.countdown_duration_seconds

        logger.info(f"Starting countdown ({countdown_seconds}s)...")
        self.event_publisher(GameEvent.COUNTDOWN_START, {"duration": countdown_seconds})

        if not self.running:
            logger.info(_MSG_COUNTDOWN_INTERRUPTED)
            return

        # Skip countdown entirely if duration is 0 (for fast tests)
        if countdown_seconds == 0:
            logger.info("Countdown skipped (duration=0)")
            self.event_publisher(GameEvent.COUNTDOWN_END, {})
            return

        # Send unified countdown effect via gameplay stream (broadcast to all controllers)
        # Controller manager handles the full Red(750ms)→Yellow(750ms)→Green(750ms) sequence
        if self.gameplay_stream:
            trace_parent, trace_state = inject_trace_context()
            effect_cmd = controller_manager_pb2.GameplayStreamControl(
                game_effect=controller_manager_pb2.GameEffectCommand(
                    serial="",  # Empty = all controllers
                    effect=controller_manager_pb2.GAME_EFFECT_COUNTDOWN,
                    trace_parent=trace_parent,
                    trace_state=trace_state,
                )
            )
            await self.gameplay_stream.write(effect_cmd)

        # Play countdown beeps in sync with the visual countdown
        # Default: Red (3), Yellow (2), Green (1 - GO!)
        # Each beep takes 0.75s, so countdown_seconds=1 means 1 beep
        beep_count = min(countdown_seconds, 3)  # Max 3 beeps even for longer countdowns
        beep_interval_ms = (countdown_seconds * 1000) // max(beep_count, 1)

        for _ in range(beep_count):
            if not self.running:
                logger.info(_MSG_COUNTDOWN_INTERRUPTED)
                return

            # Play countdown beep (Phase 29)
            await self._play_sound(Sound.SFX_BEEP_LOUD, priority=2)

            # Wait for beep interval (configurable based on countdown duration)
            wait_iterations = beep_interval_ms // 50  # 50ms per iteration
            for _ in range(wait_iterations):
                if not self.running:
                    logger.info(_MSG_COUNTDOWN_INTERRUPTED)
                    return
                await asyncio.sleep(0.05)

        # Play start sound (Phase 29 - GO!)
        await self._play_sound(Sound.SFX_START3, priority=2)

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
        self.gameplay_stream = self.controller_client.StreamGameplayData()

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

            # Track frame consistency (Issue #183)
            target_frame_time_ms = 1000.0 / update_frequency_hz
            recent_frame_times: list[float] = []  # Store recent frame times for jitter calculation
            frames_on_target = 0  # Frames within 50% of target time

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

                # Process each controller's gameplay data
                # Check win condition after EACH controller to prevent simultaneous deaths
                # This ensures the last player standing can never die
                game_over = False
                for gameplay_data in gameplay_update.controllers:
                    await self._process_controller_state(gameplay_data)

                    # Check after each controller - stop processing if we have a winner
                    if self._check_win_condition():
                        game_over = True
                        break

                if game_over:
                    # Keep game running for 1 second to clearly show winner in traces
                    logger.info("Win condition met, keeping game active for 1 second to show winner")
                    await asyncio.sleep(1.0)
                    break

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

                # Note: Win condition is now checked after EACH controller (above)
                # to prevent simultaneous deaths - the last player standing can never die

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

                # Track frame consistency (Issue #183)
                recent_frame_times.append(iteration_latency_ms)
                if len(recent_frame_times) > 60:  # Keep last 60 frames (1 second at 60Hz)
                    recent_frame_times.pop(0)

                # Check if frame is within target (50% tolerance)
                if iteration_latency_ms <= target_frame_time_ms * 1.5:
                    frames_on_target += 1

                # Check for dropped frames (>2x target time)
                if iteration_latency_ms > target_frame_time_ms * 2:
                    metrics.game_loop_frames_dropped_total.labels(mode=self.get_game_name()).inc()

                # Calculate actual Hz and frame consistency every 10 iterations
                if loop_iterations % 10 == 0:
                    elapsed = time.time() - loop_start_time
                    actual_hz = loop_iterations / elapsed if elapsed > 0 else 0
                    metrics.actual_update_frequency_hz.set(actual_hz)

                    # Calculate frame consistency percentage
                    consistency_percent = (frames_on_target / loop_iterations) * 100
                    metrics.game_loop_frame_consistency_percent.set(consistency_percent)

                    # Calculate jitter (standard deviation of recent frame times)
                    if len(recent_frame_times) >= 2:
                        jitter_ms = statistics.stdev(recent_frame_times)
                        metrics.game_loop_jitter_ms.set(jitter_ms)

                last_iteration_time = iteration_end

                # Small sleep to maintain tick rate
                await asyncio.sleep(1.0 / update_frequency_hz)

        except Exception as e:
            logger.error(f"Game loop error: {e}", exc_info=True)
            raise
        # Note: Don't set gameplay_stream = None here - it's needed by _end_game_impl
        # for sending winner effects. Stream cleanup happens after teardown phase.

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

        # Calculate acceleration magnitude (g-force units, 1.0 = 1g)
        # Standing still: sqrt(0² + 0² + 1²) ≈ 1.0g
        # Movement adds to this, e.g., 1.8g = significant movement
        accel = controller_state.accel
        accel_mag = math.sqrt(accel.x**2 + accel.y**2 + accel.z**2)

        # Apply exponential moving average filter (from original JoustMania)
        # Formula: smoothed = (smoothed * 4 + raw) / 5
        # This gives 80% weight to previous value, 20% to current - smooths sensor noise
        # Phase 73: Initialize with first reading to prevent false deaths at game start
        if player.smoothed_accel < 1e-9:  # Check for uninitialized (avoids float equality)
            player.smoothed_accel = accel_mag  # Prime filter with first real reading
        else:
            player.smoothed_accel = (player.smoothed_accel * 4 + accel_mag) / 5
        player.last_accel_mag = player.smoothed_accel

        # Get thresholds using LERP between slow/fast based on music speed
        # This matches original JoustMania's threshold scaling behavior
        sens_idx = self.sensitivity.value

        # Calculate music speed as percentage (0.0 = slow, 1.0 = fast)
        speed_range = FAST_MUSIC_SPEED - SLOW_MUSIC_SPEED
        speed_percent = (self.music_speed - SLOW_MUSIC_SPEED) / speed_range if speed_range > 0 else 0.0
        speed_percent = max(0.0, min(1.0, speed_percent))  # Clamp to [0, 1]

        # LERP between slow and fast thresholds
        base_warn = self._lerp(SLOW_WARNING[sens_idx], FAST_WARNING[sens_idx], speed_percent)
        base_death = self._lerp(SLOW_MAX[sens_idx], FAST_MAX[sens_idx], speed_percent)

        # Apply per-player sensitivity factor (Phase 3: Per-Player Sensitivity Infrastructure)
        # Clamp factor to [0.5, 2.0] for safety, then divide thresholds
        # Higher factor = lower threshold = easier to die
        clamped_factor = max(0.5, min(2.0, player.sensitivity_factor))
        effective_warn = base_warn / clamped_factor
        effective_death = base_death / clamped_factor

        smoothed = player.smoothed_accel
        current_time = time.time()

        # Analytics: Record sample if analytics is enabled and initialized
        config = get_config_manager().get_config()
        if config.analytics.enabled and player.analytics is not None:
            # Get gyro data if available
            gyro = controller_state.gyro if hasattr(controller_state, "gyro") else None
            gyro_x = gyro.x if gyro else 0.0
            gyro_y = gyro.y if gyro else 0.0
            gyro_z = gyro.z if gyro else 0.0

            # Record sample (returns current movement zone)
            zone = player.analytics.record_sample(
                accel_x=accel.x,
                accel_y=accel.y,
                accel_z=accel.z,
                raw_accel_mag=accel_mag,
                smoothed_accel=smoothed,
                death_threshold=effective_death,
                config=config.analytics,
                gyro_x=gyro_x,
                gyro_y=gyro_y,
                gyro_z=gyro_z,
                frame_duration_ms=1000.0 / config.update_frequency_hz,
            )

            # Emit Prometheus metrics periodically (every ~1 second)
            if player.analytics.sample_count % config.analytics.metrics_emit_interval_frames == 0:
                metrics.player_accel_magnitude.labels(serial=serial).set(accel_mag)
                metrics.player_movement_zone.labels(serial=serial).set(zone.value)
                metrics.player_peak_accel.labels(serial=serial, game_id=self.game_id).set(player.analytics.peak_accel)
                metrics.player_playstyle.labels(serial=serial).set(player.analytics.get_playstyle().value)

            # Record to histogram for distribution analysis
            metrics.accel_distribution.labels(game_mode=self.get_game_name()).observe(accel_mag)

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
            await self._warn_player(serial, smoothed, effective_warn)

    async def _warn_player(self, serial: str, accel_mag: float, threshold: float):
        """
        Warn a player that they're moving too much.

        This is purely visual/haptic feedback (flash + rumble) - NOT protection!
        Player can still die immediately if they exceed death threshold.
        Matches original JoustMania where warning was just feedback.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that triggered warning
            threshold: The effective warning threshold (after lerp)
        """
        from proto import controller_manager_pb2

        player = self.players.get(serial)
        if not player or not player.alive:
            return

        # Set warning feedback duration (prevents repeated warnings during flash)
        # This is NOT protection - player can still die during this time!
        player.warning_until = time.time() + WARNING_DURATION

        # Analytics: Record warning event
        if player.analytics is not None:
            player.analytics.record_warning()
            metrics.player_warnings_total.labels(serial=serial, game_mode=self.get_game_name()).inc()

        # Add warning event to player's lifecycle span
        if player.span:
            player.span.add_event(
                "death_warning",
                attributes={
                    "accel_magnitude": accel_mag,
                    "threshold": threshold,
                    "sensitivity": self.sensitivity.name,
                    "sensitivity_factor": player.sensitivity_factor,
                    "music_speed": self.music_speed,
                },
            )
        logger.info(f"Player {serial} triggered warning (accel: {accel_mag:.2f}, threshold: {threshold:.2f})")

        # Send warning effect via stream (white flash + vibrate, auto-restore)
        # Use player's span as parent so effect appears under player_lifecycle in traces
        if self.gameplay_stream:
            trace_parent, trace_state = inject_trace_context(player.span)
            effect_cmd = controller_manager_pb2.GameplayStreamControl(
                game_effect=controller_manager_pb2.GameEffectCommand(
                    serial=serial,
                    effect=controller_manager_pb2.GAME_EFFECT_PLAYER_WARNING,
                    trace_parent=trace_parent,
                    trace_state=trace_state,
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

        # Clear analytics metrics so dead players don't appear on dashboard
        metrics.clear_player_analytics(serial, self.game_id)

        # Mark player as dead in metrics (Phase 75: filter dead players from dashboard)
        metrics.player_alive.labels(serial=serial).set(0)

        # Play death explosion sound (Phase 29)
        await self._play_sound(Sound.SFX_EXPLOSION, priority=2)

        # Add death event to player's lifecycle span (Phase 3: Per-Player Sensitivity)
        if player.span:
            player.span.add_event(
                "player_death",
                attributes={
                    "accel_magnitude": accel_mag,
                    "sensitivity": self.sensitivity.name,
                    "sensitivity_factor": player.sensitivity_factor,
                    "music_speed": self.music_speed,
                    "alive_remaining": alive_count_before - 1,
                },
            )

        # Call subclass-specific death handling
        await self._kill_player_impl(serial, accel_mag)

        # Send death effect via stream (red + vibrate, no restore)
        # Use player's span as parent so effect appears under player_lifecycle in traces
        from proto import controller_manager_pb2

        if self.gameplay_stream:
            trace_parent, trace_state = inject_trace_context(player.span)
            effect_cmd = controller_manager_pb2.GameplayStreamControl(
                game_effect=controller_manager_pb2.GameEffectCommand(
                    serial=serial,
                    effect=controller_manager_pb2.GAME_EFFECT_PLAYER_DEATH,
                    trace_parent=trace_parent,
                    trace_state=trace_state,
                )
            )
            await self.gameplay_stream.write(effect_cmd)

    async def _wait_for_rainbow_effect(self) -> bool:
        """
        Wait for the winner rainbow effect to complete.

        Uses runtime config for duration. Interruptible by force_end.

        Returns:
            True if wait completed normally, False if interrupted
        """
        config = get_config_manager().get_config()
        rainbow_duration_s = config.winner_rainbow_duration_ms / 1000.0
        iterations = int(rainbow_duration_s * 10)  # 0.1s increments

        logger.debug(f"Waiting {rainbow_duration_s}s for rainbow effect")
        for i in range(iterations):
            if not self.running:
                logger.info(f"Rainbow wait interrupted at {i * 0.1:.1f}s/{rainbow_duration_s}s")
                return False
            await asyncio.sleep(0.1)

        return True

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
        1. initialization_phase (contains color_assignment, countdown_phase)
        2. gameplay_phase
        3. teardown_phase

        Phase spans are automatically children of the current game span.
        """
        try:
            # State transitions
            self.state = GameState.STARTING
            self.running = True  # Set early to allow force_end during countdown
            self.event_publisher(GameEvent.GAME_STARTING, {"game_id": self.game_id})

            # Phase 1: Initialization (includes all pre-gameplay setup)
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

                # Additional phases (e.g., color_assignment, team_formation)
                # These are children of initialization_phase
                for phase in self._get_additional_phases():
                    with tracer.start_as_current_span(phase.name):
                        await phase.execute()

                # Start gameplay stream before countdown (needed for countdown effects)
                await self._start_gameplay_stream()

                # Countdown phase (child of initialization_phase)
                with tracer.start_as_current_span("countdown_phase"):
                    await self._countdown()

                # Start game music (after countdown, still part of initialization)
                await self._start_game_music()

            # Game starts
            self.state = GameState.RUNNING
            # Note: self.start_time is set in _game_loop when first data is received
            self.event_publisher(GameEvent.GAME_STARTED, {"game_id": self.game_id, "player_count": len(self.players)})

            # Phase 2: Gameplay (with music loop running alongside)
            with tracer.start_as_current_span("gameplay_phase") as gameplay_span:
                # Store span reference and context for background tasks
                self.gameplay_span = gameplay_span
                self.gameplay_span_context = otel_context.get_current()

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

                    # Close all player spans before gameplay_phase ends
                    # This ensures player spans are children of gameplay_phase, not teardown
                    self._close_all_player_spans()

            # Phase 3: Teardown
            with tracer.start_as_current_span("teardown_phase"):
                # Stop game music first (inside teardown_phase so StopMusic span is a child)
                await self._stop_game_music()

                await self._end_game_impl()

                # Cleanup stream reference after winner effects are sent
                self.gameplay_stream = None

                # Clear all analytics metrics so dashboards show no data when game is over
                metrics.clear_all_player_analytics()

        except Exception as e:
            logger.error(f"{self.get_game_name()} game error: {e}", exc_info=True)
            self.state = GameState.ENDED
            self.event_publisher(GameEvent.GAME_ERROR, {"game_id": self.game_id, "error": str(e)})
            raise

        finally:
            self.running = False
            # Ensure analytics are always cleared, even on error
            metrics.clear_all_player_analytics()
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

    def _close_all_player_spans(self):
        """
        Close all open player lifecycle spans.

        Called at the end of gameplay_phase to ensure all player spans
        end with the gameplay phase, not during teardown.
        Subclasses can override to add custom attributes before closing.
        """
        from opentelemetry.trace import Status, StatusCode

        for serial, player in self.players.items():
            if player.span:
                # Add final event based on player state
                if player.alive:
                    player.span.add_event(
                        "game_ended",
                        attributes={
                            "survived": True,
                            "game_duration": time.time() - self.start_time if self.start_time else 0,
                        },
                    )
                player.span.set_status(Status(StatusCode.OK))
                player.span.end()
                player.span = None  # Mark as closed
                logger.debug(f"Closed lifecycle span for player {serial}")

    async def _play_sound(self, sound: str | Sound, priority: int = 2):
        """
        Play sound via Audio service (Phase 29).

        Args:
            sound: Sound enum or string name (e.g., Sound.VOX_CONGRATULATIONS or "congratulations")
            priority: Audio priority (0=LOW, 1=MEDIUM, 2=HIGH, 3=CRITICAL)
        """
        if not self.audio_client:
            return

        try:
            from proto import audio_pb2

            # Convert Sound enum to string value if needed
            sound_name = sound.value if isinstance(sound, Sound) else sound
            request = audio_pb2.PlaySoundRequest(file_path=sound_name, volume=1.0, priority=priority)

            # Fire-and-forget - don't wait for response
            # Note: play_audio setting is checked centrally in audio service
            await self.audio_client.PlaySound(request)
            logger.debug(f"Playing sound: {sound_name}")
        except Exception as e:
            logger.warning(f"Failed to play sound {sound_name}: {e}")

    # ========================================================================
    # Phase 70: Music Tempo Control
    # ========================================================================

    def _lerp(self, a: float, b: float, t: float) -> float:
        """Linear interpolation between a and b by t (0.0 to 1.0)."""
        return a * (1 - t) + b * t

    def _emit_threshold_metrics(self):
        """Emit effective threshold metrics for the current music speed (Phase 80)."""
        sens_idx = self.sensitivity.value
        speed_range = FAST_MUSIC_SPEED - SLOW_MUSIC_SPEED
        speed_percent = (self.music_speed - SLOW_MUSIC_SPEED) / speed_range if speed_range > 0 else 0.0
        speed_percent = max(0.0, min(1.0, speed_percent))

        effective_warn = self._lerp(SLOW_WARNING[sens_idx], FAST_WARNING[sens_idx], speed_percent)
        effective_death = self._lerp(SLOW_MAX[sens_idx], FAST_MAX[sens_idx], speed_percent)

        metrics.effective_warning_threshold.set(effective_warn)
        metrics.effective_death_threshold.set(effective_death)

    async def _start_game_music(self):
        """
        Start game music with tempo control (Phase 70).

        Sets volume higher than lobby and starts music at normal speed.
        Note: play_audio setting is checked centrally in audio service.
        """
        if not self.audio_client:
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
                # Update metrics for dashboard (Phase 80)
                metrics.music_tempo.set(self.music_speed)
                self._emit_threshold_metrics()
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
                old_tempo = self.music_speed
                target_tempo = FAST_MUSIC_SPEED if self.speed_up else SLOW_MUSIC_SPEED

                # Use gameplay context so gRPC span appears as child of gameplay_phase
                token = None
                if self.gameplay_span_context:
                    token = otel_context.attach(self.gameplay_span_context)

                try:
                    # Request tempo transition
                    await self.audio_client.ChangeTempo(
                        audio_pb2.ChangeTempoRequest(
                            track_id=self.music_track_id,
                            new_tempo=target_tempo,
                            transition_duration=MUSIC_TRANSITION_DURATION,
                        )
                    )
                finally:
                    if token:
                        otel_context.detach(token)

                logger.info(f"Music tempo changing: {old_tempo:.2f} -> {target_tempo:.2f}")

                # Add span event to gameplay span for tempo change
                if self.gameplay_span:
                    self.gameplay_span.add_event(
                        "music_tempo_change",
                        attributes={
                            "old_tempo": old_tempo,
                            "new_tempo": target_tempo,
                            "dead_count": self.dead_count,
                            "direction": "speed_up" if self.speed_up else "slow_down",
                        },
                    )

                # Update state
                self.music_speed = target_tempo
                self.speed_up = not self.speed_up
                self.change_time = self._get_music_change_time()
                # Update metrics for dashboard (Phase 80)
                metrics.music_tempo.set(self.music_speed)
                self._emit_threshold_metrics()

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
            raise  # Re-raise to properly propagate cancellation
        except Exception as e:
            logger.warning(f"Music loop error: {e}")
        finally:
            logger.info("Music loop ended")
