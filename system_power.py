"""Request host power actions without terminating the requesting process first."""

import subprocess
import time


_POWER_ACTIONS = frozenset(("poweroff", "reboot"))


def request_system_power(action, delay=2):
    """Queue a systemd power action after allowing the web response to finish."""
    if action not in _POWER_ACTIONS:
        raise ValueError("Unsupported system power action: {}".format(action))

    time.sleep(delay)
    # Hand the request to systemd before shutdown stops JoustMania's process group.
    subprocess.run(
        ["sudo", "systemctl", "--no-block", action],
        check=True,
    )
