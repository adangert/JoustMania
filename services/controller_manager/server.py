"""
ControllerManager gRPC Server for JoustMania

Manages PS Move controller lifecycle as a gRPC service:
- Discover and pair controllers
- Stream controller states in real-time
- Provide controller query interface
- Handle controller removal

This replaces the Queue-based IPC with gRPC (Phase 8a).
"""

import logging
import time
import threading
import queue
import asyncio
from typing import Dict, List, Optional
from concurrent import futures
import grpc
import grpc.aio
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

from services.controller_manager import controller_manager_pb2, controller_manager_pb2_grpc

# PS Move imports (optional for testing)
try:
    import psmove
    from multiprocessing import Process, Array, Value
    import controller_process
    from controller_state import ControllerState
    import common
    import pair as pair_module
    PSMOVE_AVAILABLE = True
except ImportError:
    PSMOVE_AVAILABLE = False
    logging.warning("psmove not available - controller manager will run in mock mode")

logger = logging.getLogger(__name__)

# Initialize OpenTelemetry
def init_telemetry():
    """Initialize OpenTelemetry with OTLP exporter."""
    otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4317')
    service_name = os.getenv('OTEL_SERVICE_NAME', 'controller-manager-service')

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


class ControllerManagerServicer(controller_manager_pb2_grpc.ControllerManagerServiceServicer):
    """
    ControllerManager gRPC servicer.

    Manages PS Move controllers:
    - Discovery and pairing
    - Controller process spawning
    - State monitoring and streaming
    - Health checking
    """

    def __init__(self):
        """Initialize controller manager."""
        self.tracked_controllers: Dict[str, Dict] = {}  # serial -> controller info
        self.controller_states: Dict[str, ControllerState] = {}  # serial -> state
        self.controller_processes: Dict[str, Process] = {}  # serial -> process
        self.paired_serials: List[str] = []

        # Streaming subscribers
        self.stream_subscribers: Dict[str, queue.Queue] = {}
        self.stream_lock = threading.Lock()

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
                'serial': serial,
                'move_num': move_num,
                'battery': battery,
                'ready': False,
                'team': 0,
                'connected_at': time.time(),
                'move': move  # Store move object for feedback operations
            }

            # Add attributes to current span (this is called within "spawn_controller_process" span)
            current_span = trace.get_current_span()
            current_span.set_attribute("controller.serial", serial)
            current_span.set_attribute("controller.move_num", move_num)
            current_span.set_attribute("controller.battery", battery)
            current_span.add_event("controller_added_to_tracking", {
                "serial": serial,
                "move_num": move_num,
                "battery": battery
            })

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
                    count=count,
                    success=True,
                    error=""
                )
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetControllerCount error: {e}", exc_info=True)
                return controller_manager_pb2.GetControllerCountResponse(
                    count=0,
                    success=False,
                    error=str(e)
                )

    def GetReadyControllers(self, request, context):
        """Get all ready controllers."""
        with tracer.start_as_current_span("GetReadyControllers") as span:
            try:
                ready_controllers = [
                    self._build_controller_state_message(serial, info)
                    for serial, info in self.tracked_controllers.items()
                    if info.get('ready', False)
                ]

                span.set_attribute("controller.ready_count", len(ready_controllers))

                return controller_manager_pb2.GetReadyControllersResponse(
                    controllers=ready_controllers,
                    success=True,
                    error=""
                )
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetReadyControllers error: {e}", exc_info=True)
                return controller_manager_pb2.GetReadyControllersResponse(
                    controllers=[],
                    success=False,
                    error=str(e)
                )

    def GetControllers(self, request, context):
        """Get all controllers."""
        with tracer.start_as_current_span("GetControllers") as span:
            try:
                all_controllers = [
                    self._build_controller_state_message(serial, info)
                    for serial, info in self.tracked_controllers.items()
                ]

                span.set_attribute("controller.total_count", len(all_controllers))

                return controller_manager_pb2.GetControllersResponse(
                    controllers=all_controllers,
                    success=True,
                    error=""
                )
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetControllers error: {e}", exc_info=True)
                return controller_manager_pb2.GetControllersResponse(
                    controllers=[],
                    success=False,
                    error=str(e)
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

            logger.info(f"New stream subscriber: {subscriber_id}")

            try:
                frequency = request.update_frequency_hz or 60
                interval = 1.0 / frequency

                while not context.cancelled():
                    try:
                        # Build current state
                        controllers = [
                            self._build_controller_state_message(serial, info)
                            for serial, info in self.tracked_controllers.items()
                        ]

                        update = controller_manager_pb2.ControllerStateUpdate(
                            controllers=controllers,
                            timestamp=int(time.time() * 1000)
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

                logger.info(f"Stream subscriber disconnected: {subscriber_id}")

    def PairController(self, request, context):
        """Pair a new controller."""
        with tracer.start_as_current_span("PairController") as span:
            span.set_attribute("color_index", request.color_index)

            try:
                # In production, this would trigger USB pairing
                # For now, return mock response
                serial = "mock_serial_12345"
                span.add_event("controller_paired", {
                    "serial": serial,
                    "color_index": request.color_index
                })
                return controller_manager_pb2.PairControllerResponse(
                    success=True,
                    error="",
                    serial=serial
                )
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"PairController error: {e}", exc_info=True)
                return controller_manager_pb2.PairControllerResponse(
                    success=False,
                    error=str(e),
                    serial=""
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

                    span.add_event("controller_removed", {
                        "serial": serial
                    })
                    logger.info(f"Removed controller {serial}")

                    return controller_manager_pb2.RemoveControllerResponse(
                        success=True,
                        error=""
                    )
                else:
                    return controller_manager_pb2.RemoveControllerResponse(
                        success=False,
                        error=f"Controller {serial} not found"
                    )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"RemoveController error: {e}", exc_info=True)
                return controller_manager_pb2.RemoveControllerResponse(
                    success=False,
                    error=str(e)
                )

    def SetControllerColor(self, request, context):
        """Set LED color on controller(s) - Phase 19 feedback feature."""
        with tracer.start_as_current_span("SetControllerColor") as span:
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("color.r", request.color.r)
            span.set_attribute("color.g", request.color.g)
            span.set_attribute("color.b", request.color.b)

            try:
                if not PSMOVE_AVAILABLE:
                    logger.info(f"SetControllerColor (mock): {request.serial or 'all'} -> RGB({request.color.r},{request.color.g},{request.color.b})")
                    return controller_manager_pb2.SetControllerColorResponse(
                        success=True,
                        error=""
                    )

                # Determine which controllers to update
                serials = [request.serial] if request.serial else list(self.tracked_controllers.keys())

                controllers_updated = 0
                for serial in serials:
                    if serial in self.tracked_controllers:
                        info = self.tracked_controllers[serial]
                        move = info.get('move')
                        if move:
                            move.set_leds(request.color.r, request.color.g, request.color.b)
                            move.update_leds()
                            controllers_updated += 1
                            logger.debug(f"Set color on {serial}: RGB({request.color.r},{request.color.g},{request.color.b})")

                span.set_attribute("controllers_updated", controllers_updated)
                return controller_manager_pb2.SetControllerColorResponse(
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                logger.error(f"SetControllerColor error: {e}", exc_info=True)
                return controller_manager_pb2.SetControllerColorResponse(
                    success=False,
                    error=str(e)
                )

    def SetControllerVibration(self, request, context):
        """Set vibration on controller(s) - Phase 19 feedback feature."""
        with tracer.start_as_current_span("SetControllerVibration") as span:
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("intensity", request.intensity)
            span.set_attribute("duration_ms", request.duration_ms)

            try:
                if not PSMOVE_AVAILABLE:
                    logger.info(f"SetControllerVibration (mock): {request.serial or 'all'} intensity={request.intensity} duration={request.duration_ms}ms")
                    return controller_manager_pb2.SetControllerVibrationResponse(
                        success=True,
                        error=""
                    )

                # Determine which controllers to update
                serials = [request.serial] if request.serial else list(self.tracked_controllers.keys())

                controllers_updated = 0
                for serial in serials:
                    if serial in self.tracked_controllers:
                        info = self.tracked_controllers[serial]
                        move = info.get('move')
                        if move:
                            move.set_rumble(request.intensity)
                            controllers_updated += 1
                            logger.debug(f"Set vibration on {serial}: intensity={request.intensity}")

                # TODO: Handle duration_ms by resetting rumble after timeout
                # For now, vibration stays at intensity until explicitly changed

                span.set_attribute("controllers_updated", controllers_updated)
                return controller_manager_pb2.SetControllerVibrationResponse(
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                logger.error(f"SetControllerVibration error: {e}", exc_info=True)
                return controller_manager_pb2.SetControllerVibrationResponse(
                    success=False,
                    error=str(e)
                )

    def PlayControllerEffect(self, request, context):
        """Play visual effect on controller(s) - Phase 19 feedback feature."""
        with tracer.start_as_current_span("PlayControllerEffect") as span:
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("effect", request.effect)

            try:
                if not PSMOVE_AVAILABLE:
                    effect_name = controller_manager_pb2.ControllerEffect.Name(request.effect)
                    logger.info(f"PlayControllerEffect (mock): {request.serial or 'all'} effect={effect_name}")
                    return controller_manager_pb2.PlayControllerEffectResponse(
                        success=True,
                        error=""
                    )

                # TODO: Implement effects (FLASH, PULSE, RAINBOW, FADE_OUT, FADE_IN)
                # For Phase 19, we'll implement basic color setting
                # Effects will need background threads or async tasks to animate

                # For now, just set the color (if provided)
                controllers_updated = 0
                if request.effect == controller_manager_pb2.EFFECT_NONE:
                    # Set solid color
                    serials = [request.serial] if request.serial else list(self.tracked_controllers.keys())
                    for serial in serials:
                        if serial in self.tracked_controllers:
                            info = self.tracked_controllers[serial]
                            move = info.get('move')
                            if move and request.color:
                                move.set_leds(request.color.r, request.color.g, request.color.b)
                                move.update_leds()
                                controllers_updated += 1

                effect_name = controller_manager_pb2.ControllerEffect.Name(request.effect)
                span.set_attribute("controllers_updated", controllers_updated)
                span.set_attribute("effect", effect_name)
                logger.info(f"PlayControllerEffect: {effect_name} (basic implementation)")

                return controller_manager_pb2.PlayControllerEffectResponse(
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                logger.error(f"PlayControllerEffect error: {e}", exc_info=True)
                return controller_manager_pb2.PlayControllerEffectResponse(
                    success=False,
                    error=str(e)
                )

    def _build_controller_state_message(self, serial: str, info: Dict) -> controller_manager_pb2.ControllerState:
        """Build a ControllerState protobuf message."""
        # Get state snapshot if available
        state = self.controller_states.get(serial)

        if state:
            snapshot = state.get_snapshot()
            trigger_pressed = snapshot.get('trigger', False)
            move_pressed = snapshot.get('move', False)
            cross_pressed = snapshot.get('cross', False)
            circle_pressed = snapshot.get('circle', False)
            square_pressed = snapshot.get('square', False)
            triangle_pressed = snapshot.get('triangle', False)
            ps_pressed = snapshot.get('ps', False)
            accel = snapshot.get('accel', {'x': 0, 'y': 0, 'z': 0})
            gyro = snapshot.get('gyro', {'x': 0, 'y': 0, 'z': 0})
        else:
            trigger_pressed = False
            move_pressed = False
            cross_pressed = False
            circle_pressed = False
            square_pressed = False
            triangle_pressed = False
            ps_pressed = False
            accel = {'x': 0, 'y': 0, 'z': 0}
            gyro = {'x': 0, 'y': 0, 'z': 0}

        return controller_manager_pb2.ControllerState(
            serial=serial,
            move_num=info.get('move_num', 0),
            battery=info.get('battery', 0),
            trigger_pressed=trigger_pressed,
            move_pressed=move_pressed,
            ready=info.get('ready', False),
            team=info.get('team', 0),
            color=controller_manager_pb2.RGB(r=0, g=0, b=255),
            accel=controller_manager_pb2.Vector3(x=accel['x'], y=accel['y'], z=accel['z']),
            gyro=controller_manager_pb2.Vector3(x=gyro['x'], y=gyro['y'], z=gyro['z']),
            cross_pressed=cross_pressed,
            circle_pressed=circle_pressed,
            square_pressed=square_pressed,
            triangle_pressed=triangle_pressed,
            ps_pressed=ps_pressed
        )

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
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
    await health_servicer.set("controller_manager.ControllerManagerService", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # Overall health

    # Bind to port
    server.add_insecure_port(f'[::]:{port}')

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


if __name__ == '__main__':
    asyncio.run(serve())
