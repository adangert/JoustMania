"""Main PS Move pairing daemon."""

import asyncio
import logging

from opentelemetry import trace

from .bluetooth_monitor import BluetoothMonitor
from .config import BT_MONITOR_INTERVAL, DEBUG, METRICS_PORT, POLL_INTERVAL
from .usb_pairing import USBPairing
from .utils import run_command

logger = logging.getLogger("psmove-pairing")


class PairingDaemon:
    """PS Move controller pairing daemon with async Bluetooth monitoring."""

    def __init__(self, tracer: trace.Tracer, psmove_path: str):
        self.tracer = tracer
        self.psmove = psmove_path
        self.usb_pairing = USBPairing(tracer, psmove_path)
        self.bt_monitor = BluetoothMonitor(tracer, psmove_path)
        logger.info(f"PairingDaemon initialized with psmove: {self.psmove}")

    async def run(self) -> None:
        """Main daemon loop with concurrent USB polling and Bluetooth monitoring."""
        logger.info("PS Move Pairing Daemon started")
        logger.info(f"  psmove binary: {self.psmove}")
        logger.info(f"  USB poll interval: {POLL_INTERVAL}s")
        logger.info(f"  Bluetooth monitor interval: {BT_MONITOR_INTERVAL}s")
        logger.info(f"  debug mode: {DEBUG}")
        logger.info(f"  metrics port: {METRICS_PORT}")

        # Verify psmove works
        exit_code, _ = await run_command([self.psmove, "list"])
        if exit_code != 0:
            logger.warning("'psmove list' failed - check permissions/udev rules")

        # Run both loops concurrently
        await asyncio.gather(
            self.usb_pairing.run_loop(),
            self.bt_monitor.run_loop(),
        )
