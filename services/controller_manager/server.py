"""
ControllerManager gRPC Server for JoustMania

Manages PS Move controller lifecycle as a gRPC service:
- Discover and pair controllers
- Stream controller states in real-time
- Provide controller query interface
- Handle controller removal

This replaces the Queue-based IPC with gRPC (Phase 8a).
"""

import asyncio
import logging
import os

# Import protobuf
import sys
import threading
import time
from collections import deque

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

from proto import controller_manager_pb2, controller_manager_pb2_grpc
from services.controller_manager import metrics
from services.controller_manager.effects_base import ControllerEffectsBase

# PS Move imports (optional for testing)
try:
    from multiprocessing import Process

    import pair as pair_module
    import psmove
    from controller_state import ControllerState

    PSMOVE_AVAILABLE = True
except ImportError:
    PSMOVE_AVAILABLE = False
    logging.warning("psmove not available - controller manager will run in mock mode")

logger = logging.getLogger(__name__)


# Initialize OpenTelemetry
def init_telemetry():
    """Initialize OpenTelemetry with OTLP exporter."""
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    service_name = os.getenv("OTEL_SERVICE_NAME", "controller-manager-service")

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


class MessagePool:
    """Pool of reusable protobuf messages (Phase 18 - Task 3)."""

    def __init__(self, message_class, pool_size=10):
        """Initialize message pool with pre-allocated messages."""
        self.pool = deque([message_class() for _ in range(pool_size)])
        self.message_class = message_class
        self.lock = threading.Lock()

    def get(self):
        """Get a message from pool or create new if empty."""
        with self.lock:
            if self.pool:
                msg = self.pool.popleft()
                msg.Clear()
                return msg
        # Pool empty, create new message
        return self.message_class()

    def return_msg(self, msg):
        """Return message to pool for reuse."""
        with self.lock:
            self.pool.append(msg)


class ControllerManagerServicer(controller_manager_pb2_grpc.ControllerManagerServiceServicer, ControllerEffectsBase):
    """
    ControllerManager gRPC servicer.

    Manages PS Move controllers:
    - Discovery and pairing
    - Controller process spawning
    - State monitoring and streaming
    - Health checking

    Phase 40: Inherits from ControllerEffectsBase for shared effect logic.
    """

    def __init__(self):
        """Initialize controller manager."""
        ControllerEffectsBase.__init__(self)  # Initialize effects base class
        self.tracked_controllers: dict[str, dict] = {}  # serial -> controller info
        self.controller_states: dict[str, ControllerState] = {}  # serial -> state
        self.controller_processes: dict[str, Process] = {}  # serial -> process
        self.paired_serials: list[str] = []

        # Streaming subscribers (Phase 34: async queue and lock)
        self.stream_subscribers: dict[str, asyncio.Queue] = {}
        self.stream_lock = asyncio.Lock()

        # Button event streaming (Phase 41, Phase 34: async queue and lock)
        self.button_event_subscribers: dict[str, asyncio.Queue] = {}
        self.button_states: dict[str, dict[str, bool]] = {}  # {serial: {button_name: pressed}}
        self.button_event_lock = asyncio.Lock()

        # Delta update tracking (Phase 26 - Part 3)
        # Store last sent state per subscriber per controller
        # Format: {subscriber_id: {serial: ControllerState}}
        self.last_sent_states: dict[str, dict[str, any]] = {}

        # State caching (Phase 18 - Task 1)
        # Cache protobuf messages to avoid rebuilding on every frame
        # Format: {serial: {'cached_state': ControllerState, 'snapshot_hash': str, 'dirty': bool}}
        self.state_cache: dict[str, dict] = {}

        # Protobuf object pools (Phase 18 - Task 3)
        self.controller_state_pool = MessagePool(controller_manager_pb2.ControllerState, pool_size=10)
        self.vector3_pool = MessagePool(controller_manager_pb2.Vector3, pool_size=20)

        # Controller effects (Phase 31 / Phase 40)
        # active_effects dict inherited from ControllerEffectsBase
        # Phase 34: Use async lock since effects are managed from async gRPC methods
        self.effect_lock = asyncio.Lock()

        # Battery monitoring (Phase 39 - Task 4)
        self.last_battery_warning: dict[str, float] = {}  # {serial: timestamp of last warning}
        self.low_battery_threshold = 1  # Battery level 0 or 1 (out of 5) = <20%
        self.last_battery_check = 0.0  # Timestamp of last battery check

        # RSSI monitoring (Phase 48)
        self.controller_rssi: dict[str, int] = {}  # {serial: rssi_dbm}
        self.controller_bt_addresses: dict[str, str] = {}  # {serial: bluetooth_address}
        self.last_rssi_check = 0.0
        self.rssi_check_interval = 10.0  # Check RSSI every 10 seconds
        self.weak_signal_threshold = -80  # Warn if RSSI < -80 dBm
        self.last_rssi_warning: dict[str, float] = {}  # {serial: timestamp}

        # Discovery thread
        self.running = True
        self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.discovery_thread.start()

        logger.info("ControllerManager initialized")

    def _discovery_loop(self):
        """Background thread for controller discovery and battery monitoring."""
        with tracer.start_as_current_span("discovery_loop"):
            while self.running:
                try:
                    current_time = time.time()

                    # Check for new controllers every second
                    with tracer.start_as_current_span("check_new_controllers") as span:
                        if PSMOVE_AVAILABLE:
                            self._check_for_new_controllers()
                        span.set_attribute("controller.count", len(self.tracked_controllers))

                    # Check battery levels every 30 seconds (Phase 39 - Task 4)
                    if current_time - self.last_battery_check >= 30.0:
                        self._check_battery_levels()
                        self.last_battery_check = current_time

                    # Check RSSI every 10 seconds (Phase 48)
                    if current_time - self.last_rssi_check >= self.rssi_check_interval:
                        self._check_rssi_levels()
                        self.last_rssi_check = current_time

                    time.sleep(1.0)  # Check every second

                except Exception as e:
                    logger.error(f"Discovery loop error: {e}", exc_info=True)
                    time.sleep(5.0)

    def _check_for_new_controllers(self):
        """Check for newly connected controllers (hardware)."""
        if not PSMOVE_AVAILABLE:
            return

        with tracer.start_as_current_span("discover_controllers") as span:
            try:
                count = psmove.count_connected()
                span.set_attribute("psmove.count", count)

                for move_num in range(count):
                    move = psmove.PSMove(move_num)
                    serial = move.get_serial()

                    if serial not in self.tracked_controllers:
                        # New controller found
                        logger.info(f"Discovered new controller: {serial}")

                        # Pair if USB
                        if move.connection_type == psmove.Conn_USB and serial not in self.paired_serials:
                            with tracer.start_as_current_span("pair_controller"):
                                self._pair_controller(move, serial)

                        # Spawn tracking process
                        with tracer.start_as_current_span("spawn_controller_process"):
                            self._spawn_controller_process(move, serial, move_num)

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"Error discovering controllers: {e}", exc_info=True)

    def _pair_controller(self, move, serial: str):
        """Pair a controller via Bluetooth."""
        try:
            pair_module.pair_move(serial)
            self.paired_serials.append(serial)
            logger.info(f"Paired controller {serial}")
        except Exception as e:
            logger.error(f"Error pairing controller {serial}: {e}", exc_info=True)

    def _spawn_controller_process(self, move, serial: str, move_num: int):
        """Spawn a tracking process for a controller."""
        try:
            # Get battery level
            battery = move.get_battery() if PSMOVE_AVAILABLE else 5

            # Create controller state
            controller_state = ControllerState()
            self.controller_states[serial] = controller_state

            # Track controller
            self.tracked_controllers[serial] = {
                "serial": serial,
                "move_num": move_num,
                "battery": battery,
                "ready": False,
                "team": 0,
                "connected_at": time.time(),
                "move": move,  # Store move object for feedback operations
            }

            # Add attributes to current span (this is called within "spawn_controller_process" span)
            current_span = trace.get_current_span()
            current_span.set_attribute("controller.serial", serial)
            current_span.set_attribute("controller.move_num", move_num)
            current_span.set_attribute("controller.battery", battery)
            current_span.add_event(
                "controller_added_to_tracking",
                {"serial": serial, "move_num": move_num, "battery": battery},
            )

            logger.info(f"Spawned tracking for controller {serial}")

            # Update metrics (Phase 38)
            metrics.active_controllers.inc()
            metrics.controller_connected.labels(serial=serial).set(1)
            metrics.controller_battery_level.labels(serial=serial).set(battery)
            # Check if this is a reconnect
            if serial in self.paired_serials:
                metrics.controller_reconnect_total.labels(serial=serial).inc()

            # Note: Actual process spawning would happen here in production
            # For now, we track the controller info

        except Exception as e:
            logger.error(f"Error spawning controller process {serial}: {e}", exc_info=True)

    def GetControllerCount(self, request, context):
        """Get total controller count."""
        with tracer.start_as_current_span("GetControllerCount") as span:
            try:
                count = len(self.tracked_controllers)
                span.set_attribute("controller.count", count)

                return controller_manager_pb2.GetControllerCountResponse(count=count, success=True, error="")
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetControllerCount error: {e}", exc_info=True)
                return controller_manager_pb2.GetControllerCountResponse(count=0, success=False, error=str(e))

    def GetReadyControllers(self, request, context):
        """Get all ready controllers."""
        with tracer.start_as_current_span("GetReadyControllers") as span:
            try:
                ready_controllers = [
                    self._build_or_get_cached_state(serial, info)
                    for serial, info in self.tracked_controllers.items()
                    if info.get("ready", False)
                ]

                span.set_attribute("controller.ready_count", len(ready_controllers))

                return controller_manager_pb2.GetReadyControllersResponse(
                    controllers=ready_controllers, success=True, error=""
                )
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetReadyControllers error: {e}", exc_info=True)
                return controller_manager_pb2.GetReadyControllersResponse(controllers=[], success=False, error=str(e))

    def GetControllers(self, request, context):
        """Get all controllers."""
        with tracer.start_as_current_span("GetControllers") as span:
            try:
                all_controllers = [
                    self._build_or_get_cached_state(serial, info) for serial, info in self.tracked_controllers.items()
                ]

                span.set_attribute("controller.total_count", len(all_controllers))

                return controller_manager_pb2.GetControllersResponse(
                    controllers=all_controllers, success=True, error=""
                )
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetControllers error: {e}", exc_info=True)
                return controller_manager_pb2.GetControllersResponse(controllers=[], success=False, error=str(e))

    async def StreamControllerStates(self, request, context):
        """Stream controller states in real-time (async)."""
        subscriber_id = f"stream_{time.time()}"

        with tracer.start_as_current_span("StreamControllerStates") as span:
            span.set_attribute("subscriber.id", subscriber_id)
            span.set_attribute("update_frequency_hz", request.update_frequency_hz or 60)

            # Create queue for this subscriber (Phase 34: asyncio.Queue, though not actively used)
            event_queue = asyncio.Queue(maxsize=100)

            async with self.stream_lock:  # Phase 34: async lock
                self.stream_subscribers[subscriber_id] = event_queue
                # Initialize delta tracking for this subscriber
                self.last_sent_states[subscriber_id] = {}

            # Update stream metrics (Phase 38)
            metrics.active_streams.inc()

            logger.info(f"New stream subscriber: {subscriber_id}")

            try:
                frequency = request.update_frequency_hz or 60
                interval = 1.0 / frequency

                while not context.cancelled():
                    try:
                        # Build current state for all controllers (Phase 18: Use caching)
                        current_states = {
                            serial: self._build_or_get_cached_state(serial, info)
                            for serial, info in self.tracked_controllers.items()
                        }

                        # Delta update: only include controllers that changed (Phase 26 - Part 3)
                        changed_controllers = []
                        for serial, current_state in current_states.items():
                            current_hash = self._controller_state_hash(current_state)
                            last_hash = self.last_sent_states[subscriber_id].get(serial)

                            if current_hash != last_hash:
                                changed_controllers.append(current_state)
                                self.last_sent_states[subscriber_id][serial] = current_hash

                        # Send update (empty if nothing changed, keeps stream alive)
                        update = controller_manager_pb2.ControllerStateUpdate(
                            controllers=changed_controllers, timestamp=int(time.time() * 1000)
                        )
                        yield update

                        # Track stream update (Phase 38)
                        if changed_controllers:
                            metrics.stream_updates_total.labels(stream_type="legacy").inc()

                        # CRITICAL FIX: Use async sleep instead of blocking time.sleep()
                        await asyncio.sleep(interval)

                    except Exception as e:
                        logger.error(f"Stream error for {subscriber_id}: {e}")
                        break

            finally:
                # Cleanup (Phase 34: async lock)
                async with self.stream_lock:
                    if subscriber_id in self.stream_subscribers:
                        del self.stream_subscribers[subscriber_id]
                    # Clean up delta tracking
                    if subscriber_id in self.last_sent_states:
                        del self.last_sent_states[subscriber_id]

                # Update stream metrics (Phase 38)
                metrics.active_streams.dec()

                logger.info(f"Stream subscriber disconnected: {subscriber_id}")

    async def StreamButtonEvents(self, request, context):
        """
        Stream button press/release events as they occur (Phase 41).

        This is an event-driven stream - events are only sent when buttons
        change state (press or release), not on every frame.
        """
        subscriber_id = f"button_stream_{time.time()}"

        with tracer.start_as_current_span("StreamButtonEvents") as span:
            span.set_attribute("subscriber.id", subscriber_id)

            # Create queue for this subscriber (Phase 34: asyncio.Queue)
            event_queue = asyncio.Queue(maxsize=100)

            async with self.button_event_lock:  # Phase 34: async lock
                self.button_event_subscribers[subscriber_id] = event_queue

            # Update stream metrics (Phase 38)
            metrics.active_streams.inc()

            logger.info(f"New button event subscriber: {subscriber_id}")

            try:
                while not context.cancelled():
                    try:
                        # Wait for button events (Phase 34: async wait with timeout)
                        # Check for events every 1s to stay responsive to cancellation
                        try:
                            event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                            yield event
                            # Track stream update (Phase 38)
                            metrics.stream_updates_total.labels(stream_type="button_events").inc()
                        except TimeoutError:  # Phase 34: asyncio exception
                            # No events, continue loop to check cancellation
                            continue

                    except Exception as e:
                        logger.error(f"Button event stream error for {subscriber_id}: {e}")
                        break

            finally:
                # Cleanup (Phase 34: async lock)
                async with self.button_event_lock:
                    if subscriber_id in self.button_event_subscribers:
                        del self.button_event_subscribers[subscriber_id]

                # Update stream metrics (Phase 38)
                metrics.active_streams.dec()

                logger.info(f"Button event subscriber disconnected: {subscriber_id}")

    async def StreamGameplayData(self, request, context):
        """
        Stream gameplay data (acceleration/gyro only) in real-time (Phase 41).

        This stream excludes button states and is optimized for game modes
        that only need motion data.
        """
        subscriber_id = f"gameplay_stream_{time.time()}"

        with tracer.start_as_current_span("StreamGameplayData") as span:
            span.set_attribute("subscriber.id", subscriber_id)
            span.set_attribute("update_frequency_hz", request.update_frequency_hz or 60)

            # Update stream metrics (Phase 38)
            metrics.active_streams.inc()

            logger.info(f"New gameplay data subscriber: {subscriber_id}")

            try:
                frequency = request.update_frequency_hz or 60
                interval = 1.0 / frequency

                while not context.cancelled():
                    try:
                        # Build gameplay data for all controllers
                        gameplay_data = []
                        for serial, info in self.tracked_controllers.items():
                            # Get full controller state
                            full_state = self._build_or_get_cached_state(serial, info)

                            # Convert to GameplayData (no buttons)
                            gd = controller_manager_pb2.GameplayData(
                                serial=full_state.serial,
                                move_num=full_state.move_num,
                                battery=full_state.battery,
                                ready=full_state.ready,
                                team=full_state.team,
                                color=full_state.color,
                                accel=full_state.accel,
                                gyro=full_state.gyro,
                            )
                            gameplay_data.append(gd)

                        # Send update
                        update = controller_manager_pb2.GameplayDataUpdate(
                            controllers=gameplay_data, timestamp=int(time.time() * 1000)
                        )
                        yield update

                        # Track stream update (Phase 38)
                        if gameplay_data:
                            metrics.stream_updates_total.labels(stream_type="gameplay_data").inc()

                        await asyncio.sleep(interval)

                    except Exception as e:
                        logger.error(f"Gameplay stream error for {subscriber_id}: {e}")
                        break

            finally:
                # Update stream metrics (Phase 38)
                metrics.active_streams.dec()

                logger.info(f"Gameplay data subscriber disconnected: {subscriber_id}")

    async def StreamGameplayDataDynamic(self, request_iterator, context):
        """
        Stream gameplay data with dynamic filtering via bidirectional communication (Phase 45).

        Client can send filter updates at any time to adjust which controllers
        are being monitored without restarting the stream.

        Args:
            request_iterator: AsyncIterator of GameplayStreamControl messages from client
            context: gRPC context

        Yields:
            GameplayDataUpdate messages with filtered controller data
        """
        subscriber_id = f"gameplay_dynamic_stream_{time.time()}"

        with tracer.start_as_current_span("StreamGameplayDataDynamic") as span:
            span.set_attribute("subscriber.id", subscriber_id)

            # Update stream metrics
            metrics.active_streams.inc()

            # Stream state (updated by client messages)
            current_hz = 30  # Default Hz
            current_filter = None  # None = all controllers

            # Background task to read client updates
            async def read_client_updates():
                nonlocal current_hz, current_filter

                try:
                    async for control_msg in request_iterator:
                        if control_msg.HasField("config"):
                            # Initial configuration
                            current_hz = control_msg.config.update_frequency_hz
                            current_filter = set(control_msg.config.serials) if control_msg.config.serials else None
                            logger.info(
                                f"[{subscriber_id}] Stream configured: {current_hz}Hz, "
                                f"filter={len(current_filter) if current_filter else 'all'} controllers"
                            )
                            span.set_attribute("update_frequency_hz", current_hz)
                            span.set_attribute("initial_filter_count", len(current_filter) if current_filter else 0)

                        elif control_msg.HasField("filter_update"):
                            # Mid-stream filter update
                            new_filter = (
                                set(control_msg.filter_update.serials) if control_msg.filter_update.serials else None
                            )

                            if new_filter != current_filter:
                                old_count = len(current_filter) if current_filter else 0
                                new_count = len(new_filter) if new_filter else 0

                                logger.info(
                                    f"[{subscriber_id}] Filter updated: " f"{old_count} → {new_count} controllers"
                                )

                                current_filter = new_filter

                                # Add span event for filter update
                                span.add_event(
                                    "filter_updated",
                                    {
                                        "previous_count": old_count,
                                        "new_count": new_count,
                                    },
                                )

                        elif control_msg.HasField("color_command"):
                            # Phase 46: Process color command via stream
                            cmd = control_msg.color_command
                            target_serial = cmd.serial if cmd.serial else None

                            # Apply to target serial or all controllers (broadcast)
                            serials_to_update = (
                                [target_serial] if target_serial else list(self.tracked_controllers.keys())
                            )

                            for serial in serials_to_update:
                                if serial in self.tracked_controllers:
                                    await self._set_controller_color_internal(
                                        serial, (cmd.color.r, cmd.color.g, cmd.color.b)
                                    )

                            logger.debug(
                                f"[{subscriber_id}] Color command: "
                                f"serial={cmd.serial or 'all'}, "
                                f"rgb=({cmd.color.r},{cmd.color.g},{cmd.color.b})"
                            )

                            # Metric (Phase 46)
                            metrics.stream_commands_total.labels(command_type="color").inc()

                        elif control_msg.HasField("effect_command"):
                            # Phase 46: Process effect command via stream
                            cmd = control_msg.effect_command
                            target_serial = cmd.serial if cmd.serial else None

                            # Apply to target serial or all controllers (broadcast)
                            serials_to_update = (
                                [target_serial] if target_serial else list(self.tracked_controllers.keys())
                            )

                            color_rgb = (
                                (cmd.color.r, cmd.color.g, cmd.color.b)
                                if cmd.color.r or cmd.color.g or cmd.color.b
                                else (255, 255, 255)
                            )
                            duration_ms = cmd.duration_ms or 1000

                            for serial in serials_to_update:
                                if serial in self.tracked_controllers:
                                    await self._play_effect_internal(
                                        serial, cmd.effect, color_rgb, duration_ms, speed=5
                                    )

                            effect_name = controller_manager_pb2.ControllerEffect.Name(cmd.effect)
                            logger.debug(
                                f"[{subscriber_id}] Effect command: "
                                f"serial={cmd.serial or 'all'}, effect={effect_name}"
                            )

                            # Metric (Phase 46)
                            metrics.stream_commands_total.labels(command_type="effect").inc()

                        elif control_msg.HasField("vibration_command"):
                            # Phase 46: Process vibration command via stream
                            cmd = control_msg.vibration_command
                            target_serial = cmd.serial if cmd.serial else None

                            # Apply to target serial or all controllers (broadcast)
                            serials_to_update = (
                                [target_serial] if target_serial else list(self.tracked_controllers.keys())
                            )

                            for serial in serials_to_update:
                                if serial in self.tracked_controllers:
                                    await self._set_vibration_internal(serial, cmd.intensity, cmd.duration_ms)

                            logger.debug(
                                f"[{subscriber_id}] Vibration command: "
                                f"serial={cmd.serial or 'all'}, "
                                f"intensity={cmd.intensity}, duration={cmd.duration_ms}ms"
                            )

                            # Metric (Phase 46)
                            metrics.stream_commands_total.labels(command_type="vibration").inc()

                        elif control_msg.HasField("combined_feedback"):
                            # Phase 46: Process combined color + vibration command
                            cmd = control_msg.combined_feedback
                            target_serial = cmd.serial if cmd.serial else None

                            # Apply to target serial or all controllers (broadcast)
                            serials_to_update = (
                                [target_serial] if target_serial else list(self.tracked_controllers.keys())
                            )

                            for serial in serials_to_update:
                                if serial in self.tracked_controllers:
                                    # Set color and vibration atomically
                                    await self._set_controller_color_internal(
                                        serial, (cmd.color.r, cmd.color.g, cmd.color.b)
                                    )
                                    if cmd.vibration_intensity > 0:
                                        await self._set_vibration_internal(
                                            serial,
                                            cmd.vibration_intensity,
                                            cmd.vibration_duration_ms,
                                        )

                            logger.debug(
                                f"[{subscriber_id}] Combined feedback: "
                                f"serial={cmd.serial or 'all'}, "
                                f"rgb=({cmd.color.r},{cmd.color.g},{cmd.color.b}), "
                                f"vib={cmd.vibration_intensity}@{cmd.vibration_duration_ms}ms"
                            )

                            # Metric (Phase 46)
                            metrics.stream_commands_total.labels(command_type="combined").inc()

                except Exception as e:
                    logger.error(f"[{subscriber_id}] Error reading client updates: {e}", exc_info=True)

            # Start background task to read client updates
            update_task = asyncio.create_task(read_client_updates())

            logger.info(f"New dynamic gameplay subscriber: {subscriber_id}")

            try:
                # Stream gameplay data
                while not context.cancelled():
                    try:
                        # Calculate interval from current Hz
                        interval = 1.0 / current_hz

                        # Build data for each controller (respecting filter)
                        gameplay_data = []
                        for serial, info in self.tracked_controllers.items():
                            # Apply filter if present
                            if current_filter is not None and serial not in current_filter:
                                continue  # Skip filtered controller

                            # Get full controller state
                            full_state = self._build_or_get_cached_state(serial, info)

                            # Convert to GameplayData (no buttons)
                            gd = controller_manager_pb2.GameplayData(
                                serial=full_state.serial,
                                move_num=full_state.move_num,
                                battery=full_state.battery,
                                ready=full_state.ready,
                                team=full_state.team,
                                color=full_state.color,
                                accel=full_state.accel,
                                gyro=full_state.gyro,
                            )
                            gameplay_data.append(gd)

                        # Send update
                        update = controller_manager_pb2.GameplayDataUpdate(
                            controllers=gameplay_data, timestamp=int(time.time() * 1000)
                        )
                        yield update

                        # Track stream update
                        if gameplay_data:
                            metrics.stream_updates_total.labels(stream_type="gameplay_data_dynamic").inc()
                            # Track number of controllers streamed per frame (Phase 45)
                            metrics.streamed_controllers.observe(len(gameplay_data))

                        await asyncio.sleep(interval)

                    except Exception as e:
                        logger.error(f"[{subscriber_id}] Gameplay stream error: {e}", exc_info=True)
                        break

            finally:
                # Cleanup: Cancel background task
                update_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await update_task

                # Update stream metrics
                metrics.active_streams.dec()

                logger.info(f"Dynamic gameplay subscriber disconnected: {subscriber_id}")

    def PairController(self, request, context):
        """Pair a new controller."""
        with tracer.start_as_current_span("PairController") as span:
            span.set_attribute("color_index", request.color_index)

            try:
                # In production, this would trigger USB pairing
                # For now, return mock response
                serial = "mock_serial_12345"
                span.add_event("controller_paired", {"serial": serial, "color_index": request.color_index})
                return controller_manager_pb2.PairControllerResponse(success=True, error="", serial=serial)
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"PairController error: {e}", exc_info=True)
                return controller_manager_pb2.PairControllerResponse(success=False, error=str(e), serial="")

    async def RemoveController(self, request, context):
        """Remove a controller (Phase 34: async for effect_lock)."""
        with tracer.start_as_current_span("RemoveController") as span:
            span.set_attribute("controller.serial", request.serial)

            try:
                serial = request.serial

                if serial in self.tracked_controllers:
                    # Stop process if running
                    if serial in self.controller_processes:
                        proc = self.controller_processes[serial]
                        if proc.is_alive():
                            proc.terminate()
                            proc.join(timeout=2.0)
                        del self.controller_processes[serial]

                    # Remove from tracking
                    del self.tracked_controllers[serial]

                    if serial in self.controller_states:
                        del self.controller_states[serial]

                    # Clean up state cache (Phase 18 - Task 1)
                    if serial in self.state_cache:
                        del self.state_cache[serial]

                    # Cancel any active effects (Phase 31, Phase 34: async lock)
                    async with self.effect_lock:
                        if serial in self.active_effects:
                            self.active_effects[serial].cancel()
                            del self.active_effects[serial]

                    # Update metrics (Phase 38)
                    metrics.active_controllers.dec()
                    metrics.controller_connected.labels(serial=serial).set(0)
                    metrics.controller_disconnect_total.labels(serial=serial).inc()

                    span.add_event("controller_removed", {"serial": serial})
                    logger.info(f"Removed controller {serial}")

                    return controller_manager_pb2.RemoveControllerResponse(success=True, error="")
                return controller_manager_pb2.RemoveControllerResponse(
                    success=False, error=f"Controller {serial} not found"
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"RemoveController error: {e}", exc_info=True)
                return controller_manager_pb2.RemoveControllerResponse(success=False, error=str(e))

    def SetControllerColor(self, request, context):
        """Set LED color on controller(s) - Phase 19 feedback feature."""
        with tracer.start_as_current_span("SetControllerColor") as span:
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("color.r", request.color.r)
            span.set_attribute("color.g", request.color.g)
            span.set_attribute("color.b", request.color.b)

            try:
                if not PSMOVE_AVAILABLE:
                    logger.info(
                        f"SetControllerColor (mock): {request.serial or 'all'} -> "
                        f"RGB({request.color.r},{request.color.g},{request.color.b})"
                    )
                    return controller_manager_pb2.SetControllerColorResponse(success=True, error="")

                # Determine which controllers to update
                serials = [request.serial] if request.serial else list(self.tracked_controllers.keys())

                controllers_updated = 0
                for serial in serials:
                    if serial in self.tracked_controllers:
                        info = self.tracked_controllers[serial]
                        move = info.get("move")
                        if move:
                            move.set_leds(request.color.r, request.color.g, request.color.b)
                            move.update_leds()
                            controllers_updated += 1
                            logger.debug(
                                f"Set color on {serial}: RGB({request.color.r},{request.color.g},{request.color.b})"
                            )

                span.set_attribute("controllers_updated", controllers_updated)
                return controller_manager_pb2.SetControllerColorResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                logger.error(f"SetControllerColor error: {e}", exc_info=True)
                return controller_manager_pb2.SetControllerColorResponse(success=False, error=str(e))

    def SetControllerVibration(self, request, context):
        """Set vibration on controller(s) - Phase 19 feedback feature."""
        with tracer.start_as_current_span("SetControllerVibration") as span:
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("intensity", request.intensity)
            span.set_attribute("duration_ms", request.duration_ms)

            try:
                if not PSMOVE_AVAILABLE:
                    logger.info(
                        f"SetControllerVibration (mock): {request.serial or 'all'} "
                        f"intensity={request.intensity} duration={request.duration_ms}ms"
                    )
                    return controller_manager_pb2.SetControllerVibrationResponse(success=True, error="")

                # Determine which controllers to update
                serials = [request.serial] if request.serial else list(self.tracked_controllers.keys())

                controllers_updated = 0
                for serial in serials:
                    if serial in self.tracked_controllers:
                        info = self.tracked_controllers[serial]
                        move = info.get("move")
                        if move:
                            move.set_rumble(request.intensity)
                            controllers_updated += 1
                            logger.debug(f"Set vibration on {serial}: intensity={request.intensity}")

                # TODO: Handle duration_ms by resetting rumble after timeout
                # For now, vibration stays at intensity until explicitly changed

                span.set_attribute("controllers_updated", controllers_updated)
                return controller_manager_pb2.SetControllerVibrationResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                logger.error(f"SetControllerVibration error: {e}", exc_info=True)
                return controller_manager_pb2.SetControllerVibrationResponse(success=False, error=str(e))

    async def PlayControllerEffect(self, request, context):
        """Play visual effect on controller(s) - Phase 31/40 implementation.

        Uses effect methods inherited from ControllerEffectsBase.
        Adds tracing and thread-safe task management.
        """
        with tracer.start_as_current_span("PlayControllerEffect") as span:
            effect_name = controller_manager_pb2.ControllerEffect.Name(request.effect)
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("effect", effect_name)
            span.set_attribute("duration_ms", request.duration_ms)
            span.set_attribute("speed", request.speed)

            try:
                if not PSMOVE_AVAILABLE:
                    logger.info(f"PlayControllerEffect (mock): {request.serial or 'all'} effect={effect_name}")
                    return controller_manager_pb2.PlayControllerEffectResponse(success=True, error="")

                # Determine which controllers to update
                serials = [request.serial] if request.serial else list(self.tracked_controllers.keys())

                # Color as tuple for effect methods
                color = (request.color.r, request.color.g, request.color.b) if request.color else (255, 255, 255)
                duration_ms = request.duration_ms or 1000  # Default 1 second
                speed = request.speed or 5  # Default medium speed

                controllers_updated = 0
                for serial in serials:
                    if serial not in self.tracked_controllers:
                        continue

                    # Cancel any existing effect on this controller (Phase 34: async lock)
                    async with self.effect_lock:
                        if serial in self.active_effects:
                            self.active_effects[serial].cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await self.active_effects[serial]
                            del self.active_effects[serial]

                    # Start the appropriate effect (methods inherited from ControllerEffectsBase - Phase 40)
                    if request.effect == controller_manager_pb2.EFFECT_NONE:
                        # Solid color (no animation)
                        self._set_led_color(serial, color)

                    elif request.effect == controller_manager_pb2.EFFECT_FLASH:
                        task = asyncio.create_task(self._effect_flash(serial, color, duration_ms, speed))
                        async with self.effect_lock:  # Phase 34: async lock
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_PULSE:
                        task = asyncio.create_task(self._effect_pulse(serial, color, duration_ms, speed))
                        async with self.effect_lock:  # Phase 34: async lock
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_RAINBOW:
                        task = asyncio.create_task(self._effect_rainbow(serial, duration_ms, speed))
                        async with self.effect_lock:  # Phase 34: async lock
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_FADE_OUT:
                        task = asyncio.create_task(self._effect_fade_out(serial, color, duration_ms))
                        async with self.effect_lock:  # Phase 34: async lock
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_FADE_IN:
                        task = asyncio.create_task(self._effect_fade_in(serial, color, duration_ms))
                        async with self.effect_lock:  # Phase 34: async lock
                            self.active_effects[serial] = task

                    else:
                        logger.warning(f"Unknown effect: {effect_name}")
                        continue

                    controllers_updated += 1

                span.set_attribute("controllers_updated", controllers_updated)
                logger.info(f"PlayControllerEffect: {effect_name} on {controllers_updated} controller(s)")

                return controller_manager_pb2.PlayControllerEffectResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                logger.error(f"PlayControllerEffect error: {e}", exc_info=True)
                return controller_manager_pb2.PlayControllerEffectResponse(success=False, error=str(e))

    # Phase 46: Internal feedback methods (called from both unary RPCs and stream)

    async def _set_controller_color_internal(self, serial: str, color_rgb: tuple[int, int, int]) -> bool:
        """
        Internal method to set controller color (Phase 46).

        Can be called from both SetControllerColor RPC and stream-based ColorCommand.

        Args:
            serial: Controller serial number
            color_rgb: RGB color tuple (r, g, b)

        Returns:
            True if successful, False otherwise
        """
        try:
            if not PSMOVE_AVAILABLE:
                logger.debug(f"_set_controller_color_internal (mock): {serial} -> RGB{color_rgb}")
                return True

            if serial not in self.tracked_controllers:
                logger.warning(f"Controller {serial} not found for color change")
                return False

            info = self.tracked_controllers[serial]
            move = info.get("move")
            if move:
                move.set_leds(color_rgb[0], color_rgb[1], color_rgb[2])
                move.update_leds()
                logger.debug(f"Set color on {serial}: RGB{color_rgb}")
                return True
            logger.warning(f"No move object for controller {serial}")
            return False

        except Exception as e:
            logger.error(f"Error setting color on {serial}: {e}", exc_info=True)
            return False

    async def _play_effect_internal(
        self,
        serial: str,
        effect: int,
        color_rgb: tuple[int, int, int] = (255, 255, 255),
        duration_ms: int = 1000,
        speed: int = 5,
    ) -> bool:
        """
        Internal method to play controller effect (Phase 46).

        Can be called from both PlayControllerEffect RPC and stream-based EffectCommand.

        Args:
            serial: Controller serial number
            effect: Effect enum value
            color_rgb: RGB color tuple for effect
            duration_ms: Effect duration in milliseconds
            speed: Effect speed (1-10)

        Returns:
            True if successful, False otherwise
        """
        try:
            if not PSMOVE_AVAILABLE:
                effect_name = controller_manager_pb2.ControllerEffect.Name(effect)
                logger.debug(f"_play_effect_internal (mock): {serial} effect={effect_name}")
                return True

            if serial not in self.tracked_controllers:
                logger.warning(f"Controller {serial} not found for effect")
                return False

            # Cancel any existing effect on this controller
            async with self.effect_lock:
                if serial in self.active_effects:
                    self.active_effects[serial].cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self.active_effects[serial]
                    del self.active_effects[serial]

            # Start the appropriate effect
            if effect == controller_manager_pb2.EFFECT_NONE:
                self._set_led_color(serial, color_rgb)

            elif effect == controller_manager_pb2.EFFECT_FLASH:
                task = asyncio.create_task(self._effect_flash(serial, color_rgb, duration_ms, speed))
                async with self.effect_lock:
                    self.active_effects[serial] = task

            elif effect == controller_manager_pb2.EFFECT_PULSE:
                task = asyncio.create_task(self._effect_pulse(serial, color_rgb, duration_ms, speed))
                async with self.effect_lock:
                    self.active_effects[serial] = task

            elif effect == controller_manager_pb2.EFFECT_RAINBOW:
                task = asyncio.create_task(self._effect_rainbow(serial, duration_ms, speed))
                async with self.effect_lock:
                    self.active_effects[serial] = task

            elif effect == controller_manager_pb2.EFFECT_FADE_OUT:
                task = asyncio.create_task(self._effect_fade_out(serial, color_rgb, duration_ms))
                async with self.effect_lock:
                    self.active_effects[serial] = task

            elif effect == controller_manager_pb2.EFFECT_FADE_IN:
                task = asyncio.create_task(self._effect_fade_in(serial, color_rgb, duration_ms))
                async with self.effect_lock:
                    self.active_effects[serial] = task

            else:
                effect_name = controller_manager_pb2.ControllerEffect.Name(effect)
                logger.warning(f"Unknown effect: {effect_name}")
                return False

            logger.debug(f"Playing effect {effect} on {serial}")
            return True

        except Exception as e:
            logger.error(f"Error playing effect on {serial}: {e}", exc_info=True)
            return False

    async def _set_vibration_internal(self, serial: str, intensity: int, duration_ms: int) -> bool:
        """
        Internal method to set controller vibration (Phase 46).

        Can be called from both SetControllerVibration RPC and stream-based VibrationCommand.

        Args:
            serial: Controller serial number
            intensity: Vibration intensity (0-255)
            duration_ms: Duration in milliseconds

        Returns:
            True if successful, False otherwise
        """
        try:
            if not PSMOVE_AVAILABLE:
                logger.debug(f"_set_vibration_internal (mock): {serial} intensity={intensity} duration={duration_ms}ms")
                return True

            if serial not in self.tracked_controllers:
                logger.warning(f"Controller {serial} not found for vibration")
                return False

            info = self.tracked_controllers[serial]
            move = info.get("move")
            if move:
                move.set_rumble(intensity)
                logger.debug(f"Set vibration on {serial}: intensity={intensity}")
                # TODO: Handle duration_ms by resetting rumble after timeout
                return True
            logger.warning(f"No move object for controller {serial}")
            return False

        except Exception as e:
            logger.error(f"Error setting vibration on {serial}: {e}", exc_info=True)
            return False

    def _set_led_color(self, serial: str, color: tuple[int, int, int]):
        """Helper to set LED color on a controller (Phase 31)."""
        if serial not in self.tracked_controllers:
            return

        info = self.tracked_controllers[serial]
        move = info.get("move")
        if move and PSMOVE_AVAILABLE:
            move.set_leds(color[0], color[1], color[2])
            move.update_leds()

    def _check_battery_levels(self):
        """Check battery levels and warn about low batteries (Phase 39 - Task 4).

        Called every 30 seconds from discovery loop.
        Warns when battery level is <= 1 (out of 5), which is <20%.
        """
        if not PSMOVE_AVAILABLE:
            return

        current_time = time.time()

        for serial, info in list(self.tracked_controllers.items()):
            try:
                battery = info.get("battery", 5)  # Default to full if unknown

                # Update battery metric (Phase 38)
                metrics.controller_battery_level.labels(serial=serial).set(battery)

                # Warn if battery is critically low (0 or 1 out of 5 = <20%)
                if battery <= self.low_battery_threshold:
                    # Check if we've warned recently (avoid spam)
                    last_warning = self.last_battery_warning.get(serial, 0)
                    if current_time - last_warning >= 30.0:  # Warn every 30 seconds
                        self._warn_low_battery(serial, battery)
                        self.last_battery_warning[serial] = current_time

            except Exception as e:
                logger.error(f"Error checking battery for {serial}: {e}")

    def _warn_low_battery(self, serial: str, battery_level: int):
        """Warn player about low battery with red pulse (Phase 39 - Task 4).

        Args:
            serial: Controller serial number
            battery_level: Current battery level (0-5)
        """
        logger.warning(f"Controller {serial} has low battery: {battery_level}/5 (<20%)")

        if not PSMOVE_AVAILABLE:
            return

        try:
            # Get controller move object
            info = self.tracked_controllers.get(serial)
            if not info:
                return

            move = info.get("move")
            if not move:
                return

            # Pulse red 3 times (overrides current color temporarily)
            # This is a synchronous warning that briefly interrupts current state
            for _ in range(3):
                move.set_leds(255, 0, 0)  # Bright red
                move.update_leds()
                time.sleep(0.3)

                move.set_leds(100, 0, 0)  # Dim red
                move.update_leds()
                time.sleep(0.3)

            # Note: Current game/menu state will restore color on next update
            logger.info(f"Low battery warning displayed for {serial}")

        except Exception as e:
            logger.error(f"Failed to display low battery warning for {serial}: {e}")

    def _check_rssi_levels(self):
        """
        Check RSSI (signal strength) for all Bluetooth controllers (Phase 48).

        Updates controller_rssi dict and warns about weak signals.
        Only checks Bluetooth-connected controllers (USB returns 0).
        """
        if not PSMOVE_AVAILABLE:
            return

        try:
            with tracer.start_as_current_span("check_rssi_levels") as span:
                # Import bluetooth module
                try:
                    from . import bluetooth
                except ImportError:
                    logger.warning("Bluetooth module not available, skipping RSSI check")
                    return

                # Get HCI adapters
                try:
                    hci_dict = bluetooth.get_hci_dict()
                except Exception as e:
                    logger.debug(f"Could not get HCI adapters: {e}")
                    return

                for hci in hci_dict:
                    # Get RSSI for all devices on this adapter
                    rssi_values = bluetooth.get_all_device_rssi_values(hci)

                    # Update RSSI for each controller
                    for serial, info in self.controllers.items():
                        # Skip if we don't have BT address mapping
                        if serial not in self.controller_bt_addresses:
                            # Try to discover BT address if not yet mapped
                            move_num = info.get("move_num")
                            if move_num is not None and move_num in self.moves:
                                self._discover_bt_address(serial, hci)
                            continue

                        bt_address = self.controller_bt_addresses[serial]

                        if bt_address in rssi_values:
                            rssi = rssi_values[bt_address]
                            self.controller_rssi[serial] = rssi

                            # Update metric
                            metrics.controller_rssi_dbm.labels(serial=serial).set(rssi)

                            span.set_attribute(f"controller.{serial}.rssi", rssi)

                            # Warn if signal is weak
                            if rssi < self.weak_signal_threshold:
                                self._warn_weak_signal(serial, rssi)
                        else:
                            # No RSSI available (USB or disconnected)
                            self.controller_rssi[serial] = 0
                            metrics.controller_rssi_dbm.labels(serial=serial).set(0)

                span.set_attribute("rssi.checked_controllers", len(self.controller_rssi))

        except Exception as e:
            logger.error(f"Error checking RSSI levels: {e}", exc_info=True)

    def _discover_bt_address(self, serial: str, hci: str):
        """
        Try to discover the Bluetooth MAC address for a controller (Phase 48).

        This is done by correlating with BlueZ's list of connected devices.
        PS Move controllers typically show as "Motion Controller" in device name.

        Args:
            serial: Controller serial number
            hci: HCI adapter name
        """
        try:
            from . import bluetooth

            devices = bluetooth.get_attached_addresses(hci)

            for device_addr in devices:
                try:
                    device_path = device_addr.replace(":", "_")
                    proxy = bluetooth.get_device_proxy(hci, f"dev_{device_path}")
                    device_name = bluetooth.get_device_attrib(proxy, "Name")

                    # PS Move controllers have "Motion Controller" in their name
                    if device_name and "Motion Controller" in str(device_name):
                        # Check if this device is connected (has RSSI)
                        rssi = bluetooth.get_device_rssi(hci, device_addr)
                        if rssi is not None:
                            # Assume this is our controller
                            self.controller_bt_addresses[serial] = device_addr
                            logger.info(f"Mapped controller {serial} to BT address {device_addr}")
                            return
                except Exception:
                    # Skip devices we can't query
                    continue

        except Exception as e:
            logger.debug(f"Error discovering BT address for {serial}: {e}")

    def _warn_weak_signal(self, serial: str, rssi: int):
        """
        Warn player about weak Bluetooth signal (Phase 48).

        Displays orange pulse to indicate weak connection.
        Only warns once every 60 seconds per controller to avoid spam.

        Args:
            serial: Controller serial number
            rssi: Current RSSI in dBm
        """
        if not PSMOVE_AVAILABLE:
            return

        current_time = time.time()
        last_warning = self.last_rssi_warning.get(serial, 0)

        # Warn at most once per minute
        if current_time - last_warning < 60.0:
            return

        logger.warning(f"Controller {serial} has weak signal: {rssi} dBm")

        try:
            # Get controller info
            info = self.controllers.get(serial)
            if not info:
                return

            move_num = info.get("move_num")
            move = self.moves.get(move_num)

            if not move:
                return

            # Display orange pulse (3 times, 200ms on/off)
            for _ in range(3):
                move.set_leds(255, 165, 0)  # Orange
                move.update_leds()
                time.sleep(0.2)

                move.set_leds(50, 30, 0)  # Dim orange
                move.update_leds()
                time.sleep(0.2)

            # Note: Current game/menu state will restore color on next update
            self.last_rssi_warning[serial] = current_time
            metrics.controller_weak_signal_warnings_total.labels(serial=serial).inc()
            logger.info(f"Weak signal warning displayed for {serial}")

        except Exception as e:
            logger.error(f"Failed to display weak signal warning for {serial}: {e}")

    # Effect methods (_effect_flash, _effect_pulse, etc.) inherited from ControllerEffectsBase (Phase 40)

    def _controller_state_hash(self, state: controller_manager_pb2.ControllerState) -> str:
        """Create a hash of controller state for delta comparison (Phase 26 - Part 3)."""
        # Simple hash based on key fields that change during gameplay
        return (
            f"{state.battery}|{state.trigger_pressed}|{state.move_pressed}|{state.ready}|"
            f"{state.team}|{state.color.r},{state.color.g},{state.color.b}"
        )

    def _snapshot_hash(self, serial: str, info: dict) -> str:
        """Create a hash of controller hardware snapshot (Phase 18 - Task 1)."""
        # Get state snapshot if available
        state = self.controller_states.get(serial)

        if state:
            snapshot = state.get_snapshot()
            # Hash all fields that can change during gameplay
            accel = snapshot.get("accel", {})
            gyro = snapshot.get("gyro", {})
            return (
                f"{info.get('battery', 0)}|"
                f"{snapshot.get('trigger', False)}|{snapshot.get('move', False)}|"
                f"{snapshot.get('cross', False)}|{snapshot.get('circle', False)}|"
                f"{snapshot.get('square', False)}|{snapshot.get('triangle', False)}|"
                f"{snapshot.get('ps', False)}|"
                f"{accel.get('x', 0):.2f},{accel.get('y', 0):.2f},{accel.get('z', 0):.2f}|"
                f"{gyro.get('x', 0):.2f},{gyro.get('y', 0):.2f},{gyro.get('z', 0):.2f}|"
                f"{info.get('ready', False)}|{info.get('team', 0)}"
            )
        # No state available, return hash based on info only
        return f"{info.get('battery', 0)}|{info.get('ready', False)}|{info.get('team', 0)}"

    def _build_or_get_cached_state(self, serial: str, info: dict) -> controller_manager_pb2.ControllerState:
        """Return cached state if unchanged, rebuild if dirty (Phase 18 - Task 1)."""
        # Calculate current snapshot hash
        current_hash = self._snapshot_hash(serial, info)

        # Get cache entry for this controller
        cache_entry = self.state_cache.get(serial)

        if cache_entry and cache_entry["snapshot_hash"] == current_hash:
            # State unchanged, return cached protobuf message (Phase 38: Track cache hit)
            metrics.state_cache_hits_total.inc()
            return cache_entry["cached_state"]

        # State changed or not cached yet - rebuild (Phase 38: Track cache miss)
        metrics.state_cache_misses_total.inc()
        new_state = self._build_controller_state_message(serial, info)

        # Update cache
        self.state_cache[serial] = {
            "cached_state": new_state,
            "snapshot_hash": current_hash,
        }

        return new_state

    def _build_controller_state_message(self, serial: str, info: dict) -> controller_manager_pb2.ControllerState:
        """Build a ControllerState protobuf message (Phase 18: Use pooled objects)."""
        # Get state snapshot if available
        state = self.controller_states.get(serial)

        if state:
            snapshot = state.get_snapshot()
            trigger_pressed = snapshot.get("trigger", False)
            move_pressed = snapshot.get("move", False)
            cross_pressed = snapshot.get("cross", False)
            circle_pressed = snapshot.get("circle", False)
            square_pressed = snapshot.get("square", False)
            triangle_pressed = snapshot.get("triangle", False)
            ps_pressed = snapshot.get("ps", False)
            accel = snapshot.get("accel", {"x": 0, "y": 0, "z": 0})
            gyro = snapshot.get("gyro", {"x": 0, "y": 0, "z": 0})
        else:
            trigger_pressed = False
            move_pressed = False
            cross_pressed = False
            circle_pressed = False
            square_pressed = False
            triangle_pressed = False
            ps_pressed = False
            accel = {"x": 0, "y": 0, "z": 0}
            gyro = {"x": 0, "y": 0, "z": 0}

        # Use pooled Vector3 objects (Phase 18 - Task 3)
        accel_vec = self.vector3_pool.get()
        accel_vec.x = accel["x"]
        accel_vec.y = accel["y"]
        accel_vec.z = accel["z"]

        gyro_vec = self.vector3_pool.get()
        gyro_vec.x = gyro["x"]
        gyro_vec.y = gyro["y"]
        gyro_vec.z = gyro["z"]

        # Use pooled ControllerState (Phase 18 - Task 3)
        controller_state = self.controller_state_pool.get()
        controller_state.serial = serial
        controller_state.move_num = info.get("move_num", 0)
        controller_state.battery = info.get("battery", 0)
        controller_state.trigger_pressed = trigger_pressed
        controller_state.move_pressed = move_pressed
        controller_state.ready = info.get("ready", False)
        controller_state.team = info.get("team", 0)
        controller_state.color.r = 0
        controller_state.color.g = 0
        controller_state.color.b = 255
        controller_state.accel.CopyFrom(accel_vec)
        controller_state.gyro.CopyFrom(gyro_vec)
        controller_state.cross_pressed = cross_pressed
        controller_state.circle_pressed = circle_pressed
        controller_state.square_pressed = square_pressed
        controller_state.triangle_pressed = triangle_pressed
        controller_state.ps_pressed = ps_pressed
        controller_state.rssi = self.controller_rssi.get(serial, 0)  # Phase 48

        # Return pooled Vector3 objects (ControllerState made copies with CopyFrom)
        self.vector3_pool.return_msg(accel_vec)
        self.vector3_pool.return_msg(gyro_vec)

        # Phase 41: Detect button transitions and publish events
        self._detect_button_transitions(
            serial,
            info,
            trigger_pressed,
            move_pressed,
            cross_pressed,
            circle_pressed,
            square_pressed,
            triangle_pressed,
            ps_pressed,
        )

        return controller_state

    def _detect_button_transitions(
        self,
        serial: str,
        info: dict,
        trigger: bool,
        move: bool,
        cross: bool,
        circle: bool,
        square: bool,
        triangle: bool,
        ps: bool,
    ):
        """
        Detect button press/release transitions and publish button events (Phase 41).

        Args:
            serial: Controller serial number
            info: Controller info dict (for battery, color)
            trigger, move, cross, circle, square, triangle, ps: Current button states
        """
        # Initialize button state tracking for this controller if needed
        if serial not in self.button_states:
            self.button_states[serial] = {
                "trigger": False,
                "move": False,
                "cross": False,
                "circle": False,
                "square": False,
                "triangle": False,
                "ps": False,
            }

        prev_states = self.button_states[serial]
        current_states = {
            "trigger": trigger,
            "move": move,
            "cross": cross,
            "circle": circle,
            "square": square,
            "triangle": triangle,
            "ps": ps,
        }

        # Map button names to ButtonType enum
        button_type_map = {
            "trigger": controller_manager_pb2.BUTTON_TRIGGER,
            "move": controller_manager_pb2.BUTTON_MOVE,
            "cross": controller_manager_pb2.BUTTON_CROSS,
            "circle": controller_manager_pb2.BUTTON_CIRCLE,
            "square": controller_manager_pb2.BUTTON_SQUARE,
            "triangle": controller_manager_pb2.BUTTON_TRIANGLE,
            "ps": controller_manager_pb2.BUTTON_PS,
        }

        # Detect transitions and create events
        events = []
        for button_name, current_pressed in current_states.items():
            prev_pressed = prev_states[button_name]

            if current_pressed != prev_pressed:
                # State changed - create event
                action = (
                    controller_manager_pb2.ACTION_PRESS if current_pressed else controller_manager_pb2.ACTION_RELEASE
                )
                button_type = button_type_map[button_name]

                event = controller_manager_pb2.ButtonEvent(
                    serial=serial,
                    timestamp=int(time.time() * 1000),
                    button=button_type,
                    action=action,
                    battery=info.get("battery", 0),
                    color=controller_manager_pb2.RGB(r=0, g=0, b=255),  # Default color, could get from info
                )
                events.append(event)

                # Track button event (Phase 38)
                action_str = "press" if current_pressed else "release"
                metrics.button_events_total.labels(serial=serial, button=button_name, action=action_str).inc()

                # Update tracked state
                prev_states[button_name] = current_pressed

        # Publish events to all subscribers
        # Phase 34: put_nowait() is thread-safe, no lock needed for publishing
        if events:
            for subscriber_queue in self.button_event_subscribers.values():
                for event in events:
                    try:
                        subscriber_queue.put_nowait(event)
                    except asyncio.QueueFull:  # Phase 34: asyncio exception
                        logger.warning("Button event queue full for subscriber")

    def shutdown(self):
        """Shutdown the controller manager."""
        logger.info("Shutting down ControllerManager...")
        self.running = False

        # Stop all controller processes
        for _serial, proc in self.controller_processes.items():
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2.0)

        self.discovery_thread.join(timeout=5.0)


async def serve(port=50052, metrics_port=8000):
    """Start the ControllerManager async gRPC server."""
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

    # Create async server (CRITICAL FIX: grpc.aio instead of grpc.server)
    server = grpc.aio.server()

    # Add servicer
    controller_servicer = ControllerManagerServicer()
    controller_manager_pb2_grpc.add_ControllerManagerServiceServicer_to_server(controller_servicer, server)

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

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down ControllerManager server...")
        controller_servicer.shutdown()
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
