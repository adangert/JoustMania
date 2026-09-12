import unittest
from types import SimpleNamespace
from unittest import mock
import piparty
import jm_dbus
import webui


def controller(serial, usb=False):
    return SimpleNamespace(serial=serial, usb=usb, bluetooth=not usb)


class DisconnectTest(unittest.TestCase):
    def menu(self, devices):
        menu = piparty.Menu.__new__(piparty.Menu)
        menu.moves = devices[:]
        menu.paired_moves = [c.serial for c in devices]
        menu.controller_manager = mock.Mock()
        menu.controller_manager.connected_controllers.return_value = devices
        menu.enable_bt_scanning = mock.Mock()
        menu.get_move_count = lambda: len(menu.moves)
        return menu

    @mock.patch.object(piparty, 'platform', 'linux')
    @mock.patch.object(jm_dbus, 'get_connected_device_addresses', return_value={'LIVE'})
    def test_stale_native_handle_removed_but_usb_preserved(self, query):
        menu = self.menu([controller('live'), controller('ghost'), controller('usb', True)])
        menu.check_for_new_moves()
        self.assertEqual([c.serial for c in menu.moves], ['live', 'usb'])
        self.assertEqual(menu.move_count, 2)
        self.assertNotIn('ghost', menu.paired_moves)

    @mock.patch.object(piparty, 'platform', 'linux')
    @mock.patch.object(jm_dbus, 'get_connected_device_addresses')
    def test_bluez_outage_keeps_snapshot_then_reconnect_recovers(self, query):
        menu = self.menu([controller('live'), controller('ghost')])
        query.return_value = {'LIVE'}
        menu.check_for_new_moves()
        menu._next_connection_check = 0
        query.side_effect = jm_dbus.dbus.DBusException('restarting')
        menu.check_for_new_moves()
        self.assertEqual([c.serial for c in menu.moves], ['live'])
        menu._next_connection_check = 0
        query.side_effect = None
        query.return_value = {'LIVE', 'GHOST'}
        menu.check_for_new_moves()
        self.assertEqual(len(menu.moves), 2)

    def test_same_count_replacement_removes_old_worker(self):
        menu = self.menu([controller('new')])
        menu.tracked_moves = {'old': mock.Mock()}
        menu.admin_move = 'old'
        menu.remove_controller = mock.Mock()
        menu.pair_move = mock.Mock()
        menu.sync_tracked_controllers()
        menu.remove_controller.assert_called_once_with('old')
        menu.pair_move.assert_called_once_with(menu.moves[0], 0)
        self.assertNotIn('old', menu.tracked_moves)
        self.assertIsNone(menu.admin_move)

    def test_stale_menu_options_cannot_block_ready_players(self):
        menu = self.menu([controller('live')])
        opts = lambda ready: {piparty.Opts.RANDOM_START.value: ready}
        menu.menu_opts = {'live': opts(True), 'ghost': opts(False)}
        menu.out_moves = {'live': piparty.Status.ALIVE.value, 'ghost': piparty.Status.ALIVE.value}
        menu.random_added = ['live']
        menu.game_mode = piparty.Games.JoustFFA
        menu.command_from_web = ''
        menu.start_game = mock.Mock()
        menu.check_start_game()
        menu.start_game.assert_called_once_with()

    @mock.patch.object(webui, 'bluetooth_roles', None)
    @mock.patch.object(webui.psmove_dbus, 'get_registered_controllers')
    def test_disconnected_debug_entry_does_not_show_stale_values(self, query):
        query.return_value = [{'address':'AA', 'adapter':'hci0', 'connected':False, 'loaded':True}]
        ui = webui.WebUI(ns=SimpleNamespace(battery_status={'AA':4},out_moves={'AA':0},controller_update_counts={'AA':10}))
        data = ui._controller_debug_data()[0]
        self.assertFalse(data['active'])
        self.assertEqual(data['battery'], 'Unknown')
        self.assertIsNone(data['update_count'])

    @mock.patch.object(piparty, 'platform', 'win32')
    def test_non_linux_keeps_native_connection_tracking(self):
        menu = self.menu([controller('live')])
        menu.check_for_new_moves()
        self.assertEqual(menu.moves[0].serial, 'live')

    @mock.patch.object(jm_dbus.dbus, 'Interface')
    @mock.patch.object(jm_dbus, 'ensure_process_bus')
    def test_live_snapshot_filters_disconnected_devices(self, bus, interface):
        bus.return_value.name_has_owner.return_value = True
        interface.return_value.GetManagedObjects.return_value = {
            '/connected': {'org.bluez.Device1': {'Address':'aa:bb', 'Connected':True}},
            '/saved': {'org.bluez.Device1': {'Address':'cc:dd', 'Connected':False}},
            '/adapter': {'org.bluez.Adapter1': {'Address':'ee:ff'}},
        }
        self.assertEqual(jm_dbus.get_connected_device_addresses(), {'AA:BB'})

    @mock.patch.object(jm_dbus, 'ensure_process_bus')
    def test_unavailable_service_is_not_empty_connections(self, bus):
        bus.return_value.name_has_owner.return_value = False
        with self.assertRaises(jm_dbus.dbus.DBusException):
            jm_dbus.get_connected_device_addresses()
        bus.return_value.get_object.assert_not_called()


if __name__ == '__main__': unittest.main()
