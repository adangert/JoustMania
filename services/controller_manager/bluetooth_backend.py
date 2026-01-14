"""
Linux/BlueZ Backend for PS Move Controllers

Uses psmove library + BlueZ/DBus for controller access on Raspberry Pi/Linux.
"""

import logging

from services.controller_manager.backend import ControllerBackend

# Import Linux-specific dependencies
try:
    import psmove

    from lib.controller_state import ControllerState
    from services.controller_manager import bluetooth
    from services.controller_manager.pairing import Pair as PairModule

    LINUX_DEPS_AVAILABLE = True
except ImportError:
    LINUX_DEPS_AVAILABLE = False
    logging.warning("Linux dependencies (psmove, dbus) not available")

logger = logging.getLogger(__name__)


class BluetoothBackend(ControllerBackend):
    """
    Linux BlueZ backend for PS Move controllers.

    Uses:
    - psmove library for controller I/O
    - BlueZ via DBus for Bluetooth operations
    - pair module for controller pairing
    """

    def __init__(self):
        if not LINUX_DEPS_AVAILABLE:
            raise RuntimeError("Linux dependencies not available. Install: psmove, dbus-python, controller_state, pair")

        self.controllers: dict[str, psmove.PSMove] = {}  # serial -> PSMove object
        self.controller_states: dict[str, ControllerState] = {}  # serial -> ControllerState
        self.paired_serials: list[str] = []
        self.hci = "hci0"  # Default Bluetooth adapter
        self.running = False

        logger.info("BluetoothBackend initialized")

    async def initialize(self) -> bool:
        """Initialize Bluetooth adapter and scan for controllers."""
        try:
            # Enable Bluetooth adapter
            bluetooth.enable_adapter(self.hci)
            logger.info(f"Enabled Bluetooth adapter: {self.hci}")

            # Scan for existing controllers
            count = psmove.count_connected()
            logger.info(f"Found {count} PS Move controllers")

            for move_num in range(count):
                move = psmove.PSMove(move_num)
                serial = move.get_serial()

                # Auto-pair USB controllers
                if move.connection_type == psmove.Conn_USB and serial not in self.paired_serials:
                    await self.connect_controller(serial)

                # Track all controllers
                self.controllers[serial] = move
                self.controller_states[serial] = ControllerState()
                logger.info(
                    f"Controller {serial}: " f"{'USB' if move.connection_type == psmove.Conn_USB else 'Bluetooth'}"
                )

            self.running = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Bluetooth backend: {e}", exc_info=True)
            return False

    async def scan_controllers(self) -> list[dict]:
        """Scan for available controllers."""
        controllers = []

        try:
            # Get all attached devices via BlueZ
            devices = bluetooth.get_attached_addresses(self.hci)

            for address in devices:
                # Check if it's a PS Move controller (MAC prefix 00:06:F7)
                if address.startswith("00:06:F7"):
                    controllers.append(
                        {"address": address, "serial": address.replace(":", ""), "name": "PS Move Controller"}
                    )

            # Also check currently connected via psmove
            count = psmove.count_connected()
            for move_num in range(count):
                move = psmove.PSMove(move_num)
                serial = move.get_serial()

                # Add if not already in list
                if not any(c["serial"] == serial for c in controllers):
                    controllers.append(
                        {
                            "address": serial,  # Use serial as address for connected controllers
                            "serial": serial,
                            "name": f"PS Move {serial[-4:]}",
                        }
                    )

        except Exception as e:
            logger.error(f"Error scanning controllers: {e}", exc_info=True)

        return controllers

    async def connect_controller(self, address: str) -> bool:
        """
        Connect/pair a controller.

        Note: For PS Move, pairing requires USB connection. The controller must be
        connected via USB first, then this method will pair it to Bluetooth.
        """
        try:
            # Find USB-connected controller to pair
            for i in range(psmove.count_connected()):
                move = psmove.PSMove(i)
                if move.connection_type == psmove.Conn_USB:
                    serial = move.get_serial()
                    if serial and (serial == address or serial.upper() == address.upper()):
                        # Use Pair class to pair the move controller
                        pair_helper = PairModule()
                        pair_helper.pair_move(move)
                        self.paired_serials.append(serial)
                        logger.info(f"Paired controller {serial} via USB")
                        return True

            logger.warning(f"Controller {address} not found connected via USB for pairing")
            return False

        except Exception as e:
            logger.error(f"Error connecting controller {address}: {e}", exc_info=True)
            return False

    async def disconnect_controller(self, serial: str) -> bool:
        """Disconnect a controller."""
        try:
            # Remove from tracking
            if serial in self.controllers:
                del self.controllers[serial]
            if serial in self.controller_states:
                del self.controller_states[serial]

            logger.info(f"Disconnected controller {serial}")
            return True

        except Exception as e:
            logger.error(f"Error disconnecting controller {serial}: {e}", exc_info=True)
            return False

    async def get_controller_state(self, serial: str) -> dict | None:
        """Get current controller state."""
        move = self.controllers.get(serial)
        if not move:
            return None

        try:
            # Poll for new data
            while move.poll():
                pass

            # Get controller state
            state = self.controller_states.get(serial)
            if not state:
                return None

            # Read inputs
            trigger = move.get_trigger()
            buttons = move.get_buttons()

            # Read motion sensors
            ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
            gx, gy, gz = move.get_gyroscope_frame(psmove.Frame_SecondHalf)

            # Get battery
            battery = move.get_battery()

            # Build state dict with all button states
            return {
                "serial": serial,
                "battery": battery,
                "trigger": trigger,
                "move_button": bool(buttons & psmove.Btn_MOVE),
                "trigger_button": bool(buttons & psmove.Btn_T),
                "ps_button": bool(buttons & psmove.Btn_PS),
                "cross": bool(buttons & psmove.Btn_CROSS),
                "circle": bool(buttons & psmove.Btn_CIRCLE),
                "square": bool(buttons & psmove.Btn_SQUARE),
                "triangle": bool(buttons & psmove.Btn_TRIANGLE),
                "select_button": bool(buttons & psmove.Btn_SELECT),
                "start_button": bool(buttons & psmove.Btn_START),
                "accel": {"x": ax, "y": ay, "z": az},
                "gyro": {"x": gx, "y": gy, "z": gz},
                "temperature": move.get_temperature(),
                "connection_type": move.connection_type,
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
        """Set rumble intensity on controller."""
        move = self.controllers.get(serial)
        if not move:
            return False

        try:
            move.set_rumble(intensity)
            return True

        except Exception as e:
            logger.error(f"Error setting rumble {serial}: {e}", exc_info=True)
            return False

    def get_connected_controllers(self) -> list[str]:
        """Get list of connected controller serials."""
        return list(self.controllers.keys())

    async def get_rssi(self, serial: str) -> int | None:
        """
        Get RSSI (signal strength) for a controller.

        Returns:
            RSSI in dBm (-100 to 0), or None if not available
        """
        try:
            # Get Bluetooth address for serial
            move = self.controllers.get(serial)
            if not move or move.connection_type == psmove.Conn_USB:
                return None  # USB controllers have no RSSI

            # Try to get device address (this may require additional tracking)
            # For now, we'll attempt to read via BlueZ
            devices = bluetooth.get_attached_addresses(self.hci)
            for address in devices:
                if address.replace(":", "") == serial:
                    return bluetooth.get_device_rssi(self.hci, address)

            return None

        except Exception:
            return None

    async def shutdown(self):
        """Cleanup and shutdown."""
        logger.info("Shutting down Bluetooth backend")

        # Turn off all LEDs
        for _serial, move in self.controllers.items():
            try:
                move.set_leds(0, 0, 0)
                move.update_leds()
                move.set_rumble(0)
            except Exception:
                pass

        self.controllers.clear()
        self.controller_states.clear()
        self.running = False
        logger.info("Bluetooth backend shutdown complete")
