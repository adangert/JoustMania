"""
Pytest fixtures for controller_manager tests.
"""

import os

import pytest

# Disable OpenTelemetry export during tests to prevent hanging on trace/metric export
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["OTEL_TRACES_EXPORTER"] = "none"
os.environ["OTEL_METRICS_EXPORTER"] = "none"


class FakeMove:
    """Mock PS Move controller for testing without hardware.

    Simulates the psmove API for unit testing controller logic.
    """

    def __init__(self):
        self.accel = (0, 0, 0)
        self.gyro = (0, 0, 0)
        self.buttons = 0
        self.trigger = 0
        self.battery = 5  # psmove.Batt_MAX equivalent
        self.last_poll_ = False
        self.led_r = 0
        self.led_g = 0
        self.led_b = 0
        self.rumble_intensity = 0
        self.leds_updated = False

    def poll(self):
        """Alternate yes/no returns to simulate draining the move's event queue."""
        self.last_poll_ = not self.last_poll_
        return self.last_poll_

    def get_buttons(self):
        return self.buttons

    def get_trigger(self):
        return self.trigger

    def get_accelerometer_frame(self, _):
        return self.accel

    def get_gyroscope_frame(self, _):
        return self.gyro

    def get_battery(self):
        return self.battery

    def set_leds(self, r, g, b):
        self.led_r = r
        self.led_g = g
        self.led_b = b

    def update_leds(self):
        self.leds_updated = True

    def set_rumble(self, intensity):
        self.rumble_intensity = intensity

    # Test helpers
    def set_accelerometer(self, x, y, z):
        """Set accelerometer values for testing."""
        self.accel = (x, y, z)

    def set_gyroscope(self, x, y, z):
        """Set gyroscope values for testing."""
        self.gyro = (x, y, z)

    def set_buttons(self, buttons):
        """Set button state for testing."""
        self.buttons = buttons

    def set_trigger(self, value):
        """Set trigger value for testing."""
        self.trigger = value


@pytest.fixture
def fake_move():
    """Provide a FakeMove instance for testing."""
    return FakeMove()
