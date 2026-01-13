"""
Mock ControllerManager gRPC Server for testing without hardware.

Provides:
- Same gRPC interface as real ControllerManager
- Additional control RPCs for simulation
- Configurable number of controllers
- Controllable controller states via gRPC
"""

import asyncio
import contextlib
import logging
import os
import time
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from proto import controller_manager_mock_pb2_grpc, controller_manager_pb2_grpc
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
from services.controller_manager.effects_base import ControllerEffectsBase

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
        self.death_accel = None  # Set by SimulateDeath to hold death acceleration
        self.death_hold_until = 0.0  # Timestamp until which to hold death acceleration

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
    controller_manager_pb2_grpc.ControllerManagerServiceServicer, ControllerEffectsBase
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
                current_time = time.time()
                # Get current states (apply death hold logic)
                controllers = []
                for controller in self.controllers.values():
                    # Use death_accel if we're still holding the death acceleration
                    if controller.death_hold_until > current_time and controller.death_accel:
                        # Temporarily override accel for this tick
                        original_accel = controller.accel
                        controller.accel = controller.death_accel
                        controllers.append(controller.to_proto())
                        controller.accel = original_accel
                    else:
                        controllers.append(controller.to_proto())
                        # Clear death hold if expired
                        if (
                            controller.death_hold_until > 0
                            and controller.death_hold_until <= current_time
                        ):
                            controller.death_accel = None
                            controller.death_hold_until = 0.0

                yield ControllerStateUpdate(
                    controllers=controllers, timestamp=int(time.time() * 1000)
                )

                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Controller state stream cancelled")
            raise

    async def StreamButtonEvents(self, request, context):
        """
        Stream button press/release events (Phase 41).

        For the mock, we don't simulate button presses, so this stream
        stays open but doesn't send events unless explicitly controlled.
        """
        logger.info("Starting button event stream (mock)")

        try:
            while not context.cancelled():
                # Mock implementation - no automatic button events
                # In real testing, button events could be triggered via control RPCs
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info("Button event stream cancelled")
            raise

    async def StreamGameplayData(self, request, context):
        """Stream gameplay data (acceleration/gyro only) at requested frequency (Phase 41)."""
        from proto.controller_manager_pb2 import GameplayData, GameplayDataUpdate

        frequency = request.update_frequency_hz or 60
        interval = 1.0 / frequency

        logger.info(f"Starting gameplay data stream at {frequency}Hz (mock)")

        try:
            while not context.cancelled():
                current_time = time.time()
                # Build gameplay data for all controllers (no buttons)
                gameplay_data = []
                for controller in self.controllers.values():
                    # Use death_accel if we're still holding the death acceleration
                    if controller.death_hold_until > current_time and controller.death_accel:
                        accel = controller.death_accel
                    else:
                        accel = controller.accel
                        # Clear death hold if expired
                        if (
                            controller.death_hold_until > 0
                            and controller.death_hold_until <= current_time
                        ):
                            controller.death_accel = None
                            controller.death_hold_until = 0.0
                            logger.debug(
                                f"Death hold expired for {controller.serial}, reverting to normal accel"
                            )

                    gd = GameplayData(
                        serial=controller.serial,
                        move_num=int(controller.serial.split("_")[-1]),
                        battery=controller.battery,
                        ready=controller.ready,
                        team=controller.team,
                        color=controller.color,
                        accel=accel,
                        gyro=controller.gyro,
                    )
                    gameplay_data.append(gd)

                yield GameplayDataUpdate(
                    controllers=gameplay_data, timestamp=int(time.time() * 1000)
                )

                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Gameplay data stream cancelled")
            raise

    async def StreamGameplayDataDynamic(self, request_iterator, context):
        """
        Stream gameplay data with dynamic filtering via bidirectional communication (Phase 45/46 - mock).

        This is the mock implementation that supports the same interface as the real controller manager.
        """
        from proto.controller_manager_pb2 import GameplayData, GameplayDataUpdate

        logger.info("Starting dynamic gameplay data stream (mock)")

        # Stream state (updated by client messages)
        current_hz = 30  # Default Hz
        current_filter = None  # None = all controllers
        config_received = asyncio.Event()  # Signal when initial config arrives

        # Background task to read client updates
        async def read_client_updates():
            nonlocal current_hz, current_filter

            try:
                logger.info("[mock] Background task: waiting for client messages...")
                async for control_msg in request_iterator:
                    logger.info(f"[mock] Received control message: {control_msg}")
                    if control_msg.HasField("config"):
                        # Initial configuration
                        current_hz = control_msg.config.update_frequency_hz
                        current_filter = (
                            set(control_msg.config.serials) if control_msg.config.serials else None
                        )
                        logger.info(
                            f"[mock] ✅ Stream configured: {current_hz}Hz, "
                            f"filter={len(current_filter) if current_filter else 'all'} controllers"
                        )
                        logger.info("[mock] Setting config_received event...")
                        config_received.set()  # Signal that config has been received
                        logger.info("[mock] config_received event set!")

                    elif control_msg.HasField("filter_update"):
                        # Mid-stream filter update
                        new_filter = (
                            set(control_msg.filter_update.serials)
                            if control_msg.filter_update.serials
                            else None
                        )
                        if new_filter != current_filter:
                            logger.info(
                                f"[mock] Filter updated: {len(current_filter or [])} → "
                                f"{len(new_filter or [])} controllers"
                            )
                            current_filter = new_filter

                    elif control_msg.HasField("color_command"):
                        # Process color command (Phase 46)
                        cmd = control_msg.color_command
                        target_serial = cmd.serial if cmd.serial else None
                        for serial in self.controllers:
                            if target_serial is None or serial == target_serial:
                                self._set_led_color(serial, (cmd.color.r, cmd.color.g, cmd.color.b))
                        logger.debug(f"[mock] Color command: serial={cmd.serial or 'all'}")

                    elif control_msg.HasField("combined_feedback"):
                        # Process combined color + vibration (Phase 46)
                        cmd = control_msg.combined_feedback
                        target_serial = cmd.serial if cmd.serial else None
                        for serial in self.controllers:
                            if target_serial is None or serial == target_serial:
                                self._set_led_color(serial, (cmd.color.r, cmd.color.g, cmd.color.b))
                        logger.debug(
                            f"[mock] Combined feedback: serial={cmd.serial or 'all'}, "
                            f"rgb=({cmd.color.r},{cmd.color.g},{cmd.color.b})"
                        )

            except Exception as e:
                logger.error(f"[mock] Error reading client updates: {e}", exc_info=True)

        # Start background task to read updates
        update_task = asyncio.create_task(read_client_updates())

        try:
            # Wait for initial config before starting to yield data
            logger.info("[mock] Main loop: Waiting for initial configuration...")
            try:
                await asyncio.wait_for(config_received.wait(), timeout=10.0)
                logger.info("[mock] ✅ Initial configuration received, starting data stream")
            except TimeoutError:
                logger.error("[mock] ❌ Timeout waiting for initial config (10s), aborting stream")
                return

            iteration = 0
            while not context.cancelled():
                if iteration == 0:
                    logger.info("[mock] Starting yield loop...")
                iteration += 1
                current_time = time.time()
                # Build gameplay data for filtered controllers
                gameplay_data = []

                for serial, controller in self.controllers.items():
                    # Apply filter if present (Phase 45)
                    if current_filter is not None and serial not in current_filter:
                        continue  # Skip filtered controller

                    # Use death_accel if we're still holding the death acceleration
                    if controller.death_hold_until > current_time and controller.death_accel:
                        accel = controller.death_accel
                    else:
                        accel = controller.accel
                        # Clear death hold if expired
                        if (
                            controller.death_hold_until > 0
                            and controller.death_hold_until <= current_time
                        ):
                            controller.death_accel = None
                            controller.death_hold_until = 0.0

                    gd = GameplayData(
                        serial=controller.serial,
                        move_num=int(controller.serial.split("_")[-1]),
                        battery=controller.battery,
                        ready=controller.ready,
                        team=controller.team,
                        color=controller.color,
                        accel=accel,
                        gyro=controller.gyro,
                    )
                    gameplay_data.append(gd)

                if iteration == 1:
                    logger.info(
                        f"[mock] ✅ Yielding first update with {len(gameplay_data)} controllers"
                    )

                yield GameplayDataUpdate(
                    controllers=gameplay_data, timestamp=int(time.time() * 1000)
                )

                if iteration % 30 == 0:  # Log every 30 iterations (~1 second at 30Hz)
                    logger.debug(f"[mock] Yielded update #{iteration}")

                await asyncio.sleep(1.0 / current_hz)

        except asyncio.CancelledError:
            logger.info("[mock] Dynamic gameplay data stream cancelled")
            raise
        finally:
            # Cleanup
            update_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await update_task

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
        target_serials = [request.serial] if request.serial else list(self.controllers.keys())

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

        target_serials = [request.serial] if request.serial else list(self.controllers.keys())

        logger.debug(
            f"SetControllerVibration: intensity={request.intensity}, targets={len(target_serials)}"
        )
        return SetControllerVibrationResponse(success=True, error="")

    async def PlayControllerEffect(self, request, context):
        """Play visual effect on controller(s) - Phase 31/40 implementation.

        Uses effect methods inherited from ControllerEffectsBase.
        """
        from proto import controller_manager_pb2

        # Determine target controllers
        target_serials = [request.serial] if request.serial else list(self.controllers.keys())

        color = (request.color.r, request.color.g, request.color.b)
        duration_ms = request.duration_ms
        speed = request.speed or 5

        for serial in target_serials:
            if serial not in self.controllers:
                continue

            # Cancel any existing effect
            if serial in self.active_effects:
                self.active_effects[serial].cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.active_effects[serial]
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
        self.auto_end_task = None  # Background task for auto-ending games

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
        """Simulate death by setting high acceleration and holding it for 2 seconds."""
        controller = self.manager.controllers.get(request.serial)

        if not controller:
            return DeathResponse(success=False, accel_magnitude=0.0)

        # Set death-level acceleration (>2.8 for FAST sensitivity)
        death_vector = Vector3(x=5.0, y=3.0, z=4.0)
        accel_mag = (5.0**2 + 3.0**2 + 4.0**2) ** 0.5

        # Hold death acceleration for 2 seconds to ensure game loop catches it
        # This accounts for potential timing between SimulateDeath call and game loop processing
        controller.death_accel = death_vector
        controller.death_hold_until = time.time() + 2.0

        logger.info(
            f"Simulated death for {request.serial}: magnitude={accel_mag:.2f}, holding for 2.0s"
        )

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

    async def SetAutoGameEnd(self, request, context):
        """Enable/disable automatic game ending after duration."""
        from proto.controller_manager_mock_pb2 import AutoGameEndResponse

        try:
            # Cancel existing task if any
            if self.auto_end_task and not self.auto_end_task.done():
                self.auto_end_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.auto_end_task
                self.auto_end_task = None

            if request.enabled:
                # Start new background task
                self.auto_end_task = asyncio.create_task(
                    self._auto_end_game(request.duration_seconds)
                )
                logger.info(
                    f"[mock] Auto game end enabled: will kill players after {request.duration_seconds}s"
                )
                return AutoGameEndResponse(success=True, error="")
            logger.info("[mock] Auto game end disabled")
            return AutoGameEndResponse(success=True, error="")

        except Exception as e:
            logger.error(f"[mock] Error setting auto game end: {e}", exc_info=True)
            return AutoGameEndResponse(success=False, error=str(e))

    async def _auto_end_game(self, duration: float):
        """Background task to auto-end game after duration."""
        try:
            logger.info(f"[mock] Waiting {duration}s before auto-ending game...")
            await asyncio.sleep(duration)

            # Kill all but one player (leave winner)
            serials = list(self.manager.controllers.keys())
            if len(serials) > 1:
                # Leave the last player alive (winner)
                players_to_kill = serials[:-1]
                logger.info(
                    f"[mock] Auto-ending game: killing {len(players_to_kill)} players, "
                    f"leaving {serials[-1]} alive as winner"
                )

                for serial in players_to_kill:
                    # Simulate death by directly setting controller state
                    controller = self.manager.controllers.get(serial)
                    if controller:
                        # Set death-level acceleration (same as SimulateDeath)
                        death_vector = Vector3(x=5.0, y=3.0, z=4.0)
                        controller.death_accel = death_vector
                        controller.death_hold_until = time.time() + 2.0
                        logger.info(f"[mock] Auto-killed player {serial}")
                    await asyncio.sleep(0.3)  # Stagger deaths for better trace visualization

            logger.info("[mock] Auto game end complete")

        except asyncio.CancelledError:
            logger.info("[mock] Auto game end cancelled")
            raise
        except Exception as e:
            logger.error(f"[mock] Error in auto game end: {e}", exc_info=True)


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
