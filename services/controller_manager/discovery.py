"""
Controller Discovery Module.

Phase 79: Handles periodic scanning for newly paired controllers.

The psmove library's count_connected() may not immediately reflect newly
paired Bluetooth controllers. This module provides periodic forced rescans
to ensure controllers paired externally (via pairing daemon, bluetoothctl, etc.)
are discovered promptly.
"""

import logging
import time

logger = logging.getLogger(__name__)

# Default interval between forced rescans (seconds)
DEFAULT_RESCAN_INTERVAL = 5.0


class PeriodicRescanTimer:
    """
    Simple timer for periodic forced rescans.

    Tracks when the last forced rescan occurred and determines
    whether it's time for another one.
    """

    def __init__(self, interval: float = DEFAULT_RESCAN_INTERVAL):
        """
        Initialize the rescan timer.

        Args:
            interval: Seconds between forced rescans
        """
        self.interval = interval
        self._last_rescan_time: float = 0.0

    def should_force_rescan(self) -> bool:
        """
        Check if it's time for a forced rescan.

        Returns:
            True if interval has elapsed since last forced rescan
        """
        now = time.time()
        if now - self._last_rescan_time >= self.interval:
            self._last_rescan_time = now
            return True
        return False

    def reset(self):
        """Reset the timer (e.g., after manual rescan trigger)."""
        self._last_rescan_time = time.time()
