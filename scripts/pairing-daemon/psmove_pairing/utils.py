"""Utility functions for PS Move pairing daemon."""

import asyncio
import logging
import os
import shutil
import sys

from .config import PSMOVE_PATH

logger = logging.getLogger("psmove-pairing")


def find_psmove_binary() -> str:
    """Find the psmove binary, checking various locations."""
    if PSMOVE_PATH and os.path.isfile(PSMOVE_PATH):
        return PSMOVE_PATH

    # Check if it's in PATH
    psmove_in_path = shutil.which("psmove")
    if psmove_in_path:
        return psmove_in_path

    # Common installation locations
    home = os.path.expanduser("~")
    candidates = [
        f"{home}/psmoveapi/build/psmove",
        "/home/joustmania/psmoveapi/build/psmove",
        "/usr/local/bin/psmove",
    ]

    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    logger.error("psmove binary not found. Install psmoveapi or set PSMOVE_PATH")
    sys.exit(1)


async def run_command(cmd: list[str], capture_stderr: bool = True) -> tuple[int, str]:
    """Run a subprocess command asynchronously and return exit code and output."""
    try:
        stderr = asyncio.subprocess.STDOUT if capture_stderr else asyncio.subprocess.DEVNULL

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=stderr,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = stdout.decode("utf-8", errors="replace").strip()
        return proc.returncode or 0, output
    except TimeoutError:
        logger.error(f"Command timed out: {' '.join(cmd)}")
        return -1, "timeout"
    except Exception as e:
        logger.error(f"Command failed: {e}")
        return -1, str(e)
