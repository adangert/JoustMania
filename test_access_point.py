import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

import access_point
import webui


class AccessPointTest(unittest.TestCase):
    @mock.patch.object(access_point.shutil, 'which', return_value='/usr/bin/nmcli')
    @mock.patch.object(access_point.subprocess, 'run')
    def test_status_uses_active_network_not_marker(self, run, which):
        controller = access_point.AccessPoint()
        run.return_value.stdout = 'Home Wi-Fi\n'
        self.assertFalse(controller.status()['enabled'])
        controller.cached = None
        run.return_value.stdout = 'Hotspot\n'
        self.assertTrue(controller.status()['enabled'])
        controller.status()
        self.assertEqual(run.call_count, 2)  # Polling is cached.

    @mock.patch.object(access_point.shutil, 'which', return_value='/usr/bin/nmcli')
    @mock.patch.object(access_point.subprocess, 'run', side_effect=subprocess.TimeoutExpired('nmcli', 2))
    def test_failed_status_is_unknown_not_disabled(self, run, which):
        state = access_point.AccessPoint().status()
        self.assertIsNone(state['enabled'])
        self.assertFalse(state['available'])

    @mock.patch.object(access_point.threading, 'Thread')
    def test_changes_are_validated_and_serialized(self, thread):
        controller = access_point.AccessPoint()
        with mock.patch.object(controller, 'status', return_value={'available': True}):
            with self.assertRaises(ValueError):
                controller.change('../../bad')
            controller.change('enable')
            self.assertTrue(controller.busy)
            thread.return_value.start.assert_called_once()
            with self.assertRaises(RuntimeError):
                controller.change('disable')

    @mock.patch.object(access_point.time, 'sleep')
    @mock.patch.object(access_point.subprocess, 'run')
    def test_script_failure_is_reported_and_unlocks_controls(self, run, sleep):
        controller = access_point.AccessPoint()
        controller.busy = True
        run.side_effect = subprocess.CalledProcessError(1, 'script', stderr='Wi-Fi unavailable')
        controller._run('enable')
        self.assertFalse(controller.busy)
        self.assertEqual(controller.error, 'Wi-Fi unavailable')
        self.assertIsNone(controller.cached)
        self.assertEqual(run.call_args.args[0][-1], str(access_point.APP_DIR / 'enable_ap.sh'))
        self.assertEqual(run.call_args.kwargs['cwd'], access_point.APP_DIR)


class AccessPointWebTest(unittest.TestCase):
    def setUp(self):
        self.ui = webui.WebUI(ns=SimpleNamespace(status={}, battery_status={}))
        self.client = self.ui.app.test_client()

    @mock.patch.object(webui, 'access_point')
    def test_post_dispatches_explicit_action(self, control):
        control.status.return_value = {'enabled': False, 'available': True, 'busy': True, 'error': ''}
        response = self.client.post('/debug/access-point', data={'action': 'enable'})
        self.assertEqual(response.status_code, 202)
        control.change.assert_called_once_with('enable')
        self.assertEqual(self.client.get('/debug/access-point').status_code, 405)

    @mock.patch.object(webui, 'access_point')
    def test_invalid_action_and_busy_errors(self, control):
        control.change.side_effect = ValueError('Invalid action')
        self.assertEqual(self.client.post('/debug/access-point', data={'action': 'bad'}).status_code, 400)
        control.change.side_effect = RuntimeError('Busy')
        self.assertEqual(self.client.post('/debug/access-point', data={'action': 'enable'}).status_code, 409)

    @mock.patch.object(webui, 'access_point')
    @mock.patch.object(webui.bluetooth_diagnostics, 'get_adapters', return_value=[])
    def test_debug_page_and_poll_show_hotspot_status(self, adapters, control):
        control.status.return_value = {'enabled': True, 'available': True, 'busy': False, 'error': ''}
        with mock.patch.object(self.ui, '_controller_debug_data', return_value=[]):
            response = self.client.get('/debug')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Disable Wi-Fi Hotspot', response.data)
            self.assertIn(b'joustpass', response.data)
            response = self.client.get('/debug/data')
            self.assertTrue(response.json['access_point']['enabled'])


if __name__ == '__main__':
    unittest.main()
