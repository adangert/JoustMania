"""
Windows Backend for PS Move Controllers

Uses psmoveapi library for controller access on Windows.
Designed for development/debugging on Windows with WSL.
"""

import logging
from typing import Dict, List, Optional

from services.controller_manager.backend import ControllerBackend

# Import Windows-specific dependencies
try:
    import psmove

    PSMOVE_AVAILABLE = True
except ImportError:
    PSMOVE_AVAILABLE = False
    logging.warning("psmoveapi not available - install with: pip install psmoveapi")

logger = logging.getLogger(__name__)


class WindowsBackend(ControllerBackend):
    """
    Windows backend for PS Move controllers using psmoveapi.

    Designed for development on Windows/WSL:
    - Runs natively on Windows (not in Docker)
    - Controllers paired via Windows Bluetooth settings
    - Exposes gRPC service for WSL services to connect
    """

    def __init__(self):
        if not PSMOVE_AVAILABLE:
            raise RuntimeError(
                "psmoveapi not available. Install with: pip install psmoveapi\n"
                "See: https://github.com/thp/psmoveapi"
            )

        self.controllers: Dict[str, psmove.PSMove] = {}  # serial -> PSMove object
        self.move_indices: Dict[str, int] = {}  # serial -> psmove index
        self.running = False

        logger.info("WindowsBackend initialized")

    async def initialize(self) -> bool:
        """
        Initialize and discover controllers.

        Note: Controllers must already be paired via Windows Bluetooth settings.
        """
        try:
            count = psmove.count_connected()
            logger.info(f"Found {count} PS Move controllers on Windows")

            if count == 0:
                logger.warning(
                    "No controllers found. Pair controllers via Windows Bluetooth settings:\n"
                    "  Settings > Bluetooth & devices > Add device\n"
                    "  Hold PS+Move buttons until LED flashes rapidly"
                )
                return False

            # Connect to all controllers
            for i in range(count):
                move = psmove.PSMove(i)
                serial = move.get_serial()

                # Only track Bluetooth controllers (USB not needed for Windows dev)
                if move.connection_type == psmove.Conn_Bluetooth:
                    self.controllers[serial] = move
                    self.move_indices[serial] = i
                    battery = move.get_battery()
                    logger.info(f"Connected to controller {serial} (battery: {battery}/5)")

                    # Set initial LED color (dim white to indicate ready)
                    move.set_leds(50, 50, 50)
                    move.update_leds()

            if len(self.controllers) == 0:
                logger.warning("No Bluetooth controllers found (USB controllers are not tracked)")
                return False

            self.running = True
            logger.info(f"WindowsBackend ready with {len(self.controllers)} controller(s)")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Windows backend: {e}", exc_info=True)
            return False

    async def scan_controllers(self) -> List[Dict]:
        """
        Return already connected controllers.

        Note: Windows manages pairing, so this just returns connected controllers.
        """
        controllers = []

        for serial in self.controllers.keys():
            controllers.append(
                {"address": serial, "serial": serial, "name": f"PS Move {serial[-4:]}", "paired": True}
            )

        return controllers

    async def connect_controller(self, address: str) -> bool:
        """
        Verify controller is connected.

        Note: Windows manages pairing, cannot programmatically pair from Python.
        """
        if address in self.controllers:
            logger.info(f"Controller {address} already connected")
            return True

        logger.warning(f"Controller {address} not found. Pair via Windows Bluetooth settings.")
        return False

    async def disconnect_controller(self, serial: str) -> bool:
        """
        Remove controller from tracking.

        Note: Cannot force disconnect on Windows - controllers managed by OS.
        """
        if serial in self.controllers:
            # Turn off LED before removing
            try:
                move = self.controllers[serial]
                move.set_leds(0, 0, 0)
                move.update_leds()
                move.set_rumble(0)
            except Exception:
                pass

            del self.controllers[serial]
            del self.move_indices[serial]
            logger.info(f"Removed controller {serial} from tracking")
            return True

        return False

    async def get_controller_state(self, serial: str) -> Optional[Dict]:
        """Get current controller state."""
        move = self.controllers.get(serial)
        if not move:
            return None

        try:
            # Poll for new data
            while move.poll():
                pass

            # Read inputs
            trigger = move.get_trigger()
            buttons = move.get_buttons()

            # Parse button states
            move_button = bool(buttons & psmove.Btn_MOVE)
            trigger_button = bool(buttons & psmove.Btn_T)
            ps_button = bool(buttons & psmove.Btn_PS)
            select_button = bool(buttons & psmove.Btn_SELECT)
            start_button = bool(buttons & psmove.Btn_START)
            triangle = bool(buttons & psmove.Btn_TRIANGLE)
            circle = bool(buttons & psmove.Btn_CIRCLE)
            cross = bool(buttons & psmove.Btn_CROSS)
            square = bool(buttons & psmove.Btn_SQUARE)

            # Read accelerometer (raw values)
            ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)

            # Read gyroscope (raw values)
            gx, gy, gz = move.get_gyroscope_frame(psmove.Frame_SecondHalf)

            # Battery level (0-5)
            battery = move.get_battery()

            # Temperature (internal sensor)
            temperature = move.get_temperature()

            return {
                "serial": serial,
                "battery": battery,
                "trigger": trigger,
                "move_button": move_button,
                "trigger_button": trigger_button,
                "ps_button": ps_button,
                "select_button": select_button,
                "start_button": start_button,
                "triangle": triangle,
                "circle": circle,
                "cross": cross,
                "square": square,
                "accel": {"x": ax, "y": ay, "z": az},
                "gyro": {"x": gx, "y": gy, "z": gz},
                "temperature": temperature,
                "connection_type": "bluetooth",
            }

        except Exception as e:
            logger.error(f"Error reading controller state {serial}: {e}", exc_info=True)
            return None

    async def set_led_color(self, serial: str, r: int, g: int, b: int) -> bool:
        """Set LED color on controller."""
        move = self.controllers.get(serial)
        if not move:
            return False

        try:
            move.set_leds(r, g, b)
            move.update_leds()
            return True

        except Exception as e:
            logger.error(f"Error setting LED color {serial}: {e}", exc_info=True)
            return False

    async def set_rumble(self, serial: str, intensity: int) -> bool:
        """
        Set rumble intensity on controller.

        Args:
            serial: Controller serial
            intensity: Rumble intensity (0-255)
        """
        move = self.controllers.get(serial)
        if not move:
            return False

        try:
            move.set_rumble(intensity)
            return True

        except Exception as e:
            logger.error(f"Error setting rumble {serial}: {e}", exc_info=True)
            return False

    def get_connected_controllers(self) -> List[str]:
        """Get list of connected controller serials."""
        return list(self.controllers.keys())

    async def rescan(self) -> int:
        """
        Rescan for new controllers.

        Returns:
            Number of new controllers found
        """
        try:
            count = psmove.count_connected()
            new_controllers = 0

            for i in range(count):
                move = psmove.PSMove(i)
                serial = move.get_serial()

                # Add new Bluetooth controllers
                if serial not in self.controllers and move.connection_type == psmove.Conn_Bluetooth:
                    self.controllers[serial] = move
                    self.move_indices[serial] = i
                    logger.info(f"New controller connected: {serial}")

                    # Set initial LED
                    move.set_leds(50, 50, 50)
                    move.update_leds()
                    new_controllers += 1

            return new_controllers

        except Exception as e:
            logger.error(f"Error rescanning controllers: {e}", exc_info=True)
            return 0

    async def shutdown(self):
        """Cleanup and shutdown."""
        logger.info("Shutting down Windows backend")

        # Turn off all LEDs and rumble
        for serial, move in self.controllers.items():
            try:
                move.set_leds(0, 0, 0)
                move.update_leds()
                move.set_rumble(0)
                logger.debug(f"Turned off controller {serial}")
            except Exception as e:
                logger.error(f"Error turning off controller {serial}: {e}")

        self.controllers.clear()
        self.move_indices.clear()
        self.running = False
        logger.info("Windows backend shutdown complete")
