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

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import psutil

# Prometheus metrics (Phase 38)
from prometheus_client import start_http_server

from lib.types import get_game_display_name
from proto import (
    controller_manager_pb2_grpc,
    game_coordinator_pb2,
    game_coordinator_pb2_grpc,
    settings_pb2_grpc,
)
from services.game_coordinator import metrics

# Modern game imports (gRPC-based)
from services.game_coordinator.games import ffa, nonstop_joust, random_teams, teams

# Legacy game imports (optional for testing)
try:
    from games import (
        fight_club,
        joust_ffa,
        joust_random_teams,
        joust_teams,
        swapper,
        tournament,
        traitor,
    )
    from piaudio import Audio, Music

    from common import Games

    GAMES_AVAILABLE = True
except ImportError:
    GAMES_AVAILABLE = False
    logging.warning("Legacy game modules not available - will use modern gRPC games")

logger = logging.getLogger(__name__)


# Initialize OpenTelemetry
def init_telemetry():
    """Initialize OpenTelemetry with OTLP exporter."""
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    service_name = os.getenv("OTEL_SERVICE_NAME", "game-coordinator-service")

    resource = Resource(
        attributes={
            SERVICE_NAME: service_name,
            SERVICE_VERSION: "1.0.0",
            "service.namespace": "joustmania",
        }
    )

    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    # Instrument both server and client-side gRPC calls
    GrpcInstrumentorServer().instrument()
    GrpcInstrumentorClient().instrument()

    logger.info(f"OpenTelemetry initialized: {service_name} -> {otlp_endpoint}")
    return trace.get_tracer(__name__)


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

        # Event streaming (Phase 34: async queue and lock)
        self.event_subscribers: dict[str, asyncio.Queue] = {}
        self.event_lock = asyncio.Lock()

        # Random game history
        self.random_history: list[str] = []

        # Mock game thread
        self.game_thread: threading.Thread | None = None
        self.game_running = False

        # Initialize gRPC clients for other services
        # Store gRPC service addresses (channels will be created in game loop's event loop)
        self.controller_manager_host = os.getenv("CONTROLLER_MANAGER_HOST", "controller-manager")
        self.controller_manager_port = os.getenv("CONTROLLER_MANAGER_PORT", "50052")
        self.settings_host = os.getenv("SETTINGS_HOST", "settings")
        self.settings_port = os.getenv("SETTINGS_PORT", "50051")
        self.audio_host = os.getenv("AUDIO_HOST", "audio")  # Phase 29
        self.audio_port = os.getenv("AUDIO_PORT", "50054")  # Phase 29

        # These will be set to None initially and created in the game loop
        self.controller_manager_channel = None
        self.controller_manager_client = None
        self.settings_channel = None
        self.settings_client = None
        self.audio_channel = None
        self.audio_client = None  # Phase 29: Audio integration

        logger.info("GameCoordinator initialized")

    async def _init_grpc_clients_async(self):
        """Initialize async gRPC clients (Phase 33 - using shared gRPC utilities)."""
        from lib.grpc_utils import create_channel

        try:
            # ControllerManager client (async for streaming)
            controller_manager_address = (
                f"{self.controller_manager_host}:{self.controller_manager_port}"
            )
            self.controller_manager_channel = create_channel(controller_manager_address)
            self.controller_manager_client = (
                controller_manager_pb2_grpc.ControllerManagerServiceStub(
                    self.controller_manager_channel
                )
            )
            logger.info(f"Connected to ControllerManager at {controller_manager_address}")

            # Settings client (async)
            settings_address = f"{self.settings_host}:{self.settings_port}"
            self.settings_channel = create_channel(settings_address)
            self.settings_client = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
            logger.info(f"Connected to Settings at {settings_address}")

            # Audio client (async) - Phase 29
            from proto import audio_pb2_grpc

            audio_address = f"{self.audio_host}:{self.audio_port}"
            self.audio_channel = create_channel(audio_address)
            self.audio_client = audio_pb2_grpc.AudioServiceStub(self.audio_channel)
            logger.info(f"Connected to Audio at {audio_address}")

        except Exception as e:
            logger.error(f"Failed to initialize gRPC clients: {e}")
            # Create None clients for graceful degradation
            self.controller_manager_client = None
            self.settings_client = None
            self.audio_client = None

    def StartGame(self, request, context):
        """Start a new game (creates span for RPC, game span will link with FOLLOWS_FROM)."""
        # Create StartGame span - short-lived, returns immediately
        # The actual game span (in background thread) will link to this with FOLLOWS_FROM
        with tracer.start_as_current_span("StartGame") as start_span:
            start_span.set_attribute("game.name", request.game_name)
            start_span.set_attribute("player.count", len(request.players))

            try:
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
                self._publish_event(
                    "game_start",
                    {
                        "game_name": self.game_name,
                        "game_id": self.game_id,
                        "player_count": str(len(self.players)),
                    },
                )

                # Start game in background thread (with async support)
                self.game_running = True
                self.game_thread = threading.Thread(
                    target=self._run_game_loop_threaded, daemon=True
                )
                self.game_thread.start()

                logger.info(f"Started game: {self.game_name} with {len(self.players)} players")

                return game_coordinator_pb2.StartGameResponse(
                    success=True, error="", game_id=self.game_id
                )

            except Exception as e:
                logger.error(f"StartGame error: {e}", exc_info=True)
                return game_coordinator_pb2.StartGameResponse(
                    success=False, error=str(e), game_id=""
                )

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
        await self._init_grpc_clients_async()

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
                if not self.controller_manager_client or not self.settings_client:
                    error_msg = "gRPC clients not initialized - ControllerManager and Settings services must be running"
                    logger.error(error_msg)
                    self.game_state = game_coordinator_pb2.GameState.ENDED
                    self._publish_event("game_error", {"error": error_msg})
                    return

                # Determine game mode and instantiate appropriate game
                if self.game_name.lower() in ["ffa", "free-for-all", "joust free-for-all"]:
                    logger.info("Starting FFA game")

                    # Create FFA game instance
                    game = ffa.FFAGame(
                        controller_manager_client=self.controller_manager_client,
                        settings_client=self.settings_client,
                        event_publisher=self._publish_event,
                        audio_client=self.audio_client,  # Phase 29
                        game_id=self.game_id,
                        initial_players=self.players,  # Pass players from StartGame RPC
                    )

                    # Store reference
                    self.current_game = game

                    # Run the game - phase spans will automatically be children of current game span
                    await game.run()

                    logger.info("FFA game completed")

                elif self.game_name.lower() in ["teams", "joust teams"]:
                    logger.info("Starting Teams game")

                    # Get number of teams from settings (default 2)
                    num_teams = int(self.settings.get("num_teams", "2"))

                    # Create Teams game instance
                    game = teams.SimpleTeamsGame(
                        controller_manager_client=self.controller_manager_client,
                        settings_client=self.settings_client,
                        event_publisher=self._publish_event,
                        audio_client=self.audio_client,  # Phase 29
                        game_id=self.game_id,
                        num_teams=num_teams,
                        initial_players=self.players,  # Pass players from StartGame RPC
                    )

                    # Store reference
                    self.current_game = game

                    # Run the game - phase spans will automatically be children of current game span
                    await game.run()

                    logger.info("Teams game completed")

                elif self.game_name.lower() in [
                    "random teams",
                    "joust random teams",
                    "random_teams",
                ]:
                    logger.info("Starting Random Teams game")

                    # Get number of teams from settings (default 2)
                    num_teams = int(self.settings.get("num_teams", "2"))

                    # Create Random Teams game instance
                    game = random_teams.RandomTeamsGame(
                        controller_manager_client=self.controller_manager_client,
                        settings_client=self.settings_client,
                        event_publisher=self._publish_event,
                        audio_client=self.audio_client,  # Phase 29
                        game_id=self.game_id,
                        num_teams=num_teams,
                        initial_players=self.players,  # Pass players from StartGame RPC
                    )

                    # Store reference
                    self.current_game = game

                    # Run the game - phase spans will automatically be children of current game span
                    await game.run()

                    logger.info("Random Teams game completed")

                elif self.game_name.lower() in ["nonstop", "nonstop joust", "nonstopjoust"]:
                    logger.info("Starting Nonstop Joust game")

                    # Get time limit from settings (0 = unlimited)
                    int(self.settings.get("nonstop_time_limit", "0"))

                    # Create Nonstop Joust game instance
                    game = nonstop_joust.NonstopJoustGame(
                        controller_manager_client=self.controller_manager_client,
                        settings_client=self.settings_client,
                        event_publisher=self._publish_event,
                        audio_client=self.audio_client,  # Phase 29
                        game_id=self.game_id,
                        initial_players=self.players,  # Pass players from StartGame RPC
                    )

                    # Store reference
                    self.current_game = game

                    # Run the game - phase spans will automatically be children of current game span
                    await game.run()

                    logger.info("Nonstop Joust game completed")

                else:
                    error_msg = f"Game mode '{self.game_name}' not implemented yet"
                    logger.error(error_msg)
                    self.game_state = game_coordinator_pb2.GameState.ENDED
                    self._publish_event("game_error", {"error": error_msg})

            except Exception as e:
                logger.error(f"Game loop error: {e}", exc_info=True)
                self.game_state = game_coordinator_pb2.GameState.ENDED
                self._publish_event("game_error", {"error": str(e)})
            finally:
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

                # Close async gRPC channels
                if self.controller_manager_channel:
                    await self.controller_manager_channel.close()
                if self.settings_channel:
                    await self.settings_channel.close()
                logger.info("Closed gRPC channels")

                # game_session span will automatically end here

    def GetGameStatus(self, request, context):
        """Get current game status."""
        with tracer.start_as_current_span("GetGameStatus") as span:
            try:
                elapsed = 0
                if (
                    self.game_start_time
                    and self.game_state == game_coordinator_pb2.GameState.RUNNING
                ):
                    elapsed = int(time.time() - self.game_start_time)

                span.set_attribute("game.state", self.game_state)
                span.set_attribute("game.elapsed_seconds", elapsed)

                # Get live player data from current game if running
                players_status = self.players  # Default to initial state
                if self.current_game and hasattr(self.current_game, "players"):
                    # Convert game's player dict to protobuf Player list with live state
                    players_status = []
                    for serial, player in self.current_game.players.items():
                        players_status.append(
                            game_coordinator_pb2.Player(
                                serial=serial,
                                team=player.team,
                                alive=player.alive,
                            )
                        )

                return game_coordinator_pb2.GetGameStatusResponse(
                    state=self.game_state,
                    game_name=self.game_name,
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

    def ForceEndGame(self, request, context):
        """Force end the current game."""
        # Note: Don't create a span here - the game_session span encompasses the game lifecycle
        try:
            if self.game_state not in [
                game_coordinator_pb2.GameState.STARTING,
                game_coordinator_pb2.GameState.RUNNING,
            ]:
                return game_coordinator_pb2.ForceEndGameResponse(
                    success=False, error="No game in progress"
                )

            # Stop game loop
            self.game_running = False

            # Call force_end on current game if it exists
            if self.current_game and hasattr(self.current_game, "force_end"):
                self.current_game.force_end()

            # Wait for thread to finish
            if self.game_thread and self.game_thread.is_alive():
                self.game_thread.join(timeout=5.0)

            # Update state
            self.game_state = game_coordinator_pb2.GameState.ENDED

            # Publish event
            self._publish_event(
                "game_force_ended",
                {"reason": request.reason, "game_id": self.game_id or "unknown"},
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

            # Create queue for this subscriber (Phase 34: asyncio.Queue)
            event_queue = asyncio.Queue(maxsize=100)

            async with self.event_lock:  # Phase 34: async lock
                self.event_subscribers[subscriber_id] = event_queue

            logger.info(f"New event subscriber: {subscriber_id}")

            try:
                while not context.cancelled():
                    try:
                        # Phase 34: async wait with timeout
                        event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                        yield event

                    except TimeoutError:  # Phase 34: asyncio exception
                        # No event, continue (timeout keeps connection alive)
                        continue
                    except Exception as e:
                        logger.error(f"Stream error for {subscriber_id}: {e}")
                        break

            finally:
                # Cleanup (Phase 34: async lock)
                async with self.event_lock:
                    if subscriber_id in self.event_subscribers:
                        del self.event_subscribers[subscriber_id]

                logger.info(f"Event subscriber disconnected: {subscriber_id}")

    def _publish_event(self, event_type: str, data: dict[str, str]):
        """Publish an event to all subscribers."""
        # Add as span event instead of creating child span
        current_span = trace.get_current_span()
        if current_span.is_recording():
            # Add event with attributes
            attributes = {
                "event.type": event_type,
                "subscribers.count": len(self.event_subscribers),
                **{k: str(v) for k, v in data.items()},
            }
            current_span.add_event(event_type, attributes=attributes)

        # Sync server game_state with game mode lifecycle events
        if event_type == "game_started":
            self.game_state = game_coordinator_pb2.GameState.RUNNING
            logger.info("Game state transitioned to RUNNING")
        elif event_type in ["game_ended", "game_error"]:
            self.game_state = game_coordinator_pb2.GameState.ENDED
            logger.info("Game state transitioned to ENDED")

        # Convert all values to strings (protobuf map<string, string> requirement)
        string_data = {k: str(v) for k, v in data.items()}

        event = game_coordinator_pb2.GameEvent(
            event_type=event_type, data=string_data, timestamp=int(time.time() * 1000)
        )

        # Phase 34: put_nowait() is thread-safe, no lock needed for publishing
        for sub_id, event_queue in self.event_subscribers.items():
            try:
                event_queue.put_nowait(event)
                logger.debug(f"Published {event_type} to subscriber {sub_id}")
            except asyncio.QueueFull:  # Phase 34: asyncio exception
                logger.warning(f"Subscriber {sub_id} queue full, skipping event")
            except Exception as e:
                logger.error(f"Error publishing to subscriber {sub_id}: {e}")

    async def shutdown(self):
        """Shutdown the game coordinator (Phase 34: async for proper cleanup)."""
        logger.info("Shutting down GameCoordinator...")
        self.game_running = False

        # Phase 34: Run thread.join() in executor to avoid blocking event loop
        if self.game_thread and self.game_thread.is_alive():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.game_thread.join(timeout=5.0))

        # Close gRPC channels (Phase 26 - Part 2, Phase 34: async close)
        logger.info("Closing gRPC channels...")
        if hasattr(self, "controller_manager_channel") and self.controller_manager_channel:
            await self.controller_manager_channel.close()
        if hasattr(self, "settings_channel") and self.settings_channel:
            await self.settings_channel.close()
        if hasattr(self, "audio_channel") and self.audio_channel:  # Phase 29
            await self.audio_channel.close()


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

    # Start system metrics collection task (Phase 38)
    async def collect_system_metrics():
        """
        Background task to collect system metrics every 10 seconds.
        Phase 34: Run psutil calls in thread pool to avoid blocking event loop.
        """
        process = psutil.Process()
        loop = asyncio.get_event_loop()

        while True:
            try:
                # Phase 34: Run blocking psutil calls in thread pool
                cpu_percent = await loop.run_in_executor(
                    None, lambda: process.cpu_percent(interval=None)
                )
                mem_info = await loop.run_in_executor(None, lambda: process.memory_info())
                thread_count = await loop.run_in_executor(None, process.num_threads)

                metrics.process_cpu_percent.set(cpu_percent)
                metrics.process_memory_mb.set(mem_info.rss / 1024 / 1024)
                metrics.process_threads.set(thread_count)
            except Exception as e:
                logger.error(f"Error collecting system metrics: {e}")
            await asyncio.sleep(10.0)

    asyncio.create_task(collect_system_metrics())

    # Create async server
    server = grpc.aio.server()

    # Add servicer
    game_servicer = GameCoordinatorServicer()
    game_coordinator_pb2_grpc.add_GameCoordinatorServiceServicer_to_server(game_servicer, server)

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the GameCoordinator service as SERVING
    await health_servicer.set(
        "game_coordinator.GameCoordinatorService", health_pb2.HealthCheckResponse.SERVING
    )
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
