"""Provides PS Move-specific BlueZ discovery for reset and status tools.
Live D-Bus objects provide current connection information, while saved
registration files provide controller records that BlueZ has not loaded.
Controller identification supports ZCM1 and ZCM2 models without matching
unrelated Bluetooth HID devices.

Used by:

- clear_devices.py: remove only PS Move registrations
- debug_psmove_connections.py: print saved and live controller status
- webui.py: provide data for Controller Status
"""

import configparser
import dbus
from pathlib import Path

import jm_dbus


MOVE_NAME = 'Motion Controller'
MOVE_CLASS = 0x002508

# Standard Bluetooth HID service UUID shared by PS Move and other HID devices.
# is_psmove_device() combines it with controller name and class metadata.
MOVE_HID_UUID = '00001124-0000-1000-8000-00805f9b34fb'

# Sony product IDs exposed through BlueZ Modalias and saved DeviceID data.
ZCM1_PRODUCT_ID = 'p03d5'
ZCM2_PRODUCT_ID = 'p0c5e'


def get_model(properties):
    """Returns a PS Move model name from Sony vendor and product information in
    a BlueZ Modalias, or Unknown when model metadata is unavailable.
    """
    modalias = str(properties.get('Modalias', '')).lower()
    if 'v054c' in modalias and ZCM1_PRODUCT_ID in modalias:
        return 'ZCM1'
    if 'v054c' in modalias and ZCM2_PRODUCT_ID in modalias:
        return 'ZCM2'
    return 'Unknown'


def is_psmove_device(properties):
    """Returns whether BlueZ properties identify a ZCM1 or ZCM2 controller.
    Sony vendor and product IDs provide primary identification. Controller
    name, device class, and HID UUID provide a fallback when Modalias is
    unavailable.
    """
    name = str(properties.get('Name', properties.get('Alias', '')))
    device_class = int(properties.get('Class', 0))
    modalias = str(properties.get('Modalias', '')).lower()
    uuids = [str(uuid).lower() for uuid in properties.get('UUIDs', [])]

    sony_move_model = 'v054c' in modalias and (
        ZCM1_PRODUCT_ID in modalias or ZCM2_PRODUCT_ID in modalias
    )
    move_hid_metadata = (
        name == MOVE_NAME
        and device_class == MOVE_CLASS
        and MOVE_HID_UUID in uuids
    )
    return sony_move_model or move_hid_metadata


def get_registered_controllers():
    """Returns PS Move registrations from live BlueZ state and saved files.
    One ObjectManager snapshot supplies current adapter and connection
    properties. Files under /var/lib/bluetooth add valid Sony Move
    registrations that are saved but temporarily absent from BlueZ D-Bus
    state.

    Returned fields distinguish a valid registration, a live BlueZ Device1
    object, and a current Bluetooth connection through registered, loaded, and
    connected values.
    """
    controllers = []
    adapters = {}

    # BlueZ can briefly disappear while an adapter is being reset. Use one
    # ObjectManager call so the page gets a consistent, inexpensive snapshot.
    try:
        root = jm_dbus.ensure_process_bus().get_object(jm_dbus.ORG_BLUEZ, '/')
        manager = dbus.Interface(root, 'org.freedesktop.DBus.ObjectManager')
        objects = manager.GetManagedObjects()
        adapter_paths = {}

        for path, interfaces in objects.items():
            properties = interfaces.get('org.bluez.Adapter1')
            if properties is None:
                continue
            path = str(path)
            hci = path.rsplit('/', 1)[-1]
            address = str(properties.get('Address', ''))
            adapter_paths[path] = (hci, address)
            adapters[address.upper()] = hci

        for path, interfaces in objects.items():
            properties = interfaces.get('org.bluez.Device1')
            if properties is None or not is_psmove_device(properties):
                continue

            path = str(path)
            hci, adapter_address = adapter_paths.get(
                path.rsplit('/', 1)[0], ('unknown', '')
            )
            controllers.append({
                'adapter': hci,
                'adapter_address': adapter_address,
                'address': str(properties.get('Address', '')),
                'name': str(properties.get('Name', properties.get('Alias', ''))),
                'model': get_model(properties),
                'registered': True,
                'loaded': True,
                'paired': bool(properties.get('Paired', False)),
                'connected': bool(properties.get('Connected', False)),
                'trusted': bool(properties.get('Trusted', False)),
                'blocked': bool(properties.get('Blocked', False)),
                'services_resolved': bool(properties.get('ServicesResolved', False)),
                'modalias': str(properties.get('Modalias', '')),
                'device_name': path.rsplit('/', 1)[-1],
            })
    except (dbus.DBusException, OSError):
        # Saved registrations below are still useful while BlueZ restarts.
        pass

    live_keys = {
        (controller['adapter_address'].upper(), controller['address'].upper())
        for controller in controllers
    }
    bluetooth_dir = Path('/var/lib/bluetooth')
    if bluetooth_dir.exists():
        for info_path in bluetooth_dir.glob('*/*/info'):
            adapter_address = info_path.parent.parent.name.upper()
            controller_address = info_path.parent.name.upper()
            if (adapter_address, controller_address) in live_keys:
                continue

            config = configparser.ConfigParser()
            try:
                config.read(info_path)
                general = config['General']
                device_id = config['DeviceID']
            except (KeyError, configparser.Error, OSError):
                continue

            vendor = device_id.getint('Vendor', fallback=0)
            product = device_id.getint('Product', fallback=0)
            if vendor != 0x054C or product not in (0x03D5, 0x0C5E):
                continue

            controllers.append({
                'adapter': adapters.get(adapter_address, 'unknown'),
                'adapter_address': adapter_address,
                'address': controller_address,
                'name': general.get('Name', MOVE_NAME),
                'model': 'ZCM1' if product == 0x03D5 else 'ZCM2',
                'registered': True,
                'loaded': False,
                'paired': False,
                'connected': False,
                'trusted': general.getboolean('Trusted', fallback=False),
                'blocked': general.getboolean('Blocked', fallback=False),
                'services_resolved': False,
                'modalias': '',
                'device_name': 'dev_' + controller_address.replace(':', '_'),
            })

    return sorted(controllers, key=lambda item: (item['adapter'], item['address']))
