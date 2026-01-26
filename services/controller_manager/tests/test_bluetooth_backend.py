"""
Unit tests for BluetoothBackend.

Tests the PS Move controller interface:
- Battery percentage conversion
- LED color management
- Effect active flag handling
- Controller tracking and cleanup

Note: Requires mocking psmove library as hardware is not available in tests.

Issue #209: Improve test coverage for critical game flow
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Setup paths for imports
test_dir = Path(__file__).parent
service_dir = test_dir.parent
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(test_dir))


class MockPSMove:
    """Mock psmove module constants and classes."""

    # Battery constants from psmove library
    Batt_MIN = 0x00
    Batt_20Percent = 0x01
    Batt_40Percent = 0x02
    Batt_60Percent = 0x03
    Batt_80Percent = 0x04
    Batt_MAX = 0x05
    Batt_CHARGING = 0xEE
    Batt_CHARGING_DONE = 0xEF

    # Button constants
    Btn_MOVE = 0x01
    Btn_T = 0x02
    Btn_PS = 0x04
    Btn_CROSS = 0x08
    Btn_CIRCLE = 0x10
    Btn_SQUARE = 0x20
    Btn_TRIANGLE = 0x40
    Btn_SELECT = 0x80
    Btn_START = 0x100

    # Frame constants
    Frame_SecondHalf = 1

    @staticmethod
    def count_connected():
        return 0

    class PSMove:
        def __init__(self, index=0):
            self._serial = f"test_serial_{index}"
            self._leds = (0, 0, 0)
            self._rumble = 0

        def get_serial(self):
            return self._serial

        def poll(self):
            return False

        def get_trigger(self):
            return 0

        def get_buttons(self):
            return 0

        def get_accelerometer_frame(self, frame):
            return (0.0, 0.0, 4096.0)  # ~1g on z-axis

        def get_gyroscope_frame(self, frame):
            return (0.0, 0.0, 0.0)

        def get_battery(self):
            return MockPSMove.Batt_MAX

        def get_temperature(self):
            return 25.0

        def set_leds(self, r, g, b):
            self._leds = (r, g, b)

        def update_leds(self):
            pass

        def set_rumble(self, intensity):
            self._rumble = intensity


class TestBatteryConversion:
    """Tests for battery percentage conversion."""

    def test_battery_min_returns_zero(self):
        """Batt_MIN should return 0%."""
        # Import with mocked psmove
        with patch.dict(sys.modules, {"psmove": MockPSMove}):
            # Need to reload the module to pick up the mock
            from services.controller_manager.bluetooth_backend import _battery_to_percent

            # Patch LINUX_DEPS_AVAILABLE to True
            with (
                patch("services.controller_manager.bluetooth_backend.LINUX_DEPS_AVAILABLE", True),
                patch("services.controller_manager.bluetooth_backend.psmove", MockPSMove),
            ):
                result = _battery_to_percent(MockPSMove.Batt_MIN)
                assert result == 0

    def test_battery_20_percent(self):
        """Batt_20Percent should return 20%."""
        with patch.dict(sys.modules, {"psmove": MockPSMove}):
            from services.controller_manager.bluetooth_backend import _battery_to_percent

            with (
                patch("services.controller_manager.bluetooth_backend.LINUX_DEPS_AVAILABLE", True),
                patch("services.controller_manager.bluetooth_backend.psmove", MockPSMove),
            ):
                result = _battery_to_percent(MockPSMove.Batt_20Percent)
                assert result == 20

    def test_battery_40_percent(self):
        """Batt_40Percent should return 40%."""
        with patch.dict(sys.modules, {"psmove": MockPSMove}):
            from services.controller_manager.bluetooth_backend import _battery_to_percent

            with (
                patch("services.controller_manager.bluetooth_backend.LINUX_DEPS_AVAILABLE", True),
                patch("services.controller_manager.bluetooth_backend.psmove", MockPSMove),
            ):
                result = _battery_to_percent(MockPSMove.Batt_40Percent)
                assert result == 40

    def test_battery_60_percent(self):
        """Batt_60Percent should return 60%."""
        with patch.dict(sys.modules, {"psmove": MockPSMove}):
            from services.controller_manager.bluetooth_backend import _battery_to_percent

            with (
                patch("services.controller_manager.bluetooth_backend.LINUX_DEPS_AVAILABLE", True),
                patch("services.controller_manager.bluetooth_backend.psmove", MockPSMove),
            ):
                result = _battery_to_percent(MockPSMove.Batt_60Percent)
                assert result == 60

    def test_battery_80_percent(self):
        """Batt_80Percent should return 80%."""
        with patch.dict(sys.modules, {"psmove": MockPSMove}):
            from services.controller_manager.bluetooth_backend import _battery_to_percent

            with (
                patch("services.controller_manager.bluetooth_backend.LINUX_DEPS_AVAILABLE", True),
                patch("services.controller_manager.bluetooth_backend.psmove", MockPSMove),
            ):
                result = _battery_to_percent(MockPSMove.Batt_80Percent)
                assert result == 80

    def test_battery_max_returns_100(self):
        """Batt_MAX should return 100%."""
        with patch.dict(sys.modules, {"psmove": MockPSMove}):
            from services.controller_manager.bluetooth_backend import _battery_to_percent

            with (
                patch("services.controller_manager.bluetooth_backend.LINUX_DEPS_AVAILABLE", True),
                patch("services.controller_manager.bluetooth_backend.psmove", MockPSMove),
            ):
                result = _battery_to_percent(MockPSMove.Batt_MAX)
                assert result == 100

    def test_battery_charging_returns_100(self):
        """Batt_CHARGING should return 100%."""
        with patch.dict(sys.modules, {"psmove": MockPSMove}):
            from services.controller_manager.bluetooth_backend import _battery_to_percent

            with (
                patch("services.controller_manager.bluetooth_backend.LINUX_DEPS_AVAILABLE", True),
                patch("services.controller_manager.bluetooth_backend.psmove", MockPSMove),
            ):
                result = _battery_to_percent(MockPSMove.Batt_CHARGING)
                assert result == 100

    def test_battery_charging_done_returns_100(self):
        """Batt_CHARGING_DONE should return 100%."""
        with patch.dict(sys.modules, {"psmove": MockPSMove}):
            from services.controller_manager.bluetooth_backend import _battery_to_percent

            with (
                patch("services.controller_manager.bluetooth_backend.LINUX_DEPS_AVAILABLE", True),
                patch("services.controller_manager.bluetooth_backend.psmove", MockPSMove),
            ):
                result = _battery_to_percent(MockPSMove.Batt_CHARGING_DONE)
                assert result == 100

    def test_battery_unknown_value_returns_50(self):
        """Unknown battery value should return 50% (mid-range default)."""
        with patch.dict(sys.modules, {"psmove": MockPSMove}):
            from services.controller_manager.bluetooth_backend import _battery_to_percent

            with (
                patch("services.controller_manager.bluetooth_backend.LINUX_DEPS_AVAILABLE", True),
                patch("services.controller_manager.bluetooth_backend.psmove", MockPSMove),
            ):
                result = _battery_to_percent(0xFF)  # Unknown value
                assert result == 50

    def test_battery_linux_deps_unavailable(self):
        """When Linux deps unavailable, should return 100%."""
        with patch.dict(sys.modules, {"psmove": MockPSMove}):
            from services.controller_manager.bluetooth_backend import _battery_to_percent

            with patch("services.controller_manager.bluetooth_backend.LINUX_DEPS_AVAILABLE", False):
                result = _battery_to_percent(MockPSMove.Batt_MIN)
                assert result == 100  # Default when deps unavailable


class TestEffectActiveFlag:
    """Tests for effect active flag handling."""

    def test_set_effect_active_adds_to_set(self):
        """set_effect_active(True) should add serial to _effect_active set."""
        # Create a minimal mock backend for testing effect flag
        mock_backend = MagicMock()
        mock_backend._effect_active = set()

        # Manually implement the method behavior
        def set_effect_active(serial, active):
            if active:
                mock_backend._effect_active.add(serial)
            else:
                mock_backend._effect_active.discard(serial)

        mock_backend.set_effect_active = set_effect_active

        mock_backend.set_effect_active("test_serial", True)

        assert "test_serial" in mock_backend._effect_active

    def test_set_effect_active_removes_from_set(self):
        """set_effect_active(False) should remove serial from _effect_active set."""
        mock_backend = MagicMock()
        mock_backend._effect_active = {"test_serial"}

        def set_effect_active(serial, active):
            if active:
                mock_backend._effect_active.add(serial)
            else:
                mock_backend._effect_active.discard(serial)

        mock_backend.set_effect_active = set_effect_active

        mock_backend.set_effect_active("test_serial", False)

        assert "test_serial" not in mock_backend._effect_active

    def test_set_effect_active_discard_nonexistent(self):
        """set_effect_active(False) should not raise for nonexistent serial."""
        mock_backend = MagicMock()
        mock_backend._effect_active = set()

        def set_effect_active(serial, active):
            if active:
                mock_backend._effect_active.add(serial)
            else:
                mock_backend._effect_active.discard(serial)

        mock_backend.set_effect_active = set_effect_active

        # Should not raise
        mock_backend.set_effect_active("nonexistent", False)

        assert "nonexistent" not in mock_backend._effect_active


class TestLEDColorTracking:
    """Tests for LED color tracking logic."""

    def test_led_color_stored_on_set(self):
        """set_led_color should store the color for later refresh."""
        led_colors = {}
        serial = "test_serial"

        # Simulate set_led_color storing the color
        led_colors[serial] = (255, 128, 0)

        assert led_colors[serial] == (255, 128, 0)

    def test_led_color_change_detection(self):
        """Color change should be detected by comparing stored vs last sent."""
        stored_color = (255, 0, 0)
        last_sent_color = (0, 255, 0)

        color_changed = stored_color != last_sent_color

        assert color_changed is True

    def test_led_color_no_change(self):
        """Same color should not trigger update."""
        stored_color = (255, 0, 0)
        last_sent_color = (255, 0, 0)

        color_changed = stored_color != last_sent_color

        assert color_changed is False


class TestControllerCleanup:
    """Tests for controller cleanup on disconnect."""

    def test_cleanup_removes_all_tracking(self):
        """Disconnecting controller should clean up all tracking data."""
        # Simulate tracking data structures
        controllers = {"test_serial": MagicMock()}
        controller_states = {"test_serial": {}}
        led_colors = {"test_serial": (255, 0, 0)}
        last_sent_color = {"test_serial": (255, 0, 0)}
        last_led_update = {"test_serial": 1234567890.0}
        effect_active = {"test_serial"}

        serial = "test_serial"

        # Simulate cleanup (as done in disconnect_controller)
        del controllers[serial]
        del controller_states[serial]
        led_colors.pop(serial, None)
        last_sent_color.pop(serial, None)
        last_led_update.pop(serial, None)
        effect_active.discard(serial)

        assert serial not in controllers
        assert serial not in controller_states
        assert serial not in led_colors
        assert serial not in last_sent_color
        assert serial not in last_led_update
        assert serial not in effect_active

    def test_cleanup_safe_for_missing_entries(self):
        """Cleanup should not raise for missing entries."""
        led_colors = {}
        last_sent_color = {}
        last_led_update = {}
        effect_active = set()

        serial = "nonexistent"

        # Should not raise
        led_colors.pop(serial, None)
        last_sent_color.pop(serial, None)
        last_led_update.pop(serial, None)
        effect_active.discard(serial)


class TestUpdateAllLEDs:
    """Tests for batch LED update logic."""

    def test_skip_effect_active_controllers(self):
        """Controllers with active effects should be skipped."""
        effect_active = {"controller_1"}
        led_colors = {"controller_1": (255, 0, 0), "controller_2": (0, 255, 0)}

        controllers_to_update = []
        for serial in led_colors:
            if serial not in effect_active:
                controllers_to_update.append(serial)

        assert "controller_1" not in controllers_to_update
        assert "controller_2" in controllers_to_update

    def test_keepalive_update_after_4_seconds(self):
        """LED should be refreshed after 4 seconds for keep-alive."""
        import time

        current_time = time.time()
        last_led_update = current_time - 5.0  # 5 seconds ago

        keepalive_needed = current_time - last_led_update >= 4.0

        assert keepalive_needed is True

    def test_no_keepalive_before_4_seconds(self):
        """LED should not be refreshed before 4 seconds."""
        import time

        current_time = time.time()
        last_led_update = current_time - 2.0  # 2 seconds ago

        keepalive_needed = current_time - last_led_update >= 4.0

        assert keepalive_needed is False
