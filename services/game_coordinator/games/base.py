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

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

# Game constants
UPDATE_FREQUENCY = 60  # Hz - game tick frequency
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
        controller_manager_client,
        settings_client,
        event_publisher: Callable,
        game_id: str = "",
    ):
        """
        Initialize base game mode.

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events
            game_id: Unique identifier for this game instance
        """
        self.controller_client = controller_manager_client
        self.settings_client = settings_client
        self.event_publisher = event_publisher

        # Game ID - subclasses can override with mode-specific prefix
        if not game_id:
            mode_prefix = self.get_game_name().lower().replace(" ", "_")
            game_id = f"{mode_prefix}_{int(time.time())}"
        self.game_id = game_id

        # Game state
        self.state = GameState.IDLE
        self.players: dict[str, Player] = {}
        self.start_time = None
        self.running = False

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

            response = await self.controller_client.GetReadyControllers(
                controller_manager_pb2.GetReadyControllersRequest()
            )

            if response.success:
                # Call subclass-specific initialization
                await self._initialize_players_impl(list(response.controllers))

                logger.info(f"Initialized {len(self.players)} players")

                # Publish event
                self.event_publisher(
                    "players_initialized",
                    {
                        "player_count": len(self.players),
                        "serials": list(self.players.keys()),
                    },
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
                duration_ms=0,  # Permanent until next color
            )
            await self.controller_client.SetControllerColor(color_request)

            # Wait 1 second (in 0.1s increments to allow interruption)
            for _ in range(10):
                if not self.running:
                    logger.info("Countdown interrupted by force_end")
                    return
                await asyncio.sleep(0.1)

        self.event_publisher("countdown_end", {})
        logger.info("Countdown complete")

    async def _game_loop(self):
        """Main game loop - processes controller states and checks for deaths."""
        logger.info("Starting game loop...")

        try:
            from proto import controller_manager_pb2

            # Create player lifecycle spans (subclass-specific: flat vs hierarchical)
            self._create_player_spans(trace.get_current_span().get_span_context())

            # Start streaming gameplay data (Phase 41 - acceleration/gyro only, no buttons)
            stream_request = controller_manager_pb2.GameplayStreamRequest(
                update_frequency_hz=UPDATE_FREQUENCY
            )

            # Stream gameplay data and process game logic
            async for gameplay_update in self.controller_client.StreamGameplayData(
                stream_request
            ):
                if not self.running:
                    break

                # Process each controller's gameplay data
                for gameplay_data in gameplay_update.controllers:
                    await self._process_controller_state(gameplay_data)

                # Check win condition
                if self._check_win_condition():
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

        # Call subclass-specific death handling
        await self._kill_player_impl(serial, accel_mag)

        # Set controller color to red (death indication)
        from proto import controller_manager_pb2

        death_color_request = controller_manager_pb2.SetControllerColorRequest(
            serial=serial,
            color=controller_manager_pb2.RGB(r=255, g=0, b=0),  # Red
            duration_ms=0,  # Permanent
        )
        await self.controller_client.SetControllerColor(death_color_request)

        # Strong vibration on death
        death_vibrate_request = controller_manager_pb2.SetControllerVibrationRequest(
            serial=serial,
            intensity=255,  # Maximum vibration
            duration_ms=500,  # Half second
        )
        await self.controller_client.SetControllerVibration(death_vibrate_request)

        # TODO: Play explosion sound via Audio service

    def force_end(self):
        """Force the game to end (called externally)."""
        logger.info("Force ending game...")
        self.running = False

    # ========================================================================
    # Template Method - Orchestrates entire game lifecycle with spans
    # ========================================================================

    async def run(self, game_context=None):
        """
        Main entry point to run the game (Template Method).

        Orchestrates all game phases with consistent span hierarchy:
        1. Game session span (human-readable name)
        2. initialization_phase
        3. Additional phases (e.g., team_formation)
        4. countdown_phase
        5. gameplay_phase
        6. teardown_phase

        Args:
            game_context: Parent span context for proper hierarchy
        """
        # Create main game span with human-readable name
        span_name = get_game_display_name(self.get_game_name())

        with tracer.start_as_current_span(span_name, context=game_context) as game_span:
            game_span.set_attribute("game.id", self.game_id)
            game_span.set_attribute("game.mode", self.get_game_name())

            try:
                # State transitions
                self.state = GameState.STARTING
                self.running = True  # Set early to allow force_end during countdown
                self.event_publisher("game_starting", {"game_id": self.game_id})

                # Phase 1: Initialization
                with tracer.start_as_current_span(
                    "initialization_phase", context=game_context
                ) as init_span:
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
                    with tracer.start_as_current_span(phase.name, context=game_context):
                        await phase.execute()

                # Phase 3: Countdown
                with tracer.start_as_current_span("countdown_phase", context=game_context):
                    await self._countdown()

                # Phase 4: Game starts
                self.state = GameState.RUNNING
                self.start_time = time.time()
                self.event_publisher(
                    "game_started", {"game_id": self.game_id, "player_count": len(self.players)}
                )

                # Phase 5: Gameplay
                with tracer.start_as_current_span("gameplay_phase", context=game_context):
                    await self._game_loop()

                # Phase 6: Teardown
                with tracer.start_as_current_span("teardown_phase", context=game_context):
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

    def _create_player_lifecycle_span(self, serial: str, context) -> trace.Span:
        """
        Create a player lifecycle span.

        Args:
            serial: Controller serial number
            context: Parent span context

        Returns:
            Started span (caller is responsible for ending it)
        """
        player = self.players[serial]
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
        return span
