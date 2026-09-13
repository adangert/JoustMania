"""Manage the Raspberry Pi onboard radio's boot setting, without clearing pairings."""
import argparse
import json
import re
import subprocess
import threading
from pathlib import Path
from system_power import request_system_power

APP_DIR = Path(__file__).resolve().parent
DT_ROOT = Path('/proc/device-tree')
CONFIG_PATHS = (Path('/boot/firmware/config.txt'), Path('/boot/config.txt'))
DISABLE = re.compile(r'^\s*dtoverlay\s*=\s*(?:pi3-)?disable-bt(?:-pi5)?\s*(?:,.*)?$')
MARKER = '# JoustMania internal Bluetooth'


def boot_config():
    for path in CONFIG_PATHS:
        if path.is_file():
            return path
    raise RuntimeError('Raspberry Pi boot configuration was not found.')


def config_state(text):
    """Only edit unconditionally applied settings; don't guess custom filters/includes."""
    section = 'all'
    disabled = False
    for line in text.splitlines():
        code = line.split('#', 1)[0].strip()
        if code.startswith('[') and code.endswith(']'):
            section = code[1:-1].strip().lower()
        if re.match(r'^include\s+', code):
            raise RuntimeError('Internal Bluetooth controls need a boot config without include directives.')
        if DISABLE.fullmatch(code):
            if section != 'all':
                raise RuntimeError('Move the Bluetooth disable overlay to [all] before using this control.')
            disabled = True
    return not disabled


def updated_config(text, enabled):
    if config_state(text) == enabled:  # Validate and keep repeated requests idempotent.
        return text
    lines = []
    for line in text.splitlines(keepends=True):
        if line.strip() == MARKER:
            continue
        if DISABLE.fullmatch(line.split('#', 1)[0].strip()):
            # Keep prior settings visible for a human reviewing config.txt.
            lines.append('# ' + line)
        else:
            lines.append(line)
    result = ''.join(lines)
    if not enabled:
        result = result.rstrip('\n') + '\n\n[all]\n' + MARKER + '\ndtoverlay=disable-bt\n'
    return result


def current_enabled():
    model = (DT_ROOT / 'model').read_text().rstrip('\0')
    if not model.startswith('Raspberry Pi'):
        raise RuntimeError('Internal Bluetooth controls are only available on Raspberry Pi.')
    alias = (DT_ROOT / 'aliases/bluetooth').read_text().rstrip('\0')
    node = DT_ROOT / alias.lstrip('/')
    if not node.is_dir():
        raise RuntimeError('The internal Bluetooth device was not found.')
    while node != DT_ROOT:
        status = node / 'status'
        if status.is_file() and status.read_text().rstrip('\0') not in ('ok', 'okay'):
            return False
        node = node.parent
    return True


def configure(enabled):
    current_enabled()  # Verify this is a Pi with an onboard Bluetooth node.
    path = boot_config()
    original = path.read_text()
    replacement = updated_config(original, enabled)
    # Older Pi OS versions use this service; Pi OS 13 may have no such unit.
    unit = subprocess.run(['systemctl', 'show', 'hciuart.service', '--property=LoadState', '--value'],
                          capture_output=True, text=True, check=True, timeout=5)
    if replacement != original:
        # /boot is often FAT: replace within the filesystem, without chmod/chown.
        path.with_name(path.name + '.joustmania-bak').write_text(original)
        temporary = path.with_name(path.name + '.joustmania-tmp')
        temporary.write_text(replacement)
        temporary.replace(path)
    try:
        if unit.stdout.strip() not in ('not-found', ''):
            subprocess.run(['systemctl', 'enable' if enabled else 'disable', 'hciuart.service'],
                           capture_output=True, text=True, check=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        if replacement != original:
            temporary.write_text(original)
            temporary.replace(path)
        raise


class InternalBluetooth:
    def __init__(self):
        self.lock = threading.RLock()
        self.busy = False
        self.error = ''
        self.rebooting = False

    def status(self):
        with self.lock:
            state = dict(available=False, enabled=None, configured_enabled=None,
                         reboot_required=False, busy=self.busy, rebooting=self.rebooting, error=self.error)
            try:
                state['enabled'] = current_enabled()
                state['configured_enabled'] = config_state(boot_config().read_text())
                state['available'] = True
                state['reboot_required'] = state['enabled'] != state['configured_enabled']
            except (OSError, RuntimeError) as error:
                state['error'] = self.error or str(error)
            return state

    def change(self, action, reboot=False):
        if action not in ('enable', 'disable'):
            raise ValueError('Choose enable or disable.')
        with self.lock:
            if self.busy or self.rebooting:
                raise RuntimeError('An internal Bluetooth change is already in progress.')
            state = self.status()
            if not state['available']:
                raise RuntimeError(state['error'] or 'Internal Bluetooth controls unavailable.')
            self.busy = True
            self.error = ''
            threading.Thread(target=self._run, args=(action, reboot), daemon=True).start()

    def _run(self, action, reboot=False):
        try:
            subprocess.run(['sudo', '-n', '/usr/bin/python3', str(APP_DIR / 'internal_bluetooth.py'), action],
                           capture_output=True, text=True, check=True, timeout=30)
            if reboot:
                with self.lock:
                    self.rebooting = True
                request_system_power('reboot')
        except subprocess.CalledProcessError as error:
            self.error = (error.stderr or error.stdout or 'Internal Bluetooth change failed.').strip()[-500:]
        except (OSError, subprocess.TimeoutExpired) as error:
            self.error = str(error)
        finally:
            with self.lock:
                if self.error:
                    self.rebooting = False
                self.busy = False


internal_bluetooth = InternalBluetooth()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('enable', 'disable', 'status'))
    args = parser.parse_args()
    if args.action == 'status':
        print(json.dumps(internal_bluetooth.status()))
    else:
        try:
            configure(args.action == 'enable')
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            parser.exit(1, str(error) + '\n')
        print('Internal Bluetooth setting saved. Reboot to apply.')
