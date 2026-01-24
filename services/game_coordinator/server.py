"""
GameCoordinator gRPC Server for JoustMania

Manages game lifecycle as a gRPC service:
- Start games with player configurations
- Monitor game state
- Force end games
- Stream game events (deaths, scoring, game end)

See services/game_coordinator/servicer.py for the GameCoordinatorServicer implementation.
"""

import asyncio
import logging
import os
import sys

# Configure logging early, before any logging calls
# This must happen before any logging.warning/info/etc to ensure INFO level is shown
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


# Filter to suppress noisy gRPC async errors
# These BlockingIOError messages from PollerCompletionQueue are harmless but noisy
# They occur due to gRPC's async polling internals and don't affect functionality
class GrpcPollerFilter(logging.Filter):
    """Filter out gRPC PollerCompletionQueue errors that spam the logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Suppress BlockingIOError from gRPC poller and related "Event loop is closed" errors
        msg = record.getMessage()
        return "PollerCompletionQueue" not in msg and "Event loop is closed" not in msg


# Apply filter to asyncio logger (where gRPC errors appear)
logging.getLogger("asyncio").addFilter(GrpcPollerFilter())

# Import protobuf (after logging config)
import grpc.aio  # noqa: E402
from grpc_health.v1 import health, health_pb2, health_pb2_grpc  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.otel_metrics import init_metrics  # noqa: E402
from lib.system_metrics import start_system_metrics_collector  # noqa: E402
from proto import game_coordinator_pb2_grpc  # noqa: E402
from services.game_coordinator import metrics  # noqa: E402
from services.game_coordinator.servicer import GameCoordinatorServicer  # noqa: E402

# Legacy game imports (optional for testing)
try:
    # Import legacy modules to test availability
    import piaudio  # noqa: F401

    import games  # noqa: F401

    GAMES_AVAILABLE = True
except ImportError:
    GAMES_AVAILABLE = False
    logging.warning("Legacy game modules not available - will use modern gRPC games")

logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info("GAME COORDINATOR BUILD: 2026-01-17 last-player-win-fix")
logger.info("=" * 60)


async def serve(port=50053):
    """Start the GameCoordinator async gRPC server."""
    # Note: logging.basicConfig() is now called at module level (top of file)
    # to ensure INFO level is enabled before any logging calls

    # Initialize OTEL push metrics (Issue #103)
    # 100ms export interval for real-time gameplay visualization
    init_metrics(service_name="game-coordinator", export_interval_ms=100)
    logger.info("OTEL push metrics initialized (100ms export interval)")

    # Start system metrics collection
    start_system_metrics_collector(
        cpu_gauge=metrics.process_cpu_percent,
        memory_gauge=metrics.process_memory_mb,
        threads_gauge=metrics.process_threads,
    )

    # Create async server with keepalive options and tracing interceptors
    from lib.grpc_tracing import get_server_interceptors
    from lib.grpc_utils import get_server_options

    server = grpc.aio.server(
        options=get_server_options(),
        interceptors=get_server_interceptors(),
    )

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
        await game_servicer.shutdown()
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
