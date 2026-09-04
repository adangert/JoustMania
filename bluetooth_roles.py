"""Inspect and optimize Bluetooth Classic roles for PS Move connections."""

import re
import subprocess
import threading
import time
from pathlib import Path


_CONNECTION = re.compile(
    r"ACL\s+([0-9A-F:]{17})\s+handle\s+(\d+).*?\blm\s+(CENTRAL|PERIPHERAL)\b",
    re.I,
)


def get_connection_roles(adapter_names):
    """Return controller addresses mapped to adapter, handle, and local role."""
    connections = {}
    for adapter in adapter_names:
        try:
            result = subprocess.run(
                ["hcitool", "-i", adapter, "con"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        for address, handle, role in _CONNECTION.findall(result.stdout):
            connections[address.upper()] = {
                "adapter": adapter,
                "handle": int(handle),
                "role": role.title(),
            }
    return connections


def ensure_peripheral(address, adapter_names, attempts=5, retry_delay=0.2):
    """Best-effort switch of one live connection to the local Peripheral role."""
    address = address.upper()
    last_connection = None
    for attempt in range(attempts):
        connection = get_connection_roles(adapter_names).get(address)
        if connection is not None:
            last_connection = connection
            if connection["role"] == "Peripheral":
                return {"success": True, **connection}
            try:
                subprocess.run(
                    [
                        "hcitool", "-i", connection["adapter"], "sr",
                        address, "peripheral",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
            updated = get_connection_roles(adapter_names).get(address)
            if updated is not None:
                last_connection = updated
                if updated["role"] == "Peripheral":
                    return {"success": True, **updated}
        if attempt + 1 < attempts:
            time.sleep(retry_delay)
    return {"success": False, **(last_connection or {})}


def _adapter_names():
    return sorted(
        path.name for path in Path('/sys/class/bluetooth').glob('hci[0-9]*')
        if ':' not in path.name
    )


def enforce_active_peripheral_roles(controller_manager):
    """Request Peripheral for active PS Move links that are currently Central."""
    active_addresses = {
        str(address).upper() for address in controller_manager.connected_serials()
    }
    adapter_names = _adapter_names()
    roles = get_connection_roles(adapter_names)
    attempted = []
    for address in active_addresses:
        connection = roles.get(address)
        if connection is None or connection['role'] != 'Central':
            continue
        attempted.append(address)
        try:
            subprocess.run(
                [
                    'hcitool', '-i', connection['adapter'], 'sr',
                    address, 'peripheral',
                ],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    return attempted


def start_peripheral_role_monitor(controller_manager, interval=1.0):
    """Continuously repair late or renegotiated PS Move connection roles."""
    def monitor():
        while True:
            try:
                enforce_active_peripheral_roles(controller_manager)
            except Exception:
                # Diagnostics report the live role. A monitoring failure must
                # never take down the game or controller input path.
                pass
            time.sleep(interval)

    thread = threading.Thread(
        target=monitor,
        name='PSMove-role-monitor',
        daemon=True,
    )
    thread.start()
    return thread
