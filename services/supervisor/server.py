"""
Supervisor gRPC Server for JoustMania

Monitors and manages all microservices as a gRPC service:
- Track process status
- Restart failed processes
- Stream health updates
- System-wide health summary

This replaces the Queue-based IPC with gRPC (Phase 8a).
"""

import asyncio
import logging
import os
import queue

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
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import contextlib

import psutil

# Prometheus metrics (Phase 38)
from prometheus_client import start_http_server

from proto import (
    controller_manager_pb2,
    controller_manager_pb2_grpc,
    game_coordinator_pb2,
    game_coordinator_pb2_grpc,
    menu_pb2,
    menu_pb2_grpc,
    supervisor_pb2,
    supervisor_pb2_grpc,
)
from services.supervisor import metrics

logger = logging.getLogger(__name__)


# Initialize OpenTelemetry
def init_telemetry():
    """Initialize OpenTelemetry with OTLP exporter."""
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    service_name = os.getenv("OTEL_SERVICE_NAME", "supervisor-service")

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
        [
            # Keep-alive settings to detect dead connections
            ("grpc.keepalive_time_ms", 30000),  # Send keepalive ping every 30s
            ("grpc.keepalive_timeout_ms", 5000),  # Wait 5s for keepalive ack
            ("grpc.keepalive_permit_without_calls", True),  # Allow keepalive pings when no calls
            ("grpc.http2.max_pings_without_data", 2),  # Allow 2 pings without data
            # Connection and timeout settings
            ("grpc.initial_reconnect_backoff_ms", 1000),  # 1s initial backoff
            ("grpc.max_reconnect_backoff_ms", 5000),  # 5s max backoff
            # Message size limits (10MB for large messages)
            ("grpc.max_receive_message_length", 10 * 1024 * 1024),
            ("grpc.max_send_message_length", 10 * 1024 * 1024),
            # Compression (Phase 26 - Performance)
            ("grpc.default_compression_algorithm", grpc.Compression.Gzip),
            ("grpc.grpc.default_compression_level", grpc.Compression.Gzip),
        ]

        self.processes: dict[str, dict] = {
            "Settings": {
                "name": "Settings",
                "pid": 0,
                "status": supervisor_pb2.ProcessStatus.RUNNING,
                "uptime_seconds": 0,
                "restart_count": 0,
                "last_error": "",
                "critical": True,
                "last_health_check_ago": 0,
            },
            "ControllerManager": {
                "name": "ControllerManager",
                "pid": 0,
                "status": supervisor_pb2.ProcessStatus.RUNNING,
                "uptime_seconds": 0,
                "restart_count": 0,
                "last_error": "",
                "critical": True,
                "last_health_check_ago": 0,
            },
            "GameCoordinator": {
                "name": "GameCoordinator",
                "pid": 0,
                "status": supervisor_pb2.ProcessStatus.RUNNING,
                "uptime_seconds": 0,
                "restart_count": 0,
                "last_error": "",
                "critical": True,
                "last_health_check_ago": 0,
            },
            "Menu": {
                "name": "Menu",
                "pid": 0,
                "status": supervisor_pb2.ProcessStatus.RUNNING,
                "uptime_seconds": 0,
                "restart_count": 0,
                "last_error": "",
                "critical": False,
                "last_health_check_ago": 0,
            },
        }

        # Start times
        self.start_time = time.time()
        self.process_start_times: dict[str, float] = dict.fromkeys(self.processes.keys(), self.start_time)

        # Event streaming
        self.event_subscribers: dict[str, queue.Queue] = {}
        self.event_lock = threading.Lock()

        # gRPC clients for orchestration (game lifecycle)
        self.menu_channel = None
        self.menu_stub = None
        self.game_coordinator_channel = None
        self.game_coordinator_stub = None
        self.controller_manager_channel = None
        self.controller_manager_stub = None

        # Orchestration state
        self.menu_event_task = None
        self.orchestration_running = False

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
                        success=False, error=f"Process {request.name} not found"
                    )

                info = self.processes[request.name]
                process_info = self._build_process_info(info)

                return supervisor_pb2.GetProcessStatusResponse(info=process_info, success=True, error="")

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetProcessStatus error: {e}", exc_info=True)
                return supervisor_pb2.GetProcessStatusResponse(success=False, error=str(e))

    def GetAllProcessStatus(self, request, context):
        """Get status of all processes."""
        with tracer.start_as_current_span("GetAllProcessStatus") as span:
            try:
                processes = [self._build_process_info(info) for info in self.processes.values()]

                span.set_attribute("processes.count", len(processes))

                return supervisor_pb2.GetAllProcessStatusResponse(processes=processes, success=True, error="")

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetAllProcessStatus error: {e}", exc_info=True)
                return supervisor_pb2.GetAllProcessStatusResponse(processes=[], success=False, error=str(e))

    def RestartProcess(self, request, context):
        """Restart a failed process."""
        with tracer.start_as_current_span("RestartProcess") as span:
            span.set_attribute("process.name", request.name)

            try:
                if request.name not in self.processes:
                    return supervisor_pb2.RestartProcessResponse(
                        success=False, error=f"Process {request.name} not found"
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

                return supervisor_pb2.RestartProcessResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"RestartProcess error: {e}", exc_info=True)
                return supervisor_pb2.RestartProcessResponse(success=False, error=str(e))

    def GetHealthSummary(self, request, context):
        """Get system health summary."""
        with tracer.start_as_current_span("GetHealthSummary") as span:
            try:
                total = len(self.processes)
                running = sum(1 for p in self.processes.values() if p["status"] == supervisor_pb2.ProcessStatus.RUNNING)
                failed = sum(1 for p in self.processes.values() if p["status"] == supervisor_pb2.ProcessStatus.FAILED)

                unhealthy = [
                    self._build_process_info(info)
                    for info in self.processes.values()
                    if info["status"] != supervisor_pb2.ProcessStatus.RUNNING
                ]

                all_healthy = running == total

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
                    error="",
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
                    error=str(e),
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
                    processes = [self._build_process_info(info) for info in self.processes.values()]

                    update = supervisor_pb2.ProcessStatusUpdate(processes=processes, timestamp=int(time.time() * 1000))

                    yield update

                    # Use async sleep
                    await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Stream error for {subscriber_id}: {e}")
            finally:
                logger.info(f"Supervisor stream subscriber disconnected: {subscriber_id}")

    def _build_process_info(self, info: dict) -> supervisor_pb2.ProcessInfo:
        """Build a ProcessInfo protobuf message."""
        return supervisor_pb2.ProcessInfo(
            name=info["name"],
            pid=info["pid"],
            status=info["status"],
            uptime_seconds=info["uptime_seconds"],
            restart_count=info["restart_count"],
            last_error=info["last_error"],
            critical=info["critical"],
            last_health_check_ago=info["last_health_check_ago"],
        )

    # ========================================================================
    # Game Orchestration - Subscribe to Menu Events and Start Games
    # ========================================================================

    async def _init_grpc_clients(self):
        """Initialize gRPC clients for orchestration."""
        try:
            # Menu service
            self.menu_channel = grpc.aio.insecure_channel("menu:50054")
            self.menu_stub = menu_pb2_grpc.MenuServiceStub(self.menu_channel)
            logger.info("Connected to Menu service for orchestration")

            # Game Coordinator service
            self.game_coordinator_channel = grpc.aio.insecure_channel("game-coordinator:50053")
            self.game_coordinator_stub = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(
                self.game_coordinator_channel
            )
            logger.info("Connected to Game Coordinator service for orchestration")

            # Controller Manager service
            self.controller_manager_channel = grpc.aio.insecure_channel("controller-manager:50052")
            self.controller_manager_stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(
                self.controller_manager_channel
            )
            logger.info("Connected to Controller Manager service for orchestration")

        except Exception as e:
            logger.error(f"Failed to initialize orchestration gRPC clients: {e}", exc_info=True)
            raise

    async def start_orchestration(self):
        """Start game orchestration - subscribe to menu events."""
        if self.orchestration_running:
            logger.warning("Orchestration already running")
            return

        try:
            # Initialize gRPC clients
            await self._init_grpc_clients()

            # Start menu event listener
            self.orchestration_running = True
            self.menu_event_task = asyncio.create_task(self._menu_event_listener())
            logger.info("Game orchestration started")

        except Exception as e:
            logger.error(f"Failed to start orchestration: {e}", exc_info=True)
            self.orchestration_running = False

    async def _menu_event_listener(self):
        """Listen to menu events and orchestrate game lifecycle."""
        try:
            # Subscribe to menu events
            request = menu_pb2.StreamMenuEventsRequest()

            logger.info("Subscribing to menu events...")

            async for event in self.menu_stub.StreamMenuEvents(request):
                with tracer.start_as_current_span("handle_menu_event") as span:
                    span.set_attribute("event.type", event.event_type)
                    logger.info(f"Received menu event: {event.event_type}")

                    # Handle game_requested event
                    if event.event_type == "game_requested":
                        await self._handle_game_requested(event)

        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.CANCELLED:
                logger.info("Menu event stream cancelled")
            else:
                logger.error(f"Menu event stream error: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error in menu event listener: {e}", exc_info=True)
        finally:
            self.orchestration_running = False
            logger.info("Menu event listener stopped")

    async def _handle_game_requested(self, event: menu_pb2.MenuEvent):
        """
        Handle game_requested event from menu - start the game.

        This creates the trace link: Menu Event → Supervisor → StartGame → Game
        """
        with tracer.start_as_current_span("orchestrate_game_start") as span:
            try:
                game_name = event.data.get("game_name", "JoustFFA")
                span.set_attribute("game.name", game_name)

                logger.info(f"Orchestrating game start: {game_name}")

                # Get ready controllers from controller manager
                controllers_response = await self.controller_manager_stub.GetReadyControllers(
                    controller_manager_pb2.GetReadyControllersRequest()
                )

                if not controllers_response.success:
                    logger.error(f"Failed to get ready controllers: {controllers_response.error}")
                    return

                logger.info(f"Got {len(controllers_response.controllers)} ready controllers")

                # Convert controllers to players
                players = []
                for i, controller in enumerate(controllers_response.controllers):
                    players.append(
                        game_coordinator_pb2.Player(serial=controller.serial, team=i % 2, alive=True, score=0)
                    )

                span.set_attribute("player.count", len(players))

                # Call game coordinator to start game
                # This will create a FOLLOWS_FROM link to this span
                start_response = await self.game_coordinator_stub.StartGame(
                    game_coordinator_pb2.StartGameRequest(game_name=game_name, players=players)
                )

                if start_response.success:
                    logger.info(f"Game started successfully: {start_response.game_id}")
                    span.set_attribute("game.id", start_response.game_id)
                else:
                    logger.error(f"Failed to start game: {start_response.error}")
                    span.set_attribute("error", start_response.error)

            except Exception as e:
                logger.error(f"Error handling game_requested: {e}", exc_info=True)
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

    async def shutdown(self):
        """Shutdown the supervisor."""
        logger.info("Shutting down Supervisor...")
        self.running = False
        self.orchestration_running = False

        # Cancel menu event listener task
        if self.menu_event_task:
            self.menu_event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.menu_event_task

        # Close gRPC channels
        if self.menu_channel:
            await self.menu_channel.close()
        if self.game_coordinator_channel:
            await self.game_coordinator_channel.close()
        if self.controller_manager_channel:
            await self.controller_manager_channel.close()

        self.health_thread.join(timeout=5.0)


async def serve(port=50055, metrics_port=8000):
    """Start the Supervisor gRPC server."""
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
                cpu_percent = await loop.run_in_executor(None, lambda: process.cpu_percent(interval=None))
                mem_info = await loop.run_in_executor(None, lambda: process.memory_info())
                thread_count = await loop.run_in_executor(None, process.num_threads)

                metrics.process_cpu_percent.set(cpu_percent)
                metrics.process_memory_mb.set(mem_info.rss / 1024 / 1024)
                metrics.process_threads.set(thread_count)
            except Exception as e:
                logger.error(f"Error collecting system metrics: {e}")
            await asyncio.sleep(10.0)

    asyncio.create_task(collect_system_metrics())

    # Create server
    server = grpc.aio.server()

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
