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
        self.patch = mock.patch.object(pairing_plan, 'read_layout', side_effect=layout)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_fill_five_then_round_robin_with_delayed_connections(self):
        targets = []
        for index in range(14):
            target = pairing_plan.begin(self.ns)
            targets.append(target)
            pairing_plan.finish(self.ns, str(index), target, True)
        self.assertEqual(targets, ['AA'] * 5 + ['BB'] * 5 + ['AA', 'BB', 'AA', 'BB'])

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
