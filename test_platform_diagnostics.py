"""Non-destructive debug-page tests for Windows, Proton and Pi capabilities."""

import ctypes
import json
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import access_point
import bluetooth_diagnostics as diagnostics
import internal_bluetooth
import proton_bluetooth_diagnostics as host
import proton_psmove
import webui
import windows_bluetooth_diagnostics as windows


ADDRESS = '00:06:F5:E1:2B:CA'
RADIO = '24:41:8C:C5:FA:E8'


def objects():
    return {
        '/org/bluez/hci0': {'org.bluez.Adapter1': {'Address': RADIO, 'Alias': 'Host radio', 'Powered': True}},
        '/org/bluez/hci1': {'org.bluez.Adapter1': {'Address': '11:22:33:44:55:66', 'Powered': True}},
        '/org/bluez/hci0/dev_A': {'org.bluez.Device1': {
            'Address': ADDRESS, 'Adapter': '/org/bluez/hci0', 'Connected': True,
            'Modalias': 'usb:v054Cp03D5d0100', 'Paired': True, 'Trusted': True}},
        '/org/bluez/hci1/dev_B': {'org.bluez.Device1': {
            'Address': '00:06:F7:00:00:02', 'Adapter': '/org/bluez/hci1', 'Connected': False,
            'Modalias': 'usb:v054Cp0C5Ed0100', 'Paired': True, 'Trusted': False}},
        '/org/bluez/hci1/dev_keyboard': {'org.bluez.Device1': {
            'Address': 'AA:BB:CC:DD:EE:FF', 'Adapter': '/org/bluez/hci1',
            'Name': 'Keyboard', 'Connected': True}},
    }


class WindowsDiagnosticsTest(unittest.TestCase):
    def test_address_byte_order(self):
        self.assertEqual(windows.address_text(0x24418CC5FAE8), RADIO)

    def test_model_reads_only_cached_device_ids_and_checks_vendor_namespace(self):
        registry = mock.MagicMock()
        registry.OpenKey.return_value.__enter__.return_value = 'device-key'
        for vendor, product, namespace, expected in (
                (0x054C, 0x03D5, 2, 'ZCM1'), (0x054C, 0x0C5E, 2, 'ZCM2'),
                (0x054C, 0x03D5, 1, 'Unavailable'), (0x1234, 0x03D5, 2, 'Unavailable')):
            with self.subTest(product=product, namespace=namespace, vendor=vendor):
                values = {'VID': vendor, 'PID': product, 'VIDType': namespace}
                registry.QueryValueEx.side_effect = lambda key, name: (values[name], 4)
                with mock.patch.dict(sys.modules, {'winreg': registry}):
                    self.assertEqual(windows.controller_model(ADDRESS), expected)
        self.assertEqual({call.args[1] for call in registry.QueryValueEx.call_args_list}, {'VID', 'PID', 'VIDType'})

    def test_each_radio_owns_its_device_query_and_handles_are_closed(self):
        bluetooth, kernel = mock.Mock(), mock.Mock()
        def first_radio(params, handle):
            handle._obj.value = 10
            return 100
        def next_radio(found, handle):
            if handle._obj.value == 10:
                handle._obj.value = 20
                return True
            return False
        def radio_info(handle, info):
            info._obj.address = 0x24418CC5FAE8 if handle.value == 10 else 0x112233445566
            info._obj.szName = 'Radio {}'.format(handle.value)
            info._obj.manufacturer = 2
            return 0
        def first_device(params, info):
            search = params._obj
            self.assertFalse(search.fIssueInquiry)
            self.assertTrue(search.fReturnConnected)
            info._obj.address = 0x0006F5E12BCA if search.hRadio == 10 else 0x0006F7000002
            info._obj.szName = 'Motion Controller'
            info._obj.fRemembered = True
            info._obj.fConnected = search.hRadio == 10
            return 200 + search.hRadio
        bluetooth.BluetoothFindFirstRadio.side_effect = first_radio
        bluetooth.BluetoothFindNextRadio.side_effect = next_radio
        bluetooth.BluetoothGetRadioInfo.side_effect = radio_info
        bluetooth.BluetoothFindFirstDevice.side_effect = first_device
        bluetooth.BluetoothFindNextDevice.return_value = False
        closed = []
        kernel.CloseHandle.side_effect = lambda handle: closed.append(handle.value)
        with mock.patch.object(windows, '_apis', return_value=(bluetooth, kernel)), \
                mock.patch.object(windows, 'controller_model', return_value='ZCM1'), \
                mock.patch.object(windows.windows_device_metadata, 'radio_devices', return_value=[]):
            state = windows.snapshot()
        self.assertEqual(closed, [10, 20])
        bluetooth.BluetoothFindRadioClose.assert_called_once_with(100)
        self.assertEqual(bluetooth.BluetoothFindDeviceClose.call_count, 2)
        self.assertEqual([a['connections'] for a in state['adapters']], [1, 0])
        self.assertEqual([c['adapter_address'] for c in state['controllers']], [RADIO, '11:22:33:44:55:66'])
        self.assertIsNone(state['adapters'][0]['rx_acl'])
        self.assertIsNone(state['controllers'][0]['trusted'])

    def test_enumeration_failure_still_closes_radio_and_search(self):
        bluetooth, kernel = mock.Mock(), mock.Mock()
        bluetooth.BluetoothFindFirstRadio.return_value = 100
        bluetooth.BluetoothGetRadioInfo.return_value = 5
        with mock.patch.object(windows, '_apis', return_value=(bluetooth, kernel)), \
                mock.patch.object(ctypes, 'WinError', return_value=OSError('Denied'), create=True):
            with self.assertRaises(OSError):
                windows.snapshot()
        kernel.CloseHandle.assert_called_once()
        bluetooth.BluetoothFindRadioClose.assert_called_once_with(100)


class HostDiagnosticsTest(unittest.TestCase):
    @mock.patch.object(host, '_managed_objects', side_effect=objects)
    @mock.patch.object(diagnostics, 'get_adapter_identities', return_value=[])
    def test_bluez_mapping_models_and_missing_optional_hci_tools(self, *_):
        state = host.snapshot()
        self.assertEqual(len(state['adapters']), 2)
        self.assertEqual([a['connections'] for a in state['adapters']], [1, 1])
        self.assertEqual([c['model'] for c in state['controllers']], ['ZCM1', 'ZCM2'])
        self.assertEqual(state['controllers'][0]['adapter_address'], RADIO)
        self.assertTrue(state['controllers'][0]['trusted'])
        self.assertIsNone(state['adapters'][0]['rx_acl'])

    @mock.patch.object(host.shutil, 'which', return_value='/usr/bin/busctl')
    @mock.patch.object(host.subprocess, 'run')
    def test_busctl_unwraps_variants_and_never_activates_or_authenticates(self, run, _):
        data = objects()
        typed = {path: {iface: {key: {'type': 'b' if isinstance(value, bool) else 's', 'data': value}
                                for key, value in properties.items()}
                       for iface, properties in interfaces.items()} for path, interfaces in data.items()}
        run.return_value.stdout = json.dumps({'type': 'a{oa{sa{sv}}}', 'data': [typed]})
        self.assertEqual(host._managed_objects(), data)
        command = run.call_args.args[0]
        self.assertIn('--auto-start=no', command)
        self.assertIn('--allow-interactive-authorization=no', command)
        self.assertEqual(run.call_args.kwargs['timeout'], 3)

    @mock.patch.object(host.shutil, 'which', return_value='/usr/bin/busctl')
    @mock.patch.object(host.subprocess, 'run')
    def test_rejects_unexpected_host_payload(self, run, _):
        run.return_value.stdout = '{"type":"s","data":["wrong"]}'
        with self.assertRaises(RuntimeError):
            host._managed_objects()

    def test_proton_bridge_passes_paths_as_arguments_and_reads_json(self):
        expected = dict(adapters=[], controllers=[], error='')
        def resolve(path):
            self.assertTrue(Path(path).exists())
            return str(path)
        def launch(command):
            self.assertEqual(command[:4], ['/usr/bin/timeout', '--signal=KILL', '8s', '/usr/bin/python3'])
            Path(command[-1]).write_text(json.dumps(expected), encoding='utf-8')
            return 0
        with mock.patch.object(proton_psmove, '_unix_path', side_effect=resolve), \
                mock.patch.object(proton_psmove, '_run_host', side_effect=launch) as run, \
                mock.patch.object(proton_psmove, 'stop') as stop:
            self.assertEqual(proton_psmove.bluetooth_snapshot(), expected)
        stop.assert_not_called()
        self.assertNotIn('pkexec', str(run.call_args))

    @mock.patch.object(proton_psmove, '_unix_path', side_effect=str)
    @mock.patch.object(proton_psmove, '_run_host', return_value=124)
    def test_timeout_does_not_read_a_stale_file(self, *_):
        with self.assertRaisesRegex(RuntimeError, 'Could not read'):
            proton_psmove.bluetooth_snapshot()


class PlatformPageTest(unittest.TestCase):
    def setUp(self):
        diagnostics._PLATFORM_CACHE = None
        self.addCleanup(setattr, diagnostics, '_PLATFORM_CACHE', None)
        self.ui = webui.WebUI(ns=SimpleNamespace(status={}, battery_status={ADDRESS: 4}, out_moves={ADDRESS: 0}))
        self.client = self.ui.app.test_client()
        for module, attribute, value in (
                (webui, 'psmove_dbus', None), (webui, 'bluetooth_roles', None),
                (webui.runtime_platform, 'is_linux', lambda: False),
                (webui.runtime_platform, 'is_windows', lambda: True)):
            patcher = mock.patch.object(module, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_windows_displays_real_mapping_and_unsupported_controls_are_safe(self):
        with mock.patch.object(webui.runtime_platform, 'is_proton', return_value=False), \
                mock.patch.object(windows, 'snapshot', return_value=self.state()), \
                mock.patch.object(internal_bluetooth, 'is_raspberry_pi', return_value=False), \
                mock.patch.object(webui.subprocess, 'Popen') as popen:
            state = self.client.get('/debug/data').json
            self.assertEqual(state['controllers'][0]['adapter'], 'windows_radio')
            self.assertIsNone(state['controllers'][0]['trusted'])
            response = self.client.get('/debug')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Windows radio', response.data)
            self.assertIn(b'ZCM1 (PS3)', response.data)
            self.assertNotIn(b'id="internal-bt-form"', response.data)
            self.assertNotIn(b'id="hotspot-form"', response.data)
            self.assertNotIn(b'device-tree', response.data)
            self.assertNotIn(b'id="proton-pairing-notice"', response.data)
            self.assertIn(b'reset_psmove_connections.exe', response.data)
            self.assertEqual(self.client.post('/debug/reset-bluetooth').status_code, 501)
            self.assertEqual(self.client.post('/debug/restart-joustmania').status_code, 501)
            popen.assert_not_called()

    def state(self):
        return dict(adapters=[dict(name='windows_radio', label='Windows radio', address=RADIO,
                                  connections=1, manufacturer='Intel', rx_acl=None, tx_acl=None,
                                  rx_errors=None, tx_errors=None, inquiry_tx_power_dbm=None,
                                  health='Unavailable')], controllers=[dict(
                                      address=ADDRESS, adapter='windows_radio', adapter_address=RADIO,
                                      connected=True, registered=True, loaded=True,
                                      trusted=None, model='ZCM1')], error='')

    def test_proton_uses_host_not_windows_and_reports_manual_host_reset(self):
        with mock.patch.object(webui.runtime_platform, 'is_proton', return_value=True), \
                mock.patch.object(proton_psmove, 'bluetooth_snapshot', return_value=self.state()) as host_read, \
                mock.patch.object(windows, 'snapshot') as windows_read:
            state = self.client.get('/debug/data').json
            self.assertEqual(state['diagnostics']['backend'], 'Proton (Linux host)')
            self.assertIn('Desktop Mode', state['maintenance']['reset']['reason'])
            self.assertFalse(state['maintenance']['reset']['available'])
            response = self.client.get('/debug')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'id="proton-pairing-notice"', response.data)
            self.assertIn(b'When pairing controllers, please use SteamOS Desktop Mode.', response.data)
            self.assertNotIn(b'id="exit-joustmania"', response.data)
            host_read.assert_called_once()  # Multiple reads share a short-lived snapshot.
            windows_read.assert_not_called()

    def test_missing_host_diagnostics_keeps_game_controller_visible_without_fake_metadata(self):
        with mock.patch.object(webui.runtime_platform, 'is_proton', return_value=True), \
                mock.patch.object(proton_psmove, 'bluetooth_snapshot', side_effect=RuntimeError('Host unavailable')):
            state = self.client.get('/debug/data').json
            controller = state['controllers'][0]
            self.assertTrue(controller['connected'])
            self.assertEqual(controller['adapter'], 'unknown')
            self.assertIsNone(controller['registered'])
            self.assertIsNone(controller['trusted'])
            self.assertIn('Host unavailable', state['diagnostics']['error'])
            response = self.client.get('/debug')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Adapter information is unavailable', response.data)

    def test_cached_snapshot_is_not_mutated_by_web_rows(self):
        with mock.patch.object(webui.runtime_platform, 'is_proton', return_value=False), \
                mock.patch.object(windows, 'snapshot', return_value=self.state()):
            first = diagnostics.platform_snapshot()
            first['controllers'][0]['connected'] = False
            self.assertTrue(diagnostics.platform_snapshot()['controllers'][0]['connected'])

    def test_extra_usb_metadata_and_failed_dongles_render_without_fake_radios(self):
        state = self.state()
        state['adapters'][0].update(product='Intel radio', usb_id='8087:0029',
                                   usb_link='12 Mb/s (Full Speed) at Port_#0005.Hub_#0002',
                                   hci_version='Bluetooth 5.2')
        state['unavailable_adapters'] = [dict(product='Generic Bluetooth Radio', usb_id='0A12:0001',
                                            usb_description='CSR8510 A10', usb_link='12 Mb/s (Full Speed)',
                                            usb_speed_note='', status='Code 31: Windows cannot load the required driver',
                                            driver_provider='Microsoft', driver_version='1.2.3')]
        with mock.patch.object(webui.runtime_platform, 'is_proton', return_value=False), \
                mock.patch.object(windows, 'snapshot', return_value=state):
            data = self.client.get('/debug/data').json
            self.assertEqual(len(data['adapters']), 1)
            self.assertEqual(len(data['diagnostics']['unavailable_adapters']), 1)
            page = self.client.get('/debug').data
            for expected in (b'8087:0029', b'Bluetooth 5.2', b'Port_#0005.Hub_#0002',
                             b'CSR8510 A10', b'Code 31', b'12 Mb/s (Full Speed)'):
                self.assertIn(expected, page)

    def test_waiting_pairing_has_an_actionable_row_even_before_bluetooth_registration(self):
        import time
        self.ui.ns.windows_pairing = dict(address='00:06:F7:A3:5B:AD', phase='waiting',
                                         message='Unplug USB, then press PS again until the LED stays lit.',
                                         updated_at=time.monotonic())
        with mock.patch.object(webui.runtime_platform, 'is_proton', return_value=False), \
                mock.patch.object(windows, 'snapshot', return_value=self.state()):
            data = self.client.get('/debug/data').json
            row = next(c for c in data['controllers'] if c['address'] == '00:06:F7:A3:5B:AD')
            self.assertFalse(row['connected'])
            self.assertIsNone(row['registered'])
            self.assertIn('press PS button', row['status'])
            self.assertIn('LED stays lit', data['windows_pairing']['message'])
            self.ui.ns.windows_pairing['phase'] = 'verified'
            self.assertNotIn('00:06:F7:A3:5B:AD', [c['address'] for c in self.client.get('/debug/data').json['controllers']])

    def test_waiting_pairing_overrides_stale_connected_status_then_clears(self):
        import time
        self.ui.ns.windows_pairing = dict(address=ADDRESS, phase='waiting', message='Press PS again.',
                                         updated_at=time.monotonic())
        with mock.patch.object(webui.runtime_platform, 'is_proton', return_value=False), \
                mock.patch.object(windows, 'snapshot', return_value=self.state()):
            row = self.client.get('/debug/data').json['controllers'][0]
            self.assertTrue(row['connected'])  # Do not falsify the OS observation.
            self.assertIn('Pairing:', row['status'])
            self.ui.ns.windows_pairing['phase'] = 'verified'
            row = self.client.get('/debug/data').json['controllers'][0]
            self.assertEqual(row['status'], 'Connected')
            self.assertEqual(row['pairing_message'], '')


class UnsupportedControlsTest(unittest.TestCase):
    def test_missing_pi_model_is_normal_and_never_reads_boot_config(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(internal_bluetooth, 'DT_ROOT', Path(directory)), \
                mock.patch.object(internal_bluetooth, 'boot_config') as config:
            state = internal_bluetooth.InternalBluetooth().status()
        self.assertFalse(state['supported'])
        self.assertFalse(state['available'])
        self.assertEqual(state['error'], '')
        config.assert_not_called()

    def test_proton_hotspot_never_launches_native_linux_commands_in_wine(self):
        with mock.patch.object(access_point.runtime_platform, 'is_linux', return_value=False), \
                mock.patch.object(access_point.subprocess, 'run') as run:
            control = access_point.AccessPoint()
            self.assertFalse(control.status()['supported'])
            with self.assertRaisesRegex(RuntimeError, 'operating system'):
                control.change('enable')
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
