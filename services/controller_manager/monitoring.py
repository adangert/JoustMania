"""
Controller monitoring for battery and RSSI levels.

Extracted from server.py to reduce file size.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from opentelemetry import trace

from services.controller_manager import metrics

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class ControllerMonitoring:
    """Monitors controller battery levels and Bluetooth signal strength."""

    def __init__(
        self,
        low_battery_threshold: int = 1,
        rssi_check_interval: float = 10.0,
        weak_signal_threshold: int = -80,
    ):
        """Initialize monitoring state.

        Args:
            low_battery_threshold: Battery level (0-5) at or below which to warn
            rssi_check_interval: Seconds between RSSI checks
            weak_signal_threshold: RSSI (dBm) below which to warn about weak signal
        """
        # Battery monitoring (Phase 39 - Task 4)
        self.last_battery_warning: dict[str, float] = {}
        self.low_battery_threshold = low_battery_threshold
        self.last_battery_check = 0.0

        # RSSI monitoring (Phase 48)
        self.controller_rssi: dict[str, int] = {}
        self.controller_bt_addresses: dict[str, str] = {}
        self.last_rssi_check = 0.0
        self.rssi_check_interval = rssi_check_interval
        self.weak_signal_threshold = weak_signal_threshold
        self.last_rssi_warning: dict[str, float] = {}

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

    def check_rssi_levels(
        self,
        tracked_controllers: dict[str, dict],
        backend: Any,
        run_in_discovery_loop: Callable,
    ):
        """Check RSSI (signal strength) for all Bluetooth controllers (Phase 48, Phase 57).

        Updates controller_rssi dict and warns about weak signals.
        Only checks Bluetooth-connected controllers (USB returns 0).
        Non-Bluetooth backends return None for RSSI (handled gracefully).
        Uses shared discovery loop event loop for efficiency.

        Args:
            tracked_controllers: Dict of serial → controller info
            backend: Backend instance for RSSI queries
            run_in_discovery_loop: Callable to run async code in discovery loop
        """
        with tracer.start_as_current_span("check_rssi_levels") as span:
            try:
                checked_count = 0

                # Check RSSI for each tracked controller
                for serial in list(tracked_controllers.keys()):
                    try:
                        # Get RSSI from backend using shared event loop
                        rssi = run_in_discovery_loop(backend.get_rssi(serial))

                        if rssi is not None:
                            self.controller_rssi[serial] = rssi
                            metrics.controller_rssi_dbm.labels(serial=serial).set(rssi)
                            span.set_attribute(f"controller.{serial}.rssi", rssi)
                            checked_count += 1

                            # Warn if signal is weak
                            if rssi < self.weak_signal_threshold:
                                self._warn_weak_signal(
                                    serial, rssi, tracked_controllers, backend, run_in_discovery_loop
                                )
                        else:
                            # No RSSI available (USB or disconnected)
                            self.controller_rssi[serial] = 0
                            metrics.controller_rssi_dbm.labels(serial=serial).set(0)

                    except Exception as e:
                        logger.debug(f"Could not get RSSI for {serial}: {e}")

                span.set_attribute("rssi.checked_controllers", checked_count)

            except Exception as e:
                logger.error(f"Error checking RSSI levels: {e}", exc_info=True)

    def discover_bt_address(self, serial: str, hci: str):
        """Try to discover the Bluetooth MAC address for a controller (Phase 48).

        This is done by correlating with BlueZ's list of connected devices.
        PS Move controllers typically show as "Motion Controller" in device name.

        Args:
            serial: Controller serial number
            hci: HCI adapter name
        """
        try:
            from . import bluetooth

            devices = bluetooth.get_attached_addresses(hci)

            for device_addr in devices:
                try:
                    device_path = device_addr.replace(":", "_")
                    proxy = bluetooth.get_device_proxy(hci, f"dev_{device_path}")
                    device_name = bluetooth.get_device_attrib(proxy, "Name")

                    # PS Move controllers have "Motion Controller" in their name
                    if device_name and "Motion Controller" in str(device_name):
                        # Check if this device is connected (has RSSI)
                        rssi = bluetooth.get_device_rssi(hci, device_addr)
                        if rssi is not None:
                            # Assume this is our controller
                            self.controller_bt_addresses[serial] = device_addr
                            logger.info(f"Mapped controller {serial} to BT address {device_addr}")
                            return
                except Exception:
                    # Skip devices we can't query
                    continue

        except Exception as e:
            logger.debug(f"Error discovering BT address for {serial}: {e}")

    def _warn_weak_signal(
        self,
        serial: str,
        rssi: int,
        tracked_controllers: dict[str, dict],  # noqa: ARG002
        backend: Any,
        run_in_discovery_loop: Callable,
    ):
        """Warn player about weak Bluetooth signal (Phase 48).

        Displays orange pulse to indicate weak connection.
        Only warns once every 60 seconds per controller to avoid spam.

        Phase 57: Uses backend abstraction and _run_in_discovery_loop for efficiency.

        Args:
            serial: Controller serial number
            rssi: Current RSSI in dBm
            tracked_controllers: Dict of serial → controller info (for existence check)
            backend: Backend instance for LED control
            run_in_discovery_loop: Callable to run async code in discovery loop
        """
        current_time = time.time()
        last_warning = self.last_rssi_warning.get(serial, 0)

        # Warn at most once per minute
        if current_time - last_warning < 60.0:
            return

        logger.warning(f"Controller {serial} has weak signal: {rssi} dBm")

        # Display orange pulse (3 times, 200ms on/off) using backend
        try:
            for _ in range(3):
                run_in_discovery_loop(backend.set_led_color(serial, 255, 165, 0))  # Orange
                time.sleep(0.2)

                run_in_discovery_loop(backend.set_led_color(serial, 50, 30, 0))  # Dim orange
                time.sleep(0.2)

            # Note: Current game/menu state will restore color on next update
            self.last_rssi_warning[serial] = current_time
            metrics.controller_weak_signal_warnings_total.labels(serial=serial).inc()
            logger.info(f"Weak signal warning displayed for {serial}")

        except Exception as e:
            logger.error(f"Failed to display weak signal warning for {serial}: {e}")

    def get_rssi(self, serial: str) -> int:
        """Get cached RSSI for a controller.

        Args:
            serial: Controller serial number

        Returns:
            RSSI in dBm, or 0 if not available
        """
        return self.controller_rssi.get(serial, 0)

    def cleanup_controller(self, serial: str):
        """Clean up monitoring state for a removed controller.

        Args:
            serial: Controller serial number
        """
        self.controller_rssi.pop(serial, None)
        self.controller_bt_addresses.pop(serial, None)
        self.last_battery_warning.pop(serial, None)
        self.last_rssi_warning.pop(serial, None)
