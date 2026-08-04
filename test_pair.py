import unittest
from types import SimpleNamespace
from unittest import mock

import pair


class PairTest(unittest.TestCase):
    def test_usb_controller_always_rewrites_bluetooth_host(self):
        pairing = pair.Pair.__new__(pair.Pair)
        pairing.pre_existing_devices = mock.Mock()
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

        pairing.pre_existing_devices.assert_called_once_with()
        pair_controller.assert_called_once_with("00:15:83:ef:21:57")


if __name__ == "__main__":
    unittest.main()
