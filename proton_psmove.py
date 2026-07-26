"""Native PSMoveAPI bridge used by the Windows build under Proton."""

import ctypes
import logging
import os
from pathlib import Path
import sys
import tempfile
import time

import runtime_platform


_HOST = "127.0.0.1"
_SERVICE = "joustmania-psmove.service"
_HOST_LAUNCHER = "/usr/bin/steam-runtime-launch-client"
_started_by_pid = None

logger = logging.getLogger(__name__)


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
        _app_dir() / "proton" / "pair-psmove.sh",
    )


def _unix_path(path):
    value = str(path).replace("\\", "/")
    if value.startswith("/"):
        return value
    if len(value) < 3 or value[1:3] != ":/":
        raise RuntimeError("Cannot convert Wine path to Linux path: " + value)

    drive = value[0].lower()
    relative = value[3:].lstrip("/")
    if drive == "z":
        return "/" + relative
    if drive == "c" and os.environ.get("STEAM_COMPAT_DATA_PATH"):
        compat_data = os.environ["STEAM_COMPAT_DATA_PATH"].replace("\\", "/")
        return compat_data.rstrip("/") + "/pfx/drive_c/" + relative
    raise RuntimeError(
        "The Proton helper must be on Wine drive Z: or C:, not "
        + drive.upper()
        + ":"
    )


def _run(arguments):
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
    if status:
        logger.warning(
            "Native command exited with status %s: %s",
            status,
            " ".join(arguments),
        )
    return status


def _run_host(arguments):
    return _run([_HOST_LAUNCHER, "--alongside-steam", "--", *arguments])


def _write_host_config():
    app_data = os.environ.get("APPDATA")
    if not app_data:
        raise RuntimeError("Proton did not provide the Windows APPDATA path")

    config_dir = Path(app_data) / ".psmoveapi"
    config_dir.mkdir(parents=True, exist_ok=True)
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

    helper, library, _ = _bundle_paths()
    missing = [str(path) for path in (helper, library) if not path.is_file()]
    if missing:
        raise RuntimeError(
            "This JoustMania build is missing the Proton PS Move helper: "
            + ", ".join(missing)
        )

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
    helper, _, pair_script = _bundle_paths()
    missing = [str(path) for path in (helper, pair_script) if not path.is_file()]
    if missing:
        raise RuntimeError(
            "This JoustMania build is missing Proton pairing files: "
            + ", ".join(missing)
        )

    result = (
        Path(tempfile.gettempdir())
        / "joustmania-psmove-pair-{}.result".format(os.getpid())
    )
    result.unlink(missing_ok=True)
    command = [
        "/usr/bin/pkexec",
        "/bin/sh",
        _unix_path(pair_script),
        _unix_path(result),
        _unix_path(helper),
        "pair",
    ]
    if host_address:
        command.append(host_address.lower())

    stop()
    try:
        _run_host(command)
        if not result.is_file():
            logger.warning(
                "Native PS Move pairing returned no result. "
                "Authorization may have been cancelled."
            )
            return False
        return result.read_text(encoding="utf-8").strip() == "1"
    finally:
        result.unlink(missing_ok=True)
