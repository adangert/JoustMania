"""
BaseGameMode - Abstract base class for all game modes

Phase 36b: Extracts common patterns from FFA, Teams, Random Teams, and Nonstop Joust.
Provides consistent span hierarchy orchestration and common game operations.

Uses Template Method pattern:
- run() orchestrates the entire game lifecycle with spans
- Concrete methods implement shared behavior (settings, countdown, game loop)
- Abstract methods define game-specific behavior (team assignment, win conditions, etc.)
"""

import asyncio
import logging
import math
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from opentelemetry import trace

from services.game_coordinator import metrics
from services.game_coordinator.runtime_config import get_config_manager

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

# Game constants (Phase 43: Now uses runtime config for dynamic adjustment)
UPDATE_FREQUENCY = 30  # Hz - default, overridden by runtime config
COUNTDOWN_DURATION = 3  # seconds


# Sensitivity thresholds
class Sensitivity(Enum):
    SLOW = (1.3, 1.5)  # (warning_threshold, death_threshold)
    MEDIUM = (1.6, 1.8)
    FAST = (1.9, 2.8)


@dataclass
class Player:
    """Represents a player in the game."""

    serial: str
    team: int = 0
    alive: bool = True
    color: tuple = (255, 255, 255)
    last_accel_mag: float = 0.0
    span: trace.Span | None = None  # OpenTelemetry span for this player's lifecycle


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
                "players_initialized",
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

            # Play countdown beep (Phase 29)
            await self._play_sound("Joust/sounds/beep_loud.wav", priority=2)

            # Set color on all controllers
            color_request = controller_manager_pb2.SetControllerColorRequest(
                serial="",  # Empty = all controllers
                color=controller_manager_pb2.RGB(r=r, g=g, b=b),
                duration_ms=0,  # Permanent until next color
            )
            await self.controller_client.SetControllerColor(color_request)

            # Wait 1 second (in 0.1s increments to allow interruption)
            for _ in range(10):
                if not self.running:
                    logger.info("Countdown interrupted by force_end")
                    return
                await asyncio.sleep(0.1)

        # Play start sound (Phase 29 - GO!)
        await self._play_sound("Joust/sounds/start3.wav", priority=2)

        self.event_publisher("countdown_end", {})
        logger.info("Countdown complete")

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

            logger.info(f"Starting game loop with dynamic filtering at {update_frequency_hz}Hz")

            # Create bidirectional stream (Phase 45 - dynamic filtering, Phase 46 - feedback commands)
            logger.info("Creating bidirectional stream to controller manager...")
            self.gameplay_stream = self.controller_client.StreamGameplayDataDynamic()
            logger.info("Stream created successfully")

            # Send initial configuration
            logger.info(f"Sending initial config: {update_frequency_hz}Hz, all controllers")
            initial_config = controller_manager_pb2.GameplayStreamControl(
                config=controller_manager_pb2.GameplayStreamConfig(
                    update_frequency_hz=update_frequency_hz,
                    serials=[],  # Start with all controllers
                )
            )
            await self.gameplay_stream.write(initial_config)
            logger.info("Initial config sent successfully")

            # Track current alive set for detecting changes
            last_alive_serials = set(p.serial for p in self.players.values() if p.alive)
            logger.info(f"Initial alive players: {len(last_alive_serials)}")

            # Track loop timing for actual Hz calculation (Phase 43)
            loop_start_time = time.time()
            loop_iterations = 0
            last_iteration_time = loop_start_time

            # Safety timeout: maximum 5 minutes per game
            MAX_GAME_DURATION = 300  # seconds

            # Stream gameplay data and process game logic
            logger.info("Starting gameplay data stream loop, waiting for first update...")
            async for gameplay_update in self.gameplay_stream:
                if loop_iterations == 0:
                    logger.info("✅ Received first gameplay update from stream!")

                iteration_start = time.time()

                if not self.running:
                    logger.info("Game running=False, breaking loop")
                    break

                # Safety check: timeout if game runs too long
                if (time.time() - loop_start_time) > MAX_GAME_DURATION:
                    logger.error(f"Game exceeded maximum duration of {MAX_GAME_DURATION}s, forcing end")
                    break

                # Process each controller's gameplay data
                for gameplay_data in gameplay_update.controllers:
                    await self._process_controller_state(gameplay_data)

                # Check if alive players changed (Phase 45 - dynamic filtering)
                current_alive_serials = set(
                    p.serial for p in self.players.values() if p.alive
                )

                if current_alive_serials != last_alive_serials:
                    # Send filter update to server
                    filter_msg = controller_manager_pb2.GameplayStreamControl(
                        filter_update=controller_manager_pb2.FilterUpdate(
                            serials=list(current_alive_serials)
                        )
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
                    logger.info(f"Update frequency changed: {update_frequency_hz}Hz → {current_hz}Hz (will apply on next game)")

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

        # Calculate acceleration magnitude
        accel = controller_state.accel
        accel_mag = math.sqrt(accel.x**2 + accel.y**2 + accel.z**2)

        player.last_accel_mag = accel_mag

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
            duration_ms=200,  # Brief flash
        )
        await self.controller_client.SetControllerColor(flash_request)

        # Vibrate controller briefly
        vibrate_request = controller_manager_pb2.SetControllerVibrationRequest(
            serial=serial,
            intensity=100,  # Moderate vibration
            duration_ms=200,  # Brief pulse
        )
        await self.controller_client.SetControllerVibration(vibrate_request)

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

        # Play death explosion sound (Phase 29)
        await self._play_sound("Joust/sounds/Explosion34.wav", priority=2)

        # Call subclass-specific death handling
        await self._kill_player_impl(serial, accel_mag)

        # Set controller color to red and vibrate (death indication)
        from proto import controller_manager_pb2

        # Phase 46: Use stream-based commands if stream is active, otherwise fall back to unary RPCs
        if self.gameplay_stream:
            # Send combined color + vibration via stream (single message)
            combined_feedback = controller_manager_pb2.GameplayStreamControl(
                combined_feedback=controller_manager_pb2.CombinedFeedback(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=255, g=0, b=0),  # Red
                    vibration_intensity=255,  # Maximum vibration
                    vibration_duration_ms=500  # Half second
                )
            )
            await self.gameplay_stream.write(combined_feedback)
        else:
            # Fall back to unary RPCs (menu/lobby context)
            death_color_request = controller_manager_pb2.SetControllerColorRequest(
                serial=serial,
                color=controller_manager_pb2.RGB(r=255, g=0, b=0),  # Red
                duration_ms=0,  # Permanent
            )
            await self.controller_client.SetControllerColor(death_color_request)

            death_vibrate_request = controller_manager_pb2.SetControllerVibrationRequest(
                serial=serial,
                intensity=255,  # Maximum vibration
                duration_ms=500,  # Half second
            )
            await self.controller_client.SetControllerVibration(death_vibrate_request)

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
            self.event_publisher("game_starting", {"game_id": self.game_id})

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

            # Phase 4: Game starts
            self.state = GameState.RUNNING
            self.start_time = time.time()
            self.event_publisher(
                "game_started", {"game_id": self.game_id, "player_count": len(self.players)}
            )

            # Phase 5: Gameplay
            with tracer.start_as_current_span("gameplay_phase"):
                await self._game_loop()

            # Phase 6: Teardown
            with tracer.start_as_current_span("teardown_phase"):
                await self._end_game_impl()

        except Exception as e:
            logger.error(f"{self.get_game_name()} game error: {e}", exc_info=True)
            self.state = GameState.ENDED
            self.event_publisher("game_error", {"game_id": self.game_id, "error": str(e)})
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

        # If context is provided, use it; otherwise let tracer use current active span
        if context is not None:
            span = tracer.start_span(
                f"player_{serial}_lifecycle",
                context=context,
                attributes={
                    "player.serial": serial,
                    "player.team": player.team,
                    "player.color": str(player.color),
                    "game.mode": self.get_game_name(),
                },
            )
        else:
            span = tracer.start_span(
                f"player_{serial}_lifecycle",
                attributes={
                    "player.serial": serial,
                    "player.team": player.team,
                    "player.color": str(player.color),
                    "game.mode": self.get_game_name(),
                },
            )
        return span

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

            # Prepend assets path
            full_path = f"assets/{sound_path}"

            request = audio_pb2.PlaySoundRequest(
                file_path=full_path,
                volume=1.0,
                priority=priority
            )

            # Fire-and-forget - don't wait for response
            await self.audio_client.PlaySound(request)
            logger.debug(f"Playing sound: {sound_path}")
        except Exception as e:
            logger.warning(f"Failed to play sound {sound_path}: {e}")
