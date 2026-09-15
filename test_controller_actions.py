import multiprocessing
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import controller_manager
import psmove_dbus
import webui

ADDRESS = 'AA:BB:CC:DD:EE:FF'
ADAPTER = '11:22:33:44:55:66'


class ControllerActionsTest(unittest.TestCase):
    def test_identify_restores_current_color_and_leaves_other_controller_alone(self):
        with multiprocessing.Manager() as shared:
            manager = controller_manager.ControllerManager(shared)
            index = manager.get_or_assign_controller_index(ADDRESS)
            manager.active[index] = 1
            manager.leds[:3] = [1, 2, 3]
            with mock.patch.object(controller_manager.time, 'monotonic', return_value=10):
                self.assertTrue(manager.request_identify(ADDRESS.lower()))
                self.assertEqual(manager.output_color(index), (255, 255, 255))
                self.assertEqual(manager.output_color(1), (0, 0, 0))
            manager.leds[:3] = [4, 5, 6]
            with mock.patch.object(controller_manager.time, 'monotonic', return_value=13):
                self.assertEqual(manager.output_color(index), (4, 5, 6))
            manager.active[index] = 0
            self.assertFalse(manager.request_identify(ADDRESS))

    @mock.patch.object(psmove_dbus, 'get_registered_controllers')
    @mock.patch.object(psmove_dbus.jm_dbus, 'remove_device')
    @mock.patch('shutil.rmtree')
    def test_unpair_removes_only_selected_controller_across_adapters(self, remove_saved, remove_live, records):
        records.return_value = [
            dict(address=ADDRESS, adapter='hci0', adapter_address=ADAPTER,
                 loaded=True, device_name='dev_AA_BB_CC_DD_EE_FF'),
            dict(address=ADDRESS, adapter='unknown', adapter_address=ADAPTER, loaded=False),
            dict(address='00:00:00:00:00:01', loaded=True),
        ]
        self.assertEqual(psmove_dbus.unpair_controller(ADDRESS.lower()), 2)
        remove_live.assert_called_once_with('hci0', 'dev_AA_BB_CC_DD_EE_FF')
        self.assertEqual(str(remove_saved.call_args.args[0]),
                         '/var/lib/bluetooth/' + ADAPTER + '/' + ADDRESS)
        with self.assertRaises(ValueError):
            psmove_dbus.unpair_controller('../../')
        with self.assertRaises(ValueError):
            psmove_dbus.unpair_controller('00:00:00:00:00:02')

    def test_http_actions_and_pairing_reservation(self):
        ns = SimpleNamespace(status={}, battery_status={}, pairing_lock=threading.RLock(),
                             pairing_state={'busy': False, 'reservations': {ADDRESS: ADAPTER, 'OTHER': ADAPTER}})
        manager = mock.Mock()
        ui = webui.WebUI(ns=ns, controller_manager_instance=manager)
        client = ui.app.test_client()
        with mock.patch.object(ui, '_controller_debug_data', return_value=[dict(address=ADDRESS, connected=True)]):
            self.assertEqual(client.post('/debug/controller-identify', data={'address': ADDRESS}).status_code, 200)
            manager.request_identify.assert_called_once_with(ADDRESS)
        with mock.patch.object(ui, '_controller_debug_data', return_value=[]):
            self.assertEqual(client.post('/debug/controller-identify', data={'address': ADDRESS}).status_code, 409)
        with mock.patch.object(psmove_dbus, 'unpair_controller', return_value=1) as remove:
            ns.pairing_state.update(busy=True, pairing_serial=ADDRESS)
            self.assertEqual(client.post('/debug/controller-unpair', data={'address': ADDRESS}).status_code, 409)
            remove.assert_not_called()
            # An unrelated native pairing may remain stuck indefinitely.
            ns.pairing_state['pairing_serial'] = 'OTHER'
            self.assertEqual(client.post('/debug/controller-unpair', data={'address': ADDRESS}).status_code, 200)
            self.assertEqual(ns.pairing_state['reservations'], {'OTHER': ADAPTER})
            self.assertTrue(ns.pairing_state['busy'])
            self.assertEqual(ns.pairing_state['pairing_serial'], 'OTHER')
        for route in ('controller-identify', 'controller-unpair'):
            self.assertEqual(client.get('/debug/' + route).status_code, 405)


if __name__ == '__main__':
    unittest.main()
