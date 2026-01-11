"""
Mock ControllerManager gRPC Server for testing without hardware.

Provides:
- Same gRPC interface as real ControllerManager
- Additional control RPCs for simulation
- Configurable number of controllers
- Controllable controller states via gRPC
"""

import asyncio
import logging
import os
import time
from concurrent import futures

import grpc
from proto import controller_manager_mock_pb2_grpc, controller_manager_pb2_grpc
from services.controller_manager.effects_base import ControllerEffectsBase
from proto.controller_manager_mock_pb2 import (
    ButtonResponse,
    ColorResponse,
    DeathResponse,
    ListResponse,
    MovementResponse,
    ResetResponse,
)
from proto.controller_manager_pb2 import (
    RGB,
    ControllerState,
    ControllerStateUpdate,
    GetReadyControllersResponse,
    PlayControllerEffectResponse,
    Vector3,
)
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


class MockController:
    """Represents a mock PS Move controller."""

    def __init__(self, serial: str):
        self.serial = serial
        self.battery = 100
        self.trigger_pressed = False
        self.move_pressed = False
        self.ready = True
        self.team = 0
        self.color = RGB(r=255, g=255, b=255)
        self.accel = Vector3(x=0.0, y=0.0, z=1.0)  # Default idle
        self.gyro = Vector3(x=0.0, y=0.0, z=0.0)

    def to_proto(self) -> ControllerState:
        """Convert to protobuf ControllerState."""
        return ControllerState(
            serial=self.serial,
            move_num=int(self.serial.split("_")[-1]),
            battery=self.battery,
            trigger_pressed=self.trigger_pressed,
            move_pressed=self.move_pressed,
            ready=self.ready,
            team=self.team,
            color=self.color,
            accel=self.accel,
            gyro=self.gyro,
        )


class MockControllerManagerService(
    controller_manager_pb2_grpc.ControllerManagerServiceServicer,
    ControllerEffectsBase
):
    """Mock ControllerManager implementing same interface as real one.

    Phase 40: Inherits from ControllerEffectsBase for shared effect logic.
    """

    def __init__(self, num_controllers: int):
        ControllerEffectsBase.__init__(self)  # Initialize effects base class
        self.controllers: dict[str, MockController] = {}

        # Initialize mock controllers
        for i in range(num_controllers):
            serial = f"mock_controller_{i}"
            self.controllers[serial] = MockController(serial)

        # active_effects dict inherited from ControllerEffectsBase (Phase 40)

        logger.info(f"Initialized {num_controllers} mock controllers")

    def GetReadyControllers(self, request, context):
        """Return all mock controllers as ready."""
        controllers = [c.to_proto() for c in self.controllers.values()]
        return GetReadyControllersResponse(controllers=controllers, success=True, error="")

    async def StreamControllerStates(self, request, context):
        """Stream controller states at requested frequency."""
        frequency = request.update_frequency_hz or 60
        interval = 1.0 / frequency

        logger.info(f"Starting controller state stream at {frequency}Hz")

        try:
            while not context.cancelled():
                # Get current states
                controllers = [c.to_proto() for c in self.controllers.values()]

                yield ControllerStateUpdate(controllers=controllers, timestamp=int(time.time() * 1000))

                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Controller state stream cancelled")
            raise

    def _set_led_color(self, serial: str, color: tuple[int, int, int]):
        """Helper to set LED color on a mock controller (Phase 31 / Phase 40 override)."""
        controller = self.controllers.get(serial)
        if controller:
            controller.color = RGB(r=color[0], g=color[1], b=color[2])

    # Effect methods (_effect_flash, _effect_pulse, etc.) inherited from ControllerEffectsBase (Phase 40)

    async def SetControllerColor(self, request, context):
        """Set LED color on controller(s)."""
        from proto.controller_manager_pb2 import SetControllerColorResponse

        # Determine target controllers
        if request.serial:
            target_serials = [request.serial]
        else:
            target_serials = list(self.controllers.keys())

        color = (request.color.r, request.color.g, request.color.b)

        for serial in target_serials:
            self._set_led_color(serial, color)

        logger.debug(f"SetControllerColor: color={color}, targets={len(target_serials)}")
        return SetControllerColorResponse(success=True, error="")

    async def SetControllerVibration(self, request, context):
        """Set vibration intensity on controller(s)."""
        from proto.controller_manager_pb2 import SetControllerVibrationResponse

        # Mock implementation - we don't actually vibrate in mock mode
        # but we acknowledge the request

        if request.serial:
            target_serials = [request.serial]
        else:
            target_serials = list(self.controllers.keys())

        logger.debug(f"SetControllerVibration: intensity={request.intensity}, targets={len(target_serials)}")
        return SetControllerVibrationResponse(success=True, error="")

    async def PlayControllerEffect(self, request, context):
        """Play visual effect on controller(s) - Phase 31/40 implementation.

        Uses effect methods inherited from ControllerEffectsBase.
        """
        from proto import controller_manager_pb2

        # Determine target controllers
        if request.serial:
            target_serials = [request.serial]
        else:
            target_serials = list(self.controllers.keys())

        color = (request.color.r, request.color.g, request.color.b)
        duration_ms = request.duration_ms
        speed = request.speed or 5

        for serial in target_serials:
            if serial not in self.controllers:
                continue

            # Cancel any existing effect
            if serial in self.active_effects:
                self.active_effects[serial].cancel()
                try:
                    await self.active_effects[serial]
                except asyncio.CancelledError:
                    pass
                del self.active_effects[serial]

            # Start the appropriate effect (methods inherited from ControllerEffectsBase)
            if request.effect == controller_manager_pb2.EFFECT_FLASH:
                task = asyncio.create_task(self._effect_flash(serial, color, duration_ms, speed))
                self.active_effects[serial] = task
            elif request.effect == controller_manager_pb2.EFFECT_PULSE:
                task = asyncio.create_task(self._effect_pulse(serial, color, duration_ms, speed))
                self.active_effects[serial] = task
            elif request.effect == controller_manager_pb2.EFFECT_RAINBOW:
                task = asyncio.create_task(self._effect_rainbow(serial, duration_ms, speed))
                self.active_effects[serial] = task
            elif request.effect == controller_manager_pb2.EFFECT_FADE_OUT:
                task = asyncio.create_task(self._effect_fade_out(serial, color, duration_ms))
                self.active_effects[serial] = task
            elif request.effect == controller_manager_pb2.EFFECT_FADE_IN:
                task = asyncio.create_task(self._effect_fade_in(serial, color, duration_ms))
                self.active_effects[serial] = task
            elif request.effect == controller_manager_pb2.EFFECT_NONE:
                self._set_led_color(serial, color)

        logger.info(f"PlayControllerEffect: effect={request.effect}, targets={len(target_serials)}")
        return PlayControllerEffectResponse(success=True, error="")


class MockControllerControlService(controller_manager_mock_pb2_grpc.MockControllerServiceServicer):
    """Additional RPCs for controlling mock controllers."""

    def __init__(self, controller_manager: MockControllerManagerService):
        self.manager = controller_manager

    def SimulateMovement(self, request, context):
        """Simulate controller movement by setting acceleration."""
        controller = self.manager.controllers.get(request.serial)

        if not controller:
            return MovementResponse(success=False, error=f"Controller {request.serial} not found")

        controller.accel = Vector3(x=request.accel_x, y=request.accel_y, z=request.accel_z)

        logger.info(
            f"Simulated movement for {request.serial}: ({request.accel_x}, {request.accel_y}, {request.accel_z})"
        )

        return MovementResponse(success=True, error="")

    def SimulateDeath(self, request, context):
        """Simulate death by setting high acceleration."""
        controller = self.manager.controllers.get(request.serial)

        if not controller:
            return DeathResponse(success=False, accel_magnitude=0.0)

        # Set death-level acceleration (>2.8 for FAST sensitivity)
        controller.accel = Vector3(x=5.0, y=3.0, z=4.0)
        accel_mag = (5.0**2 + 3.0**2 + 4.0**2) ** 0.5

        logger.info(f"Simulated death for {request.serial}: magnitude={accel_mag:.2f}")

        return DeathResponse(success=True, accel_magnitude=accel_mag)

    def SimulateButton(self, request, context):
        """Simulate button press."""
        controller = self.manager.controllers.get(request.serial)

        if not controller:
            return ButtonResponse(success=False, error=f"Controller {request.serial} not found")

        if request.button == 0:  # TRIGGER
            controller.trigger_pressed = request.pressed
        elif request.button == 1:  # MOVE
            controller.move_pressed = request.pressed

        logger.info(
            f"Simulated button {request.button} {'press' if request.pressed else 'release'} for {request.serial}"
        )

        return ButtonResponse(success=True, error="")

    def SetColor(self, request, context):
        """Set controller LED color."""
        controller = self.manager.controllers.get(request.serial)

        if not controller:
            return ColorResponse(success=False, error=f"Controller {request.serial} not found")

        controller.color = RGB(r=request.r, g=request.g, b=request.b)

        logger.info(f"Set color for {request.serial}: ({request.r}, {request.g}, {request.b})")

        return ColorResponse(success=True, error="")

    def ResetController(self, request, context):
        """Reset controller to idle state."""
        controller = self.manager.controllers.get(request.serial)

        if not controller:
            return ResetResponse(success=False, error=f"Controller {request.serial} not found")

        # Reset to idle
        controller.accel = Vector3(x=0.0, y=0.0, z=1.0)
        controller.gyro = Vector3(x=0.0, y=0.0, z=0.0)
        controller.trigger_pressed = False
        controller.move_pressed = False

        logger.info(f"Reset {request.serial} to idle state")

        return ResetResponse(success=True, error="")

    def ListMockControllers(self, request, context):
        """List all mock controllers."""
        serials = list(self.manager.controllers.keys())

        return ListResponse(serials=serials, count=len(serials))


def init_telemetry():
    """Initialize OpenTelemetry."""
    resource = Resource(
        attributes={
            SERVICE_NAME: "controller-manager-service",
            "service.namespace": "joustmania",
            "mock.enabled": "true",
        }
    )

    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"), insecure=True
    )
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    GrpcInstrumentorServer().instrument()

    logger.info("OpenTelemetry initialized for mock controller manager")


async def serve():
    """Start mock gRPC servers."""
    init_telemetry()

    # Get configuration
    num_controllers = int(os.getenv("MOCK_CONTROLLER_COUNT", "4"))
    main_port = int(os.getenv("GRPC_PORT", "50052"))
    control_port = int(os.getenv("MOCK_CONTROL_PORT", "50062"))

    # Create services
    controller_manager = MockControllerManagerService(num_controllers)
    control_service = MockControllerControlService(controller_manager)

    # Main server (standard ControllerManager interface)
    main_server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    controller_manager_pb2_grpc.add_ControllerManagerServiceServicer_to_server(
        controller_manager, main_server
    )

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, main_server)

    main_server.add_insecure_port(f"[::]:{main_port}")

    # Control server (mock control interface)
    control_server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    controller_manager_mock_pb2_grpc.add_MockControllerServiceServicer_to_server(
        control_service, control_server
    )
    control_server.add_insecure_port(f"[::]:{control_port}")

    logger.info("Starting Mock ControllerManager:")
    logger.info(f"  - Main gRPC server on port {main_port}")
    logger.info(f"  - Control gRPC server on port {control_port}")
    logger.info(f"  - Mock controllers: {num_controllers}")

    await main_server.start()
    await control_server.start()

    # Mark the ControllerManager service as SERVING
    await health_servicer.set(
        "controller_manager.ControllerManagerService", health_pb2.HealthCheckResponse.SERVING
    )
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # Overall health

    logger.info("Mock ControllerManager servers started")

    await main_server.wait_for_termination()


async def main():
    """Main entry point."""
    # Configure logging with environment variable support
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
    await serve()


if __name__ == "__main__":
    asyncio.run(main())
