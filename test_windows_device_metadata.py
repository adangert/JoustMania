"""Read-only Windows metadata tests with mocked native calls, on any OS."""

import ctypes
import unittest
from unittest import mock

import windows_device_metadata as metadata
import windows_bluetooth_diagnostics as diagnostics


class PropertyTest(unittest.TestCase):
    def test_usb_structures_match_packed_windows_sdk_layout(self):
        self.assertEqual(ctypes.sizeof(metadata.Guid), 16)
        self.assertEqual(ctypes.sizeof(metadata.PropertyKey), 20)
        self.assertEqual(ctypes.sizeof(metadata.UsbDescriptor), 18)
        self.assertEqual(ctypes.sizeof(metadata.UsbConnection), 35)
        self.assertEqual(metadata.UsbConnection.speed.offset, 23)
        self.assertEqual(metadata.UsbConnection.status.offset, 31)
        self.assertEqual(ctypes.sizeof(metadata.UsbConnectionV2), 16)

    def test_property_types_are_decoded_without_substituting_missing_values(self):
        cfg = mock.Mock()
        for kind, raw, expected in (
                (0x12, 'Intel\0'.encode('utf-16-le'), 'Intel'),
                (0x2012, 'one\0two\0\0'.encode('utf-16-le'), ['one', 'two']),
                (3, b'\x0b', 11), (5, b'\x02\x00', 2), (7, (31).to_bytes(4, 'little'), 31),
                (9, (0x24418CC5FAE8).to_bytes(8, 'little'), 0x24418CC5FAE8),
                (7, b'\x01', None), (0x12, b'\xff', None), (8, b'\x00' * 8, None)):
            def read(node, key, prop_type, buffer, size, flags):
                self.assertEqual(flags, 0)
                prop_type._obj.value = kind
                size._obj.value = len(raw)
                if buffer is None:
                    return 0x1A
                ctypes.memmove(buffer, raw, len(raw))
                return 0
            cfg.CM_Get_DevNode_PropertyW.side_effect = read
            with self.subTest(kind=kind, raw=raw):
                self.assertEqual(metadata._property(cfg, 42, metadata.DEVICE_PROPERTIES, 3), expected)
        cfg.CM_Get_DevNode_PropertyW.side_effect = lambda *args: 37
        self.assertIsNone(metadata._property(cfg, 42, metadata.DEVICE_PROPERTIES, 3))

    def test_present_class_list_retries_a_hotplug_size_change(self):
        cfg = mock.Mock()
        text = 'USB\\VID_8087&PID_0029\\test\0\0'
        def size(length, group, flags):
            self.assertEqual(group, metadata.BLUETOOTH_CLASS)
            self.assertEqual(flags, 0x300)
            length._obj.value = len(text)
            return 0
        calls = []
        def read(group, buffer, length, flags):
            calls.append(1)
            if len(calls) == 1:
                return 0x1A
            buffer[:len(text)] = text
            return 0
        cfg.CM_Get_Device_ID_List_SizeW.side_effect = size
        cfg.CM_Get_Device_ID_ListW.side_effect = read
        self.assertEqual(metadata._device_ids(cfg), [text.rstrip('\0')])
        self.assertEqual(len(calls), 2)

    def test_interfaces_are_queried_only_for_parent_and_present_devices(self):
        cfg = mock.Mock()
        def size(length, guid, parent, flags):
            self.assertEqual(parent, 'parent-hub')
            self.assertEqual(flags, 0)
            length._obj.value = 8
            return 0
        def read(guid, parent, buffer, length, flags):
            buffer[:7] = 'hub-a\0\0'
            return 0
        cfg.CM_Get_Device_Interface_List_SizeW.side_effect = size
        cfg.CM_Get_Device_Interface_ListW.side_effect = read
        self.assertEqual(metadata._interfaces(cfg, 'parent-hub'), ['hub-a'])

    def test_radio_properties_skip_remote_devices_and_do_not_create_devnodes(self):
        cfg, kernel = mock.Mock(), mock.Mock()
        ids = ['BTHENUM\\remote-controller', 'SWD\\wrapper', 'USB\\VID_8087&PID_0029\\radio']
        def locate(node, instance, flags):
            self.assertEqual(instance, ids[-1])
            self.assertEqual(flags, 0)  # No CM_LOCATE_DEVNODE_PHANTOM/create flags.
            node._obj.value = 42
            return 0
        cfg.CM_Locate_DevNodeW.side_effect = locate
        properties = {(metadata.DEVICE_PROPERTIES, 3): ['USB\\VID_8087&PID_0029&REV_0001'],
                      (metadata.DEVICE_PROPERTIES, 14): 'Intel radio',
                      (metadata.DEVICE_PROPERTIES, 30): 5,
                      (metadata.NODE_PROPERTIES, 8): 'parent-hub',
                      (metadata.NODE_PROPERTIES, 3): 0,
                      (metadata.RADIO_PROPERTIES, 1): 0x24418CC5FAE8,
                      (metadata.RADIO_PROPERTIES, 4): 11}
        with mock.patch.object(metadata, '_apis', return_value=(cfg, kernel)), \
                mock.patch.object(metadata, '_device_ids', return_value=ids), \
                mock.patch.object(metadata, '_property', side_effect=lambda cfg, node, group, pid: properties.get((group, pid))), \
                mock.patch.object(metadata, 'usb_link', return_value=('12 Mb/s (Full Speed)', '')) as link:
            devices = metadata.radio_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]['usb_id'], '8087:0029')
        self.assertEqual(devices[0]['radio_address'], 0x24418CC5FAE8)
        link.assert_called_once_with(cfg, kernel, 'parent-hub', 5, '8087:0029')
        cfg.CM_Locate_DevNodeW.assert_called_once()


class UsbQueryTest(unittest.TestCase):
    def query(self, speed=1, status=1, identity=(0x8087, 0x0029), flags=None, denied=False, truncated=False):
        cfg, kernel = mock.Mock(), mock.Mock()
        kernel.CreateFileW.return_value = 55
        commands = []
        def ioctl(handle, command, input_buffer, input_size, output, output_size, returned, overlapped):
            commands.append(command)
            self.assertEqual(handle, 55)
            self.assertIsNone(overlapped)
            if denied:
                return False
            if command == 0x220448:
                value = metadata.UsbConnection.from_buffer(input_buffer)
                self.assertEqual(value.port, 5)
                value.speed, value.status = speed, status
                value.descriptor.vendor, value.descriptor.product = identity
                returned._obj.value = 1 if truncated else 35
                return True
            self.assertEqual(command, 0x22045C)
            self.assertEqual(input_buffer._obj.protocols, 4)
            if flags is None:
                return False
            input_buffer._obj.flags = flags
            returned._obj.value = 16
            return True
        kernel.DeviceIoControl.side_effect = ioctl
        with mock.patch.object(metadata, '_interfaces', return_value=['hub-path']):
            result = metadata.usb_link(cfg, kernel, 'parent', 5, '8087:0029')
        kernel.CreateFileW.assert_called_once_with('hub-path', 0, 3, None, 3, 0, None)
        kernel.CloseHandle.assert_called_once_with(55)
        self.assertTrue(set(commands).issubset({0x220448, 0x22045C}))
        return result

    def test_negotiated_usb_speed_and_optional_superspeed_flags(self):
        for code, expected in ((0, '1.5 Mb/s'), (1, '12 Mb/s'), (2, '480 Mb/s'), (3, 'SuperSpeed')):
            self.assertIn(expected, self.query(speed=code)[0])
        self.assertEqual(self.query(speed=3, flags=1)[0], '5 Gb/s (SuperSpeed)')
        self.assertEqual(self.query(speed=3, flags=5)[0], 'SuperSpeedPlus (10 Gb/s or higher)')
        self.assertIsNone(self.query(speed=99)[0])

    def test_disconnected_wrong_device_short_response_and_access_denied_are_not_measurements(self):
        for arguments in (dict(status=0), dict(identity=(0x0A12, 1)), dict(truncated=True), dict(denied=True)):
            with self.subTest(arguments=arguments):
                self.assertIsNone(self.query(**arguments)[0])

    def test_invalid_port_never_opens_hardware(self):
        cfg, kernel = mock.Mock(), mock.Mock()
        for port in (None, 0, -1, 256):
            self.assertIsNone(metadata.usb_link(cfg, kernel, 'parent', port, '8087:0029')[0])
        kernel.CreateFileW.assert_not_called()

    def test_handle_closed_on_ioctl_exception(self):
        kernel = mock.Mock()
        kernel.CreateFileW.return_value = 55
        kernel.DeviceIoControl.side_effect = OSError('query error')
        with mock.patch.object(metadata, '_interfaces', return_value=['hub']):
            with self.assertRaises(OSError):
                metadata.usb_link(mock.Mock(), kernel, 'parent', 5, '8087:0029')
        kernel.CloseHandle.assert_called_once_with(55)


class EnrichmentTest(unittest.TestCase):
    def state(self):
        return dict(adapters=[dict(address='24:41:8C:C5:FA:E8', manufacturer='Intel', rx_acl=None)],
                    controllers=[dict(address='00:06:F5:E1:2B:CA')], error='')

    def test_match_only_by_mac_and_list_failed_dongles_separately(self):
        devices = [dict(product='Failed dongle', usb_id='0A12:0001', problem_code=31, radio_address=None),
                   dict(product='Intel radio', usb_id='8087:0029', radio_address=0x24418CC5FAE8,
                        usb_location='Port_#0005.Hub_#0002', usb_speed_label='12 Mb/s (Full Speed)',
                        lmp_version=11, hci_version=11)]
        with mock.patch.object(metadata, 'radio_devices', return_value=devices):
            state = diagnostics._enrich(self.state())
        self.assertEqual(len(state['adapters']), 1)
        self.assertEqual(state['adapters'][0]['usb_id'], '8087:0029')
        self.assertEqual(state['adapters'][0]['hci_version'], 'Bluetooth 5.2')
        self.assertIn('12 Mb/s', state['adapters'][0]['usb_link'])
        self.assertIsNone(state['adapters'][0]['rx_acl'])
        self.assertIn('Code 31', state['unavailable_adapters'][0]['status'])

    def test_metadata_failure_keeps_working_radio_and_controller(self):
        with mock.patch.object(metadata, 'radio_devices', side_effect=OSError('denied')):
            state = diagnostics._enrich(self.state())
        self.assertEqual(len(state['adapters']), 1)
        self.assertEqual(len(state['controllers']), 1)
        self.assertIn('denied', state['metadata_error'])

    def test_failed_dongle_visible_with_no_usable_radios(self):
        with mock.patch.object(metadata, 'radio_devices', return_value=[dict(problem_code=31)]):
            state = diagnostics._enrich(dict(adapters=[], controllers=[], error=''))
        self.assertEqual(state['adapters'], [])
        self.assertEqual(len(state['unavailable_adapters']), 1)

    def test_unknown_lmp_not_guessed_from_hci_or_product_name(self):
        self.assertEqual(diagnostics._bluetooth_version(dict(lmp_version=99, hci_version=11)), 'LMP version 99')
        self.assertEqual(diagnostics._bluetooth_version(dict(hci_version=11)), 'HCI version 11')
        self.assertEqual(diagnostics._bluetooth_version(dict(product='Bluetooth 6.0 Radio')), 'Unavailable')


if __name__ == '__main__':
    unittest.main()
