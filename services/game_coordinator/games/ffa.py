"""
FFA (Free-For-All) Game Mode - gRPC-based implementation

Modern implementation using gRPC for controller states and settings,
async/await patterns, proper state machine, and event publishing.

This is Phase 13.2 - the reference implementation for game mode refactoring.
"""

import asyncio
import logging
import time
import math
from enum import Enum
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

# Game constants
UPDATE_FREQUENCY = 60  # Hz - game tick frequency
COUNTDOWN_DURATION = 3  # seconds

# Sensitivity thresholds (will eventually come from settings)
class Sensitivity(Enum):
    SLOW = (1.3, 1.5)      # (warning_threshold, death_threshold)
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
    span: Optional[trace.Span] = None  # OpenTelemetry span for this player's lifecycle

class GameState(Enum):
    """Game lifecycle states."""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    ENDING = "ending"
    ENDED = "ended"

class FFAGame:
    """
    Free-For-All game mode using gRPC communication.

    Players try to keep their controllers still while jostling others.
    Last player standing wins.
    """

    def __init__(
        self,
        controller_manager_client,
        settings_client,
        event_publisher: Callable,
        game_id: str = ""
    ):
        """
        Initialize FFA game.

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events
            game_id: Unique identifier for this game instance
        """
        self.controller_client = controller_manager_client
        self.settings_client = settings_client
        self.event_publisher = event_publisher
        self.game_id = game_id or f"ffa_{int(time.time())}"

        # Game state
        self.state = GameState.IDLE
        self.players: Dict[str, Player] = {}
        self.start_time = None
        self.running = False

        # Settings (will be fetched from Settings service)
        self.sensitivity = Sensitivity.MEDIUM
        self.play_audio = True

        logger.info(f"FFA game initialized: {self.game_id}")

    async def _load_settings(self):
        """Fetch game settings from Settings service."""
        with tracer.start_as_current_span("ffa_load_settings"):
            try:
                from services.settings import settings_pb2
                response = self.settings_client.GetSettings(settings_pb2.GetSettingsRequest())

                if response.success:
                    settings = response.settings
                    logger.info(f"Loaded settings: {len(settings)} keys")

                    # Parse sensitivity
                    sens_str = settings.get('sensitivity', 'MEDIUM').upper()
                    if sens_str in Sensitivity.__members__:
                        self.sensitivity = Sensitivity[sens_str]

                    # Parse audio setting
                    self.play_audio = settings.get('play_audio', 'true').lower() == 'true'

                else:
                    logger.warning(f"Failed to load settings: {response.error}")

            except Exception as e:
                logger.error(f"Error loading settings: {e}", exc_info=True)
                # Use defaults

    async def _initialize_players(self):
        """Get initial controller states and create player objects."""
        with tracer.start_as_current_span("ffa_initialize_players") as span:
            try:
                from services.controller_manager import controller_manager_pb2

                response = self.controller_client.GetReadyControllers(
                    controller_manager_pb2.GetReadyControllersRequest()
                )

                if response.success:
                    for controller in response.controllers:
                        player = Player(
                            serial=controller.serial,
                            team=0,  # FFA - everyone on their own team
                            alive=True,
                            color=(255, 255, 255)
                        )
                        self.players[controller.serial] = player
                        logger.debug(f"Added player: {controller.serial}")

                    span.set_attribute("player_count", len(self.players))
                    logger.info(f"Initialized {len(self.players)} players")

                    # Publish event
                    self.event_publisher("players_initialized", {
                        "player_count": len(self.players),
                        "serials": list(self.players.keys())
                    })

                else:
                    logger.error(f"Failed to get controllers: {response.error}")
                    raise RuntimeError(f"Failed to get controllers: {response.error}")

            except Exception as e:
                logger.error(f"Error initializing players: {e}", exc_info=True)
                raise

    async def _countdown(self):
        """Run countdown before game starts."""
        with tracer.start_as_current_span("ffa_countdown"):
            logger.info("Starting countdown...")
            self.event_publisher("countdown_start", {"duration": COUNTDOWN_DURATION})

            # TODO: Set controller colors for countdown
            # Red -> Yellow -> Green

            # Use shorter sleeps to allow force_end to interrupt
            for _ in range(COUNTDOWN_DURATION * 10):
                if not self.running:
                    logger.info("Countdown interrupted by force_end")
                    return
                await asyncio.sleep(0.1)

            self.event_publisher("countdown_end", {})
            logger.info("Countdown complete")

    async def _game_loop(self):
        """Main game loop - processes controller states and checks for deaths."""
        with tracer.start_as_current_span("ffa_game_loop") as span:
            logger.info("Starting game loop...")

            try:
                from services.controller_manager import controller_manager_pb2

                # Start per-player lifecycle spans (as children of game_loop span)
                for serial, player in self.players.items():
                    player_span = tracer.start_span(
                        f"player_{serial}_lifecycle",
                        attributes={
                            "player.serial": serial,
                            "player.team": player.team,
                            "player.color": str(player.color),
                            "game.mode": "FFA"
                        }
                    )
                    player.span = player_span
                    logger.debug(f"Started lifecycle span for player {serial}")

                # Start streaming controller states
                stream_request = controller_manager_pb2.StreamRequest(
                    update_frequency_hz=UPDATE_FREQUENCY
                )

                alive_count = len([p for p in self.players.values() if p.alive])
                span.set_attribute("initial_player_count", alive_count)

                # Stream controller states and process game logic
                async for state_update in self.controller_client.StreamControllerStates(stream_request):
                    if not self.running:
                        break

                    # Process each controller's state
                    for controller_state in state_update.controllers:
                        await self._process_controller_state(controller_state)

                    # Check win condition
                    if self._check_win_condition():
                        break

                    # Small sleep to maintain tick rate
                    await asyncio.sleep(1.0 / UPDATE_FREQUENCY)

            except Exception as e:
                logger.error(f"Game loop error: {e}", exc_info=True)
                span.record_exception(e)
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
        player = self.players.get(serial)
        if not player or not player.alive:
            return

        # Add warning event to player's lifecycle span
        if player.span:
            player.span.add_event(
                "player_warning",
                attributes={
                    "accel_magnitude": accel_mag,
                    "threshold": self.sensitivity.value[0]
                }
            )
            logger.debug(f"Player {serial} triggered warning (accel: {accel_mag:.2f})")

        # TODO: Flash controller LED
        # TODO: Vibrate controller

    async def _kill_player(self, serial: str, accel_mag: float):
        """
        Kill a player.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        with tracer.start_as_current_span("ffa_kill_player") as span:
            player = self.players.get(serial)
            if not player or not player.alive:
                return

            player.alive = False
            span.set_attribute("player.serial", serial)
            span.set_attribute("accel_magnitude", accel_mag)

            alive_count = len([p for p in self.players.values() if p.alive])
            logger.info(f"Player died: {serial}, {alive_count} players remaining")

            # Add death event to player's lifecycle span and end it
            if player.span:
                player.span.add_event(
                    "player_death",
                    attributes={
                        "accel_magnitude": accel_mag,
                        "threshold": self.sensitivity.value[1],
                        "alive_count": alive_count
                    }
                )
                player.span.set_status(Status(StatusCode.OK))
                player.span.end()
                logger.debug(f"Ended lifecycle span for player {serial}")

            # Publish death event
            self.event_publisher("player_death", {
                "serial": serial,
                "accel_magnitude": accel_mag,
                "alive_count": alive_count
            })

            # TODO: Set controller color to black/red
            # TODO: Play explosion sound

    def _check_win_condition(self) -> bool:
        """
        Check if the game has a winner.

        Returns:
            True if game should end, False otherwise
        """
        alive_players = [p for p in self.players.values() if p.alive]

        if len(alive_players) <= 1:
            # Game over - we have a winner (or tie if 0)
            if len(alive_players) == 1:
                winner = alive_players[0]
                logger.info(f"Winner: {winner.serial}")

                self.event_publisher("game_winner", {
                    "serial": winner.serial
                })

            elif len(alive_players) == 0:
                logger.info("No winner - all players died simultaneously")

                self.event_publisher("game_tie", {})

            return True

        return False

    async def _end_game(self):
        """Handle game ending - show winner, cleanup."""
        with tracer.start_as_current_span("ffa_end_game"):
            logger.info("Ending game...")
            self.state = GameState.ENDING

            # End spans for any surviving players
            for serial, player in self.players.items():
                if player.span and player.alive:
                    player.span.add_event(
                        "player_survived",
                        attributes={
                            "game_duration": time.time() - self.start_time if self.start_time else 0,
                            "winner": len([p for p in self.players.values() if p.alive]) == 1
                        }
                    )
                    player.span.set_status(Status(StatusCode.OK))
                    player.span.end()
                    logger.debug(f"Ended lifecycle span for surviving player {serial}")

            # TODO: Show rainbow on winner's controller
            # TODO: Play victory sound

            # Show winner for a bit (interruptible by force_end)
            for _ in range(20):  # 2 seconds in 0.1s increments
                if not self.running:
                    logger.info("End game interrupted by force_end")
                    break
                await asyncio.sleep(0.1)

            self.state = GameState.ENDED
            self.event_publisher("game_ended", {
                "game_id": self.game_id,
                "duration": time.time() - self.start_time if self.start_time else 0
            })

            logger.info("Game ended")

    async def run(self):
        """
        Main entry point to run the FFA game.

        This is the async method called by GameCoordinator.
        """
        with tracer.start_as_current_span("ffa_run") as span:
            span.set_attribute("game.id", self.game_id)
            span.set_attribute("game.mode", "FFA")

            try:
                # IDLE -> STARTING
                self.state = GameState.STARTING
                self.running = True  # Set early to allow force_end during countdown
                self.event_publisher("game_starting", {"game_id": self.game_id})

                # Load settings
                await self._load_settings()

                # Initialize players
                await self._initialize_players()

                # Validate player count
                if len(self.players) < 2:
                    raise ValueError(f"Need at least 2 players, got {len(self.players)}")

                # Countdown
                await self._countdown()

                # STARTING -> RUNNING
                self.state = GameState.RUNNING
                self.start_time = time.time()
                self.event_publisher("game_started", {
                    "game_id": self.game_id,
                    "player_count": len(self.players)
                })

                # Run main game loop
                await self._game_loop()

                # RUNNING -> ENDING/ENDED
                await self._end_game()

                span.set_attribute("game.completed", True)

            except Exception as e:
                logger.error(f"FFA game error: {e}", exc_info=True)
                span.record_exception(e)
                span.set_attribute("game.error", str(e))

                self.state = GameState.ENDED
                self.event_publisher("game_error", {
                    "game_id": self.game_id,
                    "error": str(e)
                })

                raise

            finally:
                self.running = False
                logger.info(f"FFA game finished: {self.game_id}")

    def force_end(self):
        """Force the game to end (called externally)."""
        logger.info("Force ending game...")
        self.running = False
