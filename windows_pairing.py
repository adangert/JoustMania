"""Publish Windows CLI pairing instructions to the web process.

The native program can buffer stdout when piped, so publish the user action
before launching it. Only its explicit success/address output confirms pairing;
an exit code of 1 alone can also mean an administrator or connection error.
"""

import re
import subprocess
import sys
import time


INSTRUCTIONS = (
    "Unplug the USB cable, then press the controller's PS button. "
    "If the red status LED goes out, press PS again until it stays lit. "
    "Accept any Windows Bluetooth connection prompt."
)
_ADDRESS = re.compile(r'^Controller address: ([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\s*$')


def status(ns):
    state = dict(getattr(ns, 'windows_pairing', {}))
    if not state or (state.get('phase') != 'waiting' and
                     time.monotonic() - state.get('updated_at', 0) > 30):
        return {}
    return state


def run(command, environment, serial='', publish=None):
    """Keep CLI output visible and publish progress without changing its workflow."""
    serial = serial.upper()

    def update(phase, message):
        if publish is not None:
            publish(dict(address=serial, phase=phase, message=message,
                         updated_at=time.monotonic()))

    update('waiting', INSTRUCTIONS)
    succeeded, verified = False, False
    successful_addresses = set()
    try:
        with subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors='replace') as process:
            try:
                for line in process.stdout:
                    if sys.stdout is not None:
                        sys.stdout.write(line)
                        sys.stdout.flush()
                    text = line.strip()
                    if re.fullmatch(r'PSMove #\d+ connected via USB\.', text):
                        succeeded, verified = False, False
                    elif text == 'Connection verified.':
                        verified = True
                    elif re.fullmatch(r'Pairing of #\d+ succeeded!', text):
                        succeeded = True
                    else:
                        match = _ADDRESS.fullmatch(text)
                        if match and succeeded and verified:
                            successful_addresses.add(match[1].upper())
                result = process.wait()
            except BaseException:
                # Stop only the pairing child we launched, not any other game
                # or CLI process. This also lets Ctrl+C unwind promptly.
                if process.poll() is None:
                    process.terminate()
                process.wait()
                raise
        paired = result == 1 and (serial in successful_addresses if serial else bool(successful_addresses))
        update('verified' if paired else 'failed',
               'Wireless connection verified. Pairing succeeded.' if paired else
               'Pairing did not complete. Check the terminal output and try again.')
        return paired
    except BaseException:
        update('failed', 'Pairing stopped before the wireless connection was verified. Check the terminal output.')
        raise
