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
from typing import Any

import grpc
import grpc.aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

# OpenTelemetry (trace API for span operations)
from opentelemetry import trace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import contextlib

from prometheus_client import start_http_server

from lib.system_metrics import start_system_metrics_collector
from lib.telemetry import init_telemetry
from proto import controller_manager_pb2, controller_manager_pb2_grpc
from services.controller_manager import metrics

# Phase 57: Backend abstraction for platform independence
from services.controller_manager.backend_factory import create_backend
from services.controller_manager.effects_base import ControllerEffectsBase
from services.controller_manager.message_pool import MessagePool
from services.controller_manager.monitoring import ControllerMonitoring

logger = logging.getLogger(__name__)


# Initialize OpenTelemetry
tracer = init_telemetry()


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

        # Phase 57: Initialize backend (platform-agnostic)
        self.backend = create_backend()
        logger.info(f"Using controller backend: {self.backend.__class__.__name__}")

        self.tracked_controllers: dict[str, dict] = {}  # serial -> controller info
        self.controller_states: dict[str, dict] = {}  # serial -> state dict from backend
        self.paired_serials: list[str] = []
        self.controller_processes: dict[str, Any] = {}  # serial -> process (for cleanup)

        # Thread safety: RLock for shared state accessed by discovery thread and gRPC handlers
        # Protects: tracked_controllers, controller_states, button_states
        self.state_lock = threading.RLock()

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
        self.last_sent_states: dict[str, dict[str, Any]] = {}

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

        # Monitoring (battery and RSSI) - Phase 39, Phase 48, extracted to monitoring.py
        self.monitoring = ControllerMonitoring(
            low_battery_threshold=1,
            rssi_check_interval=10.0,
            weak_signal_threshold=-80,
        )

        # Vibration duration timers - tracks active vibration timers per controller
        self.vibration_timers: dict[str, threading.Timer] = {}
        # Vibration duration tasks - tracks active asyncio tasks for vibration stop (Phase 57 async migration)
        self.vibration_tasks: dict[str, asyncio.Task] = {}

        # Shared event loop for discovery thread (avoids creating new loop per call)
        self._discovery_loop_handle: asyncio.AbstractEventLoop | None = None

        # Discovery thread
        self.running = True
        self.backend_initialized = False  # Phase 57: Track backend init status
        self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.discovery_thread.start()

        logger.info("ControllerManager initialized")

    def _run_in_discovery_loop(self, coro):
        """
        Run an async coroutine in the discovery thread's event loop.

        This avoids creating a new event loop for each backend call.
        Must only be called from the discovery thread.
        """
        if self._discovery_loop_handle is None:
            raise RuntimeError("Discovery loop not initialized")
        return self._discovery_loop_handle.run_until_complete(coro)

    def _discovery_loop(self):
        """
        Background thread for controller discovery and battery monitoring.

        Phase 56: Event-driven spans - Only creates spans for actual events (controller connected),
        not for routine polling. Metrics track polling operations.
        Phase 57: Uses backend abstraction for platform independence.
        """
        import asyncio

        # Create a single event loop for this thread and reuse it
        self._discovery_loop_handle = asyncio.new_event_loop()
        asyncio.set_event_loop(self._discovery_loop_handle)

        try:
            # Initialize backend
            self.backend_initialized = self._discovery_loop_handle.run_until_complete(self.backend.initialize())
            if not self.backend_initialized:
                logger.error("Backend initialization failed - discovery loop will not run")
                return
            logger.info("Backend initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize backend: {e}", exc_info=True)
            return

        while self.running:
            try:
                current_time = time.time()

                # Check for new controllers every second (metrics, no span)
                with metrics.discovery_check_duration_seconds.time():
                    self._check_for_new_controllers()
                    metrics.discovery_checks_total.inc()

                # Phase 57: Update controller states from backend
                self._update_controller_states()

                # Check battery levels every 30 seconds (Phase 39 - Task 4)
                if current_time - self.monitoring.last_battery_check >= 30.0:
                    with metrics.battery_check_duration_seconds.time():
                        self.monitoring.check_battery_levels(
                            self.tracked_controllers,
                            self.backend,
                            self._run_in_discovery_loop,
                        )
                        metrics.battery_checks_total.inc()
                    self.monitoring.last_battery_check = current_time

                # Check RSSI every 10 seconds (Phase 48)
                if current_time - self.monitoring.last_rssi_check >= self.monitoring.rssi_check_interval:
                    with metrics.rssi_check_duration_seconds.time():
                        self.monitoring.check_rssi_levels(
                            self.tracked_controllers,
                            self.backend,
                            self._run_in_discovery_loop,
                        )
                        metrics.rssi_checks_total.inc()
                    self.monitoring.last_rssi_check = current_time

                time.sleep(0.016)  # ~60 Hz polling for smooth state updates

            except Exception as e:
                logger.error(f"Discovery loop error: {e}", exc_info=True)
                time.sleep(5.0)

    def _check_for_new_controllers(self):
        """
        Check for newly connected controllers (hardware).

        Phase 56: Event-driven spans - Only creates spans when NEW controllers are discovered.
        Routine checks are tracked via metrics only (no spans).
        Phase 57: Uses backend abstraction instead of direct psmove.
        """
        if not self.backend_initialized:
            return

        try:
            # Get list of connected controllers from backend
            connected_serials = self.backend.get_connected_controllers()

            for serial in connected_serials:
                if serial not in self.tracked_controllers:
                    # New controller found - create event span
                    with tracer.start_as_current_span("controller_connected") as span:
                        span.set_attribute("controller.serial", serial)
                        span.set_attribute("controller.count_total", len(connected_serials))

                        logger.info(f"Discovered new controller: {serial}")

                        # Spawn tracking process
                        with tracer.start_as_current_span("spawn_controller_process") as spawn_span:
                            spawn_span.set_attribute("controller.serial", serial)
                            self._spawn_controller_process(serial)

        except Exception as e:
            logger.error(f"Error discovering controllers: {e}", exc_info=True)

    def _update_controller_states(self):
        """
        Update states for all tracked controllers from backend.

        Phase 62: Uses parallel polling with asyncio.gather() to read all
        controllers concurrently. This reduces latency from O(n × latency)
        to O(latency), enabling support for large player counts.

        Called frequently (~60 Hz) to keep states fresh for streaming.
        Uses shared discovery loop event loop for efficiency.
        """
        if not self.backend_initialized:
            return

        try:
            # Get list of serials under lock
            with self.state_lock:
                serials = list(self.tracked_controllers.keys())

            if not serials:
                return

            # Phase 62: Parallel polling - read all controllers concurrently
            start_time = time.time()

            async def get_all_states():
                """Gather all controller states in parallel."""
                coros = [self.backend.get_controller_state(serial) for serial in serials]
                return await asyncio.gather(*coros, return_exceptions=True)

            # Single blocking call for ALL controllers (instead of one per controller)
            results = self._run_in_discovery_loop(get_all_states())

            # Record metrics
            poll_duration = time.time() - start_time
            metrics.poll_batch_duration_seconds.observe(poll_duration)
            metrics.poll_batch_size.observe(len(serials))

            # Process all results under a single lock acquisition
            with self.state_lock:
                for serial, state in zip(serials, results):
                    # Skip if controller was removed during polling
                    if serial not in self.tracked_controllers:
                        continue

                    # Handle exceptions from individual controller reads
                    if isinstance(state, Exception):
                        logger.debug(f"Error updating state for {serial}: {state}")
                        continue

                    if not state:
                        continue

                    # Update stored state
                    self.controller_states[serial] = state

                    # Update battery in tracked_controllers info
                    if "battery" in state:
                        self.tracked_controllers[serial]["battery"] = state["battery"]

                    # Phase 57: Update ready flag when Move button is pressed
                    if state.get("move_button", False) and not self.tracked_controllers[serial]["ready"]:
                        self.tracked_controllers[serial]["ready"] = True
                        logger.info(f"Controller {serial} marked as ready (Move button pressed)")

        except Exception as e:
            logger.error(f"Error updating controller states: {e}", exc_info=True)

    def _spawn_controller_process(self, serial: str):
        """
        Spawn a tracking process for a controller.

        Phase 57: Simplified to use backend for state tracking.
        Uses shared discovery loop event loop for efficiency.
        """
        try:
            # Get initial state from backend using shared event loop
            state = self._run_in_discovery_loop(self.backend.get_controller_state(serial))

            if not state:
                logger.error(f"Failed to get initial state for controller {serial}")
                return

            battery = state.get("battery", 5)

            # Track controller under lock
            with self.state_lock:
                self.tracked_controllers[serial] = {
                    "serial": serial,
                    "battery": battery,
                    "ready": False,
                    "team": 0,
                    "connected_at": time.time(),
                }

                # Store initial state
                self.controller_states[serial] = state

            # Add attributes to current span (this is called within "spawn_controller_process" span)
            current_span = trace.get_current_span()
            current_span.set_attribute("controller.serial", serial)
            current_span.set_attribute("controller.battery", battery)
            current_span.add_event(
                "controller_added_to_tracking",
                {"serial": serial, "battery": battery},
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
                with self.state_lock:
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
                with self.state_lock:
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
                with self.state_lock:
                    all_controllers = [
                        self._build_or_get_cached_state(serial, info)
                        for serial, info in self.tracked_controllers.items()
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

    async def PairController(self, request, context):
        """Pair a new controller via backend (async)."""
        with tracer.start_as_current_span("PairController") as span:
            span.set_attribute("color_index", request.color_index)

            try:
                # Scan for available controllers
                available = await self.backend.scan_controllers()

                if not available:
                    span.add_event("no_controllers_found")
                    return controller_manager_pb2.PairControllerResponse(
                        success=False, error="No controllers found. Put controller in pairing mode.", serial=""
                    )

                # Filter out already-tracked controllers
                with self.state_lock:
                    new_controllers = [c for c in available if c.get("serial") not in self.tracked_controllers]

                if not new_controllers:
                    span.add_event("all_controllers_already_paired")
                    return controller_manager_pb2.PairControllerResponse(
                        success=False, error="All discovered controllers are already paired.", serial=""
                    )

                # Connect to first available controller
                controller = new_controllers[0]
                address = controller.get("address", controller.get("serial"))

                success = await self.backend.connect_controller(address)

                if success:
                    serial = controller.get("serial", address)
                    span.add_event("controller_paired", {"serial": serial, "color_index": request.color_index})
                    logger.info(f"Paired new controller: {serial}")
                    return controller_manager_pb2.PairControllerResponse(success=True, error="", serial=serial)
                span.add_event("connection_failed", {"address": address})
                return controller_manager_pb2.PairControllerResponse(
                    success=False, error=f"Failed to connect to controller at {address}", serial=""
                )

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

                with self.state_lock:
                    if serial not in self.tracked_controllers:
                        return controller_manager_pb2.RemoveControllerResponse(
                            success=False, error=f"Controller {serial} not found"
                        )

                    # Stop process if running
                    if serial in self.controller_processes:
                        proc = self.controller_processes[serial]
                        if proc.is_alive():
                            proc.terminate()
                            proc.join(timeout=2.0)
                        del self.controller_processes[serial]

                    # Cancel any active vibration timer
                    if serial in self.vibration_timers:
                        self.vibration_timers[serial].cancel()
                        del self.vibration_timers[serial]

                    # Remove from tracking
                    del self.tracked_controllers[serial]

                    if serial in self.controller_states:
                        del self.controller_states[serial]

                    # Clean up state cache (Phase 18 - Task 1)
                    if serial in self.state_cache:
                        del self.state_cache[serial]

                    # Clean up button states
                    if serial in self.button_states:
                        del self.button_states[serial]

                # Cancel any active effects (Phase 31, Phase 34: async lock - outside state_lock)
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

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"RemoveController error: {e}", exc_info=True)
                return controller_manager_pb2.RemoveControllerResponse(success=False, error=str(e))

    async def SetControllerColor(self, request, context):
        """Set LED color on controller(s) - Phase 19 feedback feature, Phase 57 backend (async)."""
        with tracer.start_as_current_span("SetControllerColor") as span:
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("color.r", request.color.r)
            span.set_attribute("color.g", request.color.g)
            span.set_attribute("color.b", request.color.b)

            try:
                # Determine which controllers to update (under lock)
                with self.state_lock:
                    serials = [request.serial] if request.serial else list(self.tracked_controllers.keys())

                controllers_updated = 0
                controllers_failed = 0

                for serial in serials:
                    with self.state_lock:
                        controller_exists = serial in self.tracked_controllers
                    if controller_exists:
                        success = await self.backend.set_led_color(
                            serial, request.color.r, request.color.g, request.color.b
                        )
                        if success:
                            controllers_updated += 1
                            logger.debug(
                                f"Set color on {serial}: RGB({request.color.r},{request.color.g},{request.color.b})"
                            )
                        else:
                            controllers_failed += 1

                span.set_attribute("controllers_updated", controllers_updated)
                span.set_attribute("controllers_failed", controllers_failed)

                # Return success only if at least one controller was updated and none failed
                if controllers_failed > 0:
                    return controller_manager_pb2.SetControllerColorResponse(
                        success=False, error=f"Failed to set color on {controllers_failed} controller(s)"
                    )
                if controllers_updated == 0 and len(serials) > 0:
                    return controller_manager_pb2.SetControllerColorResponse(
                        success=False, error="No controllers found to update"
                    )
                return controller_manager_pb2.SetControllerColorResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                logger.error(f"SetControllerColor error: {e}", exc_info=True)
                return controller_manager_pb2.SetControllerColorResponse(success=False, error=str(e))

    async def SetControllerVibration(self, request, context):
        """Set vibration on controller(s) - Phase 19 feedback feature, Phase 57 async."""
        with tracer.start_as_current_span("SetControllerVibration") as span:
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("intensity", request.intensity)
            span.set_attribute("duration_ms", request.duration_ms)

            try:
                # Determine which controllers to update
                with self.state_lock:
                    serials = [request.serial] if request.serial else list(self.tracked_controllers.keys())

                controllers_updated = 0
                controllers_failed = 0

                for serial in serials:
                    with self.state_lock:
                        controller_exists = serial in self.tracked_controllers
                        if not controller_exists:
                            continue

                        # Cancel any existing vibration timer for this controller (under lock)
                        if serial in self.vibration_timers:
                            self.vibration_timers[serial].cancel()
                            del self.vibration_timers[serial]

                    success = await self.backend.set_rumble(serial, request.intensity)
                    if success:
                        controllers_updated += 1
                        logger.debug(f"Set vibration on {serial}: intensity={request.intensity}")

                        # Schedule vibration stop if duration is specified (using asyncio task)
                        if request.duration_ms > 0 and request.intensity > 0:
                            await self._schedule_vibration_stop(serial, request.duration_ms)
                    else:
                        controllers_failed += 1

                span.set_attribute("controllers_updated", controllers_updated)
                span.set_attribute("controllers_failed", controllers_failed)

                # Return success only if at least one controller was updated and none failed
                if controllers_failed > 0:
                    return controller_manager_pb2.SetControllerVibrationResponse(
                        success=False, error=f"Failed to set vibration on {controllers_failed} controller(s)"
                    )
                if controllers_updated == 0 and len(serials) > 0:
                    return controller_manager_pb2.SetControllerVibrationResponse(
                        success=False, error="No controllers found to update"
                    )
                return controller_manager_pb2.SetControllerVibrationResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                logger.error(f"SetControllerVibration error: {e}", exc_info=True)
                return controller_manager_pb2.SetControllerVibrationResponse(success=False, error=str(e))

    async def _schedule_vibration_stop(self, serial: str, duration_ms: int):
        """Schedule vibration to stop after duration using asyncio task (Phase 57 async migration)."""
        # Cancel existing task for this controller
        if serial in self.vibration_tasks:
            self.vibration_tasks[serial].cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.vibration_tasks[serial]

        async def stop_after_delay():
            await asyncio.sleep(duration_ms / 1000.0)
            with self.state_lock:
                # Clean up task tracking
                if serial in self.vibration_tasks:
                    del self.vibration_tasks[serial]
                # Skip if controller was removed
                if serial not in self.tracked_controllers:
                    logger.debug(f"Vibration task expired for removed controller {serial}")
                    return
            await self.backend.set_rumble(serial, 0)
            logger.debug(f"Vibration stopped on {serial} (duration expired)")

        self.vibration_tasks[serial] = asyncio.create_task(stop_after_delay())

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
                        await self._set_led_color(serial, color)

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
        Internal method to set controller color (Phase 46, Phase 57).

        Can be called from both SetControllerColor RPC and stream-based ColorCommand.
        Uses backend abstraction for platform independence.

        Args:
            serial: Controller serial number
            color_rgb: RGB color tuple (r, g, b)

        Returns:
            True if successful, False otherwise
        """
        try:
            if serial not in self.tracked_controllers:
                logger.warning(f"Controller {serial} not found for color change")
                return False

            # Phase 57: Use backend abstraction
            success = await self.backend.set_led_color(serial, color_rgb[0], color_rgb[1], color_rgb[2])
            if success:
                logger.debug(f"Set color on {serial}: RGB{color_rgb}")
            else:
                logger.warning(f"Failed to set color on {serial}")
            return success

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
                await self._set_led_color(serial, color_rgb)

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
        Internal method to set controller vibration (Phase 46, Phase 57).

        Can be called from both SetControllerVibration RPC and stream-based VibrationCommand.
        Uses backend abstraction for platform independence.

        Args:
            serial: Controller serial number
            intensity: Vibration intensity (0-255)
            duration_ms: Duration in milliseconds

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.state_lock:
                controller_exists = serial in self.tracked_controllers
            if not controller_exists:
                logger.warning(f"Controller {serial} not found for vibration")
                return False

            # Phase 57: Use backend abstraction
            success = await self.backend.set_rumble(serial, intensity)
            if success:
                logger.debug(f"Set vibration on {serial}: intensity={intensity}")

                # Schedule vibration stop if duration is specified
                if duration_ms > 0 and intensity > 0:
                    asyncio.create_task(self._delayed_stop_vibration(serial, duration_ms))
            else:
                logger.warning(f"Failed to set vibration on {serial}")
            return success

        except Exception as e:
            logger.error(f"Error setting vibration on {serial}: {e}", exc_info=True)
            return False

    async def _delayed_stop_vibration(self, serial: str, duration_ms: int):
        """Stop vibration on a controller after async delay."""
        try:
            await asyncio.sleep(duration_ms / 1000.0)
            await self.backend.set_rumble(serial, 0)
            logger.debug(f"Vibration stopped on {serial} (duration expired)")
        except Exception as e:
            logger.error(f"Error in delayed vibration stop for {serial}: {e}")

    async def _set_led_color(self, serial: str, color: tuple[int, int, int]):
        """
        Helper to set LED color on a controller (Phase 31, Phase 57, async).

        Called from effect methods which are all async.
        """
        if serial not in self.tracked_controllers:
            return

        try:
            await self.backend.set_led_color(serial, color[0], color[1], color[2])
        except Exception as e:
            logger.error(f"Error setting LED color on {serial}: {e}", exc_info=True)

    # Monitoring methods (battery, RSSI) moved to monitoring.py

    # Effect methods (_effect_flash, _effect_pulse, etc.) inherited from ControllerEffectsBase (Phase 40)

    def _controller_state_hash(self, state: controller_manager_pb2.ControllerState) -> str:
        """Create a hash of controller state for delta comparison (Phase 26 - Part 3)."""
        # Simple hash based on key fields that change during gameplay
        return (
            f"{state.battery}|{state.trigger_pressed}|{state.move_pressed}|{state.ready}|"
            f"{state.team}|{state.color.r},{state.color.g},{state.color.b}"
        )

    def _snapshot_hash(self, serial: str, info: dict) -> str:
        """
        Create a hash of controller hardware snapshot (Phase 18 - Task 1).
        Phase 57: state is now a dict from backend (no get_snapshot() method).
        """
        # Get state snapshot if available (Phase 57: already a dict from backend)
        state_dict = self.controller_states.get(serial)

        if state_dict:
            # Hash all fields that can change during gameplay
            accel = state_dict.get("accel", {})
            gyro = state_dict.get("gyro", {})
            return (
                f"{info.get('battery', 0)}|"
                f"{state_dict.get('trigger_button', False)}|{state_dict.get('move_button', False)}|"
                f"{state_dict.get('cross_button', False)}|{state_dict.get('circle_button', False)}|"
                f"{state_dict.get('square_button', False)}|{state_dict.get('triangle_button', False)}|"
                f"{state_dict.get('ps_button', False)}|"
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
        """
        Build a ControllerState protobuf message (Phase 18: Use pooled objects).

        Phase 57: Updated to use backend state dict instead of ControllerState object.
        """
        # Get state dict from backend if available
        state_dict = self.controller_states.get(serial)

        if state_dict:
            # Phase 57: State is now a dict from backend, not ControllerState object
            trigger_pressed = state_dict.get("trigger_button", False)
            move_pressed = state_dict.get("move_button", False)
            cross_pressed = state_dict.get("cross", False)
            circle_pressed = state_dict.get("circle", False)
            square_pressed = state_dict.get("square", False)
            triangle_pressed = state_dict.get("triangle", False)
            ps_pressed = state_dict.get("ps_button", False)
            accel = state_dict.get("accel", {"x": 0, "y": 0, "z": 0})
            gyro = state_dict.get("gyro", {"x": 0, "y": 0, "z": 0})
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
        controller_state.rssi = self.monitoring.get_rssi(serial)  # Phase 48

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
        # Initialize button state tracking for this controller if needed (under lock)
        with self.state_lock:
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

                # Update tracked state (dict is mutable, so this updates button_states)
                with self.state_lock:
                    prev_states[button_name] = current_pressed

        # Publish events to all subscribers
        # Take snapshot of subscribers to avoid iteration over changing dict
        if events:
            # Snapshot subscriber queues to avoid race conditions during iteration
            subscriber_queues = list(self.button_event_subscribers.values())
            for subscriber_queue in subscriber_queues:
                for event in events:
                    try:
                        subscriber_queue.put_nowait(event)
                    except asyncio.QueueFull:
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

    # Start system metrics collection (Phase 61: extracted to lib/system_metrics.py)
    start_system_metrics_collector(
        cpu_gauge=metrics.process_cpu_percent,
        memory_gauge=metrics.process_memory_mb,
        threads_gauge=metrics.process_threads,
    )

    # Create async server with keepalive options to match client settings
    # Without these options, server rejects client pings as "too many pings"
    from lib.grpc_utils import get_server_options
    server = grpc.aio.server(options=get_server_options())

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
        controller_servicer.shutdown()
        await server.stop(grace=5)

        # Stop mock server if running
        if mock_server:
            await mock_server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
