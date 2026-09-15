import threading
import unittest
from types import SimpleNamespace
from unittest import mock
import pairing_plan
import pair
import webui


def namespace():
    return SimpleNamespace(pairing_lock=threading.RLock(), pairing_state=dict(layout=[], reservations={}, override='', cursor='', busy=False, error='', refreshed=0))


def layout():
    return [dict(name='hci0', address='AA', connected=[]), dict(name='hci1', address='BB', connected=[])]


class PairingPlanTest(unittest.TestCase):
    def setUp(self):
        self.ns = namespace()
        self.read_layout = pairing_plan.read_layout
        self.patch = mock.patch.object(pairing_plan, 'read_layout', side_effect=layout)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_active_serial_is_recorded_and_cleared_even_on_failure(self):
        target = pairing_plan.begin(self.ns, 'aa:bb')
        self.assertEqual(self.ns.pairing_state['pairing_serial'], 'AA:BB')
        self.assertEqual(pairing_plan.begin(self.ns, 'other'), '')
        self.assertEqual(self.ns.pairing_state['pairing_serial'], 'AA:BB')
        pairing_plan.finish(self.ns, 'aa:bb', target, False)
        self.assertEqual(self.ns.pairing_state['pairing_serial'], '')
        self.assertFalse(self.ns.pairing_state['busy'])

    def pair_sequence(self, count):
        targets = []
        for index in range(count):
            target = pairing_plan.begin(self.ns)
            targets.append(target)
            pairing_plan.finish(self.ns, str(index), target, True)
        return targets

    def test_csr_uses_round_robin_from_first_pairing(self):
        self.assertEqual(self.pair_sequence(14), ['AA', 'BB'] * 7)

    def test_realtek_prioritized_even_after_csr_in_hci_order(self):
        mixed = layout() + [dict(name='hci2', address='CC', connected=[], realtek=True)]
        with mock.patch.object(pairing_plan, 'read_layout', return_value=mixed):
            self.assertEqual(self.pair_sequence(13), ['CC'] * 5 + ['AA', 'BB'] * 4)

    def test_two_realteks_fill_each_to_five_before_csr(self):
        mixed = [dict(a, realtek=True) for a in layout()]
        mixed.append(dict(name='hci2', address='CC', connected=[]))
        with mock.patch.object(pairing_plan, 'read_layout', return_value=mixed):
            self.assertEqual(self.pair_sequence(13), ['AA'] * 5 + ['BB'] * 5 + ['CC'] * 3)

    def test_all_realtek_fallback_after_five_each(self):
        with mock.patch.object(pairing_plan, 'read_layout', return_value=[dict(a, realtek=True) for a in layout()]):
            self.assertEqual(self.pair_sequence(14), ['AA'] * 5 + ['BB'] * 5 + ['AA', 'BB'] * 2)

    def test_realtek_five_then_other_six_then_realtek_six_then_all_seven(self):
        mixed = [dict(name='hci0', address='RT1', connected=[], realtek=True),
                 dict(name='hci1', address='RT2', connected=[], realtek=True),
                 dict(name='hci2', address='CSR1', connected=[]),
                 dict(name='hci3', address='CSR2', connected=[]),
                 dict(name='hci4', address='OTHER', connected=[])]
        with mock.patch.object(pairing_plan, 'read_layout', return_value=mixed):
            self.assertEqual(self.pair_sequence(35),
                             ['RT1'] * 5 + ['RT2'] * 5 + ['CSR1', 'CSR2', 'OTHER'] * 6 +
                             ['RT1', 'RT2'] + ['CSR1', 'CSR2', 'OTHER', 'RT1', 'RT2'])

    def test_full_csr_skipped_while_other_csr_reaches_seven(self):
        mixed = layout()
        mixed[0]['connected'] = ['OLD_A' + str(i) for i in range(7)]
        mixed[1]['connected'] = ['OLD1', 'OLD2', 'OLD3', 'OLD4', 'OLD5']
        with mock.patch.object(pairing_plan, 'read_layout', return_value=mixed):
            self.assertEqual(self.pair_sequence(2), ['BB', 'BB'])
            self.assertEqual(pairing_plan.status(self.ns)['automatic'], '')
            # A user may still explicitly choose a full adapter.
            self.assertEqual(pairing_plan.select(self.ns, 'AA')['selected'], 'AA')

    def test_unknown_adapters_round_robin_without_priority(self):
        with mock.patch.object(pairing_plan, 'read_layout', return_value=[dict(a) for a in layout()]):
            self.assertEqual(self.pair_sequence(4), ['AA', 'BB'] * 2)

    def test_existing_realtek_connections_only_fill_missing_slots(self):
        mixed = layout()
        mixed[1].update(realtek=True, connected=['OLD1', 'OLD2', 'OLD3', 'OLD4'])
        with mock.patch.object(pairing_plan, 'read_layout', return_value=mixed):
            self.assertEqual(self.pair_sequence(4), ['BB', 'AA', 'AA', 'AA'])

    def test_override_can_exceed_realtek_target_then_returns_to_csr(self):
        mixed = layout()
        mixed[0].update(realtek=True, connected=['1', '2', '3', '4', '5'])
        with mock.patch.object(pairing_plan, 'read_layout', return_value=mixed):
            self.assertEqual(pairing_plan.status(self.ns)['selected'], 'BB')
            pairing_plan.select(self.ns, 'AA')
            target = pairing_plan.begin(self.ns)
            self.assertEqual(target, 'AA')
            pairing_plan.finish(self.ns, 'six', target, True)
            self.assertEqual(pairing_plan.status(self.ns)['selected'], 'BB')

    def test_removed_round_robin_cursor_starts_at_first_remaining_adapter(self):
        self.ns.pairing_state['cursor'] = 'BB'
        with mock.patch.object(pairing_plan, 'read_layout', return_value=layout()[:1]):
            self.assertEqual(pairing_plan.begin(self.ns), 'AA')

    def test_realtek_detection_uses_hci_manufacturer_not_retail_brand(self):
        for manufacturer in ['Realtek Semiconductor Corporation (93)', 'Unknown (93)']:
            self.assertTrue(pairing_plan.is_realtek(dict(manufacturer=manufacturer, vendor='TP-Link')))
        for manufacturer in ['', 'Unknown', 'Cambridge Silicon Radio (10)', 'Broadcom Corporation (15)', 'Cypress Semiconductor (305)']:
            self.assertFalse(pairing_plan.is_realtek(dict(manufacturer=manufacturer, vendor='Realtek')))

    def test_read_layout_matches_identity_by_name_and_address(self):
        objects = {
            '/org/bluez/hci0': {'org.bluez.Adapter1': {'Address': 'AA', 'Powered': True}},
            '/org/bluez/hci1': {'org.bluez.Adapter1': {'Address': 'BB', 'Powered': True}},
            '/org/bluez/hci2': {'org.bluez.Adapter1': {'Address': 'CC', 'Powered': False}},
        }
        identities = [dict(name='hci0', address='AA', manufacturer='Realtek (93)'),
                      dict(name='hci1', address='OLD', manufacturer='Realtek (93)')]
        # Bypass setUp's layout mock to exercise BlueZ/identity integration.
        with mock.patch('jm_dbus.ensure_process_bus') as bus, mock.patch('dbus.Interface') as interface, \
                mock.patch.object(pairing_plan.bluetooth_diagnostics, 'get_adapter_identities', return_value=identities):
            bus.return_value.name_has_owner.return_value = True
            interface.return_value.GetManagedObjects.return_value = objects
            actual = self.read_layout()
        self.assertEqual([(a['address'], a['realtek']) for a in actual], [('AA', True), ('BB', False)])

    def test_one_time_override_only_consumed_on_success(self):
        pairing_plan.select(self.ns, 'BB')
        target = pairing_plan.begin(self.ns)
        self.assertEqual(target, 'BB')
        with self.assertRaises(ValueError): pairing_plan.select(self.ns, 'AA')
        pairing_plan.finish(self.ns, 'one', target, False)
        self.assertEqual(pairing_plan.status(self.ns)['override'], 'BB')
        target = pairing_plan.begin(self.ns)
        pairing_plan.finish(self.ns, 'one', target, True)
        state = pairing_plan.status(self.ns)
        self.assertEqual(state['override'], '')
        self.assertEqual(state['selected'], 'AA')

    def test_connections_and_reservations_not_double_counted(self):
        self.ns.pairing_state.update(layout=[dict(name='hci0', address='AA', connected=['ONE'])], reservations={'ONE':'AA'})
        self.assertEqual(pairing_plan.describe(self.ns.pairing_state)['adapters'][0]['count'], 1)

    def test_removed_override_falls_back_and_unavailable_service_blocks_pairing(self):
        pairing_plan.select(self.ns, 'BB')
        with mock.patch.object(pairing_plan, 'read_layout', return_value=layout()[:1]):
            pairing_plan.refresh(self.ns, force=True)
        self.assertEqual(pairing_plan.describe(self.ns.pairing_state)['selected'], 'AA')
        with mock.patch.object(pairing_plan, 'read_layout', side_effect=RuntimeError('offline')):
            self.assertEqual(pairing_plan.begin(self.ns), '')

    def test_pair_move_passes_only_selected_adapter_to_existing_command(self):
        pairing = pair.Pair.__new__(pair.Pair)
        pairing.ns = self.ns
        pairing.bt_devices = {}
        pairing.update_adapters = mock.Mock()
        pairing_plan.select(self.ns, 'BB')
        with mock.patch.object(pair.controller_manager, 'pair_controller', return_value=True) as native:
            self.assertTrue(pairing.pair_move(SimpleNamespace(serial='ONE', usb=True, bluetooth=False)))
        native.assert_called_once_with('BB')
        self.assertEqual(pairing_plan.status(self.ns)['selected'], 'AA')

    def test_target_route_validates_and_can_return_to_automatic(self):
        self.ns.status = {}; self.ns.battery_status = {}
        client = webui.WebUI(ns=self.ns).app.test_client()
        self.assertEqual(client.post('/debug/pairing-target', data={'address':'invalid'}).status_code, 409)
        result = client.post('/debug/pairing-target', data={'address':'bb'})
        self.assertEqual(result.json['selected'], 'BB')
        self.assertEqual(client.post('/debug/pairing-target', data={'address':''}).json['selected'], 'AA')
        self.assertEqual(client.get('/debug/pairing-target').status_code, 405)


if __name__ == '__main__': unittest.main()
