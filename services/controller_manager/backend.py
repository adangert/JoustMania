"""
Abstract Controller Backend Interface

Defines the contract for controller backends (BlueZ, Windows, Mock).
Each backend implements this interface to provide platform-specific
controller access while maintaining a consistent API.
"""

from abc import ABC, abstractmethod


class ControllerBackend(ABC):
    """
    Abstract interface for controller backends.

    Implementations:
    - BluetoothBackend: Linux/BlueZ backend for Raspberry Pi
    - WindowsBackend: Windows backend using psmoveapi
    - MockBackend: Mock backend for testing without hardware
    """

    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the backend.

        This may include:
        - Connecting to Bluetooth adapter
        - Scanning for paired controllers
        - Setting up device connections

        Returns:
            bool: True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    async def scan_controllers(self) -> list[dict]:
        """
        Scan for available controllers.

        Returns:
            List of controller info dicts with keys:
            - address: Bluetooth MAC address
            - serial: Controller serial number
            - name: Device name
            - paired: Whether already paired (optional)
        """
        pass

    @abstractmethod
    async def connect_controller(self, address: str) -> bool:
        """
        Connect to a controller by address.

        Args:
            address: Bluetooth MAC address or serial number

        Returns:
            bool: True if connection successful
        """
        pass

    @abstractmethod
    async def disconnect_controller(self, serial: str) -> bool:
        """
        Disconnect a controller.

        Args:
            serial: Controller serial number

        Returns:
            bool: True if disconnection successful
        """
        pass

    @abstractmethod
    async def get_controller_state(self, serial: str) -> dict | None:
        """
        Get current state of a controller.

        Args:
            serial: Controller serial number

        Returns:
            Dict with controller state, or None if controller not found:
            {
                'serial': str,
                'battery': int (0-5),
                'trigger': int (0-255),
                'move_button': bool,
                'trigger_button': bool,
                'accel': {'x': float, 'y': float, 'z': float},
                'gyro': {'x': float, 'y': float, 'z': float},
                'temperature': int (optional),
                'ready': bool (optional, for game readiness),
                'team': int (optional, for team assignment),
            }
        """
        pass

    @abstractmethod
    async def set_led_color(self, serial: str, r: int, g: int, b: int) -> bool:
        """
        Set LED color on a controller.

        Args:
            serial: Controller serial number
            r: Red component (0-255)
            g: Green component (0-255)
            b: Blue component (0-255)

        Returns:
            bool: True if successful
        """
        pass

    @abstractmethod
    async def set_rumble(self, serial: str, intensity: int) -> bool:
        """
        Set rumble intensity on a controller.

        Args:
            serial: Controller serial number
            intensity: Rumble intensity (0-255)

        Returns:
            bool: True if successful
        """
        pass

    @abstractmethod
    def get_connected_controllers(self) -> list[str]:
        """
        Get list of connected controller serials.

        Returns:
            List of serial numbers (strings)
        """
        pass

    @abstractmethod
    async def shutdown(self):
        """
        Cleanup resources and shutdown backend.

        This should:
        - Turn off controller LEDs
        - Stop rumble
        - Close connections
        - Release hardware resources
        """
        pass

    async def get_rssi(self, serial: str) -> int | None:  # noqa: ARG002
        """
        Get RSSI (signal strength) for a Bluetooth controller.

        This is optional - only BluetoothBackend implements meaningful RSSI.
        Other backends return None by default.

        Args:
            serial: Controller serial number

        Returns:
            RSSI in dBm (-100 to 0), or None if not available/supported
        """
        return None

    def set_effect_active(self, serial: str, active: bool):  # noqa: ARG002
        """
        Mark controller as having an active LED effect.

        When active, polling should skip LED refresh to avoid overwriting
        effect animations. This is optional - backends that don't need
        this optimization can use the default no-op.

        Args:
            serial: Controller serial number
            active: True if effect is starting, False when effect ends
        """
        pass
