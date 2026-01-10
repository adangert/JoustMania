"""
GameCoordinator gRPC Server for JoustMania

Manages game lifecycle as a gRPC service:
- Start games with player configurations
- Monitor game state
- Force end games
- Stream game events (deaths, scoring, game end)

This replaces the Queue-based IPC with gRPC (Phase 8a).
"""

import logging
import time
import threading
import queue
import random
import asyncio
from typing import Dict, List, Optional
from concurrent import futures
import grpc
import grpc.aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer, GrpcInstrumentorClient

# Import protobuf
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from proto import game_coordinator_pb2, game_coordinator_pb2_grpc
from proto import controller_manager_pb2, controller_manager_pb2_grpc
from proto import settings_pb2, settings_pb2_grpc

# Modern game imports (gRPC-based)
from services.game_coordinator.games import ffa, teams, random_teams

# Legacy game imports (optional for testing)
try:
    from common import Games
    from piaudio import Music, Audio
    from games import (
        joust_ffa, joust_teams, joust_random_teams,
        traitor, swapper, fight_club, tournament
    )
    GAMES_AVAILABLE = True
except ImportError:
    GAMES_AVAILABLE = False
    logging.warning("Legacy game modules not available - will use modern gRPC games")

logger = logging.getLogger(__name__)

# Initialize OpenTelemetry
def init_telemetry():
    """Initialize OpenTelemetry with OTLP exporter."""
    otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4317')
    service_name = os.getenv('OTEL_SERVICE_NAME', 'game-coordinator-service')

    resource = Resource(attributes={
        SERVICE_NAME: service_name,
        SERVICE_VERSION: "1.0.0",
        "service.namespace": "joustmania",
    })

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
        self.players: List[game_coordinator_pb2.Player] = []
        self.settings: Dict[str, str] = {}
        self.game_start_time = None
        self.game_id = None

        # Event streaming
        self.event_subscribers: Dict[str, queue.Queue] = {}
        self.event_lock = threading.Lock()

        # Random game history
        self.random_history: List[str] = []

        # Mock game thread
        self.game_thread: Optional[threading.Thread] = None
        self.game_running = False

        # Initialize gRPC clients for other services
        self.controller_manager_host = os.getenv('CONTROLLER_MANAGER_HOST', 'controller-manager')
        self.controller_manager_port = os.getenv('CONTROLLER_MANAGER_PORT', '50052')
        self.settings_host = os.getenv('SETTINGS_HOST', 'settings')
        self.settings_port = os.getenv('SETTINGS_PORT', '50051')

        self._init_grpc_clients()

        logger.info("GameCoordinator initialized")

    def _init_grpc_clients(self):
        """Initialize gRPC clients for ControllerManager and Settings with optimized channel options."""
        # gRPC channel options for better performance and reliability
        channel_options = [
            # Keep-alive settings to detect dead connections
            ('grpc.keepalive_time_ms', 30000),  # Send keepalive ping every 30s
            ('grpc.keepalive_timeout_ms', 5000),  # Wait 5s for keepalive ack
            ('grpc.keepalive_permit_without_calls', True),  # Allow keepalive pings when no calls
            ('grpc.http2.max_pings_without_data', 2),  # Allow 2 pings without data

            # Connection and timeout settings
            ('grpc.initial_reconnect_backoff_ms', 1000),  # 1s initial backoff
            ('grpc.max_reconnect_backoff_ms', 5000),  # 5s max backoff

            # Message size limits (10MB for large controller state messages)
            ('grpc.max_receive_message_length', 10 * 1024 * 1024),
            ('grpc.max_send_message_length', 10 * 1024 * 1024),
        ]

        try:
            # ControllerManager client
            controller_manager_address = f"{self.controller_manager_host}:{self.controller_manager_port}"
            self.controller_manager_channel = grpc.insecure_channel(
                controller_manager_address,
                options=channel_options
            )
            self.controller_manager_client = controller_manager_pb2_grpc.ControllerManagerServiceStub(
                self.controller_manager_channel
            )
            logger.info(f"Connected to ControllerManager at {controller_manager_address} (with channel options)")

            # Settings client
            settings_address = f"{self.settings_host}:{self.settings_port}"
            self.settings_channel = grpc.insecure_channel(
                settings_address,
                options=channel_options
            )
            self.settings_client = settings_pb2_grpc.SettingsServiceStub(
                self.settings_channel
            )
            logger.info(f"Connected to Settings at {settings_address} (with channel options)")

        except Exception as e:
            logger.error(f"Failed to initialize gRPC clients: {e}")
            # Create None clients for graceful degradation
            self.controller_manager_client = None
            self.settings_client = None

    def StartGame(self, request, context):
        """Start a new game."""
        with tracer.start_as_current_span("StartGame") as span:
            span.set_attribute("game.name", request.game_name)
            span.set_attribute("game.player_count", len(request.players))

            try:
                # Check if game already running
                if self.game_state in [game_coordinator_pb2.GameState.STARTING,
                                        game_coordinator_pb2.GameState.RUNNING]:
                    return game_coordinator_pb2.StartGameResponse(
                        success=False,
                        error="Game already in progress",
                        game_id=""
                    )

                # Validate player count
                if len(request.players) < 2:
                    return game_coordinator_pb2.StartGameResponse(
                        success=False,
                        error="Need at least 2 players",
                        game_id=""
                    )

                # Store game configuration
                self.game_name = request.game_name
                self.players = list(request.players)
                self.settings = dict(request.settings)
                self.game_id = f"game_{int(time.time())}"
                self.game_start_time = time.time()

                # Update state
                self.game_state = game_coordinator_pb2.GameState.STARTING

                # Publish game_start event
                self._publish_event("game_start", {
                    "game_name": self.game_name,
                    "game_id": self.game_id,
                    "player_count": str(len(self.players))
                })

                # Start game in background thread (with async support)
                self.game_running = True
                self.game_thread = threading.Thread(
                    target=self._run_game_loop_threaded,
                    daemon=True
                )
                self.game_thread.start()

                logger.info(f"Started game: {self.game_name} with {len(self.players)} players")

                span.set_attribute("game.id", self.game_id)
                span.set_attribute("game.started", True)

                return game_coordinator_pb2.StartGameResponse(
                    success=True,
                    error="",
                    game_id=self.game_id
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"StartGame error: {e}", exc_info=True)
                return game_coordinator_pb2.StartGameResponse(
                    success=False,
                    error=str(e),
                    game_id=""
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
        with tracer.start_as_current_span("game_loop") as span:
            span.set_attribute("game.name", self.game_name)
            span.set_attribute("game.id", self.game_id)

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
                        game_id=self.game_id
                    )

                    # Store reference
                    self.current_game = game

                    # Run the game (async)
                    await game.run()

                    logger.info("FFA game completed")

                elif self.game_name.lower() in ["teams", "joust teams"]:
                    logger.info("Starting Teams game")

                    # Get number of teams from settings (default 2)
                    num_teams = int(self.settings.get("num_teams", "2"))

                    # Create Teams game instance
                    game = teams.TeamsGame(
                        controller_manager_client=self.controller_manager_client,
                        settings_client=self.settings_client,
                        event_publisher=self._publish_event,
                        game_id=self.game_id,
                        num_teams=num_teams
                    )

                    # Store reference
                    self.current_game = game

                    # Run the game (async)
                    await game.run()

                    logger.info("Teams game completed")

                elif self.game_name.lower() in ["random teams", "joust random teams", "random_teams"]:
                    logger.info("Starting Random Teams game")

                    # Get number of teams from settings (default 2)
                    num_teams = int(self.settings.get("random_team_size", "2"))

                    # Create Random Teams game instance
                    game = random_teams.RandomTeamsGame(
                        controller_manager_client=self.controller_manager_client,
                        settings_client=self.settings_client,
                        event_publisher=self._publish_event,
                        game_id=self.game_id,
                        num_teams=num_teams
                    )

                    # Store reference
                    self.current_game = game

                    # Run the game (async)
                    await game.run()

                    logger.info("Random Teams game completed")

                else:
                    error_msg = f"Game mode '{self.game_name}' not implemented yet"
                    logger.error(error_msg)
                    self.game_state = game_coordinator_pb2.GameState.ENDED
                    self._publish_event("game_error", {"error": error_msg})

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"Game loop error: {e}", exc_info=True)
                self.game_state = game_coordinator_pb2.GameState.ENDED
                self._publish_event("game_error", {"error": str(e)})
            finally:
                self.game_running = False
                self.current_game = None

    def GetGameStatus(self, request, context):
        """Get current game status."""
        with tracer.start_as_current_span("GetGameStatus") as span:
            try:
                elapsed = 0
                if self.game_start_time and self.game_state == game_coordinator_pb2.GameState.RUNNING:
                    elapsed = int(time.time() - self.game_start_time)

                span.set_attribute("game.state", self.game_state)
                span.set_attribute("game.elapsed_seconds", elapsed)

                return game_coordinator_pb2.GetGameStatusResponse(
                    state=self.game_state,
                    game_name=self.game_name,
                    players=self.players,
                    elapsed_seconds=elapsed,
                    success=True,
                    error=""
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
                    error=str(e)
                )

    def ForceEndGame(self, request, context):
        """Force end the current game."""
        with tracer.start_as_current_span("ForceEndGame") as span:
            span.set_attribute("force_end.reason", request.reason)

            try:
                if self.game_state not in [game_coordinator_pb2.GameState.STARTING,
                                            game_coordinator_pb2.GameState.RUNNING]:
                    return game_coordinator_pb2.ForceEndGameResponse(
                        success=False,
                        error="No game in progress"
                    )

                # Stop game loop
                self.game_running = False

                # Call force_end on current game if it exists
                if self.current_game and hasattr(self.current_game, 'force_end'):
                    self.current_game.force_end()

                # Wait for thread to finish
                if self.game_thread and self.game_thread.is_alive():
                    self.game_thread.join(timeout=5.0)

                # Update state
                self.game_state = game_coordinator_pb2.GameState.ENDED

                # Publish event
                self._publish_event("game_force_ended", {
                    "reason": request.reason,
                    "game_id": self.game_id or "unknown"
                })

                logger.info(f"Force ended game: {request.reason}")

                return game_coordinator_pb2.ForceEndGameResponse(
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"ForceEndGame error: {e}", exc_info=True)
                return game_coordinator_pb2.ForceEndGameResponse(
                    success=False,
                    error=str(e)
                )

    async def StreamGameEvents(self, request, context):
        """Stream game events in real-time (async)."""
        subscriber_id = f"events_{time.time()}"

        with tracer.start_as_current_span("StreamGameEvents") as span:
            span.set_attribute("subscriber.id", subscriber_id)

            # Create queue for this subscriber
            event_queue = queue.Queue(maxsize=100)

            with self.event_lock:
                self.event_subscribers[subscriber_id] = event_queue

            logger.info(f"New event subscriber: {subscriber_id}")

            try:
                while not context.cancelled():
                    try:
                        # Non-blocking get with timeout
                        event = event_queue.get(timeout=0.1)
                        yield event

                    except queue.Empty:
                        # No event, yield control to event loop
                        await asyncio.sleep(0.1)
                        continue
                    except Exception as e:
                        logger.error(f"Stream error for {subscriber_id}: {e}")
                        break

            finally:
                # Cleanup
                with self.event_lock:
                    if subscriber_id in self.event_subscribers:
                        del self.event_subscribers[subscriber_id]

                logger.info(f"Event subscriber disconnected: {subscriber_id}")

    def _publish_event(self, event_type: str, data: Dict[str, str]):
        """Publish an event to all subscribers."""
        with tracer.start_as_current_span("publish_event") as span:
            span.set_attribute("event.type", event_type)

            event = game_coordinator_pb2.GameEvent(
                event_type=event_type,
                data=data,
                timestamp=int(time.time() * 1000)
            )

            with self.event_lock:
                subscriber_count = len(self.event_subscribers)
                span.set_attribute("subscribers.count", subscriber_count)

                for sub_id, event_queue in self.event_subscribers.items():
                    try:
                        event_queue.put_nowait(event)
                        logger.debug(f"Published {event_type} to subscriber {sub_id}")
                    except queue.Full:
                        logger.warning(f"Subscriber {sub_id} queue full, skipping event")
                    except Exception as e:
                        logger.error(f"Error publishing to subscriber {sub_id}: {e}")

    def shutdown(self):
        """Shutdown the game coordinator."""
        logger.info("Shutting down GameCoordinator...")
        self.game_running = False

        if self.game_thread and self.game_thread.is_alive():
            self.game_thread.join(timeout=5.0)


async def serve(port=50053):
    """Start the GameCoordinator async gRPC server."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create async server
    server = grpc.aio.server()

    # Add servicer
    game_servicer = GameCoordinatorServicer()
    game_coordinator_pb2_grpc.add_GameCoordinatorServiceServicer_to_server(
        game_servicer, server
    )

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the GameCoordinator service as SERVING
    await health_servicer.set("game_coordinator.GameCoordinatorService", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # Overall health

    # Bind to port
    server.add_insecure_port(f'[::]:{port}')

    # Start server
    logger.info(f"Starting GameCoordinator async gRPC server on port {port}")
    await server.start()

    logger.info(f"GameCoordinator server listening on port {port}")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down GameCoordinator server...")
        game_servicer.shutdown()
        await server.stop(grace=5)


if __name__ == '__main__':
    asyncio.run(serve())
