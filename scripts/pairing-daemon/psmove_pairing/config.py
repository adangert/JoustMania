"""Configuration and constants for PS Move pairing daemon."""

import os

# Configuration from environment
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
BT_MONITOR_INTERVAL = int(os.getenv("BT_MONITOR_INTERVAL", "5"))
DEBUG = os.getenv("DEBUG", "0") == "1"
METRICS_PORT = int(os.getenv("METRICS_PORT", "8002"))
PSMOVE_PATH = os.getenv("PSMOVE_PATH", "")
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

# PS Move USB Vendor/Product IDs
PSMOVE_USB_IDS = ["054c:03d5", "054c:042f"]  # Motion Controller variants
PSMOVE_NAV_ID = "054c:03d4"  # Navigation Controller

# PS Move Bluetooth MAC prefix (Sony)
PSMOVE_BT_PREFIX = "00:06:F7"
