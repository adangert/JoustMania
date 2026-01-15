"""
Mock Controller Control Service for integration testing.

Provides control RPCs for simulating controller behavior during tests.
Only active when using MockBackend (Phase 57).
"""

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

from lib.controller_constants import AxisKey, ButtonKey, StateKey
from proto import controller_manager_mock_pb2, controller_manager_mock_pb2_grpc

if TYPE_CHECKING:
    from services.controller_manager.mock_backend import MockBackend

logger = logging.getLogger(__name__)


class MockControllerService(controller_manager_mock_pb2_grpc.MockControllerServiceServicer):
    """Service for controlling mock controllers during integration tests."""

    def __init__(self, backend: "MockBackend"):
        """
        Initialize mock control service.

        Args:
            backend: MockBackend instance to control
        """
        self.backend = backend
        self.auto_end_task: asyncio.Task | None = None  # Background task for auto-ending games
        logger.info("MockControllerService initialized")

    def SimulateMovement(self, request, context):  # noqa: N802, ARG002
        """Simulate controller movement by setting acceleration values."""
        try:
            serial = request.serial
            if serial not in self.backend.controllers:
                return controller_manager_mock_pb2.MovementResponse(
                    success=False, error=f"Controller {serial} not found"
                )

            # Update acceleration
            self.backend.controllers[serial][StateKey.ACCEL] = {
                AxisKey.X: request.accel_x,
                AxisKey.Y: request.accel_y,
                AxisKey.Z: request.accel_z,
            }

            logger.info(
                f"Mock: Set accel for {serial}: "
                f"({request.accel_x:.2f}, {request.accel_y:.2f}, {request.accel_z:.2f})"
            )
            return controller_manager_mock_pb2.MovementResponse(success=True, error="")

        except Exception as e:
            logger.error(f"SimulateMovement error: {e}")
            return controller_manager_mock_pb2.MovementResponse(success=False, error=str(e))

    def SimulateDeath(self, request, context):  # noqa: N802, ARG002
        """Simulate death by setting high acceleration and holding it for 2 seconds."""
        try:
            serial = request.serial
            if serial not in self.backend.controllers:
                return controller_manager_mock_pb2.DeathResponse(success=False, accel_magnitude=0.0)

            # Set death-level acceleration (matches mock_server.py)
            death_accel = {AxisKey.X: 5.0, AxisKey.Y: 3.0, AxisKey.Z: 4.0}
            accel_mag = (5.0**2 + 3.0**2 + 4.0**2) ** 0.5  # ~7.07g

            # Hold death acceleration for 2 seconds to ensure game loop catches it
            self.backend.controllers[serial]["death_accel"] = death_accel
            self.backend.controllers[serial]["death_hold_until"] = time.time() + 2.0

            logger.info(f"Mock: Simulated death for {serial} with {accel_mag:.2f}g acceleration, holding for 2.0s")
            return controller_manager_mock_pb2.DeathResponse(success=True, accel_magnitude=accel_mag)

        except Exception as e:
            logger.error(f"SimulateDeath error: {e}")
            return controller_manager_mock_pb2.DeathResponse(success=False, accel_magnitude=0.0)

    def SimulateButton(self, request, context):  # noqa: N802, ARG002
        """Simulate button press."""
        try:
            serial = request.serial
            if serial not in self.backend.controllers:
                return controller_manager_mock_pb2.ButtonResponse(success=False, error=f"Controller {serial} not found")

            # Map proto button enum to backend state keys
            button_map = {
                controller_manager_mock_pb2.ButtonRequest.TRIGGER: ButtonKey.TRIGGER,
                controller_manager_mock_pb2.ButtonRequest.MOVE: ButtonKey.MOVE,
                controller_manager_mock_pb2.ButtonRequest.SELECT: ButtonKey.SELECT,
                controller_manager_mock_pb2.ButtonRequest.START: ButtonKey.START,
            }

            button_key = button_map.get(request.button)
            if button_key is None:
                return controller_manager_mock_pb2.ButtonResponse(
                    success=False, error=f"Unknown button: {request.button}"
                )

            # Set button state
            self.backend.controllers[serial][button_key] = request.pressed

            logger.info(f"Mock: Set {button_key} on {serial} to {request.pressed}")
            return controller_manager_mock_pb2.ButtonResponse(success=True, error="")

        except Exception as e:
            logger.error(f"SimulateButton error: {e}")
            return controller_manager_mock_pb2.ButtonResponse(success=False, error=str(e))

    def SetColor(self, request, context):  # noqa: N802, ARG002
        """Set controller LED color."""
        try:
            serial = request.serial
            if serial not in self.backend.controllers:
                return controller_manager_mock_pb2.ColorResponse(success=False, error=f"Controller {serial} not found")

            self.backend.controllers[serial]["led"] = {"r": request.r, "g": request.g, "b": request.b}

            logger.info(f"Mock: Set LED for {serial} to RGB({request.r}, {request.g}, {request.b})")
            return controller_manager_mock_pb2.ColorResponse(success=True, error="")

        except Exception as e:
            logger.error(f"SetColor error: {e}")
            return controller_manager_mock_pb2.ColorResponse(success=False, error=str(e))

    def ResetController(self, request, context):  # noqa: N802, ARG002
        """Reset controller to idle state."""
        try:
            serial = request.serial
            if serial not in self.backend.controllers:
                return controller_manager_mock_pb2.ResetResponse(success=False, error=f"Controller {serial} not found")

            # Reset to idle
            controller = self.backend.controllers[serial]
            controller[ButtonKey.MOVE] = True  # Keep ready for tests
            controller[ButtonKey.TRIGGER] = False
            controller[ButtonKey.PS] = False
            controller[ButtonKey.SELECT] = False
            controller[ButtonKey.START] = False
            controller[ButtonKey.TRIANGLE] = False
            controller[ButtonKey.CIRCLE] = False
            controller[ButtonKey.CROSS] = False
            controller[ButtonKey.SQUARE] = False
            controller[StateKey.ACCEL] = {AxisKey.X: 0.0, AxisKey.Y: 0.0, AxisKey.Z: 1.0}  # At rest
            controller[StateKey.GYRO] = {AxisKey.X: 0.0, AxisKey.Y: 0.0, AxisKey.Z: 0.0}
            # Clear death state
            controller["death_accel"] = None
            controller["death_hold_until"] = 0.0

            logger.info(f"Mock: Reset {serial} to idle state")
            return controller_manager_mock_pb2.ResetResponse(success=True, error="")

        except Exception as e:
            logger.error(f"ResetController error: {e}")
            return controller_manager_mock_pb2.ResetResponse(success=False, error=str(e))

    def ListMockControllers(self, request, context):  # noqa: N802, ARG002
        """List all mock controller serials."""
        try:
            serials = list(self.backend.controllers.keys())
            return controller_manager_mock_pb2.ListResponse(serials=serials, count=len(serials))

        except Exception as e:
            logger.error(f"ListMockControllers error: {e}")
            return controller_manager_mock_pb2.ListResponse(serials=[], count=0)

    async def SetAutoGameEnd(self, request, context):  # noqa: N802, ARG002
        """
        Enable/disable auto game end feature.

        When enabled, automatically sets high acceleration on all but one player
        after the specified duration.
        """
        try:
            # Cancel existing task if any
            if self.auto_end_task and not self.auto_end_task.done():
                self.auto_end_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.auto_end_task
                self.auto_end_task = None

            if request.enabled:
                # Start new background task
                self.auto_end_task = asyncio.create_task(self._auto_end_game(request.duration_seconds))
                logger.info(f"Mock: Auto game end enabled: will kill players after {request.duration_seconds}s")
                return controller_manager_mock_pb2.AutoGameEndResponse(success=True, error="")

            logger.info("Mock: Auto game end disabled")
            return controller_manager_mock_pb2.AutoGameEndResponse(success=True, error="")

        except Exception as e:
            logger.error(f"SetAutoGameEnd error: {e}")
            return controller_manager_mock_pb2.AutoGameEndResponse(success=False, error=str(e))

    async def _auto_end_game(self, duration: float):
        """Background task to auto-end game after duration."""
        try:
            logger.info(f"Mock: Waiting {duration}s before auto-ending game...")
            await asyncio.sleep(duration)

            # Kill all but one player (leave winner)
            serials = list(self.backend.controllers.keys())
            if len(serials) > 1:
                # Leave the last player alive (winner)
                players_to_kill = serials[:-1]
                logger.info(
                    f"Mock: Auto-ending game: killing {len(players_to_kill)} players, "
                    f"leaving {serials[-1]} alive as winner"
                )

                for serial in players_to_kill:
                    # Simulate death by directly setting controller state
                    controller = self.backend.controllers.get(serial)
                    if controller:
                        # Set death-level acceleration (same as SimulateDeath)
                        controller["death_accel"] = {"x": 5.0, "y": 3.0, "z": 4.0}
                        controller["death_hold_until"] = time.time() + 2.0
                        logger.info(f"Mock: Auto-killed player {serial}")
                    await asyncio.sleep(0.3)  # Stagger deaths for better trace visualization

            logger.info("Mock: Auto game end complete")

        except asyncio.CancelledError:
            logger.info("Mock: Auto game end cancelled")
            raise
        except Exception as e:
            logger.error(f"Mock: Error in auto game end: {e}", exc_info=True)
