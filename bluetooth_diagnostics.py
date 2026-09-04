"""Read-only Bluetooth adapter diagnostics for the debug web page."""

import re
import subprocess
from pathlib import Path


_COUNTERS = re.compile(
    r"RX bytes:(?P<rx_bytes>\d+) acl:(?P<rx_acl>\d+).*?errors:(?P<rx_errors>\d+)\s+"
    r"TX bytes:(?P<tx_bytes>\d+) acl:(?P<tx_acl>\d+).*?errors:(?P<tx_errors>\d+)",
    re.DOTALL,
)
_POWER_CACHE = {}


def _read(path):
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def _usb_details(hci):
    """Find the USB device above an HCI interface without invoking udev."""
    try:
        current = (Path("/sys/class/bluetooth") / hci / "device").resolve()
    except OSError:
        return {}
    for parent in (current, *current.parents):
        vendor = _read(parent / "idVendor")
        product_id = _read(parent / "idProduct")
        if vendor and product_id:
            return {
                "usb_id": "{}:{}".format(vendor, product_id),
                "vendor": _read(parent / "manufacturer") or "Unknown",
                "product": _read(parent / "product") or "Unknown USB adapter",
                "usb_speed": _read(parent / "speed"),
                "usb_path": parent.name,
            }
    return {}


def parse_hciconfig(output):
    """Parse the stable, human-readable fields emitted by hciconfig -a."""
    adapters = []
    for block in re.split(r"(?m)(?=^hci\d+:)", output):
        name_match = re.match(r"(hci\d+):", block)
        if not name_match:
            continue
        address = re.search(r"BD Address:\s*([0-9A-F:]+)", block, re.I)
        manufacturer = re.search(r"Manufacturer:\s*(.+)", block)
        hci_version = re.search(r"HCI Version:\s*([^\n]+)", block)
        mtu = re.search(r"ACL MTU:\s*([^\s]+)", block)
        counters = _COUNTERS.search(block)
        adapter = {
            "name": name_match.group(1),
            "address": address.group(1).upper() if address else "Unknown",
            "powered": "UP RUNNING" in block,
            "manufacturer": manufacturer.group(1).strip() if manufacturer else "Unknown",
            "hci_version": hci_version.group(1).strip() if hci_version else "Unknown",
            "acl_mtu": mtu.group(1) if mtu else "Unknown",
        }
        if counters:
            adapter.update({key: int(value) for key, value in counters.groupdict().items()})
        else:
            adapter.update({key: 0 for key in (
                "rx_bytes", "rx_acl", "rx_errors", "tx_bytes", "tx_acl", "tx_errors"
            )})
        adapter.update(_usb_details(adapter["name"]))
        adapter["health"] = _health(adapter)
        adapters.append(adapter)
    return adapters


def _health(adapter):
    if not adapter["powered"]:
        return "Adapter is down"
    if adapter["rx_errors"] or adapter["tx_errors"]:
        return "HCI errors detected"
    return "No reported errors"


def _connection_count(hci):
    """Count live HCI links exposed by the kernel (for example hci0:12)."""
    bluetooth_class = Path("/sys/class/bluetooth")
    try:
        return sum(1 for _path in bluetooth_class.glob("{}:*".format(hci)))
    except OSError:
        return 0


def _inquiry_tx_power(hci, address):
    """Read configured inquiry TX power in dBm, caching static adapter data.

    Bluetooth HCI does not expose a reliable radio power-class identity. This
    value is useful measured configuration, but must not be presented as proof
    of Class 1, 2, or 3 hardware.
    """
    if address in _POWER_CACHE:
        return _POWER_CACHE[address]
    try:
        result = subprocess.run(
            ["hciconfig", hci, "inqtpl"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        match = re.search(r"Inquiry transmit power level:\s*(-?\d+)", result.stdout)
        value = int(match.group(1)) if match else None
    except (OSError, subprocess.TimeoutExpired):
        value = None
    _POWER_CACHE[address] = value
    return value


def get_adapters():
    """Return adapter identity and cumulative traffic/error counters."""
    try:
        result = subprocess.run(
            ["hciconfig", "-a"], capture_output=True, text=True, timeout=3, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    adapters = parse_hciconfig(result.stdout)
    for adapter in adapters:
        adapter["connections"] = _connection_count(adapter["name"])
        adapter["inquiry_tx_power_dbm"] = _inquiry_tx_power(
            adapter["name"], adapter["address"]
        )
    return adapters
