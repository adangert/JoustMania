"""Native PSMoveAPI bridge used by the Windows build under Proton."""

import ctypes
import logging
import os
from pathlib import Path
import sys
import time
import json
import tempfile
import threading

import runtime_platform


_HOST = "127.0.0.1"
_SERVICE = "joustmania-psmove.service"
_HOST_LAUNCHER = "/usr/bin/steam-runtime-launch-client"
_started_by_pid = None
_password_notice_pid = None
_browser_session = None

logger = logging.getLogger(__name__)

_PASSWORD_SETUP_MESSAGE = """JoustMania needs an operating-system password to pair PS Move controllers over USB.

No password is currently set for this SteamOS user.

1. Exit JoustMania.
2. Switch to Desktop Mode.
3. Open Konsole.
4. Run: passwd
5. Enter a new password twice.
6. Restart JoustMania.

Nothing appears while typing the password in Konsole. This is normal.

When pairing a controller, enter this same password in the SteamOS authentication prompt. This is not your Steam account password. JoustMania does not see or store it."""


def _app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundle_paths():
    bundle = Path(
        os.environ.get(
            "PSMOVEAPI_LINUX_BUNDLE_DIR",
            str(_app_dir() / "proton" / "psmoveapi"),
        )
    )
    return (
        bundle / "psmove",
        bundle / "libpsmoveapi.so",
    )


def _unix_path(path):
    """Resolve a Windows path using Wine's actual drive and symlink mappings."""
    value = str(path)
    if value.startswith("/"):
        return value
    if len(value) < 3 or value[1] != ":" or value[2] not in "\\/":
        raise RuntimeError("Cannot convert Wine path to Linux path: " + value)

    try:
        # This Wine extension uses cdecl, unlike the Windows heap functions.
        convert = ctypes.CDLL("kernel32.dll").wine_get_unix_file_name
        kernel32 = ctypes.WinDLL("kernel32.dll")
    except (AttributeError, OSError) as error:
        raise RuntimeError(
            "This Proton version cannot resolve Wine paths to Linux paths"
        ) from error

    convert.argtypes = [ctypes.c_wchar_p]
    # Keep the allocated pointer so it can be freed after copying the path.
    convert.restype = ctypes.c_void_p
    kernel32.GetProcessHeap.argtypes = []
    kernel32.GetProcessHeap.restype = ctypes.c_void_p
    kernel32.HeapFree.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    kernel32.HeapFree.restype = ctypes.c_int

    # In particular, Proton may map S: to the parent of a steamapps directory,
    # not to the STEAM_COMPAT_LIBRARY_PATHS entry itself. Do not guess the root.
    pointer = convert(value.replace("/", "\\"))
    if not pointer:
        raise RuntimeError("Cannot resolve Wine path to Linux path: " + value)
    try:
        return ctypes.string_at(pointer).decode("utf-8")
    finally:
        kernel32.HeapFree(kernel32.GetProcessHeap(), 0, pointer)


def _run(arguments, success_statuses=(0,)):
    encoded = [str(argument).encode("utf-8") for argument in arguments]
    argv = (ctypes.c_char_p * (len(encoded) + 1))(*encoded, None)

    try:
        ntdll = ctypes.WinDLL("ntdll.dll")
        spawnvp = getattr(ntdll, "__wine_unix_spawnvp")
    except (AttributeError, OSError) as error:
        raise RuntimeError(
            "This Proton version cannot launch the native PS Move helper"
        ) from error

    spawnvp.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_int]
    spawnvp.restype = ctypes.c_int32
    status = spawnvp(argv, 1)
    if status not in success_statuses:
        logger.warning(
            "Native command exited with status %s: %s",
            status,
            " ".join(arguments),
        )
    return status


def _run_host(arguments, success_statuses=(0,)):
    return _run(
        [_HOST_LAUNCHER, "--alongside-steam", "--", *arguments],
        success_statuses,
    )


def bluetooth_snapshot():
    """Read host BlueZ metadata across Wine's boundary using a temporary JSON file.

    The host helper is bounded and unprivileged. No pairing service is stopped,
    and paths use the same Wine mapping as the native controller helper.
    """
    script = _app_dir() / "proton" / "proton_bluetooth_diagnostics.py"
    if not script.is_file() and not getattr(sys, "frozen", False):
        script = _app_dir() / "proton_bluetooth_diagnostics.py"
    if not script.is_file():
        raise RuntimeError("The Linux host diagnostics helper is missing from this build.")
    with tempfile.TemporaryDirectory(prefix="joustmania-bluetooth-") as temporary:
        output = Path(temporary) / "snapshot.json"
        # Wine resolves existing files with this API. Reserve the output before
        # translating its path, rather than assuming a not-yet-created filename
        # can be mapped on every Proton version.
        output.touch()
        status = _run_host([
            "/usr/bin/timeout", "--signal=KILL", "8s", "/usr/bin/python3",
            _unix_path(script), _unix_path(output),
        ])
        if status or not output.is_file() or not output.stat().st_size:
            raise RuntimeError("Could not read Bluetooth diagnostics from the Linux host.")
        state = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not isinstance(state.get("adapters"), list) or not isinstance(state.get("controllers"), list):
            raise RuntimeError("The Linux host returned invalid Bluetooth diagnostics.")
        return state


def _hide_game_console():
    """Hide only this process's visible console, and return a restore callback."""
    try:
        kernel32 = ctypes.WinDLL('kernel32.dll')
        user32 = ctypes.WinDLL('user32.dll')
        kernel32.GetConsoleWindow.argtypes = []
        kernel32.GetConsoleWindow.restype = ctypes.c_void_p
        user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        user32.IsWindowVisible.restype = ctypes.c_int
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.ShowWindow.restype = ctypes.c_int
        window = kernel32.GetConsoleWindow()
        if not window or not user32.IsWindowVisible(window):
            return None  # No visible console, including a pseudoconsole handle.
        user32.ShowWindow(window, 0)  # SW_HIDE; never search for other terminals.
        if user32.IsWindowVisible(window):
            logger.warning('Could not hide the JoustMania console for the game browser.')
            return None
        logger.info('JoustMania console hidden for the game browser.')

        def restore():
            user32.ShowWindow(window, 5)  # SW_SHOW after the owned browser closes.
            logger.info('JoustMania console restored after the game browser handoff ended.')
        return restore
    except (AttributeError, OSError):
        logger.warning('Console handoff is unavailable; keeping the console visible.')
        return None


def _watch_game_browser(output, temporary, restore):
    """Retain the helper status file and restore the console on close/failure."""
    try:
        modified = None
        deadline = time.monotonic() + 30
        while True:
            try:
                timestamp = output.stat().st_mtime_ns
                state = json.loads(output.read_text(encoding='utf-8'))
                if state.get('phase') == 'closed' or not state.get('success'):
                    break
                if timestamp != modified:
                    modified = timestamp
                    deadline = time.monotonic() + 30
            except (OSError, ValueError, AttributeError):
                pass  # Also tolerate reading during a helper heartbeat write.
            if time.monotonic() >= deadline:
                logger.warning('Host browser stopped responding; restoring the JoustMania console.')
                break
            time.sleep(1)
    finally:
        try:
            if restore:
                restore()
        finally:
            temporary.cleanup()


def open_webui(url, launch_id):
    """Use the host desktop browser or an owned Gamescope UI window."""
    global _browser_session
    script = _app_dir() / 'proton' / 'proton_webui_browser.py'
    if not script.is_file() and not getattr(sys, 'frozen', False):
        script = _app_dir() / 'proton_webui_browser.py'
    if not script.is_file():
        raise RuntimeError('This build is missing the Proton browser helper.')
    temporary = tempfile.TemporaryDirectory(prefix='joustmania-browser-')
    retained = False
    restore = None
    try:
        output = Path(temporary.name) / 'result.json'
        output.touch()  # Wine's filename mapping works on an existing file.
        status = _run_host([
            '/usr/bin/python3', _unix_path(script), _unix_path(output), url,
            os.environ.get('SteamAppId', '1093850'),
            os.environ.get('JOUSTMANIA_BROWSER_MODE', 'auto'), launch_id,
            os.environ.get('DISPLAY', ''),
        ], success_statuses=(0, 1))
        if not output.stat().st_size:
            raise RuntimeError('The Linux host browser helper did not respond.')
        state = json.loads(output.read_text(encoding='utf-8'))
        if not isinstance(state, dict):
            raise RuntimeError('The Linux host returned an invalid browser status.')
        if status or not state.get('success'):
            raise RuntimeError(state.get('error', 'Could not open the host browser.'))
        logger.info('Opened Web UI using the host %s browser workflow.', state.get('mode', 'unknown'))
        if state.get('mode') == 'game' and state.get('phase') == 'ready' and state.get('window'):
            logger.info('Game browser: %s, display %s, window %s, session %s, requested mode %s; '
                        'fullscreen and activation requested.', state.get('browser', 'unknown'),
                        state.get('display', 'default'), state['window'], state.get('session') or 'unknown',
                        state.get('requested_mode', 'unknown'))
            restore = _hide_game_console()
            worker = threading.Thread(target=_watch_game_browser, args=(output, temporary, restore),
                                      name='proton-game-browser', daemon=True)
            worker.start()
            _browser_session = (os.getpid(), output, worker)
            retained = True
        return True
    finally:
        if not retained:
            if restore:
                restore()
            temporary.cleanup()


def close_webui():
    """Ask only our owned Gaming Mode browser to close during application exit."""
    global _browser_session
    if _browser_session is None or _browser_session[0] != os.getpid():
        return
    _, output, worker = _browser_session
    _browser_session = None
    try:
        output.with_name(output.name + '.stop').touch()
    except OSError:
        pass  # The browser may already have closed and removed its directory.
    worker.join(timeout=8)


def _has_os_password():
    # passwd reports P only when the current SteamOS user has a usable password.
    check = (
        '/usr/bin/passwd --status | '
        '/usr/bin/awk \'$2 == "P" { found=1 } END { exit !found }\''
    )
    return _run_host(
        ["/usr/bin/sh", "-c", check],
        success_statuses=(0, 1),
    ) == 0


def _show_password_setup_if_needed():
    global _password_notice_pid
    if _password_notice_pid == os.getpid():
        return
    _password_notice_pid = os.getpid()

    if _has_os_password():
        return

    print(_PASSWORD_SETUP_MESSAGE)
    try:
        user32 = ctypes.WinDLL("user32.dll")
        user32.MessageBoxW(
            None,
            _PASSWORD_SETUP_MESSAGE,
            "JoustMania controller setup",
            0x00000040,
        )
    except (AttributeError, OSError):
        logger.warning("Could not display the SteamOS password setup dialog")


def _write_host_config():
    app_data = os.environ.get("APPDATA")
    if not app_data:
        raise RuntimeError("Proton did not provide the Windows APPDATA path")

    config_dir = Path(app_data) / ".psmoveapi"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Pairing stores calibration on the host; copy it across the Steam runtime
    # boundary so the Windows DLL can report acceleration in g.
    copy_calibration = (
        'for calibration in /etc/psmoveapi/*.calibration; do '
        '[ -f "$calibration" ] || continue; '
        '/usr/bin/cp -f "$calibration" "$1/" || exit 1; '
        "done"
    )
    _run_host(
        [
            "/usr/bin/sh",
            "-c",
            copy_calibration,
            "joustmania-calibration-sync",
            _unix_path(config_dir),
        ]
    )

    hosts_file = config_dir / "moved2_hosts.txt"
    hosts = []
    if hosts_file.is_file():
        hosts = [
            line.strip()
            for line in hosts_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if _HOST not in hosts:
        hosts.append(_HOST)
        hosts_file.write_text("\n".join(hosts) + "\n", encoding="utf-8")


def start():
    global _started_by_pid
    if not runtime_platform.is_proton():
        return
    if _started_by_pid == os.getpid():
        return

    helper, library = _bundle_paths()
    missing = [str(path) for path in (helper, library) if not path.is_file()]
    if missing:
        raise RuntimeError(
            "This JoustMania build is missing the Proton PS Move helper: "
            + ", ".join(missing)
        )

    _show_password_setup_if_needed()

    helper = _unix_path(helper)
    _write_host_config()
    if _run_host(["/usr/bin/chmod", "u+x", helper]):
        raise RuntimeError("Could not make the Proton PS Move helper executable")
    _run_host(["/usr/bin/systemctl", "--user", "stop", _SERVICE])
    if _run_host(
        [
            "/usr/bin/systemd-run",
            "--user",
            "--unit=" + _SERVICE,
            "--collect",
            helper,
            "daemon",
        ]
    ):
        raise RuntimeError("Could not start the Proton PS Move helper")
    time.sleep(0.5)
    _started_by_pid = os.getpid()


def stop():
    global _started_by_pid
    if not runtime_platform.is_proton():
        return
    if _started_by_pid != os.getpid():
        return
    _run_host(["/usr/bin/systemctl", "--user", "stop", _SERVICE])
    _started_by_pid = None


def pair(host_address=None):
    helper, _ = _bundle_paths()
    if not helper.is_file():
        raise RuntimeError(
            "This JoustMania build is missing the Proton pairing helper: "
            + str(helper)
        )

    command = [
        "/usr/bin/pkexec",
        _unix_path(helper),
        "pair",
    ]
    if host_address:
        command.append(host_address.lower())

    stop()
    # The upstream pairing CLI returns its final pairing boolean as the exit status.
    return _run_host(command, success_statuses=(1,)) == 1
