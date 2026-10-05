"""Exit the Proton application without requesting a host power action."""

import _thread
import logging
import multiprocessing
import threading
import time


logger = logging.getLogger(__name__)


def _interrupt_on_exit(exit_event, finished):
    # Use a separate event, not the game command queue: game modes consume that
    # queue themselves, and Exit must also work during a countdown or round.
    while not finished.is_set():
        if exit_event.wait(0.1) and not finished.is_set():
            _thread.interrupt_main()
            # Retry if an older broad exception handler swallowed the interrupt.
            finished.wait(1)


def _stop_children(children, timeout=3):
    # Only children of this application are supplied, never processes found by
    # executable name. Stop proxy clients before their shared Manager servers.
    for managers in (False, True):
        group = [child for child in children if child.name.startswith('SyncManager') == managers]
        for child in group:
            if child.is_alive():
                child.terminate()
        deadline = time.monotonic() + timeout
        for child in group:
            child.join(timeout=max(0, deadline - time.monotonic()))
            if child.is_alive():
                child.kill()
                child.join(timeout=1)


def cleanup(menu):
    import controller_manager
    import proton_psmove

    # Capture our own children before stopping any shared services. Music
    # workers run persistent loops even when playback is stopped, so they must
    # be reaped too or multiprocessing would wait forever at interpreter exit.
    children = multiprocessing.active_children()
    for stop in (proton_psmove.close_webui, controller_manager.stop_manager, proton_psmove.stop):
        try:
            stop()
        except Exception:
            logger.exception('Could not stop an application service during exit')
    _stop_children(children)


def run(menu):
    """Run the Proton menu with a web-requested exit and owned-process cleanup."""
    finished = threading.Event()
    worker = threading.Thread(target=_interrupt_on_exit, args=(menu.exit_event, finished),
                              name='JoustMania-Exit', daemon=True)
    try:
        worker.start()
        menu.game_loop()
    except KeyboardInterrupt:
        if not menu.exit_event.is_set():
            raise
        logger.info('Exiting JoustMania at the Web UI request')
    finally:
        finished.set()
        if worker.ident is not None:
            worker.join(timeout=1)
        cleanup(menu)
