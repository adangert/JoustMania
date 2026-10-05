"""Open the local UI once for an interactive Windows or Proton launch."""

import json
import logging
import os
import threading
import time
from urllib import request
import webbrowser

import runtime_platform

logger = logging.getLogger(__name__)


def _ready(url, launch_id):
    # Ignore proxy settings for loopback, and verify this game's web process,
    # not another application (or an older JoustMania instance) on the port.
    opener = request.build_opener(request.ProxyHandler({}))
    try:
        with opener.open(url.rstrip('/') + '/health', timeout=0.5) as response:
            state = json.loads(response.read(4096))
        return state.get('service') == 'JoustMania' and state.get('launch_id') == launch_id
    except (OSError, ValueError, AttributeError):
        return False


def _open_when_ready(url, launch_id, process_alive, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_alive():
            logger.warning('Web UI process stopped before the browser could open. URL: %s', url)
            return
        if _ready(url, launch_id):
            try:
                if runtime_platform.is_proton():
                    import proton_psmove
                    opened = proton_psmove.open_webui(url, launch_id)
                else:
                    opened = webbrowser.open_new_tab(url)
                if not opened:
                    logger.warning('Could not open a browser automatically. Open %s manually.', url)
            except (OSError, RuntimeError, webbrowser.Error):
                logger.exception('Could not open a browser automatically. Open %s manually.', url)
            return
        time.sleep(0.25)
    logger.warning('Timed out waiting for the Web UI. Open %s manually once it is ready.', url)


def start(url, launch_id, process_alive):
    """Do not change headless/native Linux (including Raspberry Pi) startup."""
    if not runtime_platform.is_windows() or os.environ.get('JOUSTMANIA_OPEN_BROWSER', '1').lower() in ('0', 'false', 'no'):
        return None
    worker = threading.Thread(target=_open_when_ready, args=(url, launch_id, process_alive),
                              name='JoustMania-WebUI-Browser', daemon=True)
    worker.start()
    return worker
