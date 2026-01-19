"""
Mock Backend for PS Move Controllers

Simulates controllers for testing without hardware.
Useful for CI/CD, development without controllers, and automated testing.
"""

import logging
import random
import time

from lib.controller_constants import (
    AxisKey,
    ButtonKey,
    StateKey,
)
from services.controller_manager.backend import ControllerBackend

logger = logging.getLogger(__name__)


class MockBackend(ControllerBackend):
    """
    Mock backend for testing without hardware.

    Simulates realistic controller behavior:
    - Random button presses
    - Motion sensor data
    - Battery drain
    - LED and rumble state tracking
    """

    def __init__(self, num_controllers: int = 4):
        """
        Initialize mock backend.

        Args:
            num_controllers: Number of mock controllers to create (default: 4)
        """
        self.num_controllers = num_controllers
        self.controllers: dict[str, dict] = {}
        self.running = False

        # Auto game end settings (set via MockControllerService.SetAutoGameEnd)
        self.auto_game_end_enabled = False
        self.auto_game_end_duration = 0.0
        self.auto_game_end_start_time: float | None = None
        self.auto_game_end_triggered = False

        logger.info(f"MockBackend initialized with {num_controllers} controllers")

    async def initialize(self) -> bool:
        """Initialize mock controllers."""
        try:
            for i in range(self.num_controllers):
                serial = f"mock_controller_{i}"  # Match old mock_server.py format

                self.controllers[serial] = {
                    StateKey.SERIAL: serial,
                    StateKey.BATTERY: 100,  # Full battery (percentage)
                    StateKey.TRIGGER: 0,
                    ButtonKey.MOVE: False,  # Start with Move not pressed
                    ButtonKey.TRIGGER: False,  # Start with trigger not pressed
                    ButtonKey.PS: False,
                    ButtonKey.SELECT: False,
                    ButtonKey.START: False,
                    ButtonKey.TRIANGLE: False,
                    ButtonKey.CIRCLE: False,
                    ButtonKey.CROSS: False,
                    ButtonKey.SQUARE: False,
                    StateKey.ACCEL: {AxisKey.X: 0.0, AxisKey.Y: 0.0, AxisKey.Z: 1.0},  # At rest (1g downward)
                    StateKey.GYRO: {AxisKey.X: 0.0, AxisKey.Y: 0.0, AxisKey.Z: 0.0},
                    StateKey.TEMPERATURE: 25,
                    "led": {"r": 255, "g": 255, "b": 255},
                    "rumble": 0,
                    "connected_at": time.time(),
                    "last_update": time.time(),
                    # Death simulation state (holds high accel until timestamp)
                    "death_accel": None,  # {"x": ..., "y": ..., "z": ...} or None
                    "death_hold_until": 0.0,  # Timestamp until which to hold death accel
                }

                logger.info(f"Created mock controller: {serial}")

            self.running = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize mock backend: {e}", exc_info=True)
            return False

    async def scan_controllers(self) -> list[dict]:
        """Return all mock controllers."""
        return [
            {"address": serial, "serial": serial, "name": f"Mock Controller {i + 1}", "paired": True}
            for i, serial in enumerate(self.controllers.keys())
        ]

    async def connect_controller(self, address: str) -> bool:
        """Mock connect - always succeeds if controller exists."""
        if address in self.controllers:
            logger.info(f"Mock: Connected to {address}")
            return True

        logger.warning(f"Mock: Controller {address} not found")
        return False

    async def disconnect_controller(self, serial: str) -> bool:
        """Mock disconnect - removes controller."""
        if serial in self.controllers:
            del self.controllers[serial]
            logger.info(f"Mock: Disconnected {serial}")
            return True

        return False

    async def get_controller_state(self, serial: str) -> dict | None:
        """
        Get mock controller state.

        Simulates realistic behavior:
        - Random button presses
        - Slight motion sensor noise
        - Battery drain over time
        """
        controller = self.controllers.get(serial)
        if not controller:
            return None

        current_time = time.time()
        time_since_update = current_time - controller["last_update"]

        # NOTE: Random button presses and trigger movement removed for predictable testing.
        # Buttons and triggers are now only changed via SimulateButton RPC.
        _ = time_since_update  # Silence unused variable warning

        # Check if we're holding death acceleration
        death_accel = None
        if controller["death_hold_until"] > current_time and controller["death_accel"]:
            # Use death acceleration (don't add noise)
            death_accel = controller["death_accel"]
        else:
            # Clear expired death hold
            if controller["death_hold_until"] > 0 and controller["death_hold_until"] <= current_time:
                controller["death_accel"] = None
                controller["death_hold_until"] = 0.0

            # Add slight noise to accelerometer (simulates hand shake)
            controller[StateKey.ACCEL][AxisKey.X] = random.gauss(0.0, 0.1)
            controller[StateKey.ACCEL][AxisKey.Y] = random.gauss(0.0, 0.1)
            controller[StateKey.ACCEL][AxisKey.Z] = random.gauss(1.0, 0.1)  # ~1g gravity

        # Add slight noise to gyroscope
        controller[StateKey.GYRO][AxisKey.X] = random.gauss(0.0, 0.5)
        controller[StateKey.GYRO][AxisKey.Y] = random.gauss(0.0, 0.5)
        controller[StateKey.GYRO][AxisKey.Z] = random.gauss(0.0, 0.5)

        # Simulate battery drain (20% per hour of use, ~5 hour battery life)
        time_since_connected = current_time - controller["connected_at"]
        hours_used = time_since_connected / 3600
        controller[StateKey.BATTERY] = max(0, 100 - int(hours_used * 20))

        # Update timestamp
        controller["last_update"] = current_time

        # Return state (use death_accel if holding, otherwise normal accel)
        return {
            StateKey.SERIAL: serial,
            StateKey.BATTERY: controller[StateKey.BATTERY],
            StateKey.TRIGGER: controller[StateKey.TRIGGER],
            ButtonKey.MOVE: controller[ButtonKey.MOVE],
            ButtonKey.TRIGGER: controller[ButtonKey.TRIGGER],
            ButtonKey.PS: controller[ButtonKey.PS],
            ButtonKey.SELECT: controller[ButtonKey.SELECT],
            ButtonKey.START: controller[ButtonKey.START],
            ButtonKey.TRIANGLE: controller[ButtonKey.TRIANGLE],
            ButtonKey.CIRCLE: controller[ButtonKey.CIRCLE],
            ButtonKey.CROSS: controller[ButtonKey.CROSS],
            ButtonKey.SQUARE: controller[ButtonKey.SQUARE],
            StateKey.ACCEL: death_accel.copy() if death_accel else controller[StateKey.ACCEL].copy(),
            StateKey.GYRO: controller[StateKey.GYRO].copy(),
            StateKey.TEMPERATURE: controller[StateKey.TEMPERATURE],
            "connection_type": "mock",
        }

    async def set_led_color(self, serial: str, r: int, g: int, b: int) -> bool:
        """Set LED color (tracked but not displayed)."""
        controller = self.controllers.get(serial)
        if not controller:
            return False

        controller["led"] = {"r": r, "g": g, "b": b}
        logger.debug(f"Mock: Set LED {serial} to RGB({r},{g},{b})")
        return True

    async def set_rumble(self, serial: str, intensity: int) -> bool:
        """Set rumble (tracked but not felt)."""
        controller = self.controllers.get(serial)
        if not controller:
            return False

        controller["rumble"] = intensity
        logger.debug(f"Mock: Set rumble {serial} to {intensity}")
        return True

    def get_connected_controllers(self, _force_rescan: bool = False) -> list[str]:
        """Get list of mock controller serials.

        Args:
            _force_rescan: Ignored for mock backend (no caching).
        """
        return list(self.controllers.keys())

    def update_all_leds(self) -> int:
        """Update LEDs for all controllers (Phase 72: no-op for mock)."""
        # Mock backend doesn't need LED refresh - just return 0
        return 0

    async def add_controller(self, serial: str | None = None) -> str:
        """
        Add a new mock controller dynamically.

        Args:
            serial: Optional serial number (auto-generated if not provided)

        Returns:
            Serial number of added controller
        """
        if serial is None:
            # Generate new serial
            serial = f"MOCK{len(self.controllers):04d}"

        if serial in self.controllers:
            logger.warning(f"Mock: Controller {serial} already exists")
            return serial

        # Create new mock controller
        self.controllers[serial] = {
            StateKey.SERIAL: serial,
            StateKey.BATTERY: 100,  # Full battery (percentage)
            StateKey.TRIGGER: 0,
            ButtonKey.MOVE: False,
            ButtonKey.TRIGGER: False,
            StateKey.ACCEL: {AxisKey.X: 0.0, AxisKey.Y: 0.0, AxisKey.Z: 1.0},
            StateKey.GYRO: {AxisKey.X: 0.0, AxisKey.Y: 0.0, AxisKey.Z: 0.0},
            StateKey.TEMPERATURE: 25,
            "led": {"r": 255, "g": 255, "b": 255},
            "rumble": 0,
            "connected_at": time.time(),
            "last_update": time.time(),
        }

        logger.info(f"Mock: Added controller {serial}")
        return serial

    async def remove_controller(self, serial: str) -> bool:
        """Remove a mock controller."""
        return await self.disconnect_controller(serial)

    async def shutdown(self):
        """Cleanup mock backend."""
        logger.info("Shutting down mock backend")
        self.controllers.clear()
        self.running = False
        logger.info("Mock backend shutdown complete")
