#!/usr/bin/env python3
"""
PS Move Controller Pairing Daemon.

Polls for USB-connected PS Move controllers and pairs them automatically.
Monitors Bluetooth-connected controllers for signal strength and connection status.
Provides Prometheus metrics and OpenTelemetry tracing for observability.

Run as a systemd service on the host (not in Docker).

LED Feedback:
  - Yellow solid: Pairing in progress
  - White flash 3x: Success - unplug and press PS button
  - Red flash 3x: Error

Environment:
  POLL_INTERVAL - seconds between USB polls (default: 10)
  BT_MONITOR_INTERVAL - seconds between Bluetooth monitoring (default: 5)
  PSMOVE_PATH   - path to psmove binary (default: auto-detect)
  DEBUG         - set to 1 for verbose logging
  METRICS_PORT  - port for Prometheus metrics (default: 8002)
  OTEL_EXPORTER_OTLP_ENDPOINT - OTLP collector endpoint (default: http://localhost:4317)
"""

import asyncio
import logging

from prometheus_client import start_http_server
from psmove_pairing import PairingDaemon, find_psmove_binary, init_telemetry
from psmove_pairing.config import DEBUG, METRICS_PORT

# Logging setup
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("psmove-pairing")


def main() -> None:
    """Entry point."""
    # Start Prometheus metrics server
    logger.info(f"Starting metrics server on port {METRICS_PORT}")
    start_http_server(METRICS_PORT)

    # Initialize OpenTelemetry
    tracer = init_telemetry()

    # Find psmove binary
    psmove_path = find_psmove_binary()

    # Create and run daemon
    daemon = PairingDaemon(tracer, psmove_path)
    asyncio.run(daemon.run())


if __name__ == "__main__":
    main()
