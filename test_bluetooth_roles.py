import subprocess
import unittest
from unittest import mock

import bluetooth_roles

ADDRESS = 'AA:BB:CC:DD:EE:FF'


def connection(role):
    return {ADDRESS: {'adapter': 'hci1', 'handle': 3, 'role': role}}


class BluetoothRolesTest(unittest.TestCase):
    @mock.patch.object(bluetooth_roles.subprocess, 'run')
    def test_connection_roles_are_scoped_to_adapter(self, run):
        run.return_value.stdout = 'Connections:\n\t> ACL AA:BB:CC:DD:EE:FF handle 3 state 1 lm CENTRAL\n'
        self.assertEqual(bluetooth_roles.get_connection_roles(['hci1']), connection('Central'))

    @mock.patch.object(bluetooth_roles, '_adapter_names', return_value=['hci0', 'hci1'])
    @mock.patch.object(bluetooth_roles, 'get_connection_roles')
    @mock.patch.object(bluetooth_roles.subprocess, 'run')
    def test_each_direction_uses_actual_adapter_and_verifies(self, run, roles, names):
        for before, target in [('Central', 'Peripheral'), ('Peripheral', 'Central')]:
            with self.subTest(target=target):
                roles.side_effect = [connection(before), connection(target)]
                result = bluetooth_roles.set_connection_role(ADDRESS.lower(), target.lower())
                self.assertEqual(result['role'], target)
                run.assert_called_with(['hcitool', '-i', 'hci1', 'sr', ADDRESS, target.lower()],
                                       capture_output=True, text=True, timeout=2, check=True)
                roles.assert_called_with(['hci1'])

    @mock.patch.object(bluetooth_roles, 'get_connection_roles', return_value=connection('Central'))
    @mock.patch.object(bluetooth_roles.subprocess, 'run')
    def test_already_requested_role_is_noop(self, run, roles):
        self.assertTrue(bluetooth_roles.set_connection_role(ADDRESS, 'central')['success'])
        run.assert_not_called()

    @mock.patch.object(bluetooth_roles, 'get_connection_roles', return_value={})
    @mock.patch.object(bluetooth_roles.subprocess, 'run')
    def test_disconnected_controller_does_not_run_switch(self, run, roles):
        with self.assertRaisesRegex(RuntimeError, 'no longer connected'):
            bluetooth_roles.set_connection_role(ADDRESS, 'central')
        run.assert_not_called()

    @mock.patch.object(bluetooth_roles.time, 'sleep')
    @mock.patch.object(bluetooth_roles, 'get_connection_roles', return_value=connection('Central'))
    @mock.patch.object(bluetooth_roles.subprocess, 'run')
    def test_successful_command_does_not_hide_rejected_role(self, run, roles, sleep):
        with self.assertRaisesRegex(RuntimeError, 'not accepted'):
            bluetooth_roles.set_connection_role(ADDRESS, 'peripheral')
        self.assertEqual(run.call_count, 1)

    @mock.patch.object(bluetooth_roles, 'get_connection_roles')
    @mock.patch.object(bluetooth_roles.subprocess, 'run')
    def test_disconnect_during_switch_is_reported(self, run, roles):
        roles.side_effect = [connection('Central'), {}]
        with self.assertRaisesRegex(RuntimeError, 'disconnected during'):
            bluetooth_roles.set_connection_role(ADDRESS, 'peripheral')

    @mock.patch.object(bluetooth_roles, 'get_connection_roles', return_value=connection('Central'))
    @mock.patch.object(bluetooth_roles.subprocess, 'run', side_effect=subprocess.TimeoutExpired('hcitool', 2))
    def test_timeout_releases_lock(self, run, roles):
        with self.assertRaisesRegex(RuntimeError, 'role change failed'):
            bluetooth_roles.set_connection_role(ADDRESS, 'peripheral')
        self.assertFalse(bluetooth_roles._ROLE_CHANGE_LOCK.locked())

    @mock.patch.object(bluetooth_roles.subprocess, 'run')
    def test_invalid_input_never_reaches_hardware(self, run):
        for address, role in [('--help', 'central'), (ADDRESS, 'invalid')]:
            with self.assertRaises(ValueError):
                bluetooth_roles.set_connection_role(address, role)
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
