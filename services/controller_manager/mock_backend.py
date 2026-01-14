"""
Mock Backend for PS Move Controllers

Simulates controllers for testing without hardware.
Useful for CI/CD, development without controllers, and automated testing.
"""

import logging
import random
import time

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
                    "serial": serial,
                    "battery": 5,  # Full battery (0-5)
                    "trigger": 0,
                    "move_button": True,  # Start with Move pressed (ready for tests)
                    "trigger_button": False,
                    "ps_button": False,
                    "select_button": False,
                    "start_button": False,
                    "triangle": False,
                    "circle": False,
                    "cross": False,
                    "square": False,
                    "accel": {"x": 0.0, "y": 0.0, "z": 1.0},  # At rest (1g downward)
                    "gyro": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "temperature": 25,
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
            {"address": serial, "serial": serial, "name": f"Mock Controller {i+1}", "paired": True}
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

        # Simulate random button presses (10% chance per second)
        if random.random() < 0.1 * time_since_update:
            button = random.choice(
                ["move_button", "trigger_button", "triangle", "circle", "cross", "square"]
            )
            controller[button] = not controller[button]

        # Simulate trigger movement (occasionally)
        if random.random() < 0.05:
            controller["trigger"] = random.randint(0, 255)
        else:
            # Drift back to zero
            controller["trigger"] = max(0, controller["trigger"] - 10)

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
            controller["accel"]["x"] = random.gauss(0.0, 0.1)
            controller["accel"]["y"] = random.gauss(0.0, 0.1)
            controller["accel"]["z"] = random.gauss(1.0, 0.1)  # ~1g gravity

        # Add slight noise to gyroscope
        controller["gyro"]["x"] = random.gauss(0.0, 0.5)
        controller["gyro"]["y"] = random.gauss(0.0, 0.5)
        controller["gyro"]["z"] = random.gauss(0.0, 0.5)

        # Simulate battery drain (1 level per hour of use)
        time_since_connected = current_time - controller["connected_at"]
        hours_used = time_since_connected / 3600
        controller["battery"] = max(0, 5 - int(hours_used))

        # Update timestamp
        controller["last_update"] = current_time

        # Return state (use death_accel if holding, otherwise normal accel)
        return {
            "serial": serial,
            "battery": controller["battery"],
            "trigger": controller["trigger"],
            "move_button": controller["move_button"],
            "trigger_button": controller["trigger_button"],
            "ps_button": controller["ps_button"],
            "select_button": controller["select_button"],
            "start_button": controller["start_button"],
            "triangle": controller["triangle"],
            "circle": controller["circle"],
            "cross": controller["cross"],
            "square": controller["square"],
            "accel": death_accel.copy() if death_accel else controller["accel"].copy(),
            "gyro": controller["gyro"].copy(),
            "temperature": controller["temperature"],
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

    def get_connected_controllers(self) -> list[str]:
        """Get list of mock controller serials."""
        return list(self.controllers.keys())

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
            "serial": serial,
            "battery": 5,
            "trigger": 0,
            "move_button": False,
            "trigger_button": False,
            "accel": {"x": 0.0, "y": 0.0, "z": 1.0},
            "gyro": {"x": 0.0, "y": 0.0, "z": 0.0},
            "temperature": 25,
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
