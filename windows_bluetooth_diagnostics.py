"""Read local Windows radios and their devices, without discovery or pairing."""

import ctypes
from ctypes import wintypes
import windows_device_metadata


class RadioSearch(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD)]


class RadioInfo(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("address", ctypes.c_ulonglong),
        ("szName", wintypes.WCHAR * 248), ("ulClassofDevice", wintypes.ULONG),
        ("lmpSubversion", wintypes.USHORT), ("manufacturer", wintypes.USHORT),
    ]


class DeviceSearch(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("fReturnAuthenticated", wintypes.BOOL),
        ("fReturnRemembered", wintypes.BOOL), ("fReturnUnknown", wintypes.BOOL),
        ("fReturnConnected", wintypes.BOOL), ("fIssueInquiry", wintypes.BOOL),
        ("cTimeoutMultiplier", ctypes.c_ubyte), ("hRadio", wintypes.HANDLE),
    ]


class SystemTime(ctypes.Structure):
    _fields_ = [(name, wintypes.WORD) for name in (
        "year", "month", "day_of_week", "day", "hour", "minute", "second", "milliseconds")]


class DeviceInfo(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("address", ctypes.c_ulonglong),
        ("ulClassofDevice", wintypes.ULONG), ("fConnected", wintypes.BOOL),
        ("fRemembered", wintypes.BOOL), ("fAuthenticated", wintypes.BOOL),
        ("stLastSeen", SystemTime), ("stLastUsed", SystemTime),
        ("szName", wintypes.WCHAR * 248),
    ]


def address_text(value):
    return ":".join("{:02X}".format(byte) for byte in value.to_bytes(6, "big"))


def controller_model(address):
    """Read Windows' cached USB Device ID metadata, never controller secrets."""
    import winreg

    path = (r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices" + "\\"
            + address.replace(":", "").lower())
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            vendor = winreg.QueryValueEx(key, "VID")[0]
            product = winreg.QueryValueEx(key, "PID")[0]
            vendor_type = winreg.QueryValueEx(key, "VIDType")[0]
        if vendor_type == 2 and vendor == 0x054C:  # USB vendor ID namespace.
            return {0x03D5: "ZCM1", 0x0C5E: "ZCM2"}.get(product, "Unavailable")
    except OSError:
        pass
    return "Unavailable"


def _apis():
    bluetooth = ctypes.WinDLL("BluetoothApis.dll", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    signatures = {
        "BluetoothFindFirstRadio": ([ctypes.POINTER(RadioSearch), ctypes.POINTER(wintypes.HANDLE)], wintypes.HANDLE),
        "BluetoothFindNextRadio": ([wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE)], wintypes.BOOL),
        "BluetoothFindRadioClose": ([wintypes.HANDLE], wintypes.BOOL),
        "BluetoothGetRadioInfo": ([wintypes.HANDLE, ctypes.POINTER(RadioInfo)], wintypes.DWORD),
        "BluetoothFindFirstDevice": ([ctypes.POINTER(DeviceSearch), ctypes.POINTER(DeviceInfo)], wintypes.HANDLE),
        "BluetoothFindNextDevice": ([wintypes.HANDLE, ctypes.POINTER(DeviceInfo)], wintypes.BOOL),
        "BluetoothFindDeviceClose": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(bluetooth, name)
        function.argtypes, function.restype = arguments, result
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return bluetooth, kernel


def _devices(bluetooth, radio):
    # Supply this radio's handle so a controller is not assigned to every radio.
    search = DeviceSearch(dwSize=ctypes.sizeof(DeviceSearch),
                          fReturnAuthenticated=True, fReturnRemembered=True,
                          fReturnConnected=True, fIssueInquiry=False, hRadio=radio)
    info = DeviceInfo(dwSize=ctypes.sizeof(DeviceInfo))
    found = bluetooth.BluetoothFindFirstDevice(ctypes.byref(search), ctypes.byref(info))
    if not found:
        error = ctypes.get_last_error()
        if error not in (0, 259):  # ERROR_NO_MORE_ITEMS is an empty device list.
            raise ctypes.WinError(error)
        return []
    devices = []
    try:
        while True:
            devices.append(dict(address=address_text(info.address), name=info.szName,
                                connected=bool(info.fConnected),
                                registered=bool(info.fRemembered),
                                paired=bool(info.fAuthenticated)))
            if not bluetooth.BluetoothFindNextDevice(found, ctypes.byref(info)):
                break
    finally:
        bluetooth.BluetoothFindDeviceClose(found)
    return devices


def _bluetooth_version(device):
    # Windows reports the LMP version independently of marketing/device names.
    versions = {0: '1.0b', 1: '1.1', 2: '1.2', 3: '2.0 + EDR', 4: '2.1 + EDR',
                5: '3.0 + HS', 6: '4.0', 7: '4.1', 8: '4.2', 9: '5.0',
                10: '5.1', 11: '5.2', 12: '5.3', 13: '5.4', 14: '6.0'}
    version = device.get('lmp_version')
    if version in versions:
        return 'Bluetooth ' + versions[version]
    if version is not None:
        return 'LMP version {}'.format(version)
    hci = device.get('hci_version')
    return 'HCI version {}'.format(hci) if hci is not None else 'Unavailable'


def _enrich(state):
    """Join PnP to live radios by MAC, never by enumeration order or USB name."""
    state.update(unavailable_adapters=[], metadata_error='')
    try:
        devices = windows_device_metadata.radio_devices()
    except (OSError, RuntimeError, ValueError, AttributeError) as error:
        state['metadata_error'] = 'Windows USB metadata unavailable: ' + str(error)
        return state  # Keep working radios/controllers when extra queries fail.
    by_address = {adapter['address']: adapter for adapter in state['adapters']}
    for device in devices:
        value = device.get('radio_address')
        address = address_text(value) if isinstance(value, int) and 0 < value < (1 << 48) else ''
        adapter = by_address.get(address)
        speed, location = device.get('usb_speed_label'), device.get('usb_location')
        link = speed or 'Speed unavailable'
        if location:
            link += ' at ' + location
        metadata = dict(
            product=device.get('product') or device.get('usb_description') or 'Unavailable',
            usb_id=device.get('usb_id', ''), usb_link=link,
            usb_speed_note=device.get('usb_speed_note', ''),
            usb_description=device.get('usb_description', ''),
            hci_version=_bluetooth_version(device),
            driver_provider=device.get('driver_provider') or 'Unavailable',
            driver_version=device.get('driver_version') or 'Unavailable',
        )
        if adapter is not None:
            adapter.update(metadata)
        else:
            code = device.get('problem_code')
            reason = ('Code 31: Windows cannot load the required driver' if code == 31 else
                      'Windows device error (Code {})'.format(code) if code else
                      'Not exposed as a usable radio by Windows Bluetooth')
            state['unavailable_adapters'].append(dict(metadata, status=reason,
                                                     instance_id=device.get('instance_id', '')))
    return state


def snapshot():
    bluetooth, kernel = _apis()
    search = RadioSearch(dwSize=ctypes.sizeof(RadioSearch))
    radio = wintypes.HANDLE()
    found = bluetooth.BluetoothFindFirstRadio(ctypes.byref(search), ctypes.byref(radio))
    if not found:
        error = ctypes.get_last_error()
        if error not in (0, 259):
            raise ctypes.WinError(error)
        return _enrich(dict(adapters=[], controllers=[], error=""))
    adapters, controllers = [], []
    try:
        while True:
            try:
                info = RadioInfo(dwSize=ctypes.sizeof(RadioInfo))
                error = bluetooth.BluetoothGetRadioInfo(radio, ctypes.byref(info))
                if error:
                    raise ctypes.WinError(error)
                address = address_text(info.address)
                name = "windows_" + address.replace(":", "")
                devices = _devices(bluetooth, radio)
                adapters.append(dict(
                    name=name, label=info.szName or "Windows Bluetooth radio",
                    address=address, powered=None, internal=False,
                    manufacturer="Intel" if info.manufacturer == 2 else
                                 "Bluetooth manufacturer ID {}".format(info.manufacturer),
                    product="Unavailable", hci_version="Unavailable", acl_mtu="Unavailable",
                    connections=sum(device["connected"] for device in devices),
                    inquiry_tx_power_dbm=None, rx_acl=None, tx_acl=None,
                    rx_errors=None, tx_errors=None, health="HCI counters unavailable on Windows",
                ))
                for device in devices:
                    if device["name"] != "Motion Controller":
                        continue
                    controllers.append(dict(device, adapter=name, adapter_address=address,
                                            model=controller_model(device['address']), loaded=True, trusted=None,
                                            services_resolved=None))
            finally:
                kernel.CloseHandle(radio)
            if not bluetooth.BluetoothFindNextRadio(found, ctypes.byref(radio)):
                break
    finally:
        bluetooth.BluetoothFindRadioClose(found)
    return _enrich(dict(adapters=adapters, controllers=controllers, error=""))
