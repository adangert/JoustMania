"""
GameCoordinator gRPC Server for JoustMania

Manages game lifecycle as a gRPC service:
- Start games with player configurations
- Monitor game state
- Force end games
- Stream game events (deaths, scoring, game end)

This replaces the Queue-based IPC with gRPC (Phase 8a).
"""

import asyncio
import logging
import os

# Import protobuf
import sys
import threading
import time

import grpc
import grpc.aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

# OpenTelemetry (trace API for span operations)
from opentelemetry import trace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Prometheus metrics (Phase 38)
from prometheus_client import start_http_server

from lib.system_metrics import start_system_metrics_collector
from lib.telemetry import init_telemetry
from lib.types import get_game_display_name
from proto import game_coordinator_pb2, game_coordinator_pb2_grpc
from services.game_coordinator import metrics

# Game factory, event bus, and client manager
from services.game_coordinator.event_bus import EventBus
from services.game_coordinator.game_factory import GameFactory
from services.game_coordinator.grpc_clients import GrpcClientManager

# Legacy game imports (optional for testing)
try:
    # Import legacy modules to test availability
    import games  # noqa: F401
    import piaudio  # noqa: F401

    GAMES_AVAILABLE = True
except ImportError:
    GAMES_AVAILABLE = False
    logging.warning("Legacy game modules not available - will use modern gRPC games")

logger = logging.getLogger(__name__)


# Initialize OpenTelemetry (game coordinator calls other services, so instrument client too)
tracer = init_telemetry(instrument_grpc_client=True)


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

        # Phase 56: Thread-safe state access lock
        # Protects: game_state, current_game, players
        self._state_lock = threading.Lock()

        # Event bus for pub/sub (Phase 61: extracted from server.py)
        self.event_bus = EventBus(state_sync_callback=self._on_event_state_sync)

        # Random game history
        self.random_history: list[str] = []

        # Mock game thread
        self.game_thread: threading.Thread | None = None
        self.game_running = False

        # gRPC client manager (Phase 61: extracted from server.py)
        self.clients = GrpcClientManager()

        logger.info("GameCoordinator initialized")

    def _on_event_state_sync(self, event_type: str):
        """
        Callback for EventBus to sync game state on lifecycle events.

        Called by EventBus.publish() while holding state lock.
        Updates game_state based on event type.
        """
        if event_type == "game_started":
            self.game_state = game_coordinator_pb2.GameState.RUNNING
            logger.info("Game state transitioned to RUNNING")
        elif event_type in ["game_ended", "game_error"]:
            self.game_state = game_coordinator_pb2.GameState.ENDED
            logger.info("Game state transitioned to ENDED")

    def StartGame(self, request, context):
        """Start a new game (creates span for RPC, game span will link with FOLLOWS_FROM)."""
        # Create StartGame span - short-lived, returns immediately
        # The actual game span (in background thread) will link to this with FOLLOWS_FROM
        with tracer.start_as_current_span("StartGame") as start_span:
            start_span.set_attribute("game.name", request.game_name)
            start_span.set_attribute("player.count", len(request.players))

            try:
                # Phase 56: Thread-safe state check and transition
                with self._state_lock:
                    # Check if game already running
                    if self.game_state in [
                        game_coordinator_pb2.GameState.STARTING,
                        game_coordinator_pb2.GameState.RUNNING,
                    ]:
                        return game_coordinator_pb2.StartGameResponse(
                            success=False, error="Game already in progress", game_id=""
                        )

                    # Validate player count
                    if len(request.players) < 2:
                        return game_coordinator_pb2.StartGameResponse(
                            success=False, error="Need at least 2 players", game_id=""
                        )

                    # Store game configuration
                    self.game_name = request.game_name
                    self.players = list(request.players)
                    self.settings = dict(request.settings)
                    self.game_id = f"game_{int(time.time())}"
                    self.game_start_time = time.time()

                    # Capture span context for FOLLOWS_FROM link in background thread
                    self.start_game_span_context = start_span.get_span_context()

                    # Update state
                    self.game_state = game_coordinator_pb2.GameState.STARTING

                # Update metrics (Phase 38)
                metrics.active_game.set(1)
                metrics.games_started_total.labels(mode=self.game_name).inc()
                metrics.active_players.set(len(self.players))

                # Publish game_start event
                self.event_bus.publish(
                    "game_start",
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

                return game_coordinator_pb2.StartGameResponse(success=True, error="", game_id=self.game_id)

            except Exception as e:
                logger.error(f"StartGame error: {e}", exc_info=True)
                return game_coordinator_pb2.StartGameResponse(success=False, error=str(e), game_id="")

    def _run_game_loop_threaded(self):
        """Run the game loop in background thread (creates async event loop)."""
        import asyncio

        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_game_loop_async())
        finally:
            loop.close()

    async def _run_game_loop_async(self):
        """Run the async game loop."""
        from opentelemetry.trace import Link

        # Initialize async gRPC clients in this event loop
        await self.clients.connect()

        # Get the display name for the game span
        game_span_name = get_game_display_name(self.game_name)

        # Create FOLLOWS_FROM link to the StartGame RPC span
        links = []
        if hasattr(self, "start_game_span_context") and self.start_game_span_context:
            # Link shows: "This game span FOLLOWS_FROM the StartGame RPC span"
            links.append(Link(self.start_game_span_context))

        # Create the game span - this will be the root span for the entire game
        # The FOLLOWS_FROM link connects it to the StartGame RPC span
        with tracer.start_as_current_span(game_span_name, links=links) as game_span:
            game_span.set_attribute("game.name", self.game_name)
            game_span.set_attribute("game.id", self.game_id)
            game_span.set_attribute("player.count", len(self.players))

            try:
                # Check if gRPC clients are available
                if not self.clients.is_connected:
                    error_msg = "gRPC clients not initialized - ControllerManager and Settings services must be running"
                    logger.error(error_msg)
                    # Phase 56: Thread-safe state transition
                    with self._state_lock:
                        self.game_state = game_coordinator_pb2.GameState.ENDED
                    self.event_bus.publish("game_error", {"error": error_msg})
                    # Phase 56: Cleanup any partially initialized channels
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
                # Phase 56: Thread-safe state transition
                with self._state_lock:
                    self.game_state = game_coordinator_pb2.GameState.ENDED
                self.event_bus.publish("game_error", {"error": str(e)})
            finally:
                # Phase 56: Thread-safe state cleanup
                with self._state_lock:
                    self.game_running = False
                    self.current_game = None

                # Update metrics (Phase 38)
                metrics.active_game.set(0)
                metrics.active_players.set(0)
                metrics.players_alive.set(0)
                if self.game_name:
                    metrics.games_completed_total.labels(mode=self.game_name).inc()
                if self.game_start_time:
                    duration = time.time() - self.game_start_time
                    metrics.game_duration_seconds.set(duration)

                # Phase 56: Use helper for channel cleanup
                await self.clients.close()
                logger.info("Closed gRPC channels")

                # game_session span will automatically end here

    def GetGameStatus(self, request, context):
        """Get current game status."""
        with tracer.start_as_current_span("GetGameStatus") as span:
            try:
                # Phase 56: Thread-safe state snapshot
                with self._state_lock:
                    current_state = self.game_state
                    current_game = self.current_game
                    game_name = self.game_name
                    players_initial = list(self.players)  # Copy
                    start_time = self.game_start_time

                elapsed = 0
                if start_time and current_state == game_coordinator_pb2.GameState.RUNNING:
                    elapsed = int(time.time() - start_time)

                span.set_attribute("game.state", current_state)
                span.set_attribute("game.elapsed_seconds", elapsed)

                # Get live player data from current game if running
                players_status = players_initial  # Default to initial state
                if current_game and hasattr(current_game, "players"):
                    # Convert game's player dict to protobuf Player list with live state
                    players_status = []
                    for serial, player in current_game.players.items():
                        players_status.append(
                            game_coordinator_pb2.Player(
                                serial=serial,
                                team=player.team,
                                alive=player.alive,
                            )
                        )

                return game_coordinator_pb2.GetGameStatusResponse(
                    state=current_state,
                    game_name=game_name,
                    players=players_status,
                    elapsed_seconds=elapsed,
                    success=True,
                    error="",
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetGameStatus error: {e}", exc_info=True)
                return game_coordinator_pb2.GetGameStatusResponse(
                    state=game_coordinator_pb2.GameState.IDLE,
                    game_name="",
                    players=[],
                    elapsed_seconds=0,
                    success=False,
                    error=str(e),
                )

    async def ForceEndGame(self, request, context):
        """Force end the current game (Phase 56: async to avoid blocking)."""
        # Note: Don't create a span here - the game_session span encompasses the game lifecycle
        try:
            # Phase 56: Thread-safe state check and update
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

            # Phase 56: Wait for thread in executor to avoid blocking gRPC server
            if game_thread and game_thread.is_alive():
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: game_thread.join(timeout=5.0))

            # Phase 56: Thread-safe state transition
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

    async def StreamGameEvents(self, request, context):
        """Stream game events in real-time (async)."""
        subscriber_id = f"events_{time.time()}"

        with tracer.start_as_current_span("StreamGameEvents") as span:
            span.set_attribute("subscriber.id", subscriber_id)

            # Subscribe to event bus (Phase 61: extracted to EventBus)
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

    async def shutdown(self):
        """Shutdown the game coordinator (Phase 34: async, Phase 56: thread-safe)."""
        logger.info("Shutting down GameCoordinator...")

        # Phase 56: Thread-safe state access
        with self._state_lock:
            self.game_running = False
            game_thread = self.game_thread

        # Phase 34: Run thread.join() in executor to avoid blocking event loop
        if game_thread and game_thread.is_alive():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: game_thread.join(timeout=5.0))

        # Phase 56: Use centralized channel cleanup
        logger.info("Closing gRPC channels...")
        await self.clients.close()


async def serve(port=50053, metrics_port=8000):
    """Start the GameCoordinator async gRPC server."""
    # Configure logging with environment variable support
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Start Prometheus metrics HTTP server (Phase 38)
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics available at http://0.0.0.0:{metrics_port}/metrics")

    # Start system metrics collection (Phase 61: extracted to lib/system_metrics.py)
    start_system_metrics_collector(
        cpu_gauge=metrics.process_cpu_percent,
        memory_gauge=metrics.process_memory_mb,
        threads_gauge=metrics.process_threads,
    )

    # Create async server
    server = grpc.aio.server()

    # Add servicer
    game_servicer = GameCoordinatorServicer()
    game_coordinator_pb2_grpc.add_GameCoordinatorServiceServicer_to_server(game_servicer, server)

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the GameCoordinator service as SERVING
    await health_servicer.set("game_coordinator.GameCoordinatorService", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # Overall health

    # Bind to port
    server.add_insecure_port(f"[::]:{port}")

    # Start server
    logger.info(f"Starting GameCoordinator async gRPC server on port {port}")
    await server.start()

    logger.info(f"GameCoordinator server listening on port {port}")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down GameCoordinator server...")
        await game_servicer.shutdown()  # Phase 34: await async shutdown
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
