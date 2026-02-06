"""USB controller pairing for PS Move controllers.

Uses the psmove Python bindings (like the original JoustMania) for reliable
adapter selection via pair_custom().
"""

import logging
import time

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

# Import config first to set up psmoveapi path
from .config import DEBUG, POLL_INTERVAL, PSMOVE_USB_IDS

# Now import psmove (path was set up by config)
try:
    import psmove
except ImportError as e:
    raise ImportError(
        "psmove module not found. Ensure PSMOVEAPI_BUILD_PATH is set correctly "
        "and psmoveapi is built with Python bindings."
    ) from e

from .adapter_manager import AdapterManager
from .metrics import (
    calibration_duration_seconds,
    pairing_adapter_device_count,
    pairing_adapter_selected_total,
    pairing_attempts_total,
    pairing_duration_seconds,
    pairing_failed_total,
    pairing_polls_total,
    pairing_success_total,
    pairing_usb_controllers,
)
from .utils import run_command

logger = logging.getLogger("psmove-pairing")

# Span attribute constants
_ATTR_CONTROLLER_SERIAL = "controller.serial"
_ATTR_ADAPTER_ADDRESS = "adapter.address"


class USBPairing:
    """Handles USB-connected PS Move controller pairing.

    Uses the psmove Python bindings with pair_custom() for reliable
    adapter selection, matching the original JoustMania approach.
    """

    def __init__(self, tracer: trace.Tracer, psmove_path: str):
        self.tracer = tracer
        self.psmove_cli = psmove_path  # Keep for calibration
        self.poll_count = 0
        self.adapter_manager = AdapterManager()

    async def check_usb_controllers(self) -> bool:
        """Check if any PS Move controller is connected via USB."""
        exit_code, output = await run_command(["lsusb"])
        if exit_code != 0:
            logger.debug("lsusb failed")
            return False

        return any(usb_id in output.lower() for usb_id in PSMOVE_USB_IDS)

    def get_usb_controllers_psmove(self) -> list[tuple[int, str]]:
        """Get list of USB-connected controllers using psmove library.

        Returns:
            List of tuples (index, serial) for USB-connected controllers
        """
        connected = psmove.count_connected()
        logger.debug(f"psmove.count_connected() = {connected}")
        pairing_usb_controllers.set(0)  # Will update below

        usb_controllers = []
        for i in range(connected):
            try:
                move = psmove.PSMove(i)
                if move.connection_type == psmove.Conn_USB:
                    serial = move.get_serial()
                    if serial:
                        usb_controllers.append((i, serial.upper()))
                        logger.debug(f"USB controller {i}: {serial}")
            except Exception as e:
                logger.debug(f"Error accessing controller {i}: {e}")

        pairing_usb_controllers.set(len(usb_controllers))
        return usb_controllers

    def pair_controller_psmove(self, move_index: int, serial: str, adapter_address: str) -> bool:
        """Pair a controller using psmove Python library's pair_custom().

        This directly specifies the target adapter, matching the original
        JoustMania's approach which is more reliable than environment variables.

        Args:
            move_index: Controller index from psmove.count_connected()
            serial: Controller MAC address
            adapter_address: Target Bluetooth adapter address

        Returns:
            True if pairing succeeded
        """
        logger.info(f"Pairing controller {serial} to adapter {adapter_address}...")

        with self.tracer.start_as_current_span("pair_controller") as span:
            span.set_attribute(_ATTR_CONTROLLER_SERIAL, serial)
            span.set_attribute(_ATTR_ADAPTER_ADDRESS, adapter_address)
            start_time = time.time()

            try:
                move = psmove.PSMove(move_index)
                if move.connection_type != psmove.Conn_USB:
                    logger.warning(f"Controller {serial} not connected via USB")
                    span.set_status(Status(StatusCode.ERROR, "Not USB connected"))
                    return False

                # Use pair_custom with the target adapter address
                result = move.pair_custom(adapter_address)
                duration = time.time() - start_time
                pairing_duration_seconds.observe(duration)

                span.set_attribute("pair.result", result)
                span.set_attribute("pair.duration_seconds", duration)

                if result:
                    logger.info(f"pair_custom() succeeded for {serial}")
                    span.set_status(Status(StatusCode.OK))
                    return True
                logger.error(f"pair_custom() returned False for {serial}")
                span.set_status(Status(StatusCode.ERROR, "pair_custom failed"))
                return False

            except Exception as e:
                duration = time.time() - start_time
                pairing_duration_seconds.observe(duration)
                logger.error(f"Exception during pairing: {e}", exc_info=DEBUG)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                return False

    async def calibrate_controller(self, serial: str) -> bool:
        """Calibrate the controller using CLI tool."""
        logger.info("Calibrating controller...")

        with self.tracer.start_as_current_span("calibrate_controller") as span:
            span.set_attribute(_ATTR_CONTROLLER_SERIAL, serial)
            start_time = time.time()

            exit_code, output = await run_command([self.psmove_cli, "calibrate"])
            duration = time.time() - start_time
            calibration_duration_seconds.observe(duration)

            logger.debug(f"Calibrate output: {output}")
            span.set_attribute("calibrate.exit_code", exit_code)
            span.set_attribute("calibrate.duration_seconds", duration)

            if exit_code != 0:
                logger.warning(f"Calibration returned non-zero: {exit_code}")
                span.set_status(Status(StatusCode.ERROR, "Calibration returned non-zero"))
            else:
                span.set_status(Status(StatusCode.OK))

            return exit_code == 0

    async def restart_bluetooth(self) -> None:
        """Restart Bluetooth service to recognize new pairing.

        The original JoustMania does this after each pairing to ensure
        BlueZ recognizes the newly paired controller.
        """
        logger.info("Restarting Bluetooth service...")
        exit_code, output = await run_command(["sudo", "systemctl", "restart", "bluetooth"])
        if exit_code != 0:
            logger.warning(f"Failed to restart bluetooth: {output}")
        else:
            # Give BlueZ time to reinitialize
            import asyncio

            await asyncio.sleep(2)

    async def process_controller(self, move_index: int, serial: str) -> bool:
        """Process a single USB-connected controller with load-balanced adapter selection."""
        with self.tracer.start_as_current_span("process_controller") as span:
            span.set_attribute(_ATTR_CONTROLLER_SERIAL, serial)

            # Refresh adapter state and check if already paired
            self.adapter_manager.refresh_adapters()

            if not self.adapter_manager.check_if_not_paired(serial):
                logger.info(f"Controller {serial} already paired, skipping")
                span.set_attribute("skipped", True)
                span.set_attribute("skip_reason", "already_paired")
                return False

            logger.info(f"Found unpaired USB controller: {serial}")
            span.set_attribute("skipped", False)
            pairing_attempts_total.inc()

            # Select least-loaded adapter for load balancing
            adapter_address = self.adapter_manager.get_lowest_bt_device()

            if not adapter_address:
                logger.error("No Bluetooth adapters available for pairing")
                pairing_failed_total.inc()
                span.set_status(Status(StatusCode.ERROR, "No adapters available"))
                return False

            # Get adapter info for logging
            adapter = self.adapter_manager.select_least_loaded_adapter()
            if adapter:
                logger.info(
                    f"Load balancing: selected adapter {adapter.address} "
                    f"({adapter.hci}) with {adapter.device_count} existing devices"
                )
                span.set_attribute(_ATTR_ADAPTER_ADDRESS, adapter.address)
                span.set_attribute("adapter.device_count", adapter.device_count)
                span.set_attribute("adapter.hci", adapter.hci)
                # Record metrics
                pairing_adapter_selected_total.labels(adapter=adapter.address).inc()
                pairing_adapter_device_count.labels(adapter=adapter.address).set(adapter.device_count)

            # Pair controller to selected adapter using Python bindings
            if not self.pair_controller_psmove(move_index, serial, adapter_address):
                logger.error(f"PAIRING FAILED: Controller {serial} could not be paired")
                pairing_failed_total.inc()
                span.set_status(Status(StatusCode.ERROR, "Pairing failed"))
                return False

            # Restart Bluetooth to recognize new pairing (like original JoustMania)
            await self.restart_bluetooth()

            # Calibrate
            await self.calibrate_controller(serial)

            # Success message
            logger.info(
                f"PAIRING SUCCESS: Controller {serial} paired to adapter "
                f"{adapter_address} - unplug USB and press PS button"
            )

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
                logger.debug("No USB PS Move detected, skipping")
                pairing_usb_controllers.set(0)
                span.set_attribute("usb_detected", False)
                return

            logger.debug("USB PS Move detected, checking with psmove...")
            span.set_attribute("usb_detected", True)

            # Get USB controllers using psmove library
            controllers = self.get_usb_controllers_psmove()
            span.set_attribute("controllers.count", len(controllers))

            if not controllers:
                logger.debug("No USB controllers found via psmove")
                return

            # Process each controller
            for move_index, serial in controllers:
                await self.process_controller(move_index, serial)

    async def run_loop(self) -> None:
        """USB polling loop."""
        import asyncio

        logger.info(f"Starting USB poll loop (interval: {POLL_INTERVAL}s)")
        logger.info(f"Using psmove Python bindings (psmove.Conn_USB={psmove.Conn_USB})")

        while True:
            try:
                await self.poll()
            except Exception as e:
                logger.error(f"Error during USB poll: {e}", exc_info=DEBUG)
            await asyncio.sleep(POLL_INTERVAL)
