"""Small runtime platform checks shared by compatibility-specific code."""

import os
import sys


def is_windows():
    return sys.platform.startswith("win")


def is_linux():
    return sys.platform.startswith("linux")


def is_proton():
    """Return True for the Windows build launched through Proton."""
    return is_windows() and bool(os.environ.get("STEAM_COMPAT_DATA_PATH"))
