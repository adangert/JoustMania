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
from typing import Dict, List, Optional
from concurrent import futures
import grpc

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer

# Import protobuf
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.game_coordinator import game_coordinator_pb2, game_coordinator_pb2_grpc

# Game imports (optional for testing)
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
    logging.warning("Game modules not available - coordinator will run in mock mode")

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

    GrpcInstrumentorServer().instrument()

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

        logger.info("GameCoordinator initialized")

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

                # Start game in background thread
                self.game_running = True
                self.game_thread = threading.Thread(
                    target=self._run_game_loop,
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

    def _run_game_loop(self):
        """Run the game loop in background thread."""
        with tracer.start_as_current_span("game_loop") as span:
            span.set_attribute("game.name", self.game_name)
            span.set_attribute("game.id", self.game_id)

            try:
                # Transition to RUNNING
                self.game_state = game_coordinator_pb2.GameState.RUNNING

                # Mock game duration (30 seconds)
                game_duration = 30
                elapsed = 0

                while self.game_running and elapsed < game_duration:
                    time.sleep(1)
                    elapsed += 1

                    # Mock random player deaths
                    if elapsed % 10 == 0 and elapsed < game_duration:
                        # Kill a random alive player
                        alive_players = [p for p in self.players if p.alive]
                        if alive_players:
                            player = random.choice(alive_players)
                            player.alive = False
                            self._publish_event("player_death", {
                                "serial": player.serial,
                                "team": str(player.team)
                            })

                # Game ended
                self.game_state = game_coordinator_pb2.GameState.ENDING

                # Determine winner (highest score)
                if self.players:
                    winner = max(self.players, key=lambda p: p.score)
                    self._publish_event("game_end", {
                        "winner_serial": winner.serial,
                        "winner_team": str(winner.team),
                        "duration": str(elapsed)
                    })

                self.game_state = game_coordinator_pb2.GameState.ENDED

                logger.info(f"Game {self.game_id} ended after {elapsed}s")

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"Game loop error: {e}", exc_info=True)
                self.game_state = game_coordinator_pb2.GameState.ENDED
            finally:
                self.game_running = False

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

    def StreamGameEvents(self, request, context):
        """Stream game events in real-time."""
        subscriber_id = f"events_{time.time()}"

        with tracer.start_as_current_span("StreamGameEvents") as span:
            span.set_attribute("subscriber.id", subscriber_id)

            # Create queue for this subscriber
            event_queue = queue.Queue(maxsize=100)

            with self.event_lock:
                self.event_subscribers[subscriber_id] = event_queue

            logger.info(f"New event subscriber: {subscriber_id}")

            try:
                while context.is_active():
                    try:
                        # Block for up to 1 second waiting for event
                        event = event_queue.get(timeout=1.0)
                        yield event

                    except queue.Empty:
                        # No event, continue
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


def serve(port=50053):
    """Start the GameCoordinator gRPC server."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # Add servicer
    game_servicer = GameCoordinatorServicer()
    game_coordinator_pb2_grpc.add_GameCoordinatorServiceServicer_to_server(
        game_servicer, server
    )

    # Bind to port
    server.add_insecure_port(f'[::]:{port}')

    # Start server
    logger.info(f"Starting GameCoordinator gRPC server on port {port}")
    server.start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down GameCoordinator server...")
        game_servicer.shutdown()
        server.stop(grace=5)


if __name__ == '__main__':
    serve()
