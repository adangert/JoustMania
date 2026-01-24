"""
Controller monitoring for battery levels.

Extracted from server.py to reduce file size.
Note: RSSI monitoring is handled by the host pairing-daemon which has
direct access to hcitool for reliable signal strength readings.
"""

import logging

from services.controller_manager import metrics

logger = logging.getLogger(__name__)


class ControllerMonitoring:
    """Monitors controller battery levels."""

    def __init__(
        self,
        low_battery_threshold: int = 1,
    ):
        """Initialize monitoring state.

        Args:
            low_battery_threshold: Battery level (0-5) at or below which to warn
        """
        # Battery monitoring (Phase 39 - Task 4)
        self.last_battery_warning: dict[str, float] = {}
        self.low_battery_threshold = low_battery_threshold
        self.last_battery_check = 0.0

    def check_battery_levels(
        self,
        tracked_controllers: dict[str, dict],
    ):
        """Update battery level metrics for all controllers.

        Called every 30 seconds from discovery loop.
        Battery display/warnings are handled by the menu service (Phase 70).

        Args:
            tracked_controllers: Dict of serial → controller info
        """
        for serial, info in list(tracked_controllers.items()):
            try:
                battery = info.get("battery", 5)  # Default to full if unknown

                # Update battery metric (Phase 38)
                metrics.controller_battery_level.labels(serial=serial).set(battery)

            except Exception as e:
                logger.error(f"Error checking battery for {serial}: {e}")

    def cleanup_controller(self, serial: str):
        """Clean up monitoring state for a removed controller.

        Args:
            serial: Controller serial number
        """
        self.last_battery_warning.pop(serial, None)
