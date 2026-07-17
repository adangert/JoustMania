"""Remove saved PS Move Bluetooth registrations from the local host."""

import argparse
import sys


def clear_linux_devices(dry_run=False):
    import jm_dbus
    import psmove_dbus

    hcis = jm_dbus.get_hci_dict().keys()
    removed = 0
    for hci in hcis:
        hci_proxy = jm_dbus.get_adapter_proxy(hci)
        devices = jm_dbus.get_node_child_names(hci_proxy)

        for dev in devices:
            proxy = jm_dbus.get_device_proxy(hci, dev)
            properties = jm_dbus.get_device_properties(proxy)
            if not psmove_dbus.is_psmove_device(properties):
                continue

            address = str(jm_dbus.get_device_attrib(proxy, "Address"))
            action = "Would remove" if dry_run else "Removing"
            print("{} PS Move {} from {}".format(action, address, hci))
            if not dry_run:
                jm_dbus.remove_device(hci, dev)
            removed += 1

    return removed


def clear_windows_devices(dry_run=False):
    import ctypes
    import winreg
    from ctypes import wintypes

    class BluetoothAddress(ctypes.Union):
        _fields_ = [
            ("value", ctypes.c_ulonglong),
            ("bytes", ctypes.c_ubyte * 6),
        ]

    class BluetoothDeviceSearchParams(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("fReturnAuthenticated", wintypes.BOOL),
            ("fReturnRemembered", wintypes.BOOL),
            ("fReturnUnknown", wintypes.BOOL),
            ("fReturnConnected", wintypes.BOOL),
            ("fIssueInquiry", wintypes.BOOL),
            ("cTimeoutMultiplier", ctypes.c_ubyte),
            ("hRadio", wintypes.HANDLE),
        ]

    class SystemTime(ctypes.Structure):
        _fields_ = [
            ("wYear", wintypes.WORD),
            ("wMonth", wintypes.WORD),
            ("wDayOfWeek", wintypes.WORD),
            ("wDay", wintypes.WORD),
            ("wHour", wintypes.WORD),
            ("wMinute", wintypes.WORD),
            ("wSecond", wintypes.WORD),
            ("wMilliseconds", wintypes.WORD),
        ]

    class BluetoothDeviceInfo(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("Address", BluetoothAddress),
            ("ulClassofDevice", wintypes.ULONG),
            ("fConnected", wintypes.BOOL),
            ("fRemembered", wintypes.BOOL),
            ("fAuthenticated", wintypes.BOOL),
            ("stLastSeen", SystemTime),
            ("stLastUsed", SystemTime),
            ("szName", wintypes.WCHAR * 248),
        ]

    bluetooth = ctypes.WinDLL("BluetoothApis.dll", use_last_error=True)
    bluetooth.BluetoothFindFirstDevice.argtypes = [
        ctypes.POINTER(BluetoothDeviceSearchParams),
        ctypes.POINTER(BluetoothDeviceInfo),
    ]
    bluetooth.BluetoothFindFirstDevice.restype = wintypes.HANDLE
    bluetooth.BluetoothFindNextDevice.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(BluetoothDeviceInfo),
    ]
    bluetooth.BluetoothFindNextDevice.restype = wintypes.BOOL
    bluetooth.BluetoothFindDeviceClose.argtypes = [wintypes.HANDLE]
    bluetooth.BluetoothFindDeviceClose.restype = wintypes.BOOL
    bluetooth.BluetoothRemoveDevice.argtypes = [ctypes.POINTER(BluetoothAddress)]
    bluetooth.BluetoothRemoveDevice.restype = wintypes.DWORD

    search = BluetoothDeviceSearchParams()
    search.dwSize = ctypes.sizeof(search)
    search.fReturnAuthenticated = True
    search.fReturnRemembered = True
    search.fReturnUnknown = True
    search.fReturnConnected = True
    search.fIssueInquiry = False
    search.cTimeoutMultiplier = 1
    search.hRadio = None

    def new_device_info():
        info = BluetoothDeviceInfo()
        info.dwSize = ctypes.sizeof(info)
        return info

    def address_string(address):
        return ":".join(
            "{:02x}".format(address.bytes[index])
            for index in range(5, -1, -1)
        )

    controllers = []
    info = new_device_info()
    find_handle = bluetooth.BluetoothFindFirstDevice(
        ctypes.byref(search),
        ctypes.byref(info),
    )
    if find_handle:
        try:
            while True:
                if info.szName == "Motion Controller":
                    native_address = BluetoothAddress()
                    native_address.value = info.Address.value
                    controllers.append((address_string(info.Address), native_address))

                info = new_device_info()
                if not bluetooth.BluetoothFindNextDevice(
                    find_handle,
                    ctypes.byref(info),
                ):
                    break
        finally:
            bluetooth.BluetoothFindDeviceClose(find_handle)

    # The Windows pairing code marks each Move as virtually cabled under a key
    # named <host Bluetooth address><controller Bluetooth address>. Match only
    # keys ending in a controller address found through the Bluetooth API.
    registry_base = (
        r"SYSTEM\CurrentControlSet\Services\HidBth\Parameters\Devices"
    )
    controller_ids = {
        address.replace(":", "").lower()
        for address, _ in controllers
    }
    registry_keys = []
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            registry_base,
            access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as devices_key:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(devices_key, index)
                except OSError:
                    break
                if any(name.lower().endswith(device_id) for device_id in controller_ids):
                    registry_keys.append(name)
                index += 1
    except FileNotFoundError:
        pass

    if not dry_run and not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError(
            "Windows PS Move reset must be run from Administrator PowerShell."
        )

    failures = []
    error_not_found = 1168
    action = "Would remove" if dry_run else "Removing"
    for address, native_address in controllers:
        print("{} PS Move Bluetooth registration {}".format(action, address))
        if not dry_run:
            result = bluetooth.BluetoothRemoveDevice(ctypes.byref(native_address))
            if result == error_not_found:
                # Windows can retain a device in the Bluetooth enumeration
                # cache after its PnP registration has already disappeared.
                print("PS Move {} was already absent".format(address))
            elif result != 0:
                failures.append(
                    "BluetoothRemoveDevice({}) failed with Windows error {}".format(
                        address,
                        result,
                    )
                )

    for name in registry_keys:
        print("{} PS Move virtual-cable registry key {}".format(action, name))
        if not dry_run:
            try:
                winreg.DeleteKeyEx(
                    winreg.HKEY_LOCAL_MACHINE,
                    registry_base + "\\" + name,
                    access=winreg.KEY_WOW64_64KEY,
                )
            except OSError as error:
                # BluetoothRemoveDevice can remove this key first.
                if getattr(error, "winerror", None) != 2:
                    failures.append(
                        "Could not remove registry key {}: {}".format(name, error)
                    )

    if failures:
        raise RuntimeError("\n".join(failures))

    return len(controllers)


def main():
    parser = argparse.ArgumentParser(
        description="Remove saved PS Move Bluetooth registrations.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show registrations that would be removed without changing anything",
    )
    args = parser.parse_args()

    if sys.platform.startswith("linux"):
        removed = clear_linux_devices(args.dry_run)
    elif sys.platform == "win32":
        removed = clear_windows_devices(args.dry_run)
    else:
        raise SystemExit("PS Move registration reset is not supported on this OS")

    verb = "Found" if args.dry_run else "Removed"
    print("{} {} PS Move controller registration(s)".format(verb, removed))


if __name__ == "__main__":
    main()
