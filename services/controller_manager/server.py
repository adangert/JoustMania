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
import queue
from collections import deque

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

from proto import controller_manager_pb2, controller_manager_pb2_grpc
from services.controller_manager.effects_base import ControllerEffectsBase

# PS Move imports (optional for testing)
try:
    from multiprocessing import Array, Process, Value

    import common
    import controller_process
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


class ControllerManagerServicer(
    controller_manager_pb2_grpc.ControllerManagerServiceServicer,
    ControllerEffectsBase
):
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

        # Streaming subscribers
        self.stream_subscribers: dict[str, queue.Queue] = {}
        self.stream_lock = threading.Lock()

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
        # Thread lock for safe access from discovery thread
        self.effect_lock = threading.Lock()

        # Discovery thread
        self.running = True
        self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.discovery_thread.start()

        logger.info("ControllerManager initialized")

    def _discovery_loop(self):
        """Background thread for controller discovery."""
        with tracer.start_as_current_span("discovery_loop"):
            while self.running:
                try:
                    with tracer.start_as_current_span("check_new_controllers") as span:
                        if PSMOVE_AVAILABLE:
                            self._check_for_new_controllers()
                        span.set_attribute("controller.count", len(self.tracked_controllers))

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
                        if move.connection_type == psmove.Conn_USB:
                            if serial not in self.paired_serials:
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

                return controller_manager_pb2.GetControllerCountResponse(
                    count=count, success=True, error=""
                )
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetControllerCount error: {e}", exc_info=True)
                return controller_manager_pb2.GetControllerCountResponse(
                    count=0, success=False, error=str(e)
                )

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
                return controller_manager_pb2.GetReadyControllersResponse(
                    controllers=[], success=False, error=str(e)
                )

    def GetControllers(self, request, context):
        """Get all controllers."""
        with tracer.start_as_current_span("GetControllers") as span:
            try:
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
                return controller_manager_pb2.GetControllersResponse(
                    controllers=[], success=False, error=str(e)
                )

    async def StreamControllerStates(self, request, context):
        """Stream controller states in real-time (async)."""
        subscriber_id = f"stream_{time.time()}"

        with tracer.start_as_current_span("StreamControllerStates") as span:
            span.set_attribute("subscriber.id", subscriber_id)
            span.set_attribute("update_frequency_hz", request.update_frequency_hz or 60)

            # Create queue for this subscriber
            event_queue = queue.Queue(maxsize=100)

            with self.stream_lock:
                self.stream_subscribers[subscriber_id] = event_queue
                # Initialize delta tracking for this subscriber
                self.last_sent_states[subscriber_id] = {}

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

                        # CRITICAL FIX: Use async sleep instead of blocking time.sleep()
                        await asyncio.sleep(interval)

                    except Exception as e:
                        logger.error(f"Stream error for {subscriber_id}: {e}")
                        break

            finally:
                # Cleanup
                with self.stream_lock:
                    if subscriber_id in self.stream_subscribers:
                        del self.stream_subscribers[subscriber_id]
                    # Clean up delta tracking
                    if subscriber_id in self.last_sent_states:
                        del self.last_sent_states[subscriber_id]

                logger.info(f"Stream subscriber disconnected: {subscriber_id}")

    def PairController(self, request, context):
        """Pair a new controller."""
        with tracer.start_as_current_span("PairController") as span:
            span.set_attribute("color_index", request.color_index)

            try:
                # In production, this would trigger USB pairing
                # For now, return mock response
                serial = "mock_serial_12345"
                span.add_event(
                    "controller_paired", {"serial": serial, "color_index": request.color_index}
                )
                return controller_manager_pb2.PairControllerResponse(
                    success=True, error="", serial=serial
                )
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"PairController error: {e}", exc_info=True)
                return controller_manager_pb2.PairControllerResponse(
                    success=False, error=str(e), serial=""
                )

    def RemoveController(self, request, context):
        """Remove a controller."""
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

                    # Cancel any active effects (Phase 31)
                    with self.effect_lock:
                        if serial in self.active_effects:
                            self.active_effects[serial].cancel()
                            del self.active_effects[serial]

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
                        f"SetControllerColor (mock): {request.serial or 'all'} -> RGB({request.color.r},{request.color.g},{request.color.b})"
                    )
                    return controller_manager_pb2.SetControllerColorResponse(success=True, error="")

                # Determine which controllers to update
                serials = (
                    [request.serial] if request.serial else list(self.tracked_controllers.keys())
                )

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
                return controller_manager_pb2.SetControllerColorResponse(
                    success=False, error=str(e)
                )

    def SetControllerVibration(self, request, context):
        """Set vibration on controller(s) - Phase 19 feedback feature."""
        with tracer.start_as_current_span("SetControllerVibration") as span:
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("intensity", request.intensity)
            span.set_attribute("duration_ms", request.duration_ms)

            try:
                if not PSMOVE_AVAILABLE:
                    logger.info(
                        f"SetControllerVibration (mock): {request.serial or 'all'} intensity={request.intensity} duration={request.duration_ms}ms"
                    )
                    return controller_manager_pb2.SetControllerVibrationResponse(
                        success=True, error=""
                    )

                # Determine which controllers to update
                serials = (
                    [request.serial] if request.serial else list(self.tracked_controllers.keys())
                )

                controllers_updated = 0
                for serial in serials:
                    if serial in self.tracked_controllers:
                        info = self.tracked_controllers[serial]
                        move = info.get("move")
                        if move:
                            move.set_rumble(request.intensity)
                            controllers_updated += 1
                            logger.debug(
                                f"Set vibration on {serial}: intensity={request.intensity}"
                            )

                # TODO: Handle duration_ms by resetting rumble after timeout
                # For now, vibration stays at intensity until explicitly changed

                span.set_attribute("controllers_updated", controllers_updated)
                return controller_manager_pb2.SetControllerVibrationResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                logger.error(f"SetControllerVibration error: {e}", exc_info=True)
                return controller_manager_pb2.SetControllerVibrationResponse(
                    success=False, error=str(e)
                )

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
                    logger.info(
                        f"PlayControllerEffect (mock): {request.serial or 'all'} effect={effect_name}"
                    )
                    return controller_manager_pb2.PlayControllerEffectResponse(
                        success=True, error=""
                    )

                # Determine which controllers to update
                serials = (
                    [request.serial] if request.serial else list(self.tracked_controllers.keys())
                )

                # Color as tuple for effect methods
                color = (request.color.r, request.color.g, request.color.b) if request.color else (255, 255, 255)
                duration_ms = request.duration_ms or 1000  # Default 1 second
                speed = request.speed or 5  # Default medium speed

                controllers_updated = 0
                for serial in serials:
                    if serial not in self.tracked_controllers:
                        continue

                    # Cancel any existing effect on this controller
                    with self.effect_lock:
                        if serial in self.active_effects:
                            self.active_effects[serial].cancel()
                            try:
                                await self.active_effects[serial]
                            except asyncio.CancelledError:
                                pass
                            del self.active_effects[serial]

                    # Start the appropriate effect (methods inherited from ControllerEffectsBase - Phase 40)
                    if request.effect == controller_manager_pb2.EFFECT_NONE:
                        # Solid color (no animation)
                        self._set_led_color(serial, color)

                    elif request.effect == controller_manager_pb2.EFFECT_FLASH:
                        task = asyncio.create_task(self._effect_flash(serial, color, duration_ms, speed))
                        with self.effect_lock:
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_PULSE:
                        task = asyncio.create_task(self._effect_pulse(serial, color, duration_ms, speed))
                        with self.effect_lock:
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_RAINBOW:
                        task = asyncio.create_task(self._effect_rainbow(serial, duration_ms, speed))
                        with self.effect_lock:
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_FADE_OUT:
                        task = asyncio.create_task(self._effect_fade_out(serial, color, duration_ms))
                        with self.effect_lock:
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_FADE_IN:
                        task = asyncio.create_task(self._effect_fade_in(serial, color, duration_ms))
                        with self.effect_lock:
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
                return controller_manager_pb2.PlayControllerEffectResponse(
                    success=False, error=str(e)
                )

    def _set_led_color(self, serial: str, color: tuple[int, int, int]):
        """Helper to set LED color on a controller (Phase 31)."""
        if serial not in self.tracked_controllers:
            return

        info = self.tracked_controllers[serial]
        move = info.get("move")
        if move and PSMOVE_AVAILABLE:
            move.set_leds(color[0], color[1], color[2])
            move.update_leds()

    # Effect methods (_effect_flash, _effect_pulse, etc.) inherited from ControllerEffectsBase (Phase 40)

    def _controller_state_hash(self, state: controller_manager_pb2.ControllerState) -> str:
        """Create a hash of controller state for delta comparison (Phase 26 - Part 3)."""
        # Simple hash based on key fields that change during gameplay
        return f"{state.battery}|{state.trigger_pressed}|{state.move_pressed}|{state.ready}|{state.team}|{state.color.r},{state.color.g},{state.color.b}"

    def _snapshot_hash(self, serial: str, info: dict) -> str:
        """Create a hash of controller hardware snapshot (Phase 18 - Task 1)."""
        # Get state snapshot if available
        state = self.controller_states.get(serial)

        if state:
            snapshot = state.get_snapshot()
            # Hash all fields that can change during gameplay
            return (
                f"{info.get('battery', 0)}|"
                f"{snapshot.get('trigger', False)}|{snapshot.get('move', False)}|"
                f"{snapshot.get('cross', False)}|{snapshot.get('circle', False)}|"
                f"{snapshot.get('square', False)}|{snapshot.get('triangle', False)}|"
                f"{snapshot.get('ps', False)}|"
                f"{snapshot.get('accel', {}).get('x', 0):.2f},{snapshot.get('accel', {}).get('y', 0):.2f},{snapshot.get('accel', {}).get('z', 0):.2f}|"
                f"{snapshot.get('gyro', {}).get('x', 0):.2f},{snapshot.get('gyro', {}).get('y', 0):.2f},{snapshot.get('gyro', {}).get('z', 0):.2f}|"
                f"{info.get('ready', False)}|{info.get('team', 0)}"
            )
        else:
            # No state available, return hash based on info only
            return f"{info.get('battery', 0)}|{info.get('ready', False)}|{info.get('team', 0)}"

    def _build_or_get_cached_state(
        self, serial: str, info: dict
    ) -> controller_manager_pb2.ControllerState:
        """Return cached state if unchanged, rebuild if dirty (Phase 18 - Task 1)."""
        # Calculate current snapshot hash
        current_hash = self._snapshot_hash(serial, info)

        # Get cache entry for this controller
        cache_entry = self.state_cache.get(serial)

        if cache_entry:
            # Check if state changed
            if cache_entry["snapshot_hash"] == current_hash:
                # State unchanged, return cached protobuf message
                return cache_entry["cached_state"]

        # State changed or not cached yet - rebuild
        new_state = self._build_controller_state_message(serial, info)

        # Update cache
        self.state_cache[serial] = {
            "cached_state": new_state,
            "snapshot_hash": current_hash,
        }

        return new_state

    def _build_controller_state_message(
        self, serial: str, info: dict
    ) -> controller_manager_pb2.ControllerState:
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

        # Return pooled Vector3 objects (ControllerState made copies with CopyFrom)
        self.vector3_pool.return_msg(accel_vec)
        self.vector3_pool.return_msg(gyro_vec)

        return controller_state

    def shutdown(self):
        """Shutdown the controller manager."""
        logger.info("Shutting down ControllerManager...")
        self.running = False

        # Stop all controller processes
        for serial, proc in self.controller_processes.items():
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2.0)

        self.discovery_thread.join(timeout=5.0)


async def serve(port=50052):
    """Start the ControllerManager async gRPC server."""
    # Configure logging with environment variable support
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create async server (CRITICAL FIX: grpc.aio instead of grpc.server)
    server = grpc.aio.server()

    # Add servicer
    controller_servicer = ControllerManagerServicer()
    controller_manager_pb2_grpc.add_ControllerManagerServiceServicer_to_server(
        controller_servicer, server
    )

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the ControllerManager service as SERVING
    await health_servicer.set(
        "controller_manager.ControllerManagerService", health_pb2.HealthCheckResponse.SERVING
    )
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
