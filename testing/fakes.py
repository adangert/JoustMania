class FakeMove:
    """Mock Move controller for testing."""

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

    # Alternate yes/no returns to simulate draining the move's event queue.
    def poll(self):
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

    def set_accelerometer(self, x, y, z):
        """Test helper to set accelerometer values."""
        self.accel = (x, y, z)

    def set_gyroscope(self, x, y, z):
        """Test helper to set gyroscope values."""
        self.gyro = (x, y, z)
