"""
Supervisor gRPC Server for JoustMania

Monitors and manages all microservices as a gRPC service:
- Track process status
- Restart failed processes
- Stream health updates
- System-wide health summary

See services/supervisor/servicer.py for the SupervisorServicer implementation.
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
from proto import supervisor_pb2_grpc
from services.supervisor import metrics
from services.supervisor.servicer import SupervisorServicer

logger = logging.getLogger(__name__)


async def serve(port=50055, metrics_port=8000):
    """Start the Supervisor gRPC server."""
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
    supervisor_servicer = SupervisorServicer()
    supervisor_pb2_grpc.add_SupervisorServiceServicer_to_server(supervisor_servicer, server)

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the Supervisor service as SERVING
    await health_servicer.set("supervisor.SupervisorService", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # Overall health

    # Bind to port
    server.add_insecure_port(f"[::]:{port}")

    # Start server
    logger.info(f"Starting Supervisor gRPC server on port {port}")
    await server.start()

    # Start orchestration - subscribe to menu events and coordinate game lifecycle
    await supervisor_servicer.start_orchestration()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Supervisor server...")
        await supervisor_servicer.shutdown()
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
