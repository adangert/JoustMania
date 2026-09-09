"""Inspect Bluetooth Classic roles and perform explicit user-requested switches."""

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


def _adapter_names():
    return sorted(
        path.name for path in Path('/sys/class/bluetooth').glob('hci[0-9]*')
        if ':' not in path.name
    )


_ROLE_CHANGE_LOCK = threading.Lock()


def set_connection_role(address, role):
    """Request one explicit role change and verify the actual resulting role."""
    if not isinstance(address, str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', address):
        raise ValueError('Invalid controller address.')
    if role not in ('central', 'peripheral'):
        raise ValueError('Choose Central or Peripheral.')
    address = address.upper()
    if not _ROLE_CHANGE_LOCK.acquire(blocking=False):
        raise RuntimeError('Another Bluetooth role change is in progress.')
    try:
        connection = get_connection_roles(_adapter_names()).get(address)
        if connection is None:
            raise RuntimeError('Controller is no longer connected over Bluetooth.')
        if connection['role'].lower() == role:
            return dict(connection, success=True)
        adapter = connection['adapter']
        try:
            subprocess.run(
                ['hcitool', '-i', adapter, 'sr', address, role],
                capture_output=True, text=True, timeout=2, check=True,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError('Bluetooth role change failed. The adapter or controller may not support this switch.') from error
        # HCI completion can arrive after hcitool exits. Observe, never force
        # the role repeatedly or assume that a successful command means success.
        for attempt in range(5):
            updated = get_connection_roles([adapter]).get(address)
            if updated is None:
                raise RuntimeError('Controller disconnected during the role change.')
            if updated['role'].lower() == role:
                return dict(updated, success=True)
            if attempt < 4:
                time.sleep(0.1)
        raise RuntimeError('The requested role was not accepted; the controller remains ' + updated['role'] + '.')
    finally:
        _ROLE_CHANGE_LOCK.release()
