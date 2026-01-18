#!/usr/bin/env python3
"""
PS Move Controller Pairing Daemon.

Polls for USB-connected PS Move controllers and pairs them automatically.
Provides Prometheus metrics and OpenTelemetry tracing for observability.

Run as a systemd service on the host (not in Docker).

LED Feedback:
  - Yellow solid: Pairing in progress
  - White flash 3x: Success - unplug and press PS button
  - Red flash 3x: Error

Environment:
  POLL_INTERVAL - seconds between polls (default: 10)
  PSMOVE_PATH   - path to psmove binary (default: auto-detect)
  DEBUG         - set to 1 for verbose logging
  METRICS_PORT  - port for Prometheus metrics (default: 8002)
  OTEL_EXPORTER_OTLP_ENDPOINT - OTLP collector endpoint (default: http://localhost:4317)
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import time

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Configuration
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
DEBUG = os.getenv("DEBUG", "0") == "1"
METRICS_PORT = int(os.getenv("METRICS_PORT", "8002"))
PSMOVE_PATH = os.getenv("PSMOVE_PATH", "")

# PS Move USB Vendor/Product IDs
PSMOVE_USB_IDS = ["054c:03d5", "054c:042f"]  # Motion Controller variants
PSMOVE_NAV_ID = "054c:03d4"  # Navigation Controller

# Logging setup
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("psmove-pairing")

# Prometheus metrics
pairing_attempts_total = Counter(
    "psmove_pairing_attempts_total",
    "Total pairing attempts",
)
pairing_success_total = Counter(
    "psmove_pairing_success_total",
    "Successful pairings",
)
pairing_failed_total = Counter(
    "psmove_pairing_failed_total",
    "Failed pairings",
)
pairing_polls_total = Counter(
    "psmove_pairing_polls_total",
    "Total polling cycles",
)
pairing_usb_controllers = Gauge(
    "psmove_pairing_usb_controllers",
    "Currently connected USB controllers",
)
pairing_duration_seconds = Histogram(
    "psmove_pairing_duration_seconds",
    "Time to complete pairing",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)
calibration_duration_seconds = Histogram(
    "psmove_pairing_calibration_duration_seconds",
    "Time to calibrate controller",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)


def init_telemetry() -> trace.Tracer:
    """Initialize OpenTelemetry with OTLP exporter."""
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    service_name = "psmove-pairing"

    resource = Resource(
        attributes={
            SERVICE_NAME: service_name,
            SERVICE_VERSION: "1.0.0",
            "service.namespace": "joustmania",
        }
    )

    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    logger.info(f"OpenTelemetry initialized: {service_name} -> {otlp_endpoint}")
    return trace.get_tracer(service_name)


def find_psmove_binary() -> str:
    """Find the psmove binary, checking various locations."""
    if PSMOVE_PATH and os.path.isfile(PSMOVE_PATH):
        return PSMOVE_PATH

    # Check if it's in PATH
    psmove_in_path = shutil.which("psmove")
    if psmove_in_path:
        return psmove_in_path

    # Common installation locations
    home = os.path.expanduser("~")
    candidates = [
        f"{home}/psmoveapi/build/psmove",
        "/home/joustmania/psmoveapi/build/psmove",
        "/usr/local/bin/psmove",
    ]

    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    logger.error("psmove binary not found. Install psmoveapi or set PSMOVE_PATH")
    sys.exit(1)


class PairingDaemon:
    """PS Move controller pairing daemon."""

    def __init__(self, tracer: trace.Tracer, psmove_path: str):
        self.tracer = tracer
        self.psmove = psmove_path
        self.poll_count = 0
        logger.info(f"PairingDaemon initialized with psmove: {self.psmove}")

    def run_command(self, cmd: list[str], capture_stderr: bool = True) -> tuple[int, str]:
        """Run a subprocess command and return exit code and output."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout
            if capture_stderr:
                output += result.stderr
            return result.returncode, output.strip()
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {' '.join(cmd)}")
            return -1, "timeout"
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return -1, str(e)

    def check_usb_controllers(self) -> bool:
        """Check if any PS Move controller is connected via USB."""
        exit_code, output = self.run_command(["lsusb"])
        if exit_code != 0:
            logger.debug("lsusb failed")
            return False

        return any(usb_id in output.lower() for usb_id in PSMOVE_USB_IDS)

    def get_usb_controllers(self) -> list[str]:
        """Get list of USB-connected controller serial numbers."""
        if DEBUG:
            exit_code, output = self.run_command([self.psmove, "list"])
        else:
            exit_code, output = self.run_command([self.psmove, "list"], capture_stderr=False)

        if exit_code != 0:
            logger.debug(f"psmove list failed with exit code {exit_code}")
            return []

        logger.debug(f"psmove list output: {output}")

        # Count USB controllers
        usb_lines = [line for line in output.split("\n") if "usb" in line.lower()]
        usb_count = len(usb_lines)
        logger.debug(f"USB controllers detected: {usb_count}")
        pairing_usb_controllers.set(usb_count)

        if usb_count == 0:
            return []

        # Extract MAC addresses from USB controller lines
        # Format: "Controller 0: aa:bb:cc:dd:ee:ff (USB)"
        mac_pattern = re.compile(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")
        serials = []
        for line in usb_lines:
            match = mac_pattern.search(line)
            if match:
                serials.append(match.group(0).upper())

        return serials

    def is_controller_known(self, serial: str) -> bool:
        """Check if controller is already known to BlueZ."""
        serial_upper = serial.upper()
        serial_nocolons = serial_upper.replace(":", "")

        # Check paired, trusted, and connected devices
        for device_type in ["Paired", "Trusted", "Connected"]:
            exit_code, output = self.run_command(["bluetoothctl", "devices", device_type])
            if exit_code == 0 and (serial_upper in output.upper() or serial_nocolons in output.upper()):
                logger.debug(f"Controller {serial_upper} found in {device_type} devices")
                return True

        return False

    def is_controller_already_paired_psmove(self, serial: str) -> bool:
        """Check if psmove thinks the controller is already paired."""
        exit_code, output = self.run_command([self.psmove, "list"])
        if exit_code != 0:
            return False

        # Check if this controller shows Bluetooth mode (already paired)
        return any(serial.upper() in line.upper() and "bluetooth" in line.lower() for line in output.split("\n"))

    def pair_controller(self, serial: str) -> bool:
        """Pair a controller using psmove pair command."""
        logger.info(f"Pairing controller {serial}...")

        with self.tracer.start_as_current_span("pair_controller") as span:
            span.set_attribute("controller.serial", serial)
            start_time = time.time()

            exit_code, output = self.run_command([self.psmove, "pair"])
            duration = time.time() - start_time
            pairing_duration_seconds.observe(duration)

            logger.debug(f"Pair output: {output}")
            logger.debug(f"Pair exit code: {exit_code}")

            span.set_attribute("pair.exit_code", exit_code)
            span.set_attribute("pair.duration_seconds", duration)

            # Check for explicit failure indicators
            failure_words = ["error", "failed", "cannot", "unable", "permission denied", "not found"]
            success_words = ["already", "set", "paired", "master"]

            pair_failed = False
            output_lower = output.lower()
            for failure in failure_words:
                if failure in output_lower:
                    # Only fail if it's a real error, not just "already set" type messages
                    is_success_message = any(s in output_lower for s in success_words)
                    if not is_success_message:
                        pair_failed = True
                        break

            if pair_failed:
                span.set_status(Status(StatusCode.ERROR, "Pairing failed"))
                span.set_attribute("pair.output", output[:500])  # Truncate for span
                return False

            span.set_status(Status(StatusCode.OK))
            return True

    def trust_device(self, serial: str) -> bool:
        """Trust the device in BlueZ."""
        logger.debug(f"Trusting device in BlueZ: {serial}")

        with self.tracer.start_as_current_span("trust_device") as span:
            span.set_attribute("controller.serial", serial)

            exit_code, output = self.run_command(["bluetoothctl", "trust", serial.upper()])
            span.set_attribute("trust.exit_code", exit_code)

            if exit_code != 0:
                logger.warning(f"bluetoothctl trust failed: {output}")
                span.set_status(Status(StatusCode.ERROR, "Trust failed"))
                return False

            span.set_status(Status(StatusCode.OK))
            return True

    def calibrate_controller(self, serial: str) -> bool:
        """Calibrate the controller."""
        logger.info("Calibrating controller...")

        with self.tracer.start_as_current_span("calibrate_controller") as span:
            span.set_attribute("controller.serial", serial)
            start_time = time.time()

            exit_code, output = self.run_command([self.psmove, "calibrate"])
            duration = time.time() - start_time
            calibration_duration_seconds.observe(duration)

            logger.debug(f"Calibrate output: {output}")
            span.set_attribute("calibrate.exit_code", exit_code)
            span.set_attribute("calibrate.duration_seconds", duration)

            # Calibration failure is not critical
            if exit_code != 0:
                logger.warning(f"Calibration returned non-zero: {exit_code}")
                span.set_status(Status(StatusCode.ERROR, "Calibration returned non-zero"))
            else:
                span.set_status(Status(StatusCode.OK))

            return exit_code == 0

    def process_controller(self, serial: str) -> bool:
        """Process a single USB-connected controller."""
        with self.tracer.start_as_current_span("process_controller") as span:
            span.set_attribute("controller.serial", serial)

            # Check if already known
            if self.is_controller_known(serial):
                logger.debug(f"Controller {serial} already known to BlueZ, skipping")
                span.set_attribute("skipped", True)
                span.set_attribute("skip_reason", "known_to_bluez")
                return False

            # Check if psmove thinks it's paired
            if self.is_controller_already_paired_psmove(serial):
                logger.info(f"Controller {serial} already paired (shows Bluetooth mode), skipping")
                span.set_attribute("skipped", True)
                span.set_attribute("skip_reason", "already_paired_psmove")
                return False

            logger.info(f"Found unpaired USB controller: {serial}")
            span.set_attribute("skipped", False)
            pairing_attempts_total.inc()

            # Pair controller
            if not self.pair_controller(serial):
                logger.error(f"Failed to pair {serial}")
                pairing_failed_total.inc()
                span.set_status(Status(StatusCode.ERROR, "Pairing failed"))
                return False

            # Trust in BlueZ
            self.trust_device(serial)

            # Calibrate
            self.calibrate_controller(serial)

            logger.info(f"Controller ready: {serial} - unplug USB and press PS button to connect")
            pairing_success_total.inc()
            span.set_status(Status(StatusCode.OK))
            return True

    def poll(self) -> None:
        """Perform one polling cycle."""
        self.poll_count += 1
        pairing_polls_total.inc()
        logger.debug(f"Poll #{self.poll_count}")

        with self.tracer.start_as_current_span("poll_cycle") as span:
            span.set_attribute("poll.count", self.poll_count)

            # Quick USB check first
            if not self.check_usb_controllers():
                logger.debug("No USB PS Move detected, skipping psmove list")
                pairing_usb_controllers.set(0)
                span.set_attribute("usb_detected", False)
                return

            logger.debug("USB PS Move detected, checking with psmove...")
            span.set_attribute("usb_detected", True)

            # Get USB controllers
            controllers = self.get_usb_controllers()
            span.set_attribute("controllers.count", len(controllers))

            if not controllers:
                logger.debug("No USB controllers found")
                return

            # Process each controller
            for serial in controllers:
                self.process_controller(serial)

    def run(self) -> None:
        """Main daemon loop."""
        logger.info("PS Move Pairing Daemon started")
        logger.info(f"  psmove binary: {self.psmove}")
        logger.info(f"  poll interval: {POLL_INTERVAL}s")
        logger.info(f"  debug mode: {DEBUG}")
        logger.info(f"  metrics port: {METRICS_PORT}")

        # Verify psmove works
        exit_code, _ = self.run_command([self.psmove, "list"])
        if exit_code != 0:
            logger.warning("'psmove list' failed - check permissions/udev rules")

        while True:
            try:
                self.poll()
            except Exception as e:
                logger.error(f"Error during poll: {e}", exc_info=DEBUG)

            time.sleep(POLL_INTERVAL)


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
    daemon.run()


if __name__ == "__main__":
    main()
