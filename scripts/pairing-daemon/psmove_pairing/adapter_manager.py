"""Bluetooth adapter management for load-balanced pairing."""

import logging
from dataclasses import dataclass
from pathlib import Path

from .utils import run_command

logger = logging.getLogger("psmove-pairing")

BLUETOOTH_DIR = Path("/var/lib/bluetooth")


@dataclass
class AdapterInfo:
    """Information about a Bluetooth adapter."""

    address: str
    name: str
    device_count: int


class AdapterManager:
    """Manages Bluetooth adapters and provides load-balanced selection."""

    def __init__(self):
        self._adapters: list[AdapterInfo] = []

    async def refresh_adapters(self) -> list[AdapterInfo]:
        """Refresh the list of available adapters and their device counts."""
        self._adapters = []

        # Get adapters from bluetoothctl
        exit_code, output = await run_command(["bluetoothctl", "list"])
        if exit_code != 0:
            logger.error(f"Failed to list Bluetooth adapters: {output}")
            return []

        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            # Parse: "Controller AA:BB:CC:DD:EE:FF hostname [default]"
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "Controller":
                address = parts[1].upper()
                name = parts[2] if len(parts) > 2 else address
                device_count = self._count_devices_for_adapter(address)
                self._adapters.append(AdapterInfo(address, name, device_count))
                logger.debug(f"Adapter {address} ({name}): {device_count} devices")

        return self._adapters

    def _count_devices_for_adapter(self, adapter_address: str) -> int:
        """Count the number of paired devices for an adapter."""
        adapter_dir = BLUETOOTH_DIR / adapter_address
        if not adapter_dir.exists():
            return 0

        count = 0
        for entry in adapter_dir.iterdir():
            # Device directories are named like "AA:BB:CC:DD:EE:FF" or "dev_AA_BB_CC_DD_EE_FF"
            if entry.is_dir() and entry.name != "cache":
                # Check if it looks like a MAC address (contains colons or underscores)
                name = entry.name
                if ":" in name or (name.startswith("dev_") and "_" in name):
                    count += 1

        return count

    async def select_least_loaded_adapter(self) -> AdapterInfo | None:
        """Select the adapter with the fewest paired devices.

        Returns None if no adapters are available.
        """
        await self.refresh_adapters()

        if not self._adapters:
            logger.warning("No Bluetooth adapters found")
            return None

        # Sort by device count, then by address for deterministic ordering
        sorted_adapters = sorted(
            self._adapters, key=lambda a: (a.device_count, a.address)
        )
        selected = sorted_adapters[0]

        logger.info(
            f"Selected adapter {selected.address} ({selected.name}) "
            f"with {selected.device_count} devices"
        )

        # Log all adapter loads for visibility
        for adapter in sorted_adapters:
            logger.debug(f"  {adapter.address}: {adapter.device_count} devices")

        return selected

    def get_adapter_by_address(self, address: str) -> AdapterInfo | None:
        """Get adapter info by address."""
        address_upper = address.upper()
        for adapter in self._adapters:
            if adapter.address == address_upper:
                return adapter
        return None
