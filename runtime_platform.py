"""Small runtime platform checks shared by compatibility-specific code."""

import os
import sys


_WINDOWS_PAIRING_NOTICE = (
    "Controller pairing notice: Windows may show a Bluetooth connection prompt "
    "when pairing a PS Move controller. Accept the prompt to continue."
)

_PROTON_PAIRING_NOTICE = (
    "Controller pairing notice: Please use SteamOS Desktop Mode when pairing a "
    "PS Move controller. SteamOS may show a system authentication prompt; "
    "approve it to continue."
)


def is_windows():
    return sys.platform.startswith("win")


def is_linux():
    return sys.platform.startswith("linux")


def is_proton():
    """Return True for the Windows build launched through Proton."""
    return is_windows() and bool(os.environ.get("STEAM_COMPAT_DATA_PATH"))


def default_web_port():
    """Avoid Steam's CEF debugging port when running through Proton."""
    return 8081 if is_proton() else 80


def controller_pairing_notice():
    """Return the startup pairing notice for Windows-compatible builds."""
    if is_proton():
        return _PROTON_PAIRING_NOTICE
    if is_windows():
        return _WINDOWS_PAIRING_NOTICE
    return None
