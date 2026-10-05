"""Proton exit UI and owned-process shutdown, without starting the game."""

import json
import multiprocessing
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock
from urllib import parse, request

from werkzeug.serving import make_server

import application_lifecycle as lifecycle
import webui


class ExitPageTest(unittest.TestCase):
    def setUp(self):
        self.exit_event = threading.Event()
        self.ns = SimpleNamespace(webui_launch_id='mine', status={}, settings={
            'color_lock_choices': {2: ['Magenta', 'Green'], 3: ['Orange', 'Turquoise', 'Purple'],
                                   4: ['Yellow', 'Green', 'Blue', 'Purple']},
            'sensitivity': 2, 'red_on_kill': True, 'random_team_size': 4, 'force_all_start': False})
        self.ui = webui.WebUI(ns=self.ns, exit_event=self.exit_event)
        self.client = self.ui.app.test_client()
        patcher = mock.patch.object(webui.runtime_platform, 'is_proton', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_exit_button_is_only_on_the_main_page_beside_start_and_kill_game(self):
        page = self.client.get('/').data
        self.assertIn(b'id="exit-joustmania"', page)
        self.assertIn(b'action="/exit" method="POST" style="display:inline-block;"', page)
        self.assertIn(b'name="launch_id" value="mine"', page)
        menu = page.split(b'id="menubuttons"', 1)[1].split(b'id="gamebuttons"', 1)[0]
        self.assertLess(menu.index(b'id="startgame"'), menu.index(b'id="exit-joustmania"'))
        self.assertLess(menu.index(b'id="exit-joustmania"'), menu.index(b'href="/debug"'))
        game = page.split(b'id="gamebuttons"', 1)[1]
        self.assertLess(game.index(b'id="killgame"'), game.index(b'id="exit-joustmania-game"'))
        self.assertNotIn(b'id="exit-joustmania"', self.client.get('/power').data)
        self.assertNotIn(b'id="exit-joustmania"', self.client.get('/settings').data)

    def test_proton_power_menu_has_no_host_shutdown_buttons(self):
        page = self.client.get('/power').data
        self.assertIn(b'Application Options', page)
        self.assertIn(b'SteamOS power menu', page)
        self.assertNotIn(b'/shutdown8675309', page)
        self.assertNotIn(b'/reboot8675309', page)
        with mock.patch.object(webui, 'Process') as process:
            self.assertEqual(self.client.get('/shutdown8675309').status_code, 501)
            self.assertEqual(self.client.get('/reboot8675309').status_code, 501)
        process.assert_not_called()

    def test_exit_requires_post_confirmation_and_the_current_launch(self):
        self.assertEqual(self.client.get('/exit').status_code, 405)
        self.assertEqual(self.client.post('/exit', data={'launch_id': 'old', 'confirm': '1'}).status_code, 409)
        self.assertEqual(self.client.post('/exit', data={'launch_id': 'mine'}).status_code, 400)
        self.assertFalse(self.exit_event.is_set())

    def test_exit_sends_response_before_signalling_and_does_not_use_game_queue(self):
        self.ui.command_queue = mock.Mock()
        response = self.client.post('/exit', data={'launch_id': 'mine', 'confirm': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Exiting JoustMania', response.data)
        self.assertFalse(self.exit_event.is_set())
        response.close()
        self.assertTrue(self.exit_event.is_set())
        self.ui.command_queue.put.assert_not_called()

    def test_windows_and_pi_keep_existing_power_ui_and_cannot_request_application_exit(self):
        with mock.patch.object(webui.runtime_platform, 'is_proton', return_value=False):
            self.assertNotIn(b'id="exit-joustmania"', self.client.get('/').data)
            self.assertIn(b'id="pick_reboot"', self.client.get('/power').data)
            self.assertIn(b'id="pick_shutdown"', self.client.get('/power').data)
            self.assertEqual(self.client.post('/exit', data={'launch_id': 'mine', 'confirm': '1'}).status_code, 501)
        self.assertFalse(self.exit_event.is_set())

    def test_standalone_proton_web_server_does_not_offer_nonfunctional_exit(self):
        self.ui.exit_event = None
        self.assertNotIn(b'id="exit-joustmania"', self.client.get('/').data)
        self.assertEqual(self.client.post('/exit', data={'launch_id': 'mine', 'confirm': '1'}).status_code, 501)


class LifecycleTest(unittest.TestCase):
    def test_requested_exit_unwinds_the_game_and_cleans_up(self):
        menu = mock.Mock()
        menu.exit_event.is_set.return_value = True
        menu.game_loop.side_effect = KeyboardInterrupt
        with mock.patch.object(lifecycle.threading, 'Thread') as thread, \
                mock.patch.object(lifecycle, 'cleanup') as cleanup:
            lifecycle.run(menu)
        cleanup.assert_called_once_with(menu)
        thread.return_value.join.assert_called_once_with(timeout=1)

    def test_cleanup_also_runs_for_an_unexpected_game_error(self):
        menu = mock.Mock()
        menu.game_loop.side_effect = ValueError('Game failed')
        with mock.patch.object(lifecycle.threading, 'Thread'), \
                mock.patch.object(lifecycle, 'cleanup') as cleanup:
            with self.assertRaisesRegex(ValueError, 'Game failed'):
                lifecycle.run(menu)
        cleanup.assert_called_once_with(menu)

    def test_unrequested_keyboard_interrupt_is_not_swallowed(self):
        menu = mock.Mock()
        menu.exit_event.is_set.return_value = False
        menu.game_loop.side_effect = KeyboardInterrupt
        with mock.patch.object(lifecycle.threading, 'Thread'), mock.patch.object(lifecycle, 'cleanup'):
            with self.assertRaises(KeyboardInterrupt):
                lifecycle.run(menu)

    def test_interrupt_retries_until_shutdown_begins(self):
        exit_event, finished = threading.Event(), threading.Event()
        exit_event.set()
        def interrupt():
            if injected.call_count == 2:
                finished.set()
        with mock.patch.object(lifecycle._thread, 'interrupt_main', side_effect=interrupt) as injected:
            lifecycle._interrupt_on_exit(exit_event, finished)
        self.assertEqual(injected.call_count, 2)

    def test_proxy_clients_are_stopped_before_manager_servers(self):
        order = []
        def child(name):
            process = mock.Mock()
            process.name = name
            process.is_alive.side_effect = [True, False]
            process.terminate.side_effect = lambda: order.append(name)
            return process
        manager, audio, web = child('SyncManager-1'), child('Music-worker'), child('WebUI')
        lifecycle._stop_children([manager, audio, web])
        self.assertEqual(order, ['Music-worker', 'WebUI', 'SyncManager-1'])
        for process in [manager, audio, web]:
            process.kill.assert_not_called()
            process.join.assert_called_once()

    def test_stubborn_owned_worker_has_a_bounded_kill_fallback(self):
        child = mock.Mock()
        child.name = 'Music-worker'
        child.is_alive.return_value = True
        lifecycle._stop_children([child], timeout=0)
        child.terminate.assert_called_once()
        child.kill.assert_called_once()
        self.assertEqual(child.join.call_args_list, [mock.call(timeout=0), mock.call(timeout=1)])

    def test_cleanup_stops_only_game_services_and_supplied_children(self):
        import controller_manager
        import proton_psmove
        children = [mock.Mock()]
        with mock.patch.object(lifecycle.multiprocessing, 'active_children', return_value=children), \
                mock.patch.object(proton_psmove, 'close_webui') as close, \
                mock.patch.object(controller_manager, 'stop_manager') as stop_api, \
                mock.patch.object(proton_psmove, 'stop') as stop_host, \
                mock.patch.object(lifecycle, '_stop_children') as stop_children:
            lifecycle.cleanup(mock.Mock())
        close.assert_called_once_with()
        stop_api.assert_called_once_with()
        stop_host.assert_called_once_with()
        stop_children.assert_called_once_with(children)

    def test_real_exit_post_interrupts_fake_round_and_reaps_owned_workers(self):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--fake-application'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(state, dict(exit_requested=True, workers_stopped=True,
                                    browser_closed=True, api_stopped=True, host_stopped=True))


def idle_worker():
    while True:
        time.sleep(1)


def exit_web_worker(exit_event, port_queue):
    ns = SimpleNamespace(webui_launch_id='mine')
    with mock.patch.object(webui.runtime_platform, 'is_proton', return_value=True):
        ui = webui.WebUI(ns=ns, exit_event=exit_event)
        server = make_server('127.0.0.1', 0, ui.app)
        port_queue.put(server.server_port)
        server.serve_forever()


def fake_application():
    import controller_manager
    import proton_psmove
    context = multiprocessing.get_context('spawn')
    exit_event, port_queue = context.Event(), context.Queue()
    workers = [context.Process(target=exit_web_worker, args=(exit_event, port_queue), name='Fake-WebUI'),
               context.Process(target=idle_worker, name='Fake-Music')]
    manager = context.Manager()
    for worker in workers:
        worker.start()
    port = port_queue.get(timeout=8)
    errors = []
    def request_exit():
        try:
            opener = request.build_opener(request.ProxyHandler({}))
            body = parse.urlencode(dict(launch_id='mine', confirm='1')).encode()
            with opener.open('http://127.0.0.1:' + str(port) + '/exit', body, timeout=5) as response:
                assert b'Exiting JoustMania' in response.read()
        except Exception as error:
            errors.append(repr(error))
            exit_event.set()  # Never leave test children behind if HTTP fails.
    requester = threading.Thread(target=request_exit)
    def fake_round():
        requester.start()
        while True:
            time.sleep(0.01)
    with mock.patch.object(proton_psmove, 'close_webui') as close, \
            mock.patch.object(controller_manager, 'stop_manager') as stop_api, \
            mock.patch.object(proton_psmove, 'stop') as stop_host:
        lifecycle.run(SimpleNamespace(exit_event=exit_event, game_loop=fake_round))
    requester.join(timeout=5)
    assert not errors, errors
    print(json.dumps(dict(exit_requested=exit_event.is_set(),
                          workers_stopped=all(not w.is_alive() for w in workers) and not manager._process.is_alive(),
                          browser_closed=close.called, api_stopped=stop_api.called, host_stopped=stop_host.called)))


if __name__ == '__main__':
    if sys.argv[1:2] == ['--fake-application']:
        fake_application()
    else:
        unittest.main()
