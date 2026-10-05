"""Read Windows radio metadata and USB connection speed without changing devices.

Configuration Manager supplies PnP properties, including failed radios which
BluetoothFindFirstRadio cannot expose. The only USB requests here query the
parent hub's connection information; none reset ports or send radio commands.
"""

import ctypes
import re
import uuid


U32 = ctypes.c_uint32
BLUETOOTH_CLASS = '{e0cbf06c-cd8b-4647-bb8a-263b43f0f974}'
USB_HUB_INTERFACE = 'f18a0e88-c30c-11d0-8815-00a0c906bed8'
DEVICE_PROPERTIES = 'a45c254e-df1c-4efd-8020-67d146a850e0'
NODE_PROPERTIES = '4340a6c5-93fa-4706-972c-7b648008a5a7'
DRIVER_PROPERTIES = 'a8b865dd-2e3d-4094-ad97-e593a70c75d6'
BUS_PROPERTIES = '540b947e-8b40-45bc-a8a2-6a0b894cbda2'
RADIO_PROPERTIES = 'a92f26ca-eda7-4b1d-9db2-27b68aa5a2eb'
_USB_ID = re.compile(r'USB\\VID_([0-9A-F]{4})&PID_([0-9A-F]{4})', re.I)


class Guid(ctypes.Structure):
    _fields_ = [('bytes', ctypes.c_ubyte * 16)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class PropertyKey(ctypes.Structure):
    _fields_ = [('guid', Guid), ('pid', U32)]


class UsbDescriptor(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [('length', ctypes.c_ubyte), ('type', ctypes.c_ubyte), ('usb_version', ctypes.c_uint16),
                ('device_class', ctypes.c_ubyte), ('subclass', ctypes.c_ubyte), ('protocol', ctypes.c_ubyte),
                ('max_packet', ctypes.c_ubyte), ('vendor', ctypes.c_uint16), ('product', ctypes.c_uint16),
                ('revision', ctypes.c_uint16), ('manufacturer', ctypes.c_ubyte), ('name', ctypes.c_ubyte),
                ('serial', ctypes.c_ubyte), ('configurations', ctypes.c_ubyte)]


class UsbConnection(ctypes.LittleEndianStructure):
    # usbioctl.h packs these structures to one byte, including the 18-byte
    # descriptor. Default ctypes alignment would read the wrong speed/status.
    _pack_ = 1
    _fields_ = [('port', U32), ('descriptor', UsbDescriptor), ('configuration', ctypes.c_ubyte),
                ('speed', ctypes.c_ubyte), ('is_hub', ctypes.c_ubyte), ('address', ctypes.c_uint16),
                ('pipe_count', U32), ('status', U32)]


class UsbConnectionV2(ctypes.Structure):
    _fields_ = [('port', U32), ('length', U32), ('protocols', U32), ('flags', U32)]


def _apis():
    cfg = ctypes.WinDLL('cfgmgr32.dll')
    kernel = ctypes.WinDLL('kernel32.dll', use_last_error=True)
    signatures = {
        'CM_Get_Device_ID_List_SizeW': ([ctypes.POINTER(U32), ctypes.c_wchar_p, U32], U32),
        'CM_Get_Device_ID_ListW': ([ctypes.c_wchar_p, ctypes.c_wchar_p, U32, U32], U32),
        'CM_Locate_DevNodeW': ([ctypes.POINTER(U32), ctypes.c_wchar_p, U32], U32),
        'CM_Get_DevNode_PropertyW': ([U32, ctypes.POINTER(PropertyKey), ctypes.POINTER(U32),
                                    ctypes.c_void_p, ctypes.POINTER(U32), U32], U32),
        'CM_Get_Device_Interface_List_SizeW': ([ctypes.POINTER(U32), ctypes.POINTER(Guid), ctypes.c_wchar_p, U32], U32),
        'CM_Get_Device_Interface_ListW': ([ctypes.POINTER(Guid), ctypes.c_wchar_p, ctypes.c_wchar_p, U32, U32], U32),
    }
    for name, (arguments, result) in signatures.items():
        getattr(cfg, name).argtypes, getattr(cfg, name).restype = arguments, result
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, U32, U32, ctypes.c_void_p, U32, U32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.DeviceIoControl.argtypes = [ctypes.c_void_p, U32, ctypes.c_void_p, U32, ctypes.c_void_p, U32,
                                      ctypes.POINTER(U32), ctypes.c_void_p]
    kernel.DeviceIoControl.restype = ctypes.c_int
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [ctypes.c_void_p], ctypes.c_int
    return cfg, kernel


def _device_ids(cfg):
    # PRESENT | CLASS, not every historical device in the registry.
    flags = 0x100 | 0x200
    for _ in range(3):
        length = U32()
        if cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(length), BLUETOOTH_CLASS, flags):
            raise RuntimeError('Could not enumerate Windows Bluetooth device properties.')
        if not 0 < length.value <= 65536:
            return []
        buffer = ctypes.create_unicode_buffer(length.value)
        status = cfg.CM_Get_Device_ID_ListW(BLUETOOTH_CLASS, buffer, length, flags)
        if status == 0:
            return [value for value in buffer[:].split('\0') if value]
        if status != 0x1A:  # CR_BUFFER_SMALL: a device was added between calls.
            break
    raise RuntimeError('Windows Bluetooth device enumeration changed or failed.')


def _property(cfg, node, group, pid):
    key = PropertyKey(Guid.parse(group), pid)
    size, kind = U32(), U32()
    status = cfg.CM_Get_DevNode_PropertyW(node, ctypes.byref(key), ctypes.byref(kind), None, ctypes.byref(size), 0)
    if status not in (0, 0x1A) or not 0 < size.value <= 65536:
        return None  # Missing/unreadable metadata is not a zero measurement.
    buffer = (ctypes.c_ubyte * size.value)()
    if cfg.CM_Get_DevNode_PropertyW(node, ctypes.byref(key), ctypes.byref(kind), buffer, ctypes.byref(size), 0):
        return None
    raw = bytes(buffer[:size.value])
    if kind.value in (0x12, 0x2012):  # DEVPROP_TYPE_STRING / STRING_LIST
        try:
            text = raw.decode('utf-16-le').rstrip('\0')
        except UnicodeDecodeError:
            return None
        return text.split('\0') if kind.value == 0x2012 else text
    widths = {3: 1, 5: 2, 7: 4, 9: 8}  # BYTE, UINT16, UINT32, UINT64
    if widths.get(kind.value) == len(raw):
        return int.from_bytes(raw, 'little')
    return None


def _interfaces(cfg, parent):
    guid = Guid.parse(USB_HUB_INTERFACE)
    for _ in range(3):
        length = U32()
        if cfg.CM_Get_Device_Interface_List_SizeW(ctypes.byref(length), ctypes.byref(guid), parent, 0):
            return []
        if not 0 < length.value <= 65536:
            return []
        buffer = ctypes.create_unicode_buffer(length.value)
        status = cfg.CM_Get_Device_Interface_ListW(ctypes.byref(guid), parent, buffer, length, 0)
        if status == 0:
            return [value for value in buffer[:].split('\0') if value]
        if status != 0x1A:
            break
    return []


def usb_link(cfg, kernel, parent, port, usb_id):
    """Query only this device's parent hub/port and validate its USB identity."""
    if not parent or not isinstance(port, int) or not 0 < port <= 255 or not usb_id:
        return None, 'USB parent, port or identity unavailable'
    for path in _interfaces(cfg, parent):
        # Zero desired access is sufficient for these FILE_ANY_ACCESS queries.
        # Do not request write access or elevate if the hub denies the query.
        handle = kernel.CreateFileW(path, 0, 3, None, 3, 0, None)
        if handle in (None, ctypes.c_void_p(-1).value):
            continue
        try:
            buffer = (ctypes.c_ubyte * 4096)()  # Space for optional pipe records.
            connection = UsbConnection.from_buffer(buffer)
            connection.port = port
            returned = U32()
            # CTL_CODE(FILE_DEVICE_USB=0x22, function=274, METHOD_BUFFERED, ANY_ACCESS).
            if not kernel.DeviceIoControl(handle, 0x220448, buffer, len(buffer), buffer, len(buffer),
                                          ctypes.byref(returned), None):
                continue
            identity = '{:04X}:{:04X}'.format(connection.descriptor.vendor, connection.descriptor.product)
            if returned.value < ctypes.sizeof(UsbConnection) or connection.status != 1 or identity != usb_id:
                return None, 'USB port identity changed or connection information unavailable'
            speed = {0: '1.5 Mb/s (Low Speed)', 1: '12 Mb/s (Full Speed)',
                     2: '480 Mb/s (High Speed)', 3: 'SuperSpeed'}.get(connection.speed)
            version2 = UsbConnectionV2(port, ctypes.sizeof(UsbConnectionV2), 4, 0)
            if kernel.DeviceIoControl(handle, 0x22045C, ctypes.byref(version2), ctypes.sizeof(version2),
                                      ctypes.byref(version2), ctypes.sizeof(version2), ctypes.byref(returned), None):
                if returned.value >= ctypes.sizeof(version2):
                    if version2.flags & 4:
                        speed = 'SuperSpeedPlus (10 Gb/s or higher)'
                    elif version2.flags & 1:
                        speed = '5 Gb/s (SuperSpeed)'
            return speed, '' if speed else 'USB speed code unavailable'
        finally:
            kernel.CloseHandle(handle)
    return None, 'USB hub speed query unavailable (not exposed or access denied)'


def radio_devices():
    """Return present hardware radios, not remote controllers or SWD wrappers."""
    cfg, kernel = _apis()
    devices = []
    for instance in _device_ids(cfg):
        if instance.upper().startswith(('BTH', 'SWD')):
            continue
        node = U32()
        if cfg.CM_Locate_DevNodeW(ctypes.byref(node), instance, 0):
            continue
        read = lambda group, pid: _property(cfg, node, group, pid)
        hardware = read(DEVICE_PROPERTIES, 3) or []
        if isinstance(hardware, str):
            hardware = [hardware]
        match = next((found for value in hardware if (found := _USB_ID.search(value))), None)
        usb_id = '{}:{}'.format(*match.groups()).upper() if match else ''
        parent, port = read(NODE_PROPERTIES, 8), read(DEVICE_PROPERTIES, 30)
        speed, speed_note = usb_link(cfg, kernel, parent, port, usb_id) if usb_id else (None, '')
        devices.append(dict(
            instance_id=instance, radio_address=read(RADIO_PROPERTIES, 1),
            product=read(DEVICE_PROPERTIES, 14) or read(DRIVER_PROPERTIES, 4) or read(DEVICE_PROPERTIES, 2),
            usb_description=read(BUS_PROPERTIES, 4) or '',
            usb_id=usb_id, usb_location=read(DEVICE_PROPERTIES, 15) or '',
            usb_speed_label=speed, usb_speed_note=speed_note,
            problem_code=read(NODE_PROPERTIES, 3),
            lmp_version=read(RADIO_PROPERTIES, 4), hci_version=read(RADIO_PROPERTIES, 6),
            manufacturer=read(RADIO_PROPERTIES, 2),
            driver_provider=read(DRIVER_PROPERTIES, 9), driver_version=read(DRIVER_PROPERTIES, 3),
        ))
    return devices
