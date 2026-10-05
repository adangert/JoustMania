"""Read-only Linux host snapshot, run by the Proton build with host Python 3.

This helper never pairs devices, changes radio settings, or requests elevation.
BlueZ is queried once; optional HCI counters supplement its adapter identities.
"""

import json
from pathlib import Path
import sys
import subprocess
import shutil

import bluetooth_diagnostics


def _unwrap(value):
    """busctl wraps D-Bus variants in {type, data}; keep only their values."""
    if isinstance(value, dict):
        if set(value) == {"type", "data"}:
            return _unwrap(value["data"])
        return {key: _unwrap(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_unwrap(item) for item in value]
    return value


def _managed_objects():
    if shutil.which('busctl'):
        # Read the host system bus without starting BlueZ or opening a password
        # prompt. busctl avoids requiring the optional Python D-Bus module.
        result = subprocess.run([
            'busctl', '--system', '--json=short', '--timeout=2', '--auto-start=no',
            '--allow-interactive-authorization=no', 'call', 'org.bluez', '/',
            'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects',
        ], capture_output=True, text=True, check=True, timeout=3)
        payload = json.loads(result.stdout)
        if payload.get('type') != 'a{oa{sa{sv}}}':
            raise RuntimeError('Unexpected BlueZ ObjectManager response.')
        objects = _unwrap(payload['data'][0])
        if not isinstance(objects, dict):
            raise RuntimeError('Invalid BlueZ ObjectManager response.')
        return objects
    import dbus
    bus = dbus.SystemBus(private=True)
    try:
        if not bus.name_has_owner('org.bluez'):
            raise RuntimeError('The host Bluetooth service is unavailable.')
        root = bus.get_object('org.bluez', '/', introspect=False)
        return dbus.Interface(root, 'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=2)
    finally:
        bus.close()


def snapshot():
    objects = _managed_objects()
    # Skip per-radio power queries so several adapters still fit within the
    # helper's timeout. BlueZ below supplies connected-device counts.
    counters = {adapter["name"]: adapter for adapter in bluetooth_diagnostics.get_adapter_identities()}
    adapters, controllers, adapter_paths = [], [], {}
    for path, interfaces in objects.items():
        properties = interfaces.get("org.bluez.Adapter1")
        if properties is None:
            continue
        name = str(path).rsplit("/", 1)[-1]
        address = str(properties.get("Address", "")).upper()
        adapter_paths[str(path)] = (name, address)
        adapter = counters.get(name, dict(
            name=name, address=address, internal=False,
            manufacturer="Unavailable", hci_version="Unavailable", acl_mtu="Unavailable",
            inquiry_tx_power_dbm=None, rx_acl=None, tx_acl=None, rx_errors=None, tx_errors=None,
            health="HCI counters unavailable",
        ))
        adapter.update(label=str(properties.get("Alias", name)),
                       powered=bool(properties.get("Powered", False)), connections=0,
                       inquiry_tx_power_dbm=None)
        adapters.append(adapter)
    for path, interfaces in objects.items():
        properties = interfaces.get("org.bluez.Device1")
        if properties is None:
            continue
        name, adapter_address = adapter_paths.get(str(properties.get("Adapter", "")), ("unknown", ""))
        connected = bool(properties.get("Connected", False))
        for adapter in adapters:
            if adapter["name"] == name and connected:
                adapter["connections"] += 1
        modalias = str(properties.get("Modalias", "")).lower()
        sony = "v054c" in modalias
        model = "ZCM1" if sony and "p03d5" in modalias else (
            "ZCM2" if sony and "p0c5e" in modalias else "Unavailable")
        move_metadata = (str(properties.get("Name", "")) == "Motion Controller"
                         and int(properties.get("Class", 0)) == 0x2508
                         and "00001124-0000-1000-8000-00805f9b34fb" in
                         [str(uuid).lower() for uuid in properties.get("UUIDs", [])])
        if model == "Unavailable" and not move_metadata:
            continue
        controllers.append(dict(
            adapter=name, adapter_address=adapter_address,
            address=str(properties.get("Address", "")).upper(), model=model,
            registered=True, loaded=True, connected=connected,
            paired=bool(properties.get("Paired", False)),
            trusted=bool(properties.get("Trusted", False)),
            services_resolved=bool(properties.get("ServicesResolved", False)),
        ))
    return dict(adapters=adapters, controllers=controllers, error="")


if __name__ == "__main__":
    try:
        state = snapshot()
    except Exception as error:
        state = dict(adapters=[], controllers=[], error="Host Bluetooth diagnostics unavailable: " + str(error))
    Path(sys.argv[1]).write_text(json.dumps(state), encoding="utf-8")
