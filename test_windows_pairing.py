"""Pairing progress tests that never invoke Bluetooth or the real CLI."""

import io
from types import SimpleNamespace
import unittest
from unittest import mock

import windows_pairing as pairing


SERIAL = '00:06:F7:A3:5B:AD'
SUCCESS = ('PSMove #1 connected via USB.\nUnplug the controller.\nConnection verified.\n'
           'Pairing of #1 succeeded!\nController address: ' + SERIAL.lower() + '\n')


class WindowsPairingTest(unittest.TestCase):
    def run_output(self, output, code=1):
        states = []
        process = mock.MagicMock()
        process.__enter__.return_value = process
        process.wait.return_value = code
        def lines():
            # The instruction must be available before the child flushes stdout.
            self.assertEqual(states[0]['phase'], 'waiting')
            self.assertIn('PS button', states[0]['message'])
            yield from output.splitlines(keepends=True)
        process.stdout = lines()
        console = io.StringIO()
        with mock.patch.object(pairing.subprocess, 'Popen', return_value=process) as popen, \
                mock.patch.object(pairing.sys, 'stdout', console):
            result = pairing.run(['psmove.exe', 'pair'], {'TEST': 'yes'}, SERIAL, states.append)
        self.assertEqual(console.getvalue(), output)
        self.assertEqual(popen.call_args.args[0], ['psmove.exe', 'pair'])
        self.assertEqual(popen.call_args.kwargs['env'], {'TEST': 'yes'})
        return result, states

    def test_real_success_for_requested_controller_finishes_waiting(self):
        paired, states = self.run_output(SUCCESS)
        self.assertTrue(paired)
        self.assertEqual(states[-1]['phase'], 'verified')
        self.assertEqual(states[-1]['address'], SERIAL)

    def test_exit_code_alone_admin_error_or_unverified_connection_is_not_success(self):
        for output, code in (('This program must be run as Administrator.\n', 1),
                             (SUCCESS.replace('Connection verified.\n', ''), 1),
                             (SUCCESS.replace(SERIAL.lower(), '00:06:f7:00:00:02'), 1),
                             (SUCCESS, 0), ('Pairing of #1 failed.\n', 1)):
            with self.subTest(output=output, code=code):
                paired, states = self.run_output(output, code)
                self.assertFalse(paired)
                self.assertEqual(states[-1]['phase'], 'failed')

    def test_verification_does_not_leak_from_previous_usb_controller(self):
        output = SUCCESS.replace(SERIAL.lower(), '00:06:f7:00:00:02')
        output += SUCCESS.replace('Connection verified.\n', '').replace('#1', '#2')
        paired, _ = self.run_output(output)
        self.assertFalse(paired)

    def test_launch_failure_clears_waiting_and_preserves_exception(self):
        states = []
        with mock.patch.object(pairing.subprocess, 'Popen', side_effect=OSError('missing')):
            with self.assertRaises(OSError):
                pairing.run(['psmove.exe', 'pair'], {}, SERIAL, states.append)
        self.assertEqual([state['phase'] for state in states], ['waiting', 'failed'])

    def test_cancel_stops_only_owned_child_and_clears_waiting(self):
        states = []
        process = mock.MagicMock()
        process.__enter__.return_value = process
        process.poll.return_value = None
        def cancelled():
            raise KeyboardInterrupt
            yield ''
        process.stdout = cancelled()
        with mock.patch.object(pairing.subprocess, 'Popen', return_value=process):
            with self.assertRaises(KeyboardInterrupt):
                pairing.run(['psmove.exe', 'pair'], {}, SERIAL, states.append)
        process.terminate.assert_called_once()
        self.assertEqual(states[-1]['phase'], 'failed')

    def test_manager_routes_native_windows_to_progress_runner_and_restarts_api(self):
        import controller_manager
        from pathlib import Path
        with mock.patch.object(controller_manager.runtime_platform, 'is_proton', return_value=False), \
                mock.patch.object(controller_manager.runtime_platform, 'is_windows', return_value=True), \
                mock.patch.object(controller_manager, '_binding_paths', return_value=(None, None, Path('test-cli'))), \
                mock.patch.object(controller_manager, 'stop_manager') as stop, \
                mock.patch.object(controller_manager, 'start_manager') as start, \
                mock.patch.object(pairing, 'run', side_effect=OSError('missing')) as run:
            callback = mock.Mock()
            with self.assertRaises(OSError):
                controller_manager.pair_controller(None, serial=SERIAL, publish=callback)
            self.assertEqual(run.call_args.args[0], [str(Path('test-cli') / 'psmove.exe'), 'pair'])
            self.assertEqual(run.call_args.args[2:], (SERIAL, callback))
            stop.assert_called_once()
            start.assert_called_once()

    def test_terminal_result_expires_but_waiting_remains_visible(self):
        ns = SimpleNamespace(windows_pairing=dict(phase='verified', updated_at=10))
        with mock.patch.object(pairing.time, 'monotonic', return_value=41):
            self.assertEqual(pairing.status(ns), {})
            ns.windows_pairing['phase'] = 'waiting'
            self.assertEqual(pairing.status(ns)['phase'], 'waiting')
        self.assertEqual(pairing.status(SimpleNamespace()), {})


if __name__ == '__main__':
    unittest.main()
