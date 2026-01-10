"""
Supervisor gRPC Server for JoustMania

Monitors and manages all microservices as a gRPC service:
- Track process status
- Restart failed processes
- Stream health updates
- System-wide health summary

This replaces the Queue-based IPC with gRPC (Phase 8a).
"""

import logging
import time
import threading
import queue
from typing import Dict, List
from concurrent import futures
import grpc
import grpc.aio
import asyncio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

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

from services.supervisor import supervisor_pb2, supervisor_pb2_grpc

logger = logging.getLogger(__name__)

# Initialize OpenTelemetry
def init_telemetry():
    """Initialize OpenTelemetry with OTLP exporter."""
    otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4317')
    service_name = os.getenv('OTEL_SERVICE_NAME', 'supervisor-service')

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


class SupervisorServicer(supervisor_pb2_grpc.SupervisorServiceServicer):
    """
    Supervisor gRPC servicer.

    Monitors and manages all microservices:
    - Track process status
    - Health monitoring
    - Restart management
    """

    def __init__(self):
        """Initialize supervisor."""
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

            # Message size limits (10MB for large messages)
            ('grpc.max_receive_message_length', 10 * 1024 * 1024),
            ('grpc.max_send_message_length', 10 * 1024 * 1024),
        ]

        self.processes: Dict[str, Dict] = {
            "Settings": {
                "name": "Settings",
                "pid": 0,
                "status": supervisor_pb2.ProcessStatus.RUNNING,
                "uptime_seconds": 0,
                "restart_count": 0,
                "last_error": "",
                "critical": True,
                "last_health_check_ago": 0
            },
            "ControllerManager": {
                "name": "ControllerManager",
                "pid": 0,
                "status": supervisor_pb2.ProcessStatus.RUNNING,
                "uptime_seconds": 0,
                "restart_count": 0,
                "last_error": "",
                "critical": True,
                "last_health_check_ago": 0
            },
            "GameCoordinator": {
                "name": "GameCoordinator",
                "pid": 0,
                "status": supervisor_pb2.ProcessStatus.RUNNING,
                "uptime_seconds": 0,
                "restart_count": 0,
                "last_error": "",
                "critical": True,
                "last_health_check_ago": 0
            },
            "Menu": {
                "name": "Menu",
                "pid": 0,
                "status": supervisor_pb2.ProcessStatus.RUNNING,
                "uptime_seconds": 0,
                "restart_count": 0,
                "last_error": "",
                "critical": False,
                "last_health_check_ago": 0
            }
        }

        # Start times
        self.start_time = time.time()
        self.process_start_times: Dict[str, float] = {
            name: self.start_time for name in self.processes.keys()
        }

        # Event streaming
        self.event_subscribers: Dict[str, queue.Queue] = {}
        self.event_lock = threading.Lock()

        # Health monitoring thread
        self.running = True
        self.health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self.health_thread.start()

        logger.info("Supervisor initialized")

    def _health_check_loop(self):
        """Background thread for health checking."""
        with tracer.start_as_current_span("health_check_loop"):
            while self.running:
                try:
                    with tracer.start_as_current_span("health_check_cycle") as span:
                        # Update uptime for all running processes
                        current_time = time.time()
                        healthy_count = 0
                        unhealthy_count = 0

                        for name, info in self.processes.items():
                            if info["status"] == supervisor_pb2.ProcessStatus.RUNNING:
                                start_time = self.process_start_times.get(name, current_time)
                                info["uptime_seconds"] = int(current_time - start_time)
                                info["last_health_check_ago"] = 0
                                healthy_count += 1
                            else:
                                info["last_health_check_ago"] += 5
                                unhealthy_count += 1

                        span.set_attribute("processes.healthy", healthy_count)
                        span.set_attribute("processes.unhealthy", unhealthy_count)

                    time.sleep(5.0)  # Check every 5 seconds

                except Exception as e:
                    logger.error(f"Health check loop error: {e}", exc_info=True)
                    time.sleep(5.0)

    def GetProcessStatus(self, request, context):
        """Get status of a specific process."""
        with tracer.start_as_current_span("GetProcessStatus") as span:
            span.set_attribute("process.name", request.name)

            try:
                if request.name not in self.processes:
                    return supervisor_pb2.GetProcessStatusResponse(
                        success=False,
                        error=f"Process {request.name} not found"
                    )

                info = self.processes[request.name]
                process_info = self._build_process_info(info)

                return supervisor_pb2.GetProcessStatusResponse(
                    info=process_info,
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetProcessStatus error: {e}", exc_info=True)
                return supervisor_pb2.GetProcessStatusResponse(
                    success=False,
                    error=str(e)
                )

    def GetAllProcessStatus(self, request, context):
        """Get status of all processes."""
        with tracer.start_as_current_span("GetAllProcessStatus") as span:
            try:
                processes = [
                    self._build_process_info(info)
                    for info in self.processes.values()
                ]

                span.set_attribute("processes.count", len(processes))

                return supervisor_pb2.GetAllProcessStatusResponse(
                    processes=processes,
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetAllProcessStatus error: {e}", exc_info=True)
                return supervisor_pb2.GetAllProcessStatusResponse(
                    processes=[],
                    success=False,
                    error=str(e)
                )

    def RestartProcess(self, request, context):
        """Restart a failed process."""
        with tracer.start_as_current_span("RestartProcess") as span:
            span.set_attribute("process.name", request.name)

            try:
                if request.name not in self.processes:
                    return supervisor_pb2.RestartProcessResponse(
                        success=False,
                        error=f"Process {request.name} not found"
                    )

                info = self.processes[request.name]

                # Simulate restart
                info["status"] = supervisor_pb2.ProcessStatus.STARTING
                info["restart_count"] += 1
                self.process_start_times[request.name] = time.time()

                # Transition to RUNNING after a moment
                info["status"] = supervisor_pb2.ProcessStatus.RUNNING
                info["last_error"] = ""

                logger.info(f"Restarted process: {request.name}")

                span.set_attribute("process.restart_count", info["restart_count"])

                return supervisor_pb2.RestartProcessResponse(
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"RestartProcess error: {e}", exc_info=True)
                return supervisor_pb2.RestartProcessResponse(
                    success=False,
                    error=str(e)
                )

    def GetHealthSummary(self, request, context):
        """Get system health summary."""
        with tracer.start_as_current_span("GetHealthSummary") as span:
            try:
                total = len(self.processes)
                running = sum(1 for p in self.processes.values()
                             if p["status"] == supervisor_pb2.ProcessStatus.RUNNING)
                failed = sum(1 for p in self.processes.values()
                            if p["status"] == supervisor_pb2.ProcessStatus.FAILED)

                unhealthy = [
                    self._build_process_info(info)
                    for info in self.processes.values()
                    if info["status"] != supervisor_pb2.ProcessStatus.RUNNING
                ]

                all_healthy = (running == total)

                span.set_attribute("health.all_healthy", all_healthy)
                span.set_attribute("processes.total", total)
                span.set_attribute("processes.running", running)
                span.set_attribute("processes.failed", failed)

                return supervisor_pb2.GetHealthSummaryResponse(
                    all_healthy=all_healthy,
                    total_processes=total,
                    running_processes=running,
                    failed_processes=failed,
                    unhealthy=unhealthy,
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetHealthSummary error: {e}", exc_info=True)
                return supervisor_pb2.GetHealthSummaryResponse(
                    all_healthy=False,
                    total_processes=0,
                    running_processes=0,
                    failed_processes=0,
                    unhealthy=[],
                    success=False,
                    error=str(e)
                )

    async def StreamProcessUpdates(self, request, context):
        """Stream process status updates (async)."""
        subscriber_id = f"supervisor_{time.time()}"

        with tracer.start_as_current_span("StreamProcessUpdates") as span:
            span.set_attribute("subscriber.id", subscriber_id)
            span.set_attribute("interval_seconds", request.interval_seconds or 5)

            logger.info(f"New supervisor stream subscriber: {subscriber_id}")

            try:
                interval = request.interval_seconds or 5

                while not context.cancelled():
                    # Build current status
                    processes = [
                        self._build_process_info(info)
                        for info in self.processes.values()
                    ]

                    update = supervisor_pb2.ProcessStatusUpdate(
                        processes=processes,
                        timestamp=int(time.time() * 1000)
                    )

                    yield update

                    # Use async sleep
                    await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Stream error for {subscriber_id}: {e}")
            finally:
                logger.info(f"Supervisor stream subscriber disconnected: {subscriber_id}")

    def _build_process_info(self, info: Dict) -> supervisor_pb2.ProcessInfo:
        """Build a ProcessInfo protobuf message."""
        return supervisor_pb2.ProcessInfo(
            name=info["name"],
            pid=info["pid"],
            status=info["status"],
            uptime_seconds=info["uptime_seconds"],
            restart_count=info["restart_count"],
            last_error=info["last_error"],
            critical=info["critical"],
            last_health_check_ago=info["last_health_check_ago"]
        )

    def shutdown(self):
        """Shutdown the supervisor."""
        logger.info("Shutting down Supervisor...")
        self.running = False
        self.health_thread.join(timeout=5.0)


async def serve(port=50055):
    """Start the Supervisor gRPC server."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create server
    server = grpc.aio.server()

    # Add servicer
    supervisor_servicer = SupervisorServicer()
    supervisor_pb2_grpc.add_SupervisorServiceServicer_to_server(
        supervisor_servicer, server
    )

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the Supervisor service as SERVING
    await health_servicer.set("supervisor.SupervisorService", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # Overall health

    # Bind to port
    server.add_insecure_port(f'[::]:{port}')

    # Start server
    logger.info(f"Starting Supervisor gRPC server on port {port}")
    await server.start()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Supervisor server...")
        supervisor_servicer.shutdown()
        await server.stop(grace=5)


if __name__ == '__main__':
    asyncio.run(serve())
