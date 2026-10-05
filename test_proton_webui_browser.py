"""Test host browser ownership, plus X11 tagging on a private virtual display."""

import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import proton_webui_browser as host


class HostBrowserTest(unittest.TestCase):
    def test_auto_session_detection_does_not_treat_every_steam_deck_as_gaming_mode(self):
        self.assertFalse(host.gaming_mode({'XDG_CURRENT_DESKTOP': 'KDE', 'SteamDeck': '1'}))
        self.assertTrue(host.gaming_mode({'XDG_CURRENT_DESKTOP': 'gamescope'}))
        self.assertTrue(host.gaming_mode({'WAYLAND_DISPLAY': 'gamescope-0'}))
        display = mock.Mock(root=1)
        display.cardinal.return_value = 123
        self.assertTrue(host.gaming_mode({}, display))
        display.cardinal.assert_called_once_with(1, 'GAMESCOPE_PID')
        display.cardinal.reset_mock()
        self.assertFalse(host.gaming_mode({'XDG_CURRENT_DESKTOP': 'KDE',
                                          'GAMESCOPE_WAYLAND_DISPLAY': 'gamescope-0'}, display))
        display.cardinal.assert_not_called()
        self.assertTrue(host.gaming_mode({'GAMESCOPE_WAYLAND_DISPLAY': 'gamescope-0'}))

    def test_installed_flatpak_browser_is_used_without_installing_or_overriding_permissions(self):
        with mock.patch.object(host.shutil, 'which', return_value='/usr/bin/flatpak'), \
                mock.patch.object(host.subprocess, 'run', return_value=mock.Mock(stdout='org.mozilla.firefox\n')) as run:
            self.assertEqual(host.installed_browser(),
                             ('firefox', ['/usr/bin/flatpak', 'run', '--socket=x11'], 'org.mozilla.firefox'))
        run.assert_called_once_with(['/usr/bin/flatpak', 'list', '--app', '--columns=application'],
                                    capture_output=True, text=True, check=True, timeout=3)

    def test_native_browser_fallback_and_missing_browser_message(self):
        with mock.patch.object(host.shutil, 'which', side_effect=lambda name: '/usr/bin/firefox' if name == 'firefox' else None):
            self.assertEqual(host.installed_browser(), ('firefox', ['/usr/bin/firefox'], ''))
        with mock.patch.object(host.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'Install one in Desktop Mode'):
                host.installed_browser()

    def test_app_commands_use_isolated_profile_and_game_x11_display(self):
        command = host.browser_command('chromium', ['flatpak', 'run', '--socket=x11'],
                                       'org.chromium.Chromium', '/profile', 'JoustMania_UI_mine',
                                       'http://localhost:8090', ':1', 8)
        self.assertIn('--instance-id-fd=8', command)
        self.assertIn('--env=DISPLAY=:1', command)
        self.assertIn('--ozone-platform=x11', command)
        self.assertIn('--class=JoustMania_UI_mine', command)
        self.assertIn('--user-data-dir=/profile', command)
        self.assertIn('--app=http://localhost:8090', command)
        firefox = host.browser_command('firefox', ['firefox'], '', '/profile', 'mine', 'http://localhost', ':1')
        self.assertIn('--no-remote', firefox)
        self.assertIn('--new-instance', firefox)
        self.assertEqual(firefox[-2:], ['--kiosk', 'http://localhost'])
        self.assertNotIn('-c', command)

    def test_desktop_default_browser_is_not_owned_or_stopped(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE'}, clear=True), \
                mock.patch.object(host, 'X11', side_effect=RuntimeError('No X display')), \
                mock.patch.object(host.shutil, 'which', return_value='/usr/bin/xdg-open'), \
                mock.patch.object(host.subprocess, 'Popen') as popen, \
                mock.patch.object(host, 'stop_owned_browser') as stop:
            output = Path(directory) / 'result.json'
            host.launch(output, 'http://localhost:8090', 1093850, 'desktop', 'mine', '')
            self.assertEqual(json.loads(output.read_text()), {'success': True, 'mode': 'desktop'})
        self.assertEqual(popen.call_args.args[0], ['/usr/bin/xdg-open', 'http://localhost:8090'])
        stop.assert_not_called()

    def test_game_window_is_tagged_and_profile_removed_after_game_stops(self):
        browser = mock.Mock()
        browser.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(host.Path, 'home', return_value=Path(directory)), \
                mock.patch.object(host, 'X11') as display, \
                mock.patch.object(host, 'installed_browser', return_value=('firefox', ['firefox'], '')), \
                mock.patch.object(host.subprocess, 'Popen', return_value=browser) as popen, \
                mock.patch.object(host, 'game_alive', side_effect=[True, False, False, False, False, False]), \
                mock.patch.object(host, 'write_status', wraps=host.write_status) as publish, \
                mock.patch.object(host.time, 'sleep'), \
                mock.patch.object(host, 'stop_owned_browser') as stop:
            output = Path(directory) / 'result.json'
            display.return_value.tag_window.return_value = 123
            host.launch(output, 'http://localhost:8090', 1093850, 'game', 'mine', ':1')
            self.assertEqual(json.loads(output.read_text())['phase'], 'closed')
            ready = publish.call_args_list[0].args[1]
            self.assertEqual(ready['phase'], 'ready')
            self.assertEqual(ready['window'], 123)
            self.assertEqual(ready['display'], ':1')
            command = popen.call_args.args[0]
            profile = command[command.index('--profile') + 1]
            self.assertFalse(Path(profile).exists())
        display.return_value.tag_window.assert_called_once_with('JoustMania_UI_mine', 1093850)
        display.return_value.close.assert_called_once()
        stop.assert_called_once()
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
        self.assertEqual(popen.call_args.kwargs['env']['DISPLAY'], ':1')

    def test_game_window_failure_reports_error_and_cleans_its_browser(self):
        browser = mock.Mock()
        browser.poll.return_value = 2
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(host.Path, 'home', return_value=Path(directory)), \
                mock.patch.object(host, 'X11'), \
                mock.patch.object(host, 'installed_browser', return_value=('firefox', ['firefox'], '')), \
                mock.patch.object(host.subprocess, 'Popen', return_value=browser), \
                mock.patch.object(host, 'stop_owned_browser') as stop:
            output = Path(directory) / 'result.json'
            host.launch(output, 'http://localhost', 1093850, 'game', 'mine', ':1')
            state = json.loads(output.read_text())
            self.assertFalse(state['success'])
            self.assertIn('did not create', state['error'])
        stop.assert_called_once()

    def test_flatpak_cleanup_uses_only_instance_id_written_by_our_launch(self):
        browser = mock.Mock(pid=123)
        browser.poll.return_value = None
        with mock.patch.object(host.subprocess, 'run') as run, mock.patch.object(host.os, 'killpg', create=True) as kill:
            host.stop_owned_browser(browser, '/usr/bin/flatpak', io.BytesIO(b'987654\n'))
        self.assertEqual(run.call_args.args[0], ['/usr/bin/flatpak', 'kill', '987654'])
        kill.assert_called_once_with(123, signal.SIGTERM)
        with mock.patch.object(host.subprocess, 'run') as run, mock.patch.object(host.os, 'killpg', create=True):
            host.stop_owned_browser(browser, '/usr/bin/flatpak', io.BytesIO(b'org.mozilla.firefox'))
        run.assert_not_called()

    def test_already_closed_browser_does_not_terminate_any_process(self):
        browser = mock.Mock()
        browser.poll.return_value = 0
        with mock.patch.object(host.os, 'killpg', create=True) as kill, mock.patch.object(host.subprocess, 'run') as run:
            host.stop_owned_browser(browser, 'flatpak', io.BytesIO(b'123'))
        kill.assert_not_called()
        run.assert_not_called()

    def test_host_health_requires_this_game_instance_and_bypasses_proxy(self):
        with mock.patch.object(host.request, 'build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b'{"service":"JoustMania","launch_id":"mine"}'
            self.assertTrue(host.game_alive('http://localhost:8090', 'mine'))
            self.assertFalse(host.game_alive('http://localhost:8090', 'other'))
            self.assertEqual(opener.call_args.args[0].proxies, {})


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('Xvfb'),
                     'Requires Linux Xvfb for a private virtual display')
class X11IntegrationTest(unittest.TestCase):
    def start_display(self):
        read_fd, write_fd = os.pipe()
        server = subprocess.Popen(['Xvfb', '-displayfd', str(write_fd), '-screen', '0', '1280x800x24', '-nolisten', 'tcp'],
                                  pass_fds=(write_fd,), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        os.close(write_fd)
        def stop_server():
            server.terminate()
            server.communicate(timeout=5)
        self.addCleanup(stop_server)
        try:
            self.assertTrue(select.select([read_fd], [], [], 5)[0], 'Private display did not start')
            return ':' + os.read(read_fd, 64).decode().strip()
        finally:
            os.close(read_fd)

    def test_real_x11_tag_affects_only_our_window(self):
        x11 = host.X11(self.start_display())
        self.addCleanup(x11.close)
        pointer, window = ctypes.c_void_p, ctypes.c_ulong
        x11.lib.XCreateSimpleWindow.argtypes = [pointer, window, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
                                               ctypes.c_uint, ctypes.c_uint, window, window]
        x11.lib.XCreateSimpleWindow.restype = window
        x11.lib.XSetClassHint.argtypes = [pointer, window, ctypes.POINTER(host.ClassHint)]
        x11.lib.XSetClassHint.restype = ctypes.c_int
        x11.lib.XMapWindow.argtypes = [pointer, window]
        x11.lib.XMapWindow.restype = ctypes.c_int
        x11.lib.XDestroyWindow.argtypes = [pointer, window]
        x11.lib.XDestroyWindow.restype = ctypes.c_int
        def make_window(name, mapped=True):
            created = x11.lib.XCreateSimpleWindow(x11.display, x11.root, 0, 0, 600, 400, 0, 0, 0)
            resource = ctypes.create_string_buffer(name.encode())
            hint = host.ClassHint(ctypes.cast(resource, pointer), ctypes.cast(resource, pointer))
            x11.lib.XSetClassHint(x11.display, created, ctypes.byref(hint))
            if mapped:
                x11.lib.XMapWindow(x11.display, created)
            return created
        hidden = make_window('JoustMania_UI_mine', mapped=False)
        ours, personal = make_window('JoustMania_UI_mine'), make_window('PersonalBrowser')
        x11.lib.XSelectInput.argtypes = [pointer, window, ctypes.c_long]
        x11.lib.XSelectInput.restype = ctypes.c_int
        x11.lib.XPending.argtypes = [pointer]
        x11.lib.XPending.restype = ctypes.c_int
        x11.lib.XNextEvent.argtypes = [pointer, ctypes.POINTER(host.XEvent)]
        x11.lib.XNextEvent.restype = ctypes.c_int
        x11.lib.XSync(x11.display, False)
        x11.lib.XSelectInput(x11.display, x11.root, 1 << 19)  # SubstructureNotifyMask
        self.assertFalse(x11.tag_window('JoustMania_UI_other', 1093850))
        self.assertEqual(x11.tag_window('JoustMania_UI_mine', 1093850), ours)
        self.assertEqual(x11.cardinal(ours, 'STEAM_GAME'), 1093850)
        self.assertIsNone(x11.cardinal(personal, 'STEAM_GAME'))
        self.assertIsNone(x11.cardinal(hidden, 'STEAM_GAME'))
        self.assertEqual((x11.attributes(ours).width, x11.attributes(ours).height), (1280, 800))
        self.assertEqual((x11.attributes(personal).width, x11.attributes(personal).height), (600, 400))
        messages = {}
        while x11.lib.XPending(x11.display):
            event = host.XEvent()
            x11.lib.XNextEvent(x11.display, ctypes.byref(event))
            if event.client.type == 33:
                self.assertEqual(event.client.window, ours)
                self.assertEqual(event.client.format, 32)
                messages[event.client.message_type] = list(event.client.data.longs)
        active = x11.lib.XInternAtom(x11.display, b'_NET_ACTIVE_WINDOW', False)
        state = x11.lib.XInternAtom(x11.display, b'_NET_WM_STATE', False)
        fullscreen = x11.lib.XInternAtom(x11.display, b'_NET_WM_STATE_FULLSCREEN', False)
        self.assertEqual(messages[active][:3], [1, 0, 0])
        self.assertEqual(messages[state][:4], [1, fullscreen, 0, 1])
        x11.lib.XDestroyWindow(x11.display, ours)
        self.assertFalse(x11.tag_window('JoustMania_UI_mine', 1093850))
        x11.lib.XDestroyWindow(x11.display, personal)
        x11.lib.XDestroyWindow(x11.display, hidden)

    def test_real_detached_helper_returns_then_cleans_owned_browser_and_profile(self):
        self.check_detached_helper(remove_status=False)

    def test_real_detached_helper_cleanup_tolerates_removed_status_directory(self):
        self.check_detached_helper(remove_status=True)

    def test_application_exit_closes_owned_browser_while_web_health_is_still_alive(self):
        self.check_detached_helper(remove_status=False, request_stop=True)

    def check_detached_helper(self, remove_status, request_stop=False):
        display = self.start_display()
        running = [True]
        class Health(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps(dict(service='JoustMania', launch_id='mine' if running[0] else 'stopped')).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *_):
                pass
        health = ThreadingHTTPServer(('127.0.0.1', 0), Health)
        worker = threading.Thread(target=health.serve_forever, daemon=True)
        worker.start()
        def stop_health():
            running[0] = False
            health.shutdown()
            health.server_close()
            worker.join(timeout=5)
        self.addCleanup(stop_health)
        with tempfile.TemporaryDirectory() as directory:
            status_directory = Path(directory) / 'status'
            status_directory.mkdir()
            output = status_directory / 'result.json'
            output.touch()
            url = 'http://127.0.0.1:' + str(health.server_address[1])
            command = [sys.executable, str(Path(__file__).resolve()), '--launch-test-helper',
                       str(output), url, display, directory]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(output.read_text())['success'])
            profiles = list((Path(directory) / '.cache/joustmania-ui').glob('profile-*'))
            self.assertEqual(len(profiles), 1)
            browser_pid = int((profiles[0] / 'test-browser.pid').read_text())
            def stop_test_browser():
                try:
                    os.killpg(browser_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            self.addCleanup(stop_test_browser)
            ready = json.loads(output.read_text())
            self.assertEqual(ready['phase'], 'ready')
            self.assertEqual(ready['display'], display)
            self.assertIsInstance(ready['window'], int)
            if remove_status:
                # A failed Wine-side handoff can remove this directory while
                # the host helper still owns its browser. Cleanup must work.
                output.unlink()
                # A heartbeat may be between its temporary write and rename.
                # Rename the whole directory first, then remove its contents.
                abandoned = status_directory.with_name('abandoned-status')
                status_directory.rename(abandoned)
                for pending in abandoned.iterdir():
                    pending.unlink()
                abandoned.rmdir()
            if request_stop:
                output.with_name(output.name + '.stop').touch()
            else:
                running[0] = False
            deadline = time.monotonic() + 12
            while profiles[0].exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertFalse(profiles[0].exists(), 'Detached helper did not clean up its browser profile')
            if not remove_status:
                self.assertEqual(json.loads(output.read_text())['phase'], 'closed')


def fake_browser():
    """A private X11 window stands in for a browser, never a real desktop app."""
    x11 = host.X11(os.environ['DISPLAY'])
    pointer, window = ctypes.c_void_p, ctypes.c_ulong
    x11.lib.XCreateSimpleWindow.argtypes = [pointer, window, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
                                           ctypes.c_uint, ctypes.c_uint, window, window]
    x11.lib.XCreateSimpleWindow.restype = window
    x11.lib.XSetClassHint.argtypes = [pointer, window, ctypes.POINTER(host.ClassHint)]
    x11.lib.XSetClassHint.restype = ctypes.c_int
    x11.lib.XMapWindow.argtypes = [pointer, window]
    x11.lib.XMapWindow.restype = ctypes.c_int
    created = x11.lib.XCreateSimpleWindow(x11.display, x11.root, 0, 0, 600, 400, 0, 0, 0)
    resource = ctypes.create_string_buffer(sys.argv[sys.argv.index('--class') + 1].encode())
    hint = host.ClassHint(ctypes.cast(resource, pointer), ctypes.cast(resource, pointer))
    x11.lib.XSetClassHint(x11.display, created, ctypes.byref(hint))
    x11.lib.XMapWindow(x11.display, created)
    x11.lib.XFlush(x11.display)
    profile = Path(sys.argv[sys.argv.index('--profile') + 1])
    (profile / 'test-browser.pid').write_text(str(os.getpid()))
    while True:
        time.sleep(1)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--fake-browser']:
        fake_browser()
    elif sys.argv[1:2] == ['--launch-test-helper']:
        output, url, display, directory = sys.argv[2:]
        sys.argv = ['helper', output, url, '1093850', 'game', 'mine', display]
        with mock.patch.object(host.Path, 'home', return_value=Path(directory)), \
                mock.patch.object(host, 'installed_browser', return_value=(
                    'firefox', [sys.executable, str(Path(__file__).resolve()), '--fake-browser'], '')):
            sys.exit(host.main())
    else:
        unittest.main()
