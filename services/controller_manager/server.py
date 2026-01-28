"""
ControllerManager gRPC Server entry point for JoustMania.

This module provides the entry point for the ControllerManager service.
The actual servicer implementation is in servicer.py.
"""

import asyncio
import logging
import os

import grpc
import grpc.aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from lib.otel_metrics import init_metrics
from lib.system_metrics import start_system_metrics_collector
from proto import controller_manager_pb2_grpc
from services.controller_manager import metrics
from services.controller_manager.servicer import ControllerManagerServicer

logger = logging.getLogger(__name__)


async def serve(port=50052):
    """Start the ControllerManager async gRPC server."""
    # Configure logging with environment variable support
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Initialize OTEL push metrics (Issue #104)
    # 1000ms export interval - controller metrics don't need sub-second updates
    init_metrics(service_name="controller-manager", export_interval_ms=1000)
    logger.info("OTEL push metrics initialized (1000ms export interval)")

    # Start system metrics collection (Phase 61: extracted to lib/system_metrics.py)
    start_system_metrics_collector(
        cpu_gauge=metrics.process_cpu_percent,
        memory_gauge=metrics.process_memory_mb,
        threads_gauge=metrics.process_threads,
    )

    # Create async server with keepalive options and tracing interceptors
    # Without keepalive options, server rejects client pings as "too many pings"
    from lib.grpc_tracing import get_server_interceptors
    from lib.grpc_utils import get_server_options

    server = grpc.aio.server(
        options=get_server_options(),
        interceptors=get_server_interceptors(),
    )

    # Add servicer
    controller_servicer = ControllerManagerServicer()
    controller_manager_pb2_grpc.add_ControllerManagerServiceServicer_to_server(controller_servicer, server)

    # Start discovery loop immediately (don't defer to first stream connection)
    # This ensures controllers are discovered before any clients connect
    controller_servicer.discovery_loop.start()
    controller_servicer._discovery_started = True

    # Wait for backend initialization before accepting connections
    init_success = await controller_servicer.discovery_loop.wait_initialized(timeout_seconds=10.0)
    if init_success:
        logger.info("Discovery loop started and backend initialized")
    else:
        logger.warning("Discovery loop started but backend initialization may have failed")

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the ControllerManager service as SERVING
    await health_servicer.set("controller_manager.ControllerManagerService", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # Overall health

    # Bind to port
    server.add_insecure_port(f"[::]:{port}")

    # Start server
    logger.info(f"Starting ControllerManager async gRPC server on port {port}")
    await server.start()

    logger.info(f"ControllerManager server listening on port {port}")

    # Phase 57: If using mock backend, start MockControllerService on port 50062
    mock_server = None
    if controller_servicer.backend.__class__.__name__ == "MockBackend":
        from proto import controller_manager_mock_pb2_grpc
        from services.controller_manager.mock_control_service import MockControllerService

        mock_server = grpc.aio.server(options=get_server_options())
        mock_servicer = MockControllerService(controller_servicer.backend)
        controller_manager_mock_pb2_grpc.add_MockControllerServiceServicer_to_server(mock_servicer, mock_server)

        mock_port = 50062
        mock_server.add_insecure_port(f"[::]:{mock_port}")
        await mock_server.start()
        logger.info(f"MockControllerService listening on port {mock_port}")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down ControllerManager server...")
        await controller_servicer.shutdown()
        await server.stop(grace=5)

        # Stop mock server if running
        if mock_server:
            await mock_server.stop(grace=5)


if __name__ == "__main__":
    # Performance optimization: Use uvloop for faster event loop on Linux
    # uvloop provides 2-4x faster asyncio performance by using libuv
    try:
        import uvloop

        uvloop.install()
        logger.info("uvloop installed for improved asyncio performance")
    except ImportError:
        # uvloop not available (e.g., macOS/Windows development)
        pass

    asyncio.run(serve())
