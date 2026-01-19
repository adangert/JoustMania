"""
Supervisor gRPC Servicer for JoustMania

Monitors and manages all microservices:
- Track process status
- Restart failed processes
- Stream health updates
- System-wide health summary
- Game orchestration (menu events -> game coordinator)
"""

import asyncio
import contextlib
import json
import logging
import queue
import threading
import time

import grpc
import grpc.aio
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from lib.grpc_utils import create_channel
from lib.telemetry import init_telemetry
from proto import (
    controller_manager_pb2_grpc,
    game_coordinator_pb2,
    game_coordinator_pb2_grpc,
    menu_pb2,
    menu_pb2_grpc,
    supervisor_pb2,
    supervisor_pb2_grpc,
)

logger = logging.getLogger(__name__)

# Initialize OpenTelemetry
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
            # Compression
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

    def GetProcessStatus(self, request, context):  # noqa: N802, ARG002
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

    def GetAllProcessStatus(self, request, context):  # noqa: N802, ARG002
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

    def RestartProcess(self, request, context):  # noqa: N802, ARG002
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

    def GetHealthSummary(self, request, context):  # noqa: N802, ARG002
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

    async def StreamProcessUpdates(self, request, context):  # noqa: N802, ARG002
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
        """Initialize gRPC clients for orchestration with trace propagation."""
        try:
            # Menu service (with tracing for context propagation)
            self.menu_channel = create_channel("menu:50054")
            self.menu_stub = menu_pb2_grpc.MenuServiceStub(self.menu_channel)
            logger.info("Connected to Menu service for orchestration")

            # Game Coordinator service (with tracing for StartGame calls)
            self.game_coordinator_channel = create_channel("game-coordinator:50053")
            self.game_coordinator_stub = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(
                self.game_coordinator_channel
            )
            logger.info("Connected to Game Coordinator service for orchestration")

            # Controller Manager service (with tracing for controller queries)
            self.controller_manager_channel = create_channel("controller-manager:50052")
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
                # Extract W3C Trace Context from event data (injected by Menu service)
                # This links the Supervisor's spans to the Menu's trace
                propagator = TraceContextTextMapPropagator()
                carrier = {
                    "traceparent": event.data.get("_traceparent", ""),
                    "tracestate": event.data.get("_tracestate", ""),
                }
                ctx = propagator.extract(carrier)

                # Create span with extracted context as parent
                with tracer.start_as_current_span("handle_menu_event", context=ctx) as span:
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

        This creates the trace link: Menu Event -> Supervisor -> StartGame -> Game

        The menu passes the controller list directly in the event - it is the
        source of truth for which controllers should participate in the game.
        """
        with tracer.start_as_current_span("orchestrate_game_start") as span:
            try:
                game_name = event.data.get("game_name", "JoustFFA")
                source = event.data.get("source", "unknown")
                span.set_attribute("game.name", game_name)
                span.set_attribute("game.source", source)

                logger.info(f"Orchestrating game start: {game_name} (source: {source})")

                # Get controllers from event - menu is source of truth
                # Controllers are JSON-encoded since MenuEvent.data is map<string, string>
                controllers_json = event.data.get("controllers", "[]")
                try:
                    controller_serials = json.loads(controllers_json) if controllers_json else []
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode controllers JSON: {controllers_json}")
                    controller_serials = []

                if not controller_serials:
                    logger.error("No controllers in event - Menu must provide controller list")
                    span.set_attribute("error", "no_controllers_in_event")
                    return

                logger.info(f"Starting game with {len(controller_serials)} controllers: {controller_serials}")

                # Convert controller serials to players
                players = []
                for i, serial in enumerate(controller_serials):
                    players.append(game_coordinator_pb2.Player(serial=serial, team=i % 2, alive=True, score=0))

                span.set_attribute("player.count", len(players))

                # Inject trace context into gRPC metadata for cross-service propagation
                propagator = TraceContextTextMapPropagator()
                carrier: dict[str, str] = {}
                propagator.inject(carrier)
                metadata = list(carrier.items())

                # Call game coordinator to start game with trace context
                start_response = await self.game_coordinator_stub.StartGame(
                    game_coordinator_pb2.StartGameRequest(game_name=game_name, players=players),
                    metadata=metadata,
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
