"""Control the existing Wi-Fi hotspot scripts without blocking web responses."""
from pathlib import Path
import shutil
import subprocess
import threading
import time

APP_DIR = Path(__file__).resolve().parent


class AccessPoint:
    def __init__(self):
        self.lock = threading.RLock()
        self.busy = False
        self.error = ''
        self.cached = None
        self.checked_at = 0

    def status(self):
        with self.lock:
            if self.cached is None or time.monotonic() - self.checked_at >= 3:
                state = {'enabled': None, 'available': False}
                if shutil.which('nmcli'):
                    try:
                        result = subprocess.run(
                            ['nmcli', '-t', '-f', 'NAME', 'connection', 'show', '--active'],
                            capture_output=True, text=True, check=True, timeout=2,
                        )
                        state = {'enabled': 'Hotspot' in result.stdout.splitlines(), 'available': True}
                    except (OSError, subprocess.SubprocessError):
                        pass
                self.cached = state
                self.checked_at = time.monotonic()
            return dict(self.cached, busy=self.busy, error=self.error)

    def change(self, action):
        if action not in ('enable', 'disable'):
            raise ValueError('Choose enable or disable.')
        with self.lock:
            if self.busy:
                raise RuntimeError('A hotspot change is already in progress.')
            if not self.status()['available']:
                raise RuntimeError('Wi-Fi hotspot controls require NetworkManager.')
            self.busy = True
            self.error = ''
            threading.Thread(target=self._run, args=(action,), daemon=True).start()

    def _run(self, action):
        try:
            # Deliver the response before switching the network used by the browser.
            time.sleep(1)
            subprocess.run(
                ['sudo', '-n', '/bin/bash', str(APP_DIR / (action + '_ap.sh'))],
                cwd=APP_DIR, capture_output=True, text=True, check=True, timeout=90,
            )
        except subprocess.CalledProcessError as error:
            with self.lock:
                self.error = (error.stderr or error.stdout or 'Hotspot change failed.').strip()[-500:]
        except (OSError, subprocess.TimeoutExpired) as error:
            with self.lock:
                self.error = str(error)
        finally:
            with self.lock:
                self.busy = False
                self.cached = None


access_point = AccessPoint()
