"""
Backend Factory for Controller Manager

Detects platform and creates appropriate backend instance.
"""

import logging
import os
import platform

from services.controller_manager.backend import ControllerBackend

logger = logging.getLogger(__name__)


def create_backend() -> ControllerBackend:
    """
    Create appropriate backend based on platform and environment.

    Environment variables:
        MOCK_CONTROLLERS: Set to 'true' to use mock backend
        MOCK_CONTROLLER_COUNT: Number of mock controllers (default: 4)
        CONTROLLER_BACKEND: Force specific backend ('bluetooth', 'windows', 'mock')

    Returns:
        ControllerBackend instance

    Raises:
        RuntimeError: If no suitable backend available
    """
    # Check for forced backend (useful for testing)
    forced_backend = os.getenv("CONTROLLER_BACKEND", "").lower()

    if forced_backend:
        logger.info(f"Using forced backend: {forced_backend}")

        if forced_backend == "mock":
            from services.controller_manager.mock_backend import MockBackend

            num_controllers = int(os.getenv("MOCK_CONTROLLER_COUNT", "4"))
            return MockBackend(num_controllers)

        if forced_backend == "bluetooth":
            from services.controller_manager.bluetooth_backend import BluetoothBackend

            return BluetoothBackend()

        if forced_backend == "windows":
            from services.controller_manager.windows_backend import WindowsBackend

            return WindowsBackend()

        raise RuntimeError(f"Unknown backend: {forced_backend}")

    # Check for mock mode (environment variable)
    if os.getenv("MOCK_CONTROLLERS", "").lower() == "true":
        from services.controller_manager.mock_backend import MockBackend

        num_controllers = int(os.getenv("MOCK_CONTROLLER_COUNT", "4"))
        logger.info(f"Using Mock backend (MOCK_CONTROLLERS=true) with {num_controllers} controllers")
        return MockBackend(num_controllers)

    # Platform detection
    system = platform.system()

    if system == "Windows":
        try:
            from services.controller_manager.windows_backend import WindowsBackend

            logger.info("Using Windows backend (psmoveapi)")
            return WindowsBackend()

        except ImportError as e:
            logger.error(f"Windows backend not available: {e}")
            logger.info("Install psmoveapi: pip install psmoveapi")
            logger.info("Or use mock mode: set MOCK_CONTROLLERS=true")
            raise RuntimeError("Windows backend not available") from e

    elif system == "Linux":
        try:
            from services.controller_manager.bluetooth_backend import BluetoothBackend

            logger.info("Using Linux BlueZ backend")
            return BluetoothBackend()

        except ImportError as e:
            logger.error(f"Bluetooth backend not available: {e}")
            logger.info("Install dependencies: apt-get install python3-dbus, pip install psmove")
            logger.info("Or use mock mode: set MOCK_CONTROLLERS=true")
            raise RuntimeError("Bluetooth backend not available") from e

    else:
        raise RuntimeError(f"Unsupported platform: {system}. Set CONTROLLER_BACKEND=mock to use mock controllers.")
