"""Bluetooth adapter management for load-balanced pairing.

Uses DBus to query BlueZ for adapter and device information,
matching the approach used in the original JoustMania.
"""

import logging
from dataclasses import dataclass
from xml.etree import ElementTree

import dbus

logger = logging.getLogger("psmove-pairing")

BUS = dbus.SystemBus()
ORG_BLUEZ = "org.bluez"
ORG_BLUEZ_PATH = "/org/bluez"


@dataclass
class AdapterInfo:
    """Information about a Bluetooth adapter."""

    hci: str  # e.g., "hci0"
    address: str  # e.g., "AA:BB:CC:DD:EE:FF"
    name: str
    device_count: int


def _get_root_proxy():
    """Get root Bluez DBus node."""
    return BUS.get_object(ORG_BLUEZ, ORG_BLUEZ_PATH)


def _get_adapter_proxy(hci: str):
    """Get Bluez DBus adapter node."""
    import os

    hci_path = os.path.join(ORG_BLUEZ_PATH, hci)
    return BUS.get_object(ORG_BLUEZ, hci_path)


def _introspect_tree(proxy):
    """Return parsed introspection tree for a DBus node."""
    iface = dbus.Interface(proxy, "org.freedesktop.DBus.Introspectable")
    return ElementTree.fromstring(iface.Introspect())


def _get_node_child_names(proxy) -> list[str]:
    """Get child node names from a DBus node."""
    tree = _introspect_tree(proxy)
    return [child.attrib["name"] for child in tree if child.tag == "node"]


def _get_node_interfaces(proxy) -> list[str]:
    """List interface names exposed by a DBus node."""
    tree = _introspect_tree(proxy)
    return [child.attrib["name"] for child in tree if child.tag == "interface"]


def _get_adapter_attrib(proxy, attrib: str):
    """Get attribute from Bluez Adapter1 interface."""
    iface = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
    return iface.Get("org.bluez.Adapter1", attrib)


def get_hci_dict() -> dict[str, str]:
    """Get dictionary mapping hci name to Bluetooth address.

    Returns:
        Dict like {"hci0": "AA:BB:CC:DD:EE:FF", "hci1": "BB:CC:DD:EE:FF:00"}
    """
    proxy = _get_root_proxy()
    hcis = _get_node_child_names(proxy)
    hci_dict = {}

    for hci in hcis:
        try:
            proxy2 = _get_adapter_proxy(hci)
            interfaces = _get_node_interfaces(proxy2)
            if (
                "org.freedesktop.DBus.Properties" not in interfaces
                or "org.bluez.Adapter1" not in interfaces
            ):
                continue
            addr = _get_adapter_attrib(proxy2, "Address")
            hci_dict[hci] = str(addr)
        except dbus.exceptions.DBusException as e:
            logger.debug(f"Error getting adapter {hci}: {e}")
            continue

    return hci_dict


def get_attached_addresses(hci: str) -> list[str]:
    """Get the addresses of devices known by an HCI adapter.

    Args:
        hci: Adapter name like "hci0"

    Returns:
        List of device MAC addresses paired to this adapter
    """
    try:
        proxy = _get_adapter_proxy(hci)
        devices = _get_node_child_names(proxy)

        known_devices = []
        for dev in devices:
            try:
                import os

                device_path = os.path.join(ORG_BLUEZ_PATH, hci, dev)
                dev_proxy = BUS.get_object(ORG_BLUEZ, device_path)
                iface = dbus.Interface(dev_proxy, "org.freedesktop.DBus.Properties")
                dev_addr = str(iface.Get("org.bluez.Device1", "Address"))
                known_devices.append(dev_addr)
            except dbus.exceptions.DBusException:
                # Not a device node (e.g., could be a service node)
                continue

        return known_devices
    except dbus.exceptions.DBusException as e:
        logger.debug(f"Error getting devices for {hci}: {e}")
        return []


class AdapterManager:
    """Manages Bluetooth adapters and provides load-balanced selection.

    Uses DBus to query BlueZ directly, matching the original JoustMania approach.
    """

    def __init__(self):
        self._hci_dict: dict[str, str] = {}  # hci -> address
        self._bt_devices: dict[str, list[str]] = {}  # address -> [device_addrs]

    def refresh_adapters(self) -> dict[str, list[str]]:
        """Refresh the list of adapters and their paired devices.

        Returns:
            Dict mapping adapter address to list of paired device addresses
        """
        self._hci_dict = get_hci_dict()
        self._bt_devices = {}

        for hci, addr in self._hci_dict.items():
            devices = get_attached_addresses(hci)
            self._bt_devices[addr] = devices
            logger.debug(f"Adapter {addr} ({hci}): {len(devices)} devices")

        return self._bt_devices

    def get_lowest_bt_device(self) -> str:
        """Get the address of the adapter with the fewest paired devices.

        This matches the original JoustMania's get_lowest_bt_device() method.

        Returns:
            Bluetooth address of the least-loaded adapter, or empty string if none
        """
        self.refresh_adapters()

        if not self._bt_devices:
            logger.warning("No Bluetooth adapters found")
            return ""

        # Find minimum device count
        min_count = min(len(devices) for devices in self._bt_devices.values())

        # Return first adapter with that count (deterministic ordering)
        for addr in sorted(self._bt_devices.keys()):
            if len(self._bt_devices[addr]) == min_count:
                logger.info(
                    f"Selected adapter {addr} with {min_count} devices "
                    f"(of {len(self._bt_devices)} adapters)"
                )
                return addr

        return ""

    def select_least_loaded_adapter(self) -> AdapterInfo | None:
        """Select the adapter with the fewest paired devices.

        Returns:
            AdapterInfo for the least-loaded adapter, or None if no adapters
        """
        self.refresh_adapters()

        if not self._bt_devices:
            logger.warning("No Bluetooth adapters found")
            return None

        # Find minimum device count
        min_count = min(len(devices) for devices in self._bt_devices.values())

        # Find adapter with that count
        for addr in sorted(self._bt_devices.keys()):
            if len(self._bt_devices[addr]) == min_count:
                # Find the hci name for this address
                hci = next(
                    (h for h, a in self._hci_dict.items() if a == addr),
                    "unknown",
                )
                adapter = AdapterInfo(
                    hci=hci,
                    address=addr,
                    name=f"adapter-{hci}",
                    device_count=min_count,
                )
                logger.info(f"Selected adapter {addr} ({hci}) with {min_count} devices")
                # Log all adapter loads for visibility
                for a, devs in sorted(self._bt_devices.items()):
                    logger.debug(f"  {a}: {len(devs)} devices")
                return adapter

        return None

    def check_if_not_paired(self, controller_addr: str) -> bool:
        """Check if a controller is not yet paired to any adapter.

        Args:
            controller_addr: Controller MAC address

        Returns:
            True if the controller is NOT paired to any adapter
        """
        controller_upper = controller_addr.upper()
        for devices in self._bt_devices.values():
            if controller_upper in [d.upper() for d in devices]:
                return False
        return True
