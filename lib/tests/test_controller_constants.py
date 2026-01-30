"""Tests for lib/controller_constants.py"""

import sys
from pathlib import Path

# Add lib to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.controller_constants import (
    BUTTON_TRACKING_TO_STATE,
    DEFAULT_ACCEL,
    DEFAULT_BATTERY,
    DEFAULT_GYRO,
    AxisKey,
    ButtonKey,
    ButtonTrackingKey,
    ControllerInfoKey,
    LobbyState,
    StateKey,
)


class TestButtonKey:
    """Tests for ButtonKey enum."""

    def test_all_buttons_are_strings(self):
        """All button keys should be usable as strings."""
        for button in ButtonKey:
            assert isinstance(button.value, str)
            # Should be usable as dict key
            d = {button: True}
            assert d[button] is True

    def test_expected_buttons_exist(self):
        """Should have all expected PS Move buttons."""
        assert ButtonKey.TRIGGER.value == "trigger_button"
        assert ButtonKey.MOVE.value == "move_button"
        assert ButtonKey.PS.value == "ps_button"
        assert ButtonKey.CROSS.value == "cross"
        assert ButtonKey.CIRCLE.value == "circle"
        assert ButtonKey.SQUARE.value == "square"
        assert ButtonKey.TRIANGLE.value == "triangle"


class TestStateKey:
    """Tests for StateKey enum."""

    def test_state_keys_are_strings(self):
        """All state keys should be usable as strings."""
        for key in StateKey:
            assert isinstance(key.value, str)

    def test_expected_keys_exist(self):
        """Should have expected state keys."""
        assert StateKey.SERIAL.value == "serial"
        assert StateKey.TRIGGER.value == "trigger"
        assert StateKey.BATTERY.value == "battery"
        assert StateKey.ACCEL.value == "accel"
        assert StateKey.GYRO.value == "gyro"


class TestAxisKey:
    """Tests for AxisKey enum."""

    def test_axis_keys(self):
        """Should have x, y, z axes."""
        assert AxisKey.X.value == "x"
        assert AxisKey.Y.value == "y"
        assert AxisKey.Z.value == "z"


class TestControllerInfoKey:
    """Tests for ControllerInfoKey enum."""

    def test_info_keys_are_strings(self):
        """All info keys should be strings."""
        for key in ControllerInfoKey:
            assert isinstance(key.value, str)

    def test_expected_keys_exist(self):
        """Should have expected controller info keys."""
        assert ControllerInfoKey.SERIAL.value == "serial"
        assert ControllerInfoKey.BATTERY.value == "battery"
        assert ControllerInfoKey.TEAM.value == "team"
        assert ControllerInfoKey.CONNECTED_AT.value == "connected_at"


class TestLobbyState:
    """Tests for LobbyState enum."""

    def test_lobby_states(self):
        """Should have expected lobby states."""
        assert LobbyState.FLASH.value == "flash"
        assert LobbyState.CONNECTED.value == "connected"
        assert LobbyState.READY.value == "ready"
        assert LobbyState.ADMIN.value == "admin"


class TestButtonTrackingToState:
    """Tests for BUTTON_TRACKING_TO_STATE mapping."""

    def test_all_tracking_keys_mapped(self):
        """All ButtonTrackingKey values should be mapped."""
        for tracking_key in ButtonTrackingKey:
            assert tracking_key in BUTTON_TRACKING_TO_STATE

    def test_mapping_returns_button_keys(self):
        """Mapping should return ButtonKey values."""
        for _tracking_key, button_key in BUTTON_TRACKING_TO_STATE.items():
            assert isinstance(button_key, ButtonKey)


class TestDefaults:
    """Tests for default values."""

    def test_default_battery(self):
        """Default battery should be reasonable value."""
        assert DEFAULT_BATTERY == 5
        assert 0 <= DEFAULT_BATTERY <= 7

    def test_default_accel(self):
        """Default accel should represent rest (1g gravity on z)."""
        assert DEFAULT_ACCEL == {"x": 0.0, "y": 0.0, "z": 1.0}
        assert "x" in DEFAULT_ACCEL
        assert "y" in DEFAULT_ACCEL
        assert "z" in DEFAULT_ACCEL

    def test_default_gyro(self):
        """Default gyro should be zero (no rotation)."""
        assert DEFAULT_GYRO == {"x": 0.0, "y": 0.0, "z": 0.0}
