"""USB controller pairing for PS Move controllers."""

import logging
import re
import time

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from .config import DEBUG, POLL_INTERVAL, PSMOVE_USB_IDS
from .metrics import (
    calibration_duration_seconds,
    pairing_attempts_total,
    pairing_duration_seconds,
    pairing_failed_total,
    pairing_polls_total,
    pairing_success_total,
    pairing_usb_controllers,
)
from .utils import run_command

logger = logging.getLogger("psmove-pairing")

# Span attribute constant (matches lib/telemetry.SpanAttr.CONTROLLER_SERIAL)
_ATTR_CONTROLLER_SERIAL = "controller.serial"


class USBPairing:
    """Handles USB-connected PS Move controller pairing."""

    def __init__(self, tracer: trace.Tracer, psmove_path: str):
        self.tracer = tracer
        self.psmove = psmove_path
        self.poll_count = 0

    async def check_usb_controllers(self) -> bool:
        """Check if any PS Move controller is connected via USB."""
        exit_code, output = await run_command(["lsusb"])
        if exit_code != 0:
            logger.debug("lsusb failed")
            return False

        return any(usb_id in output.lower() for usb_id in PSMOVE_USB_IDS)

    async def get_usb_controllers(self) -> list[str]:
        """Get list of USB-connected controller serial numbers."""
        if DEBUG:
            exit_code, output = await run_command([self.psmove, "list"])
        else:
            exit_code, output = await run_command([self.psmove, "list"], capture_stderr=False)

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

    async def is_controller_known(self, serial: str) -> bool:
        """Check if controller is already known to BlueZ."""
        serial_upper = serial.upper()
        serial_nocolons = serial_upper.replace(":", "")

        # Check paired, trusted, and connected devices
        for device_type in ["Paired", "Trusted", "Connected"]:
            exit_code, output = await run_command(["bluetoothctl", "devices", device_type])
            if exit_code == 0 and (serial_upper in output.upper() or serial_nocolons in output.upper()):
                logger.debug(f"Controller {serial_upper} found in {device_type} devices")
                return True

        return False

    async def is_controller_already_paired_psmove(self, serial: str) -> bool:
        """Check if psmove thinks the controller is already paired."""
        exit_code, output = await run_command([self.psmove, "list"])
        if exit_code != 0:
            return False

        # Check if this controller shows Bluetooth mode (already paired)
        return any(serial.upper() in line.upper() and "bluetooth" in line.lower() for line in output.split("\n"))

    async def pair_controller(self, serial: str) -> bool:
        """Pair a controller using psmove pair command."""
        logger.info(f"Pairing controller {serial}...")

        with self.tracer.start_as_current_span("pair_controller") as span:
            span.set_attribute(_ATTR_CONTROLLER_SERIAL, serial)
            start_time = time.time()

            exit_code, output = await run_command([self.psmove, "pair"])
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

    async def trust_device(self, serial: str) -> bool:
        """Trust the device in BlueZ."""
        logger.debug(f"Trusting device in BlueZ: {serial}")

        with self.tracer.start_as_current_span("trust_device") as span:
            span.set_attribute(_ATTR_CONTROLLER_SERIAL, serial)

            exit_code, output = await run_command(["bluetoothctl", "trust", serial.upper()])
            span.set_attribute("trust.exit_code", exit_code)

            if exit_code != 0:
                logger.warning(f"bluetoothctl trust failed: {output}")
                span.set_status(Status(StatusCode.ERROR, "Trust failed"))
                return False

            span.set_status(Status(StatusCode.OK))
            return True

    async def calibrate_controller(self, serial: str) -> bool:
        """Calibrate the controller."""
        logger.info("Calibrating controller...")

        with self.tracer.start_as_current_span("calibrate_controller") as span:
            span.set_attribute(_ATTR_CONTROLLER_SERIAL, serial)
            start_time = time.time()

            exit_code, output = await run_command([self.psmove, "calibrate"])
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

    async def process_controller(self, serial: str) -> bool:
        """Process a single USB-connected controller."""
        with self.tracer.start_as_current_span("process_controller") as span:
            span.set_attribute(_ATTR_CONTROLLER_SERIAL, serial)

            # Check if already known
            if await self.is_controller_known(serial):
                logger.debug(f"Controller {serial} already known to BlueZ, skipping")
                span.set_attribute("skipped", True)
                span.set_attribute("skip_reason", "known_to_bluez")
                return False

            # Check if psmove thinks it's paired
            if await self.is_controller_already_paired_psmove(serial):
                logger.info(f"Controller {serial} already paired (shows Bluetooth mode), skipping")
                span.set_attribute("skipped", True)
                span.set_attribute("skip_reason", "already_paired_psmove")
                return False

            logger.info(f"Found unpaired USB controller: {serial}")
            span.set_attribute("skipped", False)
            pairing_attempts_total.inc()

            # Pair controller
            if not await self.pair_controller(serial):
                logger.error(f"Failed to pair {serial}")
                pairing_failed_total.inc()
                span.set_status(Status(StatusCode.ERROR, "Pairing failed"))
                return False

            # Trust in BlueZ
            await self.trust_device(serial)

            # Calibrate
            await self.calibrate_controller(serial)

            logger.info(f"Controller ready: {serial} - unplug USB and press PS button to connect")
            pairing_success_total.inc()
            span.set_status(Status(StatusCode.OK))
            return True

    async def poll(self) -> None:
        """Perform one USB polling cycle."""
        self.poll_count += 1
        pairing_polls_total.inc()
        logger.debug(f"Poll #{self.poll_count}")

        with self.tracer.start_as_current_span("poll_cycle") as span:
            span.set_attribute("poll.count", self.poll_count)

            # Quick USB check first
            if not await self.check_usb_controllers():
                logger.debug("No USB PS Move detected, skipping psmove list")
                pairing_usb_controllers.set(0)
                span.set_attribute("usb_detected", False)
                return

            logger.debug("USB PS Move detected, checking with psmove...")
            span.set_attribute("usb_detected", True)

            # Get USB controllers
            controllers = await self.get_usb_controllers()
            span.set_attribute("controllers.count", len(controllers))

            if not controllers:
                logger.debug("No USB controllers found")
                return

            # Process each controller
            for serial in controllers:
                await self.process_controller(serial)

    async def run_loop(self) -> None:
        """USB polling loop."""
        import asyncio

        logger.info(f"Starting USB poll loop (interval: {POLL_INTERVAL}s)")
        while True:
            try:
                await self.poll()
            except Exception as e:
                logger.error(f"Error during USB poll: {e}", exc_info=DEBUG)
            await asyncio.sleep(POLL_INTERVAL)
