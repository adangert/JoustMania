
class FakeMove:
    def __init__(self):
        self.accel = (0, 0, 0)
        self.last_poll_ = False

    # Alternate yes/no returns to simulate draining the move's event queue.
    def poll(self):
        self.last_poll_ = not self.last_poll_
        return self.last_poll_

    def get_buttons(self):
        return 0

    def get_trigger(self):
        return 0

    def get_accelerometer_frame(self, _):
        return self.accel

    def set_leds(self, r, g, b):
        pass

    def update_leds(self):
        pass

    def set_rumble(self, intensity):
        pass
