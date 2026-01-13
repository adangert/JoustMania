"""
Mock Controller Control Service for integration testing.

Provides control RPCs for simulating controller behavior during tests.
Only active when using MockBackend (Phase 57).
"""

import logging
from typing import Optional

from proto import controller_manager_mock_pb2, controller_manager_mock_pb2_grpc

logger = logging.getLogger(__name__)


class MockControllerService(controller_manager_mock_pb2_grpc.MockControllerServiceServicer):
    """Service for controlling mock controllers during integration tests."""

    def __init__(self, backend):
        """
        Initialize mock control service.

        Args:
            backend: MockBackend instance to control
        """
        self.backend = backend
        logger.info("MockControllerService initialized")

    def SimulateMovement(self, request, context):
        """Simulate controller movement by setting acceleration values."""
        try:
            serial = request.serial
            if serial not in self.backend.controllers:
                return controller_manager_mock_pb2.MovementResponse(
                    success=False, error=f"Controller {serial} not found"
                )

            # Update acceleration
            self.backend.controllers[serial]["accel"] = {
                "x": request.accel_x,
                "y": request.accel_y,
                "z": request.accel_z,
            }

            logger.info(
                f"Mock: Set acceleration for {serial}: ({request.accel_x:.2f}, {request.accel_y:.2f}, {request.accel_z:.2f})"
            )
            return controller_manager_mock_pb2.MovementResponse(success=True, error="")

        except Exception as e:
            logger.error(f"SimulateMovement error: {e}")
            return controller_manager_mock_pb2.MovementResponse(success=False, error=str(e))

    def SimulateDeath(self, request, context):
        """Simulate death by setting high acceleration."""
        try:
            serial = request.serial
            if serial not in self.backend.controllers:
                return controller_manager_mock_pb2.DeathResponse(success=False, accel_magnitude=0.0)

            # Set very high acceleration (death threshold is typically 4g)
            death_accel = 10.0  # 10g acceleration
            self.backend.controllers[serial]["accel"] = {"x": 0.0, "y": death_accel, "z": 0.0}

            logger.info(f"Mock: Simulated death for {serial} with {death_accel}g acceleration")
            return controller_manager_mock_pb2.DeathResponse(success=True, accel_magnitude=death_accel)

        except Exception as e:
            logger.error(f"SimulateDeath error: {e}")
            return controller_manager_mock_pb2.DeathResponse(success=False, accel_magnitude=0.0)

    def SimulateButton(self, request, context):
        """Simulate button press."""
        try:
            serial = request.serial
            if serial not in self.backend.controllers:
                return controller_manager_mock_pb2.ButtonResponse(
                    success=False, error=f"Controller {serial} not found"
                )

            # Map proto button enum to backend state keys
            button_map = {
                controller_manager_mock_pb2.ButtonRequest.TRIGGER: "trigger_button",
                controller_manager_mock_pb2.ButtonRequest.MOVE: "move_button",
                controller_manager_mock_pb2.ButtonRequest.SELECT: "select_button",
                controller_manager_mock_pb2.ButtonRequest.START: "start_button",
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

    def SetColor(self, request, context):
        """Set controller LED color."""
        try:
            serial = request.serial
            if serial not in self.backend.controllers:
                return controller_manager_mock_pb2.ColorResponse(
                    success=False, error=f"Controller {serial} not found"
                )

            self.backend.controllers[serial]["led"] = {"r": request.r, "g": request.g, "b": request.b}

            logger.info(f"Mock: Set LED for {serial} to RGB({request.r}, {request.g}, {request.b})")
            return controller_manager_mock_pb2.ColorResponse(success=True, error="")

        except Exception as e:
            logger.error(f"SetColor error: {e}")
            return controller_manager_mock_pb2.ColorResponse(success=False, error=str(e))

    def ResetController(self, request, context):
        """Reset controller to idle state."""
        try:
            serial = request.serial
            if serial not in self.backend.controllers:
                return controller_manager_mock_pb2.ResetResponse(
                    success=False, error=f"Controller {serial} not found"
                )

            # Reset to idle
            controller = self.backend.controllers[serial]
            controller["move_button"] = True  # Keep ready for tests
            controller["trigger_button"] = False
            controller["ps_button"] = False
            controller["select_button"] = False
            controller["start_button"] = False
            controller["triangle"] = False
            controller["circle"] = False
            controller["cross"] = False
            controller["square"] = False
            controller["accel"] = {"x": 0.0, "y": 0.0, "z": 1.0}  # At rest
            controller["gyro"] = {"x": 0.0, "y": 0.0, "z": 0.0}

            logger.info(f"Mock: Reset {serial} to idle state")
            return controller_manager_mock_pb2.ResetResponse(success=True, error="")

        except Exception as e:
            logger.error(f"ResetController error: {e}")
            return controller_manager_mock_pb2.ResetResponse(success=False, error=str(e))

    def ListMockControllers(self, request, context):
        """List all mock controller serials."""
        try:
            serials = list(self.backend.controllers.keys())
            return controller_manager_mock_pb2.ListResponse(serials=serials, count=len(serials))

        except Exception as e:
            logger.error(f"ListMockControllers error: {e}")
            return controller_manager_mock_pb2.ListResponse(serials=[], count=0)

    def SetAutoGameEnd(self, request, context):
        """
        Enable/disable auto game end feature.

        When enabled, automatically sets high acceleration on all but one player
        after the specified duration.
        """
        try:
            # Store settings in backend
            self.backend.auto_game_end_enabled = request.enabled
            self.backend.auto_game_end_duration = request.duration_seconds

            logger.info(
                f"Mock: Auto game end {'enabled' if request.enabled else 'disabled'} "
                f"(duration: {request.duration_seconds}s)"
            )
            return controller_manager_mock_pb2.AutoGameEndResponse(success=True, error="")

        except Exception as e:
            logger.error(f"SetAutoGameEnd error: {e}")
            return controller_manager_mock_pb2.AutoGameEndResponse(success=False, error=str(e))
