"""
Menu gRPC Server for JoustMania

Manages the game selection menu and lobby experience:
- Game mode selection and cycling
- Controller lobby state (connected/ready)
- LED feedback based on game mode and player state
- Admin mode for in-game configuration
- Real-time event streaming for UI updates

See services/menu/README.md for full documentation.
"""

import asyncio
import contextlib
import logging
import os

import grpc.aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from prometheus_client import start_http_server

from lib.system_metrics import start_system_metrics_collector
from proto import menu_pb2, menu_pb2_grpc
from services.menu import metrics
from services.menu.servicer import MenuServicer

logger = logging.getLogger(__name__)


async def serve(port=50054, metrics_port=8000):
    """Start the Menu gRPC server."""
    # Configure logging
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Start Prometheus metrics HTTP server
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics available at http://0.0.0.0:{metrics_port}/metrics")

    # Start system metrics collection
    background_tasks = []
    metrics_task = start_system_metrics_collector(
        cpu_gauge=metrics.process_cpu_percent,
        memory_gauge=metrics.process_memory_mb,
        threads_gauge=metrics.process_threads,
    )
    background_tasks.append(metrics_task)

    # Create server
    from lib.grpc_utils import get_server_options

    server = grpc.aio.server(options=get_server_options())

    # Add servicer
    menu_servicer = MenuServicer()
    menu_pb2_grpc.add_MenuServiceServicer_to_server(menu_servicer, server)

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the Menu service as SERVING
    await health_servicer.set("menu.MenuService", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    # Bind to port
    server.add_insecure_port(f"[::]:{port}")

    # Start server
    logger.info(f"Starting Menu gRPC server on port {port}")
    await server.start()

    # Start controller button monitoring
    await menu_servicer.start_button_monitor()

    # Start game event monitoring (stops button monitor during games)
    await menu_servicer.start_game_event_monitor()

    # Auto-start menu (so controllers light up immediately)
    auto_start = os.getenv("MENU_AUTO_START", "true").lower() == "true"
    if auto_start:
        menu_servicer.state = menu_pb2.MenuState.RUNNING
        menu_servicer.current_selection = "JoustFFA"
        logger.info("Menu auto-started (MENU_AUTO_START=true)")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Menu server...")

        # Cancel background tasks
        for task in background_tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        logger.info("Background tasks cancelled")

        await menu_servicer.stop_button_monitor()
        await menu_servicer.stop_game_event_monitor()
        await menu_servicer.shutdown()
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
