"""
This module handles interacting with Bluez over DBus for JoustMania
"""

import logging
import os
from xml.etree import ElementTree

import dbus

logger = logging.getLogger(__name__)

BUS = dbus.SystemBus()
ORG_BLUEZ = "org.bluez"
ORG_BLUEZ_PATH = "/org/bluez"


def get_hci_dict():
    """Get dictionary mapping hci number to address"""
    proxy = get_root_proxy()
    hcis = get_node_child_names(proxy)
    hci_dict = {}

    for hci in hcis:
        proxy2 = get_adapter_proxy(hci)
        interfaces = get_node_interfaces(proxy2)
        if "org.freedesktop.DBus.Properties" not in interfaces or "org.bluez.Adapter1" not in interfaces:
            continue
        addr = get_adapter_attrib(proxy2, "Address")
        hci_dict[hci] = str(addr)

    return hci_dict


def get_attached_addresses(hci):
    """Get the addresses of devices known by hci"""
    proxy = get_adapter_proxy(hci)
    devices = get_node_child_names(proxy)

    known_devices = []
    for dev in devices:
        proxy2 = get_device_proxy(hci, dev)

        dev_addr = str(get_device_attrib(proxy2, "Address"))
        known_devices.append(dev_addr)

    return known_devices


def get_connected_addresses(hci):
    """Get the addresses of devices currently connected via hci.

    Unlike get_attached_addresses() which returns all known/paired devices,
    this returns only devices with an active Bluetooth connection.
    """
    proxy = get_adapter_proxy(hci)
    devices = get_node_child_names(proxy)

    connected_devices = []
    for dev in devices:
        try:
            proxy2 = get_device_proxy(hci, dev)
            # Check if device is currently connected
            connected = get_device_attrib(proxy2, "Connected")
            if connected:
                dev_addr = str(get_device_attrib(proxy2, "Address"))
                connected_devices.append(dev_addr)
        except Exception:
            # Skip devices that can't be queried
            continue

    return connected_devices


def get_bus():
    """Get DBus hook"""
    return BUS


def get_root_proxy():
    """Get root Bluez DBus node"""
    return BUS.get_object(ORG_BLUEZ, ORG_BLUEZ_PATH)


def enable_pairable(hci):
    """Allow devices to pair with the HCI"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
    if not iface.Get("org.bluez.Adapter1", "Pairable"):
        iface.Set("org.bluez.Adapter1", "Pairable", True)


def disable_pairable(hci):
    """Prevent devices from pairing with the HCI"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
    if iface.Get("org.bluez.Adapter1", "Pairable"):
        iface.Set("org.bluez.Adapter1", "Pairable", False)


def get_discovery_filters(hci):
    """Get information about discovery options"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, "org.bluez.Adapter1")
    return iface.GetDiscoveryFilters()


def start_discovery(hci):
    """Start scanning for devices"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, "org.bluez.Adapter1")
    if not get_adapter_attrib(proxy, "Discovering").real:
        try:
            return iface.StartDiscovery()
        except dbus.exceptions.DBusException as e:
            if "InProgress" in str(e) or "NotReady" in str(e):
                pass
            else:
                raise e
    return None


def stop_discovery(hci):
    """Stop scanning for devices"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, "org.bluez.Adapter1")
    if get_adapter_attrib(proxy, "Discovering").real:
        try:
            return iface.StopDiscovery()
        except dbus.exceptions.DBusException as e:
            if "InProgress" in str(e) or "NotReady" in str(e):
                pass
            else:
                raise e
    return None


def remove_device(hci, dev):
    hci_proxy = get_adapter_proxy(hci)
    dev_proxy = get_device_proxy(hci, dev)
    iface = dbus.Interface(hci_proxy, "org.bluez.Adapter1")
    return iface.RemoveDevice(dev_proxy)


def enable_adapter(hci):
    """Set the HCI's Powered attribute to true"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
    if iface.Get("org.bluez.Adapter1", "Powered").real:
        return False
    try:
        print("Enabling adapter")
        iface.Set("org.bluez.Adapter1", "Powered", True)
        return True
    except dbus.exceptions.DBusException as e:
        if "rfkill" in str(e):
            rfkill_unblock(hci)
            # Recurse after unblocking the bluetooth adapter
            return enable_adapter(hci)
        raise e


def rfkill_unblock(hci):
    hci_id = os.popen(f'rfkill list | grep {hci} | cut -d ":" -f 1').read().split("\n")[0]
    os.popen(f"rfkill unblock {hci_id}").read()


def disable_adapter(hci):
    """Set the HCI's Powered attribute to false"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
    if iface.Get("org.bluez.Adapter1", "Powered").real:
        iface.Set("org.bluez.Adapter1", "Powered", False)
        return True
    return False


def get_adapter_proxy(hci):
    """Abstract getting Bluez DBus adapter nodes"""
    hci_path = os.path.join(ORG_BLUEZ_PATH, hci)
    return BUS.get_object(ORG_BLUEZ, hci_path)


def get_device_proxy(hci, dev):
    """Abstract getting Bluez DBus device nodes"""
    device_path = os.path.join(ORG_BLUEZ_PATH, hci, dev)
    return BUS.get_object(ORG_BLUEZ, device_path)


def get_bluez_attrib(proxy, kind, attrib):
    """Abstract getting attributes from Bluez DBus Interfaces"""
    iface = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
    return iface.Get(f"org.bluez.{kind}", attrib)


def get_adapter_attrib(proxy, attrib):
    """Abstract getting attributes from Bluez Adapter1 Interfaces"""
    return get_bluez_attrib(proxy, "Adapter1", attrib)


def get_device_attrib(proxy, attrib):
    """Abstract getting attributes from Bluez Device1 Interfaces"""
    return get_bluez_attrib(proxy, "Device1", attrib)


def _introspect_tree(proxy):
    """Return parsed introspection tree for a DBus node"""
    iface = dbus.Interface(proxy, "org.freedesktop.DBus.Introspectable")
    return ElementTree.fromstring(iface.Introspect())


def get_node_child_names(proxy):
    """Abstract finding child nodes of a DBus Node"""
    tree = _introspect_tree(proxy)
    return [child.attrib["name"] for child in tree if child.tag == "node"]


def get_node_interfaces(proxy):
    """List interface names exposed by a DBus node"""
    tree = _introspect_tree(proxy)
    return [child.attrib["name"] for child in tree if child.tag == "interface"]


def get_device_rssi(hci, device_address):
    """
    Get RSSI (signal strength) for a Bluetooth device (Phase 48).

    Args:
        hci: HCI adapter name (e.g., "hci0")
        device_address: Bluetooth MAC address (e.g., "00:1A:2B:3C:4D:5E")

    Returns:
        RSSI in dBm (-100 to 0), or None if not available

    Note:
        Uses hcitool for connected devices (more reliable than DBus RSSI property).
        Falls back to DBus property if hcitool is unavailable.
    """
    # Try hcitool first - more reliable for connected devices
    rssi = _get_rssi_via_hcitool(device_address)
    if rssi is not None:
        return rssi

    # Fall back to DBus property (only works during discovery)
    try:
        # Convert MAC address to DBus path format (replace : with _)
        device_path = device_address.replace(":", "_")
        proxy = get_device_proxy(hci, f"dev_{device_path}")

        # Get RSSI property via DBus
        rssi = get_device_attrib(proxy, "RSSI")

        if rssi is not None:
            return int(rssi)

        return None

    except dbus.exceptions.DBusException:
        # RSSI not available (device not connected, USB, or BlueZ version issue)
        return None
    except Exception:
        # Other errors (invalid device path, etc.)
        return None


def _get_rssi_via_hcitool(device_address):
    """
    Get RSSI using hcitool (works for connected devices).

    Args:
        device_address: Bluetooth MAC address (e.g., "00:1A:2B:3C:4D:5E")

    Returns:
        RSSI in dBm, or None if not available
    """
    import subprocess

    try:
        # hcitool rssi returns: "RSSI return value: -50"
        result = subprocess.run(
            ["hcitool", "rssi", device_address],
            capture_output=True,
            text=True,
            timeout=1.0,
        )

        if result.returncode == 0 and result.stdout:
            # Parse "RSSI return value: -50"
            output = result.stdout.strip()
            if "RSSI return value:" in output:
                rssi_str = output.split(":")[-1].strip()
                return int(rssi_str)

        # Log failure reason for debugging
        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "no error output"
            logger.debug(f"hcitool rssi failed for {device_address}: returncode={result.returncode}, stderr={stderr}")

        return None

    except FileNotFoundError:
        logger.warning("hcitool not found - RSSI monitoring unavailable")
        return None
    except subprocess.TimeoutExpired:
        logger.debug(f"hcitool rssi timed out for {device_address}")
        return None
    except (ValueError, IndexError) as e:
        logger.debug(f"Error parsing hcitool rssi output: {e}")
        return None
    except Exception as e:
        logger.debug(f"Unexpected error in hcitool rssi: {e}")
        return None


def get_all_device_rssi_values(hci):
    """
    Get RSSI values for all connected Bluetooth devices (Phase 48).

    Args:
        hci: HCI adapter name (e.g., "hci0")

    Returns:
        Dictionary mapping device addresses to RSSI values in dBm
    """
    rssi_map = {}

    try:
        devices = get_attached_addresses(hci)

        for device_addr in devices:
            rssi = get_device_rssi(hci, device_addr)
            if rssi is not None:
                rssi_map[device_addr] = rssi

    except Exception:
        # Return partial results if error occurs
        pass

    return rssi_map
