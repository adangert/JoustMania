"""Bluetooth monitoring for connected devices."""

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
    """Monitors Bluetooth-connected devices for RSSI and connection status.

    Uses hcitool to monitor all HCI connections - no psmove dependency.
    This avoids conflicts with controller_manager which uses psmoveapi.
    """

    def __init__(self, tracer: trace.Tracer):
        self.tracer = tracer
        self.monitor_count = 0
        # Track known devices for disconnect detection
        # Key: (serial, hci_adapter), Value: last_seen_timestamp
        self._known_devices: dict[tuple[str, str], float] = {}

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
                connections.append(match.group(0).lower())

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
        """Monitor all Bluetooth-connected devices."""
        self.monitor_count += 1
        logger.debug(f"Bluetooth monitor #{self.monitor_count}")

        with self.tracer.start_as_current_span("bluetooth_monitor_cycle") as span:
            span.set_attribute("monitor.count", self.monitor_count)

            adapters = await self.get_bluetooth_adapters()
            span.set_attribute("adapters.count", len(adapters))

            # Track currently seen devices this cycle
            currently_seen: set[tuple[str, str]] = set()

            for hci in adapters:
                connections = await self.get_adapter_connections(hci)

                # Update adapter connection count
                bluetooth_adapter_connections.labels(hci_adapter=hci).set(len(connections))
                logger.debug(f"{hci}: {len(connections)} devices connected")

                for serial in connections:
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
                    self._known_devices[(serial, hci)] = ts

            # Check for disconnected devices
            for (serial, hci), _last_seen in self._known_devices.items():
                if (serial, hci) not in currently_seen:
                    # Device disconnected
                    bluetooth_device_connected.labels(serial=serial, hci_adapter=hci).set(0)
                    logger.debug(f"Device {serial} disconnected from {hci}")
                    # Keep last_seen timestamp as-is for staleness detection

            span.set_attribute("devices.total", len(currently_seen))

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
