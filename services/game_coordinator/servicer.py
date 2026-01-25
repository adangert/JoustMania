"""
GameCoordinator gRPC Servicer for JoustMania

Manages game lifecycle:
- Start games with player configurations
- Monitor game state
- Force end games
- Stream game events (deaths, scoring, game end)
"""

import asyncio
import logging
import threading
import time

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from lib.telemetry import init_telemetry
from lib.types import GameEvent, get_game_display_name
from proto import game_coordinator_pb2, game_coordinator_pb2_grpc
from services.game_coordinator import metrics
from services.game_coordinator.event_bus import EventBus
from services.game_coordinator.game_factory import GameFactory
from services.game_coordinator.grpc_clients import GrpcClientManager

logger = logging.getLogger(__name__)

# Initialize OpenTelemetry
tracer = init_telemetry()


class GameCoordinatorServicer(game_coordinator_pb2_grpc.GameCoordinatorServiceServicer):
    """
    GameCoordinator gRPC servicer.

    Manages game lifecycle:
    - Start games
    - Monitor game state
    - Force end games
    - Stream game events
    """

    def __init__(self):
        """Initialize game coordinator."""
        self.current_game = None
        self.game_state = game_coordinator_pb2.GameState.IDLE
        self.game_name = ""
        self.players: list[game_coordinator_pb2.Player] = []
        self.settings: dict[str, str] = {}
        self.game_start_time = None
        self.game_id = None

        # Thread-safe state access lock
        # Protects: game_state, current_game, players
        self._state_lock = threading.Lock()

        # Event bus for pub/sub
        self.event_bus = EventBus(state_sync_callback=self._on_event_state_sync)

        # Random game history
        self.random_history: list[str] = []

        # Mock game thread
        self.game_thread: threading.Thread | None = None
        self.game_running = False

        # gRPC client manager
        self.clients = GrpcClientManager()

        logger.info("GameCoordinator initialized")

    def _on_event_state_sync(self, event_type: str):
        """
        Callback for EventBus to sync game state on lifecycle events.

        Called by EventBus.publish() while holding state lock.
        Updates game_state based on event type.
        """
        if event_type == GameEvent.GAME_STARTED:
            self.game_state = game_coordinator_pb2.GameState.RUNNING
            logger.info("Game state transitioned to RUNNING")
        elif GameEvent.is_game_ending(event_type):
            self.game_state = game_coordinator_pb2.GameState.ENDED
            logger.info("Game state transitioned to ENDED")

    def _start_game_from_config(self, config, parent_span) -> tuple[bool, str]:
        """
        Start a game from StartGameConfig (internal helper).

        Args:
            config: StartGameConfig with game_name, players, settings
            parent_span: Parent span for trace context

        Returns:
            Tuple of (success, error_message_or_game_id)
        """
        try:
            # Thread-safe state check and transition
            with self._state_lock:
                # Check if game already running
                if self.game_state in [
                    game_coordinator_pb2.GameState.STARTING,
                    game_coordinator_pb2.GameState.RUNNING,
                ]:
                    return False, "Game already in progress"

                # Validate player count
                if len(config.players) < 2:
                    return False, "Need at least 2 players"

                # Store game configuration
                self.game_name = config.game_name
                self.players = list(config.players)
                self.settings = dict(config.settings)
                self.game_id = f"game_{int(time.time())}"
                self.game_start_time = time.time()

                # Capture parent context for game span in background thread
                self.game_parent_context = trace.set_span_in_context(parent_span)

                # Update state
                self.game_state = game_coordinator_pb2.GameState.STARTING

            # Update metrics
            metrics.active_game.set(1)
            metrics.games_started_total.labels(mode=self.game_name).inc()
            metrics.active_players.set(len(self.players))

            # Publish game_start event
            self.event_bus.publish(
                GameEvent.GAME_START,
                {
                    "game_name": self.game_name,
                    "game_id": self.game_id,
                    "player_count": str(len(self.players)),
                },
            )

            # Start game in background thread (with async support)
            self.game_running = True
            self.game_thread = threading.Thread(target=self._run_game_loop_threaded, daemon=True)
            self.game_thread.start()

            logger.info(f"Started game: {self.game_name} with {len(self.players)} players")
            return True, self.game_id

        except Exception as e:
            logger.error(f"StartGame error: {e}", exc_info=True)
            return False, str(e)

    def _run_game_loop_threaded(self):
        """Run the game loop in background thread (creates async event loop)."""
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_game_loop_async())
        finally:
            # Properly cleanup gRPC async resources before closing loop
            # This prevents BlockingIOError from gRPC's PollerCompletionQueue
            try:
                # Cancel any remaining tasks
                pending = asyncio.all_tasks(loop)
                if pending:
                    logger.debug(f"Cancelling {len(pending)} pending tasks before loop close")
                    for task in pending:
                        task.cancel()
                    # Wait for cancellation to complete (with timeout)
                    loop.run_until_complete(asyncio.wait(pending, timeout=1.0))

                # Give gRPC pollers time to drain their queues
                loop.run_until_complete(asyncio.sleep(0.1))
            except Exception as e:
                logger.debug(f"Cleanup before loop close: {e}")
            finally:
                loop.close()

    async def _run_game_loop_async(self):
        """Run the async game loop."""
        # Initialize async gRPC clients in this event loop
        await self.clients.connect()

        # Get the display name for the game span
        game_span_name = get_game_display_name(self.game_name)

        # Get parent context captured from StartGame RPC span
        # This keeps the game span in the same trace as the StartGame call
        parent_context = getattr(self, "game_parent_context", None)

        # Create the game span as a child of StartGame, keeping it in the same trace
        with tracer.start_as_current_span(game_span_name, context=parent_context) as game_span:
            game_span.set_attribute("game.name", self.game_name)
            game_span.set_attribute("game.id", self.game_id)
            game_span.set_attribute("player.count", len(self.players))

            try:
                # Check if gRPC clients are available
                if not self.clients.is_connected:
                    error_msg = "gRPC clients not initialized - ControllerManager and Settings services must be running"
                    logger.error(error_msg)
                    # Thread-safe state transition
                    with self._state_lock:
                        self.game_state = game_coordinator_pb2.GameState.ENDED
                    self.event_bus.publish("game_error", {"error": error_msg})
                    # Cleanup any partially initialized channels
                    await self.clients.close()
                    return

                # Create game instance using factory
                try:
                    game = GameFactory.create_game(
                        game_name=self.game_name,
                        controller_manager_client=self.clients.controller_manager,
                        settings_client=self.clients.settings,
                        event_publisher=self.event_bus.publish,
                        audio_client=self.clients.audio,
                        game_id=self.game_id,
                        initial_players=self.players,
                        game_settings=self.settings,
                    )
                except ValueError as e:
                    # Unknown game mode
                    error_msg = str(e)
                    logger.error(error_msg)
                    with self._state_lock:
                        self.game_state = game_coordinator_pb2.GameState.ENDED
                    self.event_bus.publish("game_error", {"error": error_msg})
                    await self.clients.close()
                    return

                # Store reference and run game
                self.current_game = game
                await game.run()
                logger.info(f"{self.game_name} game completed")

            except Exception as e:
                logger.error(f"Game loop error: {e}", exc_info=True)
                # Thread-safe state transition
                with self._state_lock:
                    self.game_state = game_coordinator_pb2.GameState.ENDED
                self.event_bus.publish("game_error", {"error": str(e)})
            finally:
                # Thread-safe state cleanup
                with self._state_lock:
                    self.game_running = False
                    self.current_game = None

                # Update metrics
                metrics.active_game.set(0)
                metrics.active_players.set(0)
                metrics.players_alive.set(0)
                if self.game_name:
                    metrics.games_completed_total.labels(mode=self.game_name).inc()
                if self.game_start_time:
                    duration = time.time() - self.game_start_time
                    metrics.game_duration_seconds.set(duration)

                # Cleanup channels
                await self.clients.close()
                logger.info("Closed gRPC channels")

    async def ForceEndGame(self, request, context):  # noqa: N802, ARG002
        """Force end the current game."""
        try:
            # Thread-safe state check and update
            with self._state_lock:
                if self.game_state not in [
                    game_coordinator_pb2.GameState.STARTING,
                    game_coordinator_pb2.GameState.RUNNING,
                ]:
                    return game_coordinator_pb2.ForceEndGameResponse(success=False, error="No game in progress")

                # Stop game loop
                self.game_running = False
                current_game = self.current_game
                game_thread = self.game_thread
                game_id = self.game_id

            # Call force_end on current game if it exists
            if current_game and hasattr(current_game, "force_end"):
                current_game.force_end()

            # Wait for thread in executor to avoid blocking gRPC server
            if game_thread and game_thread.is_alive():
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: game_thread.join(timeout=5.0))

            # Thread-safe state transition
            with self._state_lock:
                self.game_state = game_coordinator_pb2.GameState.ENDED

            # Publish event
            self.event_bus.publish(
                "game_force_ended",
                {"reason": request.reason, "game_id": game_id or "unknown"},
            )

            logger.info(f"Force ended game: {request.reason}")

            return game_coordinator_pb2.ForceEndGameResponse(success=True, error="")

        except Exception as e:
            logger.error(f"ForceEndGame error: {e}", exc_info=True)
            return game_coordinator_pb2.ForceEndGameResponse(success=False, error=str(e))

    async def StreamGameEvents(self, request, context):  # noqa: N802
        """
        Stream game events in real-time.

        If start_config is provided, starts a new game before streaming events.
        Otherwise, subscribes to current/upcoming game events.
        """
        subscriber_id = f"events_{time.time()}"

        # Extract trace context from gRPC metadata for cross-service propagation
        propagator = TraceContextTextMapPropagator()
        metadata: dict[str, str] = {}
        if context.invocation_metadata():
            for key, value in context.invocation_metadata():
                metadata[key] = value
        parent_ctx = propagator.extract(metadata)

        with tracer.start_as_current_span("StreamGameEvents", context=parent_ctx) as span:
            span.set_attribute("subscriber.id", subscriber_id)

            # Check if this is a game start request
            if request.HasField("start_config"):
                config = request.start_config
                span.set_attribute("game.name", config.game_name)
                span.set_attribute("player.count", len(config.players))
                span.set_attribute("game.start_via_stream", True)

                # Start the game
                success, result = self._start_game_from_config(config, span)

                if not success:
                    # Yield error event and close stream
                    logger.error(f"Failed to start game via stream: {result}")
                    span.set_attribute("error", result)
                    yield game_coordinator_pb2.GameEvent(
                        event_type="game_start_error",
                        data={"error": result},
                        timestamp=int(time.time() * 1000),
                    )
                    return

                span.set_attribute("game.id", result)
                logger.info(f"Game {result} started via stream")

            # Subscribe to event bus
            event_queue = await self.event_bus.subscribe(subscriber_id)

            try:
                while not context.cancelled():
                    try:
                        # Async wait with timeout
                        event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                        yield event

                    except TimeoutError:
                        # No event, continue (timeout keeps connection alive)
                        continue
                    except Exception as e:
                        logger.error(f"Stream error for {subscriber_id}: {e}")
                        break

            finally:
                # Cleanup via EventBus
                await self.event_bus.unsubscribe(subscriber_id)

    async def GetGameState(self, request, context):  # noqa: N802, ARG002
        """
        Get current game state for testing and observability.

        Returns detailed player information including team assignments,
        colors, and alive status.
        """
        try:
            with self._state_lock:
                # Build game info response
                game_info = game_coordinator_pb2.GameInfo(
                    game_mode=self.game_name or "",
                    state=self.game_state,
                    game_id=self.game_id or "",
                    start_time_ms=int((self.game_start_time or 0) * 1000),
                )

                # Get player info from current game if running
                if self.current_game and hasattr(self.current_game, "players"):
                    # Get team info if available (for team-based games)
                    teams = getattr(self.current_game, "teams", {})

                    for serial, player in self.current_game.players.items():
                        # Get team name from teams dict if available
                        team_name = ""
                        if player.team >= 0 and player.team in teams:
                            team_name = teams[player.team].name

                        # Get color components
                        color = player.color if player.color else (0, 0, 0)
                        r, g, b = color[0], color[1], color[2]

                        player_info = game_coordinator_pb2.PlayerInfo(
                            serial=serial,
                            team=player.team,
                            team_name=team_name,
                            color=game_coordinator_pb2.RGB(r=r, g=g, b=b),
                            alive=player.alive,
                            sensitivity_factor=player.sensitivity_factor,
                            score=0,  # Score tracking not yet implemented in base Player
                        )
                        game_info.players.append(player_info)

            logger.debug(
                f"GetGameState: mode={game_info.game_mode}, state={game_info.state}, players={len(game_info.players)}"
            )
            return game_coordinator_pb2.GetGameStateResponse(
                success=True,
                error="",
                game_info=game_info,
            )

        except Exception as e:
            logger.error(f"GetGameState error: {e}", exc_info=True)
            return game_coordinator_pb2.GetGameStateResponse(
                success=False,
                error=str(e),
            )

    async def shutdown(self):
        """Shutdown the game coordinator."""
        logger.info("Shutting down GameCoordinator...")

        # Thread-safe state access
        with self._state_lock:
            self.game_running = False
            game_thread = self.game_thread

        # Run thread.join() in executor to avoid blocking event loop
        if game_thread and game_thread.is_alive():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: game_thread.join(timeout=5.0))

        # Centralized channel cleanup
        logger.info("Closing gRPC channels...")
        await self.clients.close()
