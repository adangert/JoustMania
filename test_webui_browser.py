import os
import json
import tempfile
from pathlib import Path
import unittest
from unittest import mock

import proton_psmove
import webui_browser as browser


class WebUIBrowserTest(unittest.TestCase):
    def test_native_linux_and_pi_never_start_a_browser_thread(self):
        with mock.patch.object(browser.runtime_platform, 'is_windows', return_value=False), \
                mock.patch.object(browser.threading, 'Thread') as thread:
            self.assertIsNone(browser.start('http://localhost', 'launch', lambda: True))
        thread.assert_not_called()

    def test_auto_open_can_be_disabled(self):
        with mock.patch.object(browser.runtime_platform, 'is_windows', return_value=True), \
                mock.patch.dict(os.environ, {'JOUSTMANIA_OPEN_BROWSER': '0'}), \
                mock.patch.object(browser.threading, 'Thread') as thread:
            self.assertIsNone(browser.start('http://localhost', 'launch', lambda: True))
        thread.assert_not_called()

    def test_worker_waits_for_ready_then_opens_windows_browser_once(self):
        with mock.patch.object(browser.runtime_platform, 'is_proton', return_value=False), \
                mock.patch.object(browser, '_ready', side_effect=[False, True]), \
                mock.patch.object(browser.time, 'sleep') as sleep, \
                mock.patch.object(browser.webbrowser, 'open_new_tab', return_value=True) as open_tab:
            browser._open_when_ready('http://localhost:8091', 'launch', lambda: True)
        sleep.assert_called_once_with(0.25)
        open_tab.assert_called_once_with('http://localhost:8091')

    def test_proton_uses_linux_host_not_windows_browser(self):
        with mock.patch.object(browser.runtime_platform, 'is_proton', return_value=True), \
                mock.patch.object(browser, '_ready', return_value=True), \
                mock.patch.object(proton_psmove, 'open_webui', return_value=True) as open_host, \
                mock.patch.object(browser.webbrowser, 'open_new_tab') as open_tab:
            browser._open_when_ready('http://localhost:8090', 'launch', lambda: True)
        open_host.assert_called_once_with('http://localhost:8090', 'launch')
        open_tab.assert_not_called()

    def test_failed_web_process_does_not_open_a_browser(self):
        with mock.patch.object(browser, '_ready') as ready, \
                mock.patch.object(browser.webbrowser, 'open_new_tab') as open_tab:
            browser._open_when_ready('http://localhost', 'launch', lambda: False)
        ready.assert_not_called()
        open_tab.assert_not_called()

    def test_timeout_does_not_open_a_browser(self):
        with mock.patch.object(browser.time, 'monotonic', side_effect=[0, 31]), \
                mock.patch.object(browser.webbrowser, 'open_new_tab') as open_tab:
            browser._open_when_ready('http://localhost', 'launch', lambda: True)
        open_tab.assert_not_called()

    def test_readiness_matches_instance_and_bypasses_proxy(self):
        with mock.patch.object(browser.request, 'build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b'{"service":"JoustMania","launch_id":"mine"}'
            self.assertTrue(browser._ready('http://localhost:8090/', 'mine'))
            self.assertFalse(browser._ready('http://localhost:8090', 'other'))
            opener.return_value.open.assert_called_with('http://localhost:8090/health', timeout=0.5)
            self.assertEqual(opener.call_args.args[0].proxies, {})

    def test_proton_host_url_is_an_argument_not_shell_code(self):
        def launch(arguments, **kwargs):
            Path(arguments[2]).write_text(json.dumps(dict(success=True, mode='game')), encoding='utf-8')
            return 0
        with mock.patch.object(proton_psmove, '_run_host', side_effect=launch) as run, \
                mock.patch.object(proton_psmove, '_unix_path', side_effect=str):
            self.assertTrue(proton_psmove.open_webui('http://localhost:8090', 'launch'))
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[0], '/usr/bin/python3')
        self.assertEqual(arguments[3], 'http://localhost:8090')
        self.assertNotIn('-c', arguments)

    def test_browser_exception_does_not_interrupt_game_startup(self):
        with mock.patch.object(browser.runtime_platform, 'is_proton', return_value=False), \
                mock.patch.object(browser, '_ready', return_value=True), \
                mock.patch.object(browser.webbrowser, 'open_new_tab', side_effect=OSError('No browser')), \
                self.assertLogs(browser.logger, level='ERROR'):
            browser._open_when_ready('http://localhost', 'launch', lambda: True)


class ProtonBrowserHandoffTest(unittest.TestCase):
    def setUp(self):
        previous = proton_psmove._browser_session
        proton_psmove._browser_session = None
        self.addCleanup(setattr, proton_psmove, '_browser_session', previous)

    @staticmethod
    def host_response(state):
        def launch(arguments, **kwargs):
            Path(arguments[2]).write_text(json.dumps(state), encoding='utf-8')
            return 0
        return launch

    def test_desktop_keeps_console_and_removes_startup_result(self):
        with mock.patch.object(proton_psmove, '_run_host', side_effect=self.host_response(
                dict(success=True, mode='desktop'))) as run, \
                mock.patch.object(proton_psmove, '_unix_path', side_effect=str), \
                mock.patch.object(proton_psmove, '_hide_game_console') as hide, \
                mock.patch.object(proton_psmove.threading, 'Thread') as thread:
            self.assertTrue(proton_psmove.open_webui('http://localhost:8090', 'mine'))
        hide.assert_not_called()
        thread.assert_not_called()
        self.assertFalse(Path(run.call_args.args[0][2]).parent.exists())

    def test_ready_game_hides_only_after_window_ready_and_restores_on_close(self):
        restore = mock.Mock()
        with mock.patch.object(proton_psmove, '_run_host', side_effect=self.host_response(
                dict(success=True, mode='game', phase='ready', window=123, display=':1', browser='firefox'))), \
                mock.patch.object(proton_psmove, '_unix_path', side_effect=str), \
                mock.patch.object(proton_psmove, '_hide_game_console', return_value=restore) as hide, \
                mock.patch.object(proton_psmove.threading, 'Thread') as thread:
            self.assertTrue(proton_psmove.open_webui('http://localhost:8090', 'mine'))
        hide.assert_called_once_with()
        thread.return_value.start.assert_called_once_with()
        self.assertTrue(thread.call_args.kwargs['daemon'])
        output, temporary, callback = thread.call_args.kwargs['args']
        self.addCleanup(temporary.cleanup)
        self.assertTrue(output.exists())
        output.write_text(json.dumps(dict(success=True, phase='closed')))
        thread.call_args.kwargs['target'](output, temporary, callback)
        restore.assert_called_once_with()
        self.assertFalse(output.parent.exists())

    def test_failed_browser_never_hides_console(self):
        with mock.patch.object(proton_psmove, '_run_host', side_effect=self.host_response(
                dict(success=False, error='Browser unavailable'))) as run, \
                mock.patch.object(proton_psmove, '_unix_path', side_effect=str), \
                mock.patch.object(proton_psmove, '_hide_game_console') as hide:
            with self.assertRaisesRegex(RuntimeError, 'Browser unavailable'):
                proton_psmove.open_webui('http://localhost:8090', 'mine')
        hide.assert_not_called()
        self.assertFalse(Path(run.call_args.args[0][2]).parent.exists())

    def test_game_status_without_ready_window_does_not_hide_console(self):
        for state in [dict(success=True, mode='game'),
                      dict(success=True, mode='game', phase='closed', window=123),
                      dict(success=True, mode='game', phase='ready', window=0)]:
            with self.subTest(state=state), \
                    mock.patch.object(proton_psmove, '_run_host', side_effect=self.host_response(state)), \
                    mock.patch.object(proton_psmove, '_unix_path', side_effect=str), \
                    mock.patch.object(proton_psmove, '_hide_game_console') as hide:
                self.assertTrue(proton_psmove.open_webui('http://localhost:8090', 'mine'))
            hide.assert_not_called()

    def test_thread_start_failure_restores_console_and_cleans_status(self):
        restore = mock.Mock()
        with mock.patch.object(proton_psmove, '_run_host', side_effect=self.host_response(
                dict(success=True, mode='game', phase='ready', window=123))) as run, \
                mock.patch.object(proton_psmove, '_unix_path', side_effect=str), \
                mock.patch.object(proton_psmove, '_hide_game_console', return_value=restore), \
                mock.patch.object(proton_psmove.threading, 'Thread') as thread:
            thread.return_value.start.side_effect = RuntimeError('No thread available')
            with self.assertRaisesRegex(RuntimeError, 'No thread available'):
                proton_psmove.open_webui('http://localhost:8090', 'mine')
        restore.assert_called_once_with()
        self.assertFalse(Path(run.call_args.args[0][2]).parent.exists())

    def test_handoff_uses_only_the_associated_visible_console_handle(self):
        kernel32, user32 = mock.Mock(), mock.Mock()
        kernel32.GetConsoleWindow.return_value = 42
        user32.IsWindowVisible.side_effect = [1, 0]
        with mock.patch.object(proton_psmove.ctypes, 'WinDLL', create=True,
                               side_effect=[kernel32, user32]):
            restore = proton_psmove._hide_game_console()
            restore()
        kernel32.GetConsoleWindow.assert_called_once_with()
        self.assertEqual(user32.ShowWindow.call_args_list, [mock.call(42, 0), mock.call(42, 5)])

    def test_no_console_or_invisible_pseudoconsole_is_not_hidden(self):
        for handle, visible in [(0, 1), (42, 0)]:
            kernel32, user32 = mock.Mock(), mock.Mock()
            kernel32.GetConsoleWindow.return_value = handle
            user32.IsWindowVisible.return_value = visible
            with self.subTest(handle=handle), \
                    mock.patch.object(proton_psmove.ctypes, 'WinDLL', create=True,
                                      side_effect=[kernel32, user32]):
                self.assertIsNone(proton_psmove._hide_game_console())
            user32.ShowWindow.assert_not_called()

    def test_unavailable_console_api_is_nonfatal(self):
        with mock.patch.object(proton_psmove.ctypes, 'WinDLL', create=True, side_effect=OSError('Unavailable')), \
                self.assertLogs(proton_psmove.logger, level='WARNING'):
            self.assertIsNone(proton_psmove._hide_game_console())

    def test_missing_status_restores_console_and_cleans_up(self):
        output, temporary, restore = mock.Mock(), mock.Mock(), mock.Mock()
        output.stat.side_effect = FileNotFoundError()
        with mock.patch.object(proton_psmove.time, 'monotonic', side_effect=[0, 31]), \
                self.assertLogs(proton_psmove.logger, level='WARNING'):
            proton_psmove._watch_game_browser(output, temporary, restore)
        restore.assert_called_once_with()
        temporary.cleanup.assert_called_once_with()

    def test_stale_ready_status_restores_console_if_host_helper_dies(self):
        output, temporary, restore = mock.Mock(), mock.Mock(), mock.Mock()
        output.stat.return_value.st_mtime_ns = 1
        output.read_text.return_value = '{"success":true,"phase":"ready"}'
        with mock.patch.object(proton_psmove.time, 'monotonic', side_effect=[0, 1, 2, 32]), \
                mock.patch.object(proton_psmove.time, 'sleep') as sleep, \
                self.assertLogs(proton_psmove.logger, level='WARNING'):
            proton_psmove._watch_game_browser(output, temporary, restore)
        sleep.assert_called_once_with(1)
        restore.assert_called_once_with()
        temporary.cleanup.assert_called_once_with()

    def test_heartbeat_keeps_console_handoff_until_browser_closes(self):
        output, temporary, restore = mock.Mock(), mock.Mock(), mock.Mock()
        output.stat.side_effect = [mock.Mock(st_mtime_ns=n) for n in [1, 2, 3]]
        output.read_text.side_effect = ['{"success":true,"phase":"ready"}',
                                        '{"success":true,"phase":"ready"}',
                                        '{"success":true,"phase":"closed"}']
        with mock.patch.object(proton_psmove.time, 'monotonic', side_effect=[0, 1, 10, 20, 45]), \
                mock.patch.object(proton_psmove.time, 'sleep') as sleep:
            proton_psmove._watch_game_browser(output, temporary, restore)
        self.assertEqual(sleep.call_count, 2)
        restore.assert_called_once_with()
        temporary.cleanup.assert_called_once_with()

    def test_application_exit_requests_only_its_owned_browser_to_close(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'result.json'
            output.touch()
            worker = mock.Mock()
            proton_psmove._browser_session = (os.getpid(), output, worker)
            proton_psmove.close_webui()
            self.assertTrue(output.with_name('result.json.stop').exists())
            worker.join.assert_called_once_with(timeout=8)
            self.assertIsNone(proton_psmove._browser_session)
            proton_psmove.close_webui()  # Safe to call again at shutdown.
            worker.join.assert_called_once()

    def test_child_process_cannot_close_parent_browser(self):
        output, worker = mock.Mock(), mock.Mock()
        proton_psmove._browser_session = (os.getpid() + 1, output, worker)
        proton_psmove.close_webui()
        output.with_name.assert_not_called()
        worker.join.assert_not_called()

    def test_already_closed_browser_session_is_safe_to_stop(self):
        output, worker = mock.Mock(), mock.Mock()
        output.name = 'result.json'
        output.with_name.return_value.touch.side_effect = FileNotFoundError()
        proton_psmove._browser_session = (os.getpid(), output, worker)
        proton_psmove.close_webui()
        worker.join.assert_called_once_with(timeout=8)
        self.assertIsNone(proton_psmove._browser_session)


if __name__ == '__main__':
    unittest.main()
