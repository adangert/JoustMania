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

Endpoints:
  GET /metrics  - Prometheus metrics
  GET /healthz  - Health check (200 if healthy, 503 if unhealthy)
"""

import asyncio
import json
import logging

from prometheus_client import REGISTRY, MetricsHandler

from psmove_pairing import PairingDaemon, find_psmove_binary, init_telemetry
from psmove_pairing.config import DEBUG, METRICS_PORT

# Global daemon reference for health checks
_daemon: PairingDaemon | None = None

# Logging setup
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("psmove-pairing")


class HealthHandler(MetricsHandler):
    """HTTP handler that adds /healthz endpoint to prometheus metrics."""

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/healthz" or self.path == "/healthz/":
            self._handle_healthz()
        elif self.path == "/health" or self.path == "/health/":
            # Alias for /healthz
            self._handle_healthz()
        else:
            # Delegate to prometheus metrics handler
            super().do_GET()

    def _handle_healthz(self):
        """Handle health check request."""
        global _daemon

        if _daemon is None:
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"healthy": False, "error": "daemon not started"}).encode())
            return

        status = _daemon.get_health_status()
        if status["healthy"]:
            self.send_response(200)
        else:
            self.send_response(503)

        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())


def start_http_server_with_health(port: int) -> None:
    """Start HTTP server with both metrics and health endpoints."""
    from http.server import HTTPServer
    from threading import Thread

    def handler(*args, **kwargs):
        return HealthHandler(*args, registry=REGISTRY, **kwargs)

    server = HTTPServer(("", port), handler)
    thread = Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()


def main() -> None:
    """Entry point."""
    global _daemon

    # Start HTTP server with metrics and health endpoints
    logger.info(f"Starting HTTP server on port {METRICS_PORT} (metrics + healthz)")
    start_http_server_with_health(METRICS_PORT)

    # Initialize OpenTelemetry
    tracer = init_telemetry()

    # Find psmove binary
    psmove_path = find_psmove_binary()

    # Create and run daemon
    _daemon = PairingDaemon(tracer, psmove_path)
    asyncio.run(_daemon.run())


if __name__ == "__main__":
    main()
