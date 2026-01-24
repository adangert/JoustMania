"""Bluetooth monitoring for connected PS Move controllers."""

import logging
import re
import time

from opentelemetry import trace

from .config import BT_MONITOR_INTERVAL
from .metrics import (
    bluetooth_adapter_connections,
    bluetooth_device_connected,
    bluetooth_device_last_seen,
    bluetooth_device_rssi_dbm,
)
from .utils import run_command

logger = logging.getLogger("psmove-pairing")


class BluetoothMonitor:
    """Monitors Bluetooth-connected controllers for RSSI and connection status.

    Uses psmove list to get known controller MACs and monitors only those.
    """

    def __init__(self, tracer: trace.Tracer, psmove_path: str = ""):
        self.tracer = tracer
        self.psmove = psmove_path
        self.monitor_count = 0
        # Track known controllers for disconnect detection
        # Key: (serial, hci_adapter), Value: last_seen_timestamp
        self._known_controllers: dict[tuple[str, str], float] = {}
        # Cache of known controller MACs from psmove list
        self._psmove_known_macs: set[str] = set()
        self._psmove_list_interval = 30  # Refresh psmove list every 30 seconds
        self._last_psmove_list = 0.0

    async def get_psmove_known_controllers(self) -> set[str]:
        """Get set of MAC addresses known to psmoveapi."""
        if not self.psmove:
            logger.debug("psmove path not set, cannot get known controllers")
            return set()

        exit_code, output = await run_command([self.psmove, "list"], capture_stderr=False)
        if exit_code != 0:
            logger.debug("psmove list failed")
            return set()

        # Parse MAC addresses from output
        # Format: "Controller 0: aa:bb:cc:dd:ee:ff (USB)" or "(Bluetooth)"
        mac_pattern = re.compile(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")
        macs = set()
        for line in output.split("\n"):
            match = mac_pattern.search(line)
            if match:
                macs.add(match.group(0).upper())

        logger.debug(f"psmove list knows {len(macs)} controllers: {macs}")
        return macs

    async def get_bluetooth_adapters(self) -> list[str]:
        """Get list of available HCI adapters (hci0, hci1, etc.)."""
        exit_code, output = await run_command(["hciconfig", "-a"])
        if exit_code != 0:
            logger.debug("hciconfig failed")
            return []

        # Parse adapter names from output
        # Format: "hci0:   Type: Primary  Bus: USB"
        adapters = []
        for line in output.split("\n"):
            match = re.match(r"^(hci\d+):", line)
            if match:
                adapters.append(match.group(1))

        logger.debug(f"Found Bluetooth adapters: {adapters}")
        return adapters

    async def get_adapter_connections(self, hci: str) -> list[str]:
        """Get MAC addresses connected to a specific adapter."""
        exit_code, output = await run_command(["hcitool", "-i", hci, "con"])
        if exit_code != 0:
            logger.debug(f"hcitool con failed for {hci}")
            return []

        # Parse connected devices
        # Format: "< ACL 00:06:F7:XX:XX:XX handle 256 state 1 lm MASTER"
        mac_pattern = re.compile(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")
        connections = []
        for line in output.split("\n"):
            match = mac_pattern.search(line)
            if match:
                connections.append(match.group(0).upper())

        return connections

    async def get_rssi(self, hci: str, address: str) -> int | None:
        """Get RSSI for a device on a specific adapter."""
        exit_code, output = await run_command(["hcitool", "-i", hci, "rssi", address])
        if exit_code != 0:
            logger.debug(f"hcitool rssi failed for {address} on {hci}")
            return None

        # Parse RSSI value
        # Format: "RSSI return value: -45"
        match = re.search(r"RSSI return value:\s*(-?\d+)", output)
        if match:
            return int(match.group(1))

        return None

    async def monitor(self) -> None:
        """Monitor all Bluetooth-connected controllers known to psmove."""
        self.monitor_count += 1
        logger.debug(f"Bluetooth monitor #{self.monitor_count}")

        with self.tracer.start_as_current_span("bluetooth_monitor_cycle") as span:
            span.set_attribute("monitor.count", self.monitor_count)

            # Periodically refresh psmove known controllers
            now = time.time()
            if now - self._last_psmove_list > self._psmove_list_interval:
                self._psmove_known_macs = await self.get_psmove_known_controllers()
                self._last_psmove_list = now
                span.set_attribute("psmove.known_count", len(self._psmove_known_macs))

            if not self._psmove_known_macs:
                logger.debug("No known controllers from psmove list, skipping monitor")
                return

            adapters = await self.get_bluetooth_adapters()
            span.set_attribute("adapters.count", len(adapters))

            # Track currently seen controllers this cycle
            currently_seen: set[tuple[str, str]] = set()

            for hci in adapters:
                connections = await self.get_adapter_connections(hci)

                # Filter to controllers known to psmove
                known_connections = [addr for addr in connections if addr.upper() in self._psmove_known_macs]

                # Update adapter connection count
                bluetooth_adapter_connections.labels(hci_adapter=hci).set(len(known_connections))
                logger.debug(f"{hci}: {len(known_connections)} known controllers (of {len(connections)} total)")

                for serial in known_connections:
                    currently_seen.add((serial, hci))
                    ts = time.time()

                    # Get RSSI
                    rssi = await self.get_rssi(hci, serial)

                    # Update metrics
                    bluetooth_device_connected.labels(serial=serial, hci_adapter=hci).set(1)
                    bluetooth_device_last_seen.labels(serial=serial, hci_adapter=hci).set(ts)

                    if rssi is not None:
                        bluetooth_device_rssi_dbm.labels(serial=serial, hci_adapter=hci).set(rssi)
                        logger.debug(f"  {serial} on {hci}: RSSI={rssi} dBm")
                    else:
                        logger.debug(f"  {serial} on {hci}: RSSI unavailable")

                    # Track for disconnect detection
                    self._known_controllers[(serial, hci)] = ts

            # Check for disconnected controllers
            for (serial, hci), _last_seen in list(self._known_controllers.items()):
                if (serial, hci) not in currently_seen:
                    # Controller disconnected
                    bluetooth_device_connected.labels(serial=serial, hci_adapter=hci).set(0)
                    logger.debug(f"Controller {serial} disconnected from {hci}")
                    # Keep last_seen timestamp as-is for staleness detection

            span.set_attribute("controllers.total", len(currently_seen))

    async def run_loop(self) -> None:
        """Bluetooth monitoring loop."""
        import asyncio

        logger.info(f"Starting Bluetooth monitor loop (interval: {BT_MONITOR_INTERVAL}s)")
        while True:
            try:
                await self.monitor()
            except Exception as e:
                from .config import DEBUG

                logger.error(f"Error during Bluetooth monitor: {e}", exc_info=DEBUG)
            await asyncio.sleep(BT_MONITOR_INTERVAL)
