import unittest
from unittest import mock

import bluetooth_roles


class BluetoothRolesTest(unittest.TestCase):
    @mock.patch.object(bluetooth_roles.subprocess, "run")
    def test_connection_roles_are_scoped_to_adapter(self, run):
        run.return_value.stdout = (
            "Connections:\n"
            "\t> ACL 00:06:F7:8F:FA:3C handle 2 state 1 lm CENTRAL \n"
        )
        roles = bluetooth_roles.get_connection_roles(["hci1"])
        self.assertEqual(roles["00:06:F7:8F:FA:3C"], {
            "adapter": "hci1", "handle": 2, "role": "Central",
        })

    @mock.patch.object(bluetooth_roles, "get_connection_roles")
    @mock.patch.object(bluetooth_roles.subprocess, "run")
    def test_central_connection_is_switched_and_verified(self, run, roles):
        roles.side_effect = [
            {"AA:BB:CC:DD:EE:FF": {"adapter": "hci1", "handle": 3, "role": "Central"}},
            {"AA:BB:CC:DD:EE:FF": {"adapter": "hci1", "handle": 3, "role": "Peripheral"}},
        ]
        result = bluetooth_roles.ensure_peripheral(
            "aa:bb:cc:dd:ee:ff", ["hci0", "hci1"], retry_delay=0
        )
        self.assertTrue(result["success"])
        run.assert_called_once_with(
            ["hcitool", "-i", "hci1", "sr", "AA:BB:CC:DD:EE:FF", "peripheral"],
            capture_output=True, text=True, timeout=2, check=False,
        )

    @mock.patch.object(bluetooth_roles, "get_connection_roles")
    @mock.patch.object(bluetooth_roles.subprocess, "run")
    def test_peripheral_connection_is_left_alone(self, run, roles):
        roles.return_value = {
            "AA:BB:CC:DD:EE:FF": {
                "adapter": "hci0", "handle": 1, "role": "Peripheral",
            }
        }
        result = bluetooth_roles.ensure_peripheral(
            "AA:BB:CC:DD:EE:FF", ["hci0"]
        )
        self.assertTrue(result["success"])
        run.assert_not_called()

    @mock.patch.object(bluetooth_roles, "_adapter_names", return_value=["hci0"])
    @mock.patch.object(bluetooth_roles, "get_connection_roles")
    @mock.patch.object(bluetooth_roles.subprocess, "run")
    def test_monitor_repairs_only_active_central_links(self, run, roles, _names):
        manager = mock.Mock()
        manager.connected_serials.return_value = ["AA:BB:CC:DD:EE:FF"]
        roles.return_value = {
            "AA:BB:CC:DD:EE:FF": {
                "adapter": "hci0", "handle": 1, "role": "Central",
            },
            "11:22:33:44:55:66": {
                "adapter": "hci0", "handle": 2, "role": "Central",
            },
        }
        attempted = bluetooth_roles.enforce_active_peripheral_roles(manager)
        self.assertEqual(attempted, ["AA:BB:CC:DD:EE:FF"])
        run.assert_called_once_with(
            ["hcitool", "-i", "hci0", "sr", "AA:BB:CC:DD:EE:FF", "peripheral"],
            capture_output=True, text=True, timeout=2, check=False,
        )


if __name__ == "__main__":
    unittest.main()
