import unittest
from unittest import mock

import bluetooth_diagnostics


SAMPLE = """hci1: Type: Primary  Bus: USB
    BD Address: 8C:68:8B:C3:DD:47  ACL MTU: 1021:6  SCO MTU: 255:12
    UP RUNNING
    RX bytes:745187 acl:12731 sco:0 events:576 errors:2
    TX bytes:48434 acl:75 sco:0 commands:495 errors:0
    HCI Version: 5.1 (0xa)  Revision: 0xdfc6
    Manufacturer: Realtek Semiconductor Corporation (93)
"""


class BluetoothDiagnosticsTest(unittest.TestCase):
    @mock.patch.object(bluetooth_diagnostics, "_usb_details", return_value={})
    def test_parse_adapter_identity_and_counters(self, _usb_details):
        adapter = bluetooth_diagnostics.parse_hciconfig(SAMPLE)[0]
        self.assertEqual(adapter["name"], "hci1")
        self.assertEqual(adapter["address"], "8C:68:8B:C3:DD:47")
        self.assertEqual(adapter["rx_acl"], 12731)
        self.assertEqual(adapter["tx_acl"], 75)
        self.assertEqual(adapter["health"], "HCI errors detected")

    @mock.patch.object(bluetooth_diagnostics.Path, "glob")
    def test_connection_count_uses_kernel_hci_links(self, glob):
        glob.return_value = iter(["hci1:1", "hci1:2"])
        self.assertEqual(bluetooth_diagnostics._connection_count("hci1"), 2)

    @mock.patch.object(bluetooth_diagnostics.subprocess, "run")
    def test_inquiry_power_is_parsed_as_dbm_not_power_class(self, run):
        run.return_value.stdout = "Inquiry transmit power level: 4\n"
        bluetooth_diagnostics._POWER_CACHE.clear()
        self.assertEqual(
            bluetooth_diagnostics._inquiry_tx_power("hci0", "00:11:22:33:44:55"),
            4,
        )


if __name__ == "__main__":
    unittest.main()
