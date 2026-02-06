"""Configuration and constants for PS Move pairing daemon."""

import glob
import os
import sys

# Configuration from environment
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
BT_MONITOR_INTERVAL = int(os.getenv("BT_MONITOR_INTERVAL", "5"))
DEBUG = os.getenv("DEBUG", "0") == "1"
METRICS_PORT = int(os.getenv("METRICS_PORT", "8002"))
PSMOVE_PATH = os.getenv("PSMOVE_PATH", "")
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")


def _find_psmove_bindings() -> str | None:
    """Find psmove Python bindings in common locations.

    The bindings can be installed via:
    - install_psmoveapi.sh (extracts from Docker to venv site-packages)
    - Manual psmoveapi build (~/psmoveapi/build)
    - System-wide installation

    Returns:
        Path to add to sys.path, or None if psmove is already importable
    """
    # First check if psmove is already importable
    try:
        import psmove  # noqa: F401

        return None  # Already available, no path modification needed
    except ImportError:
        pass

    # Check environment variable first
    env_path = os.getenv("PSMOVEAPI_BUILD_PATH")
    if env_path and os.path.isdir(env_path):
        if os.path.exists(os.path.join(env_path, "psmove.py")):
            return env_path

    # Common installation locations
    home = os.path.expanduser("~")
    candidates = [
        # Pairing daemon's own venv (installed by install_psmoveapi.sh)
        "/opt/joustmania/scripts/pairing-daemon/venv/lib/python*/site-packages",
        # Main JoustMania venv (installed by install_psmoveapi.sh)
        f"{home}/JoustMania/venv/lib/python*/site-packages",
        "/home/joustmania/JoustMania/venv/lib/python*/site-packages",
        # Manual psmoveapi build
        f"{home}/psmoveapi/build",
        "/home/joustmania/psmoveapi/build",
    ]

    for pattern in candidates:
        for path in glob.glob(pattern):
            if os.path.exists(os.path.join(path, "psmove.py")):
                return path

    return None


# Set up psmove import path
_psmove_path = _find_psmove_bindings()
if _psmove_path and _psmove_path not in sys.path:
    sys.path.insert(0, _psmove_path)

# PS Move USB Vendor/Product IDs
PSMOVE_USB_IDS = ["054c:03d5", "054c:042f"]  # Motion Controller variants
PSMOVE_NAV_ID = "054c:03d4"  # Navigation Controller

# PS Move Bluetooth MAC prefix (Sony)
PSMOVE_BT_PREFIX = "00:06:F7"
