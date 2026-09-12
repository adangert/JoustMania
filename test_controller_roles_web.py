import unittest
from types import SimpleNamespace
from unittest import mock

import webui

ADDRESS = 'AA:BB:CC:DD:EE:FF'


class ControllerRolesWebTest(unittest.TestCase):
    def setUp(self):
        self.ui = webui.WebUI(ns=SimpleNamespace(status={}, battery_status={}))
        self.client = self.ui.app.test_client()
        self.controllers = mock.patch.object(self.ui, '_controller_debug_data', return_value=[
            {'address': ADDRESS, 'connected': True, 'adapter': 'hci0', 'role': 'Central'}
        ])
        self.controllers.start()
        self.addCleanup(self.controllers.stop)

    @mock.patch.object(webui.bluetooth_roles, 'set_connection_role')
    def test_explicit_role_request_is_verified(self, switch):
        switch.return_value = {'role': 'Central', 'adapter': 'hci0', 'success': True}
        response = self.client.post('/debug/controller-role', data={'address': ADDRESS.lower(), 'role': 'central'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['role'], 'Central')
        switch.assert_called_once_with(ADDRESS, 'central')
        self.assertEqual(self.client.get('/debug/controller-role').status_code, 405)

    @mock.patch.object(webui.bluetooth_roles, 'set_connection_role')
    def test_disconnected_or_unrecognized_controller_cannot_be_switched(self, switch):
        self.ui._controller_debug_data.return_value[0]['connected'] = False
        response = self.client.post('/debug/controller-role', data={'address': ADDRESS, 'role': 'peripheral'})
        self.assertEqual(response.status_code, 409)
        switch.assert_not_called()

    @mock.patch.object(webui.bluetooth_roles, 'set_connection_role')
    def test_unavailable_adapter_or_role_cannot_be_switched(self, switch):
        controller = self.ui._controller_debug_data.return_value[0]
        for adapter, role in [('unknown', 'Central'), ('hci0', 'Unavailable')]:
            controller.update(adapter=adapter, role=role)
            self.assertEqual(self.client.post('/debug/controller-role',
                data={'address': ADDRESS, 'role': 'peripheral'}).status_code, 409)
        switch.assert_not_called()

    @mock.patch.object(webui.bluetooth_roles, 'set_connection_role')
    def test_invalid_role_does_not_reach_hardware(self, switch):
        response = self.client.post('/debug/controller-role', data={'address': ADDRESS, 'role': 'toggle'})
        self.assertEqual(response.status_code, 400)
        switch.assert_not_called()

    @mock.patch.object(webui.bluetooth_roles, 'set_connection_role', side_effect=RuntimeError('Switch rejected'))
    def test_failure_is_reported_to_browser(self, switch):
        response = self.client.post('/debug/controller-role', data={'address': ADDRESS, 'role': 'peripheral'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['error'], 'Switch rejected')

    @mock.patch.object(webui, 'bluetooth_roles', None)
    def test_unsupported_platform(self):
        self.assertEqual(self.client.post('/debug/controller-role').status_code, 501)

    @mock.patch.object(webui.bluetooth_diagnostics, 'get_adapters', return_value=[{'name': 'hci0', 'rx_errors': 0, 'tx_errors': 0}])
    def test_debug_page_renders_individual_controls(self, adapters):
        self.ui._controller_debug_data.return_value = [{
            'address': ADDRESS, 'adapter': 'hci0', 'connected': True,
            'role': 'Central', 'battery_code': None,
        }]
        response = self.client.get('/debug')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Switch to Peripheral', response.data)
        self.assertIn(b'<th>Switch Role</th>', response.data)
        self.assertNotIn(b'Try All Peripheral', response.data)
        self.assertIn(b'<th>Unpair</th>', response.data)
        self.assertIn(b'<th>Identify</th>', response.data)
        self.ui._controller_debug_data.return_value[0]['connected'] = False
        response = self.client.get('/debug')
        self.assertNotIn(b'data-action="identify"', response.data)
        self.assertNotIn(b'class="role-toggle"', response.data)
        self.assertIn(b'data-action="unpair"', response.data)
        for heading in ('Loaded', 'BlueZ Paired', 'Services'):
            self.assertNotIn(('<th>' + heading + '</th>').encode(), response.data)



if __name__ == '__main__':
    unittest.main()
