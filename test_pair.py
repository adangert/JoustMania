import unittest
from types import SimpleNamespace
from unittest import mock

import pair


class PairTest(unittest.TestCase):
    def test_usb_controller_always_rewrites_bluetooth_host(self):
        pairing = pair.Pair.__new__(pair.Pair)
        pairing.bt_devices = {"00:15:83:ef:21:57": []}
        pairing.update_adapters = mock.Mock()
        pairing.get_lowest_bt_device = mock.Mock(
            return_value="00:15:83:ef:21:57"
        )
        controller = SimpleNamespace(
            serial="00:06:f7:97:4d:57",
            usb=True,
            bluetooth=False,
        )

        with mock.patch.object(
            pair.controller_manager,
            "pair_controller",
            return_value=True,
        ) as pair_controller:
            self.assertTrue(pairing.pair_move(controller))

        pairing.update_adapters.assert_called_once_with()
        pair_controller.assert_called_once_with("00:15:83:ef:21:57")
        self.assertEqual(
            pairing.bt_devices["00:15:83:ef:21:57"],
            ["00:06:f7:97:4d:57"],
        )

    @mock.patch.object(pair.jm_dbus, "get_hci_dict")
    def test_adapter_refresh_removes_unplugged_addresses(self, get_hci_dict):
        get_hci_dict.return_value = {"hci0": "8C:68:8B:C3:DD:47"}
        pairing = pair.Pair.__new__(pair.Pair)
        pairing.hci_dict = {"hci0": "00:15:83:EF:21:57"}
        pairing.bt_devices = {"00:15:83:EF:21:57": ["old-controller"]}
        pairing.pre_existing_devices = mock.Mock()

        pairing.update_adapters()

        self.assertEqual(pairing.bt_devices, {"8C:68:8B:C3:DD:47": []})
        pairing.pre_existing_devices.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
