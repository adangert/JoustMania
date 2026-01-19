"""
Settings gRPC Server for JoustMania

Manages settings as a gRPC service:
- Load/save settings from/to YAML file
- Validate setting updates against schema
- Provide gRPC interface for queries and updates
- Publish change events via streaming

See services/settings/servicer.py for the SettingsServicer implementation.
"""

import asyncio
import logging
import os
import sys

import grpc.aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from prometheus_client import start_http_server

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.system_metrics import start_system_metrics_collector
from proto import settings_pb2_grpc
from services.settings import metrics
from services.settings.servicer import SettingsServicer

logger = logging.getLogger(__name__)


async def serve(port: int = 50051, metrics_port: int = 8000):
    """
    Start the Settings gRPC server.

    Args:
        port: Port to listen on (default: 50051)
        metrics_port: Port for Prometheus metrics (default: 8000)
    """
    # Configure logging with environment variable support
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Start Prometheus metrics HTTP server
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics available at http://0.0.0.0:{metrics_port}/metrics")

    # Start system metrics collection
    start_system_metrics_collector(
        cpu_gauge=metrics.process_cpu_percent,
        memory_gauge=metrics.process_memory_mb,
        threads_gauge=metrics.process_threads,
    )

    # Create server with keepalive options to match client settings
    from lib.grpc_utils import get_server_options

    server = grpc.aio.server(options=get_server_options())

    # Add servicer
    settings_servicer = SettingsServicer()
    settings_pb2_grpc.add_SettingsServiceServicer_to_server(settings_servicer, server)

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the Settings service as SERVING
    await health_servicer.set("settings.SettingsService", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # Overall health

    # Bind to port
    server.add_insecure_port(f"[::]:{port}")

    # Start server
    logger.info(f"Starting Settings gRPC server on port {port}")
    await server.start()

    try:
        # Keep server running
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Settings server...")
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
