"""Launch the host browser for Proton, with an owned Gaming Mode UI window.

Desktop Mode delegates to the default browser. Gaming Mode uses an installed
Chrome/Chromium or Firefox with an isolated temporary profile. Only the window
with our unique WM_CLASS is tagged with Gamescope's STEAM_GAME property.
Fullscreen and activation requests go through the window manager, rather
than changing Gamescope's global focus controls or the display resolution.
"""

import ctypes
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from urllib import request


class ClassHint(ctypes.Structure):
    _fields_ = [('name', ctypes.c_void_p), ('class_name', ctypes.c_void_p)]


class WindowAttributes(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int) for name in ('x', 'y', 'width', 'height', 'border_width', 'depth')] + [
        ('visual', ctypes.c_void_p), ('root', ctypes.c_ulong), ('window_class', ctypes.c_int),
        ('bit_gravity', ctypes.c_int), ('win_gravity', ctypes.c_int), ('backing_store', ctypes.c_int),
        ('backing_planes', ctypes.c_ulong), ('backing_pixel', ctypes.c_ulong),
        ('save_under', ctypes.c_int), ('colormap', ctypes.c_ulong), ('map_installed', ctypes.c_int),
        ('map_state', ctypes.c_int), ('all_event_masks', ctypes.c_long), ('your_event_mask', ctypes.c_long),
        ('do_not_propagate_mask', ctypes.c_long), ('override_redirect', ctypes.c_int), ('screen', ctypes.c_void_p)]


class ClientMessageData(ctypes.Union):
    _fields_ = [('bytes', ctypes.c_char * 20), ('shorts', ctypes.c_short * 10), ('longs', ctypes.c_long * 5)]


class ClientMessage(ctypes.Structure):
    _fields_ = [('type', ctypes.c_int), ('serial', ctypes.c_ulong), ('send_event', ctypes.c_int),
               ('display', ctypes.c_void_p), ('window', ctypes.c_ulong), ('message_type', ctypes.c_ulong),
               ('format', ctypes.c_int), ('data', ClientMessageData)]


class XEvent(ctypes.Union):
    # Xlib's public XEvent union reserves 24 native longs, even for a shorter
    # client message. Using fixed 32-bit integers would break the 64-bit ABI.
    _fields_ = [('client', ClientMessage), ('padding', ctypes.c_long * 24)]


class X11:
    def __init__(self, display):
        self.lib = ctypes.CDLL('libX11.so.6')
        pointer, window = ctypes.c_void_p, ctypes.c_ulong
        signatures = {
            'XOpenDisplay': ([ctypes.c_char_p], pointer),
            'XCloseDisplay': ([pointer], ctypes.c_int),
            'XDefaultRootWindow': ([pointer], window),
            'XInternAtom': ([pointer, ctypes.c_char_p, ctypes.c_int], window),
            'XQueryTree': ([pointer, window, ctypes.POINTER(window), ctypes.POINTER(window),
                           ctypes.POINTER(ctypes.POINTER(window)), ctypes.POINTER(ctypes.c_uint)], ctypes.c_int),
            'XGetClassHint': ([pointer, window, ctypes.POINTER(ClassHint)], ctypes.c_int),
            'XGetWindowAttributes': ([pointer, window, ctypes.POINTER(WindowAttributes)], ctypes.c_int),
            'XMoveResizeWindow': ([pointer, window, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint], ctypes.c_int),
            'XSendEvent': ([pointer, window, ctypes.c_int, ctypes.c_long, ctypes.POINTER(XEvent)], ctypes.c_int),
            'XChangeProperty': ([pointer, window, window, window, ctypes.c_int, ctypes.c_int,
                                 ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int], ctypes.c_int),
            'XGetWindowProperty': ([pointer, window, window, ctypes.c_long, ctypes.c_long, ctypes.c_int,
                                    window, ctypes.POINTER(window), ctypes.POINTER(ctypes.c_int),
                                    ctypes.POINTER(window), ctypes.POINTER(window),
                                    ctypes.POINTER(ctypes.c_void_p)], ctypes.c_int),
            'XRaiseWindow': ([pointer, window], ctypes.c_int),
            'XFlush': ([pointer], ctypes.c_int),
            'XSync': ([pointer, ctypes.c_int], ctypes.c_int),
            'XFree': ([pointer], ctypes.c_int),
            'XSetErrorHandler': ([pointer], pointer),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = arguments, result
        self.display = self.lib.XOpenDisplay(display.encode() if display else None)
        if not self.display:
            raise RuntimeError('The host game display could not be opened.')
        # A window can disappear between tree enumeration and reading its class.
        # Ignore that race in this standalone helper, without affecting the game.
        self.error_handler = ctypes.CFUNCTYPE(ctypes.c_int, pointer, pointer)(lambda *_: 0)
        self.previous_handler = self.lib.XSetErrorHandler(ctypes.cast(self.error_handler, pointer))
        self.root = self.lib.XDefaultRootWindow(self.display)

    def close(self):
        self.lib.XCloseDisplay(self.display)
        self.lib.XSetErrorHandler(self.previous_handler)

    def cardinal(self, window, name):
        atom = self.lib.XInternAtom(self.display, name.encode(), True)
        if not atom:
            return None
        actual, count, remaining = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_ulong()
        format_bits, data = ctypes.c_int(), ctypes.c_void_p()
        self.lib.XGetWindowProperty(self.display, window, atom, 0, 1, False, 6,
                                   ctypes.byref(actual), ctypes.byref(format_bits), ctypes.byref(count),
                                   ctypes.byref(remaining), ctypes.byref(data))
        try:
            if data.value and count.value and format_bits.value == 32:
                return ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))[0]
        finally:
            if data.value:
                self.lib.XFree(data)
        return None

    def _children(self, window):
        root, parent, children, count = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.POINTER(ctypes.c_ulong)(), ctypes.c_uint()
        self.lib.XQueryTree(self.display, window, ctypes.byref(root), ctypes.byref(parent),
                            ctypes.byref(children), ctypes.byref(count))
        try:
            return list(children[:count.value]) if children else []
        finally:
            if children:
                self.lib.XFree(children)

    def _class(self, window):
        hint = ClassHint()
        self.lib.XGetClassHint(self.display, window, ctypes.byref(hint))
        try:
            return ctypes.string_at(hint.class_name).decode(errors='replace') if hint.class_name else ''
        finally:
            for value in (hint.name, hint.class_name):
                if value:
                    self.lib.XFree(value)

    def attributes(self, window):
        attributes = WindowAttributes()
        return attributes if self.lib.XGetWindowAttributes(self.display, window, ctypes.byref(attributes)) else None

    def _request(self, window, message, values):
        event = XEvent()
        event.client = ClientMessage(type=33, send_event=True, display=self.display, window=window,
                                     message_type=self.lib.XInternAtom(self.display, message.encode(), False), format=32)
        for index, value in enumerate(values):
            event.client.data.longs[index] = value
        # Send an EWMH request to the WM. A raw XRaiseWindow alone does not
        # update Gamescope's own focus priority; _NET_ACTIVE_WINDOW does.
        return bool(self.lib.XSendEvent(self.display, self.root, False, (1 << 19) | (1 << 20), ctypes.byref(event)))

    def present(self, window):
        fullscreen = self.lib.XInternAtom(self.display, b'_NET_WM_STATE_FULLSCREEN', False)
        self._request(window, '_NET_WM_STATE', [1, fullscreen, 0, 1])
        size = self.attributes(self.root)
        if size and size.width > 1 and size.height > 1:
            # Size only our browser to the existing game viewport. Do not use
            # xrandr, a hard-coded Deck resolution, or resize any other window.
            self.lib.XMoveResizeWindow(self.display, window, 0, 0, size.width, size.height)
        self._request(window, '_NET_ACTIVE_WINDOW', [1, 0, 0])
        self.lib.XRaiseWindow(self.display, window)
        self.lib.XSync(self.display, False)

    def tag_window(self, class_name, app_id):
        parents = [self.root]
        for _ in range(3):
            children = [child for parent in parents for child in self._children(parent)]
            for window in children:
                if self._class(window) != class_name:
                    continue
                attributes = self.attributes(window)
                if not attributes or attributes.map_state != 2 or attributes.width <= 1 or attributes.height <= 1:
                    continue  # Ignore unmapped startup/helper windows sharing the class.
                # Gamescope reads STEAM_GAME as an authoritative application ID.
                # WM_CLASS is only our unique selector, not the game ID itself.
                atom = self.lib.XInternAtom(self.display, b'STEAM_GAME', False)
                value = (ctypes.c_ulong * 1)(app_id)
                self.lib.XChangeProperty(self.display, window, atom, 6, 32, 0,
                                         ctypes.cast(value, ctypes.POINTER(ctypes.c_ubyte)), 1)
                self.present(window)
                return window
            parents = children
        return 0


def gaming_mode(environment, x11=None):
    desktop = ' '.join(environment.get(key, '') for key in (
        'XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION')).lower()
    if 'gamescope' in desktop:
        return True
    if any(name in desktop for name in ('kde', 'plasma', 'gnome', 'xfce', 'cinnamon', 'mate', 'lxqt')):
        return False  # A nested game display can also run under a normal desktop.
    hints = ' '.join(environment.get(key, '') for key in ('WAYLAND_DISPLAY', 'GAMESCOPE_WAYLAND_DISPLAY')).lower()
    return 'gamescope' in hints or bool(x11 and x11.cardinal(x11.root, 'GAMESCOPE_PID'))


def installed_browser():
    # Flatpak is the common immutable-host installation path. Never install or
    # change persistent permissions; enumerate only the applications present.
    flatpak = shutil.which('flatpak')
    if flatpak:
        try:
            result = subprocess.run([flatpak, 'list', '--app', '--columns=application'],
                                    capture_output=True, text=True, check=True, timeout=3)
            installed = set(result.stdout.splitlines())
            for app, kind in [('com.google.Chrome', 'chromium'), ('org.chromium.Chromium', 'chromium'),
                              ('org.mozilla.firefox', 'firefox')]:
                if app in installed:
                    return kind, [flatpak, 'run', '--socket=x11'], app
        except (OSError, subprocess.SubprocessError):
            pass
    for executable, kind in [('google-chrome', 'chromium'), ('chromium', 'chromium'),
                             ('chromium-browser', 'chromium'), ('firefox', 'firefox')]:
        found = shutil.which(executable)
        if found:
            return kind, [found], ''
    raise RuntimeError('Gaming Mode needs an installed Chrome, Chromium or Firefox browser. '
                       'Install one in Desktop Mode, or open the Web UI manually.')


def browser_command(kind, prefix, app, profile, class_name, url, display, instance_fd=None):
    command = list(prefix)
    if app:
        if instance_fd is not None:
            command.append('--instance-id-fd=' + str(instance_fd))
        command += ['--env=MOZ_ENABLE_WAYLAND=0', '--env=GDK_BACKEND=x11']
        if display:
            command.append('--env=DISPLAY=' + display)
        command.append(app)
    if kind == 'chromium':
        command += ['--ozone-platform=x11', '--class=' + class_name, '--user-data-dir=' + str(profile),
                    '--no-first-run', '--no-default-browser-check', '--start-fullscreen', '--app=' + url]
    else:
        command += ['--class', class_name, '--no-remote', '--new-instance', '--profile', str(profile), '--kiosk', url]
    return command


def game_alive(url, launch_id):
    try:
        opener = request.build_opener(request.ProxyHandler({}))
        with opener.open(url.rstrip('/') + '/health', timeout=1) as response:
            state = json.loads(response.read(4096))
        return state.get('service') == 'JoustMania' and state.get('launch_id') == launch_id
    except (OSError, ValueError, AttributeError):
        return False


def stop_owned_browser(browser, flatpak='', instance_file=None):
    # This Popen owns a new session and an isolated profile. Never terminate an
    # existing/default browser, nor look up unrelated processes by their name.
    if browser.poll() is None:
        if flatpak and instance_file is not None:
            instance_file.seek(0)
            instance = instance_file.read(64).decode('ascii', errors='replace').strip()
            if instance.isascii() and instance.isdecimal():
                # A sandbox can have its own process group. Use only the ID
                # written by our flatpak run, never the application ID (which
                # could also stop a personal browser instance).
                try:
                    subprocess.run([flatpak, 'kill', instance], timeout=3,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except (OSError, subprocess.SubprocessError):
                    pass
        try:
            if browser.poll() is None:
                os.killpg(browser.pid, signal.SIGTERM)
                browser.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(browser.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            browser.wait(timeout=5)
        except ProcessLookupError:
            pass


def write_status(output, state):
    """Publish complete JSON snapshots across the host/Wine boundary."""
    pending = output.with_name(output.name + '.tmp')
    pending.write_text(json.dumps(state), encoding='utf-8')
    pending.replace(output)


def launch(output, url, app_id, mode, launch_id, display):
    environment = dict(os.environ)
    if display:
        environment['DISPLAY'] = display
    display = environment.get('DISPLAY', '')
    x11 = None
    responded = False
    try:
        try:
            x11 = X11(display)
        except (OSError, RuntimeError):
            pass
        use_game_window = mode == 'game' or (mode == 'auto' and gaming_mode(environment, x11))
        if not use_game_window:
            opener = shutil.which('xdg-open')
            if not opener:
                raise RuntimeError('The Linux host has no default-browser launcher (xdg-open).')
            subprocess.Popen([opener, url], env=environment, start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            write_status(output, dict(success=True, mode='desktop'))
            return
        if x11 is None:
            raise RuntimeError('Gaming Mode browser window needs access to the host X11 game display.')
        kind, prefix, app = installed_browser()
        cache = Path.home() / ('.var/app/' + app + '/cache' if app else '.cache') / 'joustmania-ui'
        cache.mkdir(parents=True, exist_ok=True)
        class_name = 'JoustMania_UI_' + launch_id
        environment.update(MOZ_ENABLE_WAYLAND='0', GDK_BACKEND='x11', SteamAppId=str(app_id))
        with tempfile.TemporaryDirectory(prefix='profile-', dir=cache) as profile, \
                tempfile.TemporaryFile() as instance_file:
            command = browser_command(kind, prefix, app, profile, class_name, url, display,
                                      instance_file.fileno() if app else None)
            browser = subprocess.Popen(command, env=environment, start_new_session=True,
                                       pass_fds=(instance_file.fileno(),) if app else (),
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 12
                while browser.poll() is None and time.monotonic() < deadline:
                    window = x11.tag_window(class_name, app_id)
                    if window:
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError('The Gaming Mode browser did not create its UI window. Open the UI in Desktop Mode.')
                ready = dict(success=True, phase='ready', mode='game', browser=kind,
                             display=display, window=window, requested_mode=mode,
                             session=environment.get('XDG_CURRENT_DESKTOP', ''))
                write_status(output, ready)
                responded = True
                # Keep ownership until the game closes. Several missed checks
                # tolerate a short busy web response without closing its UI.
                misses = 0
                while browser.poll() is None and misses < 5 and not output.with_name(output.name + '.stop').exists():
                    misses = 0 if game_alive(url, launch_id) else misses + 1
                    # The Wine caller restores its console if these heartbeats
                    # stop, including a helper crash that skips normal cleanup.
                    try:
                        write_status(output, ready)
                    except OSError:
                        pass
                    time.sleep(1)
            finally:
                try:
                    stop_owned_browser(browser, prefix[0] if app else '', instance_file)
                finally:
                    if responded:
                        # The Wine caller retains this status file while its
                        # console is hidden, and restores it if the browser closes.
                        try:
                            write_status(output, dict(success=True, mode='game', phase='closed'))
                        except OSError:
                            pass
    except Exception as error:
        if not responded:
            # A startup failure leaves the Wine console available for diagnostics.
            try:
                write_status(output, dict(success=False, error=str(error)))
            except OSError:
                pass
    finally:
        if x11:
            x11.close()


def main():
    output, url, app_id, mode, launch_id, display = sys.argv[1:]
    output = Path(output)
    app_id = int(app_id)
    if not 0 < app_id < 2**32 or mode not in ('auto', 'game', 'desktop') or not launch_id.isalnum():
        raise ValueError('Invalid browser launch configuration.')
    # The child owns the Gaming Mode browser and cleans it up when JoustMania
    # closes. The Wine caller waits only for the initial result, not game exit.
    child = os.fork()
    if child == 0:
        os.setsid()
        def cancel_launch(*_):
            raise RuntimeError('The host browser launch was cancelled.')
        signal.signal(signal.SIGTERM, cancel_launch)
        with open(os.devnull, 'rb+', buffering=0) as null:
            for descriptor in (0, 1, 2):
                os.dup2(null.fileno(), descriptor)
        launch(output, url, app_id, mode, launch_id, display)
        os._exit(0)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            state = json.loads(output.read_text(encoding='utf-8'))
            return 0 if state.get('success') else 1
        except (OSError, ValueError):
            if os.waitpid(child, os.WNOHANG)[0]:
                return 1
            time.sleep(0.1)
    # A slow or stuck launch must not leave a detached browser behind. SIGTERM
    # runs the child's ownership cleanup before the bounded final fallback.
    try:
        os.kill(child, signal.SIGTERM)
    except ProcessLookupError:
        return 1
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if os.waitpid(child, os.WNOHANG)[0]:
            return 1
        time.sleep(0.1)
    os.kill(child, signal.SIGKILL)
    os.waitpid(child, 0)
    return 1


if __name__ == '__main__':
    sys.exit(main())
