"""Main PS Move pairing daemon."""

import asyncio
import logging
import shutil
import time

from opentelemetry import trace

from .bluetooth_monitor import BluetoothMonitor
from .config import BT_MONITOR_INTERVAL, DEBUG, METRICS_PORT, POLL_INTERVAL
from .usb_pairing import USBPairing
from .utils import run_command

logger = logging.getLogger("psmove-pairing")

# Health check thresholds
_HEALTH_STALENESS_THRESHOLD = 60.0  # seconds


class PairingDaemon:
    """PS Move controller pairing daemon with async Bluetooth monitoring."""

    def __init__(self, tracer: trace.Tracer, psmove_path: str):
        self.tracer = tracer
        self.psmove = psmove_path
        self.usb_pairing = USBPairing(tracer, psmove_path)
        self.bt_monitor = BluetoothMonitor(tracer)

        # Health tracking timestamps
        self._last_usb_poll: float = 0.0
        self._last_bt_monitor: float = 0.0
        self._startup_time: float = time.time()

        logger.info(f"PairingDaemon initialized with psmove: {self.psmove}")

    async def validate_prerequisites(self) -> bool:
        """Validate that required tools are available.

        Returns True if all prerequisites are met, False otherwise.
        """
        errors = []

        # Check psmove binary
        exit_code, output = await run_command([self.psmove, "list"])
        if exit_code != 0:
            errors.append(f"psmove binary failed: {output}")

        # Check bluetoothctl
        if not shutil.which("bluetoothctl"):
            errors.append("bluetoothctl not found")
        else:
            exit_code, output = await run_command(["bluetoothctl", "show"])
            if exit_code != 0:
                errors.append(f"bluetoothctl failed: {output}")

        # Check hciconfig (for Bluetooth monitoring)
        if not shutil.which("hciconfig"):
            errors.append("hciconfig not found")

        # Check hcitool (for RSSI monitoring)
        if not shutil.which("hcitool"):
            errors.append("hcitool not found")

        if errors:
            for error in errors:
                logger.error(f"Prerequisite check failed: {error}")
            return False

        logger.info("All prerequisites validated successfully")
        return True

    def is_healthy(self) -> bool:
        """Check if daemon is healthy (loops running within threshold).

        Returns True if both USB poll and Bluetooth monitor have run recently.
        """
        now = time.time()

        # During startup, allow grace period
        if now - self._startup_time < _HEALTH_STALENESS_THRESHOLD:
            return True

        # Check USB poll staleness
        usb_stale = (now - self._last_usb_poll) > _HEALTH_STALENESS_THRESHOLD
        # Check BT monitor staleness
        bt_stale = (now - self._last_bt_monitor) > _HEALTH_STALENESS_THRESHOLD

        if usb_stale:
            logger.warning(f"USB poll loop stale: {now - self._last_usb_poll:.1f}s since last poll")
        if bt_stale:
            logger.warning(f"BT monitor loop stale: {now - self._last_bt_monitor:.1f}s since last monitor")

        return not (usb_stale or bt_stale)

    def get_health_status(self) -> dict:
        """Get detailed health status for /healthz endpoint."""
        now = time.time()
        return {
            "healthy": self.is_healthy(),
            "uptime_seconds": now - self._startup_time,
            "last_usb_poll_seconds_ago": now - self._last_usb_poll if self._last_usb_poll else None,
            "last_bt_monitor_seconds_ago": now - self._last_bt_monitor if self._last_bt_monitor else None,
            "usb_poll_count": self.usb_pairing.poll_count,
            "bt_monitor_count": self.bt_monitor.monitor_count,
        }

    def update_usb_poll_timestamp(self) -> None:
        """Update the last USB poll timestamp."""
        self._last_usb_poll = time.time()

    def update_bt_monitor_timestamp(self) -> None:
        """Update the last Bluetooth monitor timestamp."""
        self._last_bt_monitor = time.time()

    async def _usb_poll_loop(self) -> None:
        """USB polling loop with health tracking."""
        logger.info(f"Starting USB poll loop (interval: {POLL_INTERVAL}s)")
        while True:
            try:
                await self.usb_pairing.poll()
                self.update_usb_poll_timestamp()
            except Exception as e:
                logger.error(f"Error during USB poll: {e}", exc_info=DEBUG)
            await asyncio.sleep(POLL_INTERVAL)

    async def _bt_monitor_loop(self) -> None:
        """Bluetooth monitoring loop with health tracking."""
        logger.info(f"Starting Bluetooth monitor loop (interval: {BT_MONITOR_INTERVAL}s)")
        while True:
            try:
                await self.bt_monitor.monitor()
                self.update_bt_monitor_timestamp()
            except Exception as e:
                logger.error(f"Error during Bluetooth monitor: {e}", exc_info=DEBUG)
            await asyncio.sleep(BT_MONITOR_INTERVAL)

    async def run(self) -> None:
        """Main daemon loop with concurrent USB polling and Bluetooth monitoring."""
        logger.info("PS Move Pairing Daemon started")
        logger.info(f"  psmove binary: {self.psmove}")
        logger.info(f"  USB poll interval: {POLL_INTERVAL}s")
        logger.info(f"  Bluetooth monitor interval: {BT_MONITOR_INTERVAL}s")
        logger.info(f"  debug mode: {DEBUG}")
        logger.info(f"  metrics port: {METRICS_PORT}")

        # Validate prerequisites
        if not await self.validate_prerequisites():
            logger.warning("Some prerequisites failed - daemon may not work correctly")

        # Run both loops concurrently
        await asyncio.gather(
            self._usb_poll_loop(),
            self._bt_monitor_loop(),
        )
