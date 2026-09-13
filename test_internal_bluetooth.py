import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import internal_bluetooth as bt
import webui


class InternalBluetoothTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dt = self.root / 'dt'
        (self.dt / 'aliases').mkdir(parents=True)
        (self.dt / 'model').write_text('Raspberry Pi 5 Model B\0')
        (self.dt / 'aliases/bluetooth').write_text('/serial/bluetooth\0')
        (self.dt / 'serial/bluetooth').mkdir(parents=True)
        (self.dt / 'serial/bluetooth/status').write_text('disabled\0')
        self.config = self.root / 'config.txt'
        self.original = 'dtparam=audio=on\n[all]\ndtoverlay=disable-bt\n'
        self.config.write_text(self.original)
        for name, value in [('DT_ROOT', self.dt), ('CONFIG_PATHS', (self.config,))]:
            patcher = mock.patch.object(bt, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_pending_change_and_cancel_survive_new_status_instance(self):
        self.assertFalse(bt.InternalBluetooth().status()['reboot_required'])
        self.config.write_text(bt.updated_config(self.original, True))
        state = bt.InternalBluetooth().status()
        self.assertFalse(state['enabled'])
        self.assertTrue(state['configured_enabled'])
        self.assertTrue(state['reboot_required'])
        self.config.write_text(bt.updated_config(self.config.read_text(), False))
        self.assertFalse(bt.InternalBluetooth().status()['reboot_required'])

    def test_preserves_settings_and_global_scope_and_is_idempotent(self):
        original = '# dtoverlay=disable-bt\n[pi5]\ndtoverlay=nospi10\n'
        disabled = bt.updated_config(original, False)
        self.assertTrue(disabled.startswith(original))
        self.assertIn('[all]\n' + bt.MARKER + '\ndtoverlay=disable-bt', disabled)
        self.assertEqual(bt.updated_config(disabled, False), disabled)
        enabled = bt.updated_config(disabled, True)
        self.assertTrue(bt.config_state(enabled))
        self.assertIn('dtoverlay=nospi10', enabled)

    def test_custom_config_is_not_silently_overridden(self):
        for text in ['include usercfg.txt\n', '[pi4]\ndtoverlay=disable-bt\n']:
            with self.assertRaises(RuntimeError):
                bt.updated_config(text, True)

    def test_legacy_overlay_names_and_multiple_lines(self):
        text = 'dtoverlay=pi3-disable-bt\ndtoverlay=disable-bt-pi5 # old\n'
        self.assertTrue(bt.config_state(bt.updated_config(text, True)))

    @mock.patch.object(bt.subprocess, 'run')
    def test_configure_without_hciuart_saves_backup_and_never_reboots(self, run):
        run.return_value.stdout = 'not-found\n'
        bt.configure(True)
        self.assertTrue(bt.config_state(self.config.read_text()))
        self.assertEqual(self.config.with_name('config.txt.joustmania-bak').read_text(), self.original)
        self.assertEqual(run.call_count, 1)
        self.assertNotIn('reboot', str(run.call_args_list))

    @mock.patch.object(bt.subprocess, 'run')
    def test_older_pi_enables_service_without_stopping_current_links(self, run):
        run.return_value.stdout = 'loaded\n'
        bt.configure(True)
        self.assertEqual(run.call_args.args[0], ['systemctl', 'enable', 'hciuart.service'])

    @mock.patch.object(bt.subprocess, 'run')
    def test_service_failure_restores_boot_config(self, run):
        run.side_effect = [SimpleNamespace(stdout='loaded\n'), subprocess.CalledProcessError(1, 'systemctl')]
        with self.assertRaises(subprocess.CalledProcessError):
            bt.configure(True)
        self.assertEqual(self.config.read_text(), self.original)

    def test_unavailable_platform_and_disabled_parent(self):
        (self.dt / 'serial/bluetooth/status').unlink()
        (self.dt / 'serial/status').write_text('disabled\0')
        self.assertFalse(bt.current_enabled())
        (self.dt / 'model').write_text('Other computer')
        self.assertFalse(bt.InternalBluetooth().status()['available'])

    @mock.patch.object(bt.threading, 'Thread')
    def test_rejects_bad_and_concurrent_actions(self, thread):
        control = bt.InternalBluetooth()
        with self.assertRaises(ValueError):
            control.change('../../bad')
        control.change('enable')
        with self.assertRaises(RuntimeError):
            control.change('disable')

    @mock.patch.object(bt.subprocess, 'run', side_effect=subprocess.TimeoutExpired('helper', 30))
    def test_worker_failure_unlocks_and_reports_error(self, run):
        control = bt.InternalBluetooth()
        control.busy = True
        control._run('enable')
        self.assertFalse(control.busy)
        self.assertTrue(control.status()['error'])


class InternalBluetoothWebTest(unittest.TestCase):
    @mock.patch.object(webui, 'internal_bluetooth')
    def test_post_validation_and_debug_state(self, control):
        ui = webui.WebUI(ns=SimpleNamespace(status={}, battery_status={}))
        client = ui.app.test_client()
        control.status.return_value = dict(available=True, enabled=False, configured_enabled=True,
                                          reboot_required=True, busy=False, error='')
        self.assertEqual(client.get('/debug/internal-bluetooth').status_code, 405)
        response = client.post('/debug/internal-bluetooth', data={'action': 'enable'})
        self.assertEqual(response.status_code, 202)
        control.change.assert_called_once_with('enable')
        control.change.side_effect = ValueError('Bad action')
        self.assertEqual(client.post('/debug/internal-bluetooth', data={'action': 'bad'}).status_code, 400)
        control.change.side_effect = RuntimeError('Busy')
        self.assertEqual(client.post('/debug/internal-bluetooth', data={'action': 'disable'}).status_code, 409)
        with mock.patch.object(ui, '_controller_debug_data', return_value=[]), mock.patch.object(webui.bluetooth_diagnostics, 'get_adapters', return_value=[]):
            self.assertTrue(client.get('/debug/data').json['internal_bluetooth']['reboot_required'])
            html = client.get('/debug').data
            self.assertIn(b'Disable Internal Bluetooth', html)
            self.assertIn(b'Reboot required', html)


if __name__ == '__main__':
    unittest.main()
