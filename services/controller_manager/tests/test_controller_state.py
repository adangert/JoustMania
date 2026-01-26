"""
Unit tests for ControllerState and ControllerStateManager.

Tests the shared memory state management:
- ControllerState initialization
- State updates from hardware
- Snapshot generation
- Freshness checking
- LED and rumble control
- ControllerStateManager operations

Note: Requires mocking psmove library as hardware is not available in tests.

Issue #209: Improve test coverage for critical game flow
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Setup paths for imports
test_dir = Path(__file__).parent
service_dir = test_dir.parent
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(test_dir))


class MockPSMove:
    """Mock psmove module for testing."""

    Batt_MIN = 0x00
    Batt_MAX = 0x05
    Frame_SecondHalf = 1

    class PSMove:
        def poll(self):
            return True

        def get_accelerometer_frame(self, frame):
            return (0.1, 0.2, 4096.0)

        def get_gyroscope_frame(self, frame):
            return (0.01, 0.02, 0.03)

        def get_buttons(self):
            return 0

        def get_trigger(self):
            return 128

        def get_battery(self):
            return MockPSMove.Batt_MAX

        def set_leds(self, r, g, b):
            pass

        def set_rumble(self, intensity):
            pass

        def update_leds(self):
            pass


# Patch psmove before importing controller_state
with patch.dict(sys.modules, {"psmove": MockPSMove}):
    from services.controller_manager.controller_state import (
        ControllerState,
        ControllerStateManager,
    )


class TestControllerStateInit:
    """Tests for ControllerState initialization."""

    def test_init_accel_zero(self):
        """Accelerometer should initialize to zero."""
        state = ControllerState()

        assert state.accel_x.value == 0.0
        assert state.accel_y.value == 0.0
        assert state.accel_z.value == 0.0

    def test_init_gyro_zero(self):
        """Gyroscope should initialize to zero."""
        state = ControllerState()

        assert state.gyro_x.value == 0.0
        assert state.gyro_y.value == 0.0
        assert state.gyro_z.value == 0.0

    def test_init_buttons_zero(self):
        """Buttons should initialize to zero."""
        state = ControllerState()

        assert state.buttons.value == 0

    def test_init_trigger_zero(self):
        """Trigger should initialize to zero."""
        state = ControllerState()

        assert state.trigger.value == 0

    def test_init_not_connected(self):
        """Controller should start as not connected."""
        state = ControllerState()

        assert state.connected.value == False  # noqa: E712 - Value wrapper returns int

    def test_init_led_off(self):
        """LED should initialize to off (0, 0, 0)."""
        state = ControllerState()

        assert state.led_r.value == 0
        assert state.led_g.value == 0
        assert state.led_b.value == 0

    def test_init_rumble_off(self):
        """Rumble should initialize to off."""
        state = ControllerState()

        assert state.rumble.value == 0


class TestControllerStateUpdate:
    """Tests for ControllerState update method."""

    def test_update_sets_connected(self):
        """update() should mark controller as connected."""
        state = ControllerState()
        mock_move = MockPSMove.PSMove()

        state.update(mock_move)

        assert state.connected.value == True  # noqa: E712 - Value wrapper returns int

    def test_update_sets_timestamp(self):
        """update() should set timestamp."""
        state = ControllerState()
        mock_move = MockPSMove.PSMove()

        before = time.time()
        state.update(mock_move)
        after = time.time()

        assert before <= state.timestamp.value <= after

    def test_update_increments_count(self):
        """update() should increment update_count."""
        state = ControllerState()
        mock_move = MockPSMove.PSMove()

        initial_count = state.update_count.value
        state.update(mock_move)

        assert state.update_count.value == initial_count + 1

    def test_update_reads_accel(self):
        """update() should read accelerometer values."""
        state = ControllerState()
        mock_move = MockPSMove.PSMove()

        state.update(mock_move)

        assert state.accel_x.value == pytest.approx(0.1, rel=1e-5)
        assert state.accel_y.value == pytest.approx(0.2, rel=1e-5)
        assert state.accel_z.value == pytest.approx(4096.0, rel=1e-5)

    def test_update_reads_trigger(self):
        """update() should read trigger value."""
        state = ControllerState()
        mock_move = MockPSMove.PSMove()

        state.update(mock_move)

        assert state.trigger.value == 128

    def test_update_returns_true_on_poll(self):
        """update() should return True when poll succeeds."""
        state = ControllerState()
        mock_move = MockPSMove.PSMove()

        result = state.update(mock_move)

        assert result is True

    def test_update_returns_false_no_data(self):
        """update() should return False when no data available."""
        state = ControllerState()
        mock_move = MagicMock()
        mock_move.poll.return_value = False

        result = state.update(mock_move)

        assert result is False


class TestControllerStateSnapshot:
    """Tests for ControllerState get_snapshot method."""

    def test_snapshot_includes_accel(self):
        """get_snapshot() should include accelerometer tuple."""
        state = ControllerState()
        state.accel_x.value = 1.0
        state.accel_y.value = 2.0
        state.accel_z.value = 3.0

        snapshot = state.get_snapshot()

        assert snapshot["accelerometer"] == (1.0, 2.0, 3.0)

    def test_snapshot_includes_gyro(self):
        """get_snapshot() should include gyroscope tuple."""
        state = ControllerState()
        state.gyro_x.value = 0.1
        state.gyro_y.value = 0.2
        state.gyro_z.value = 0.3

        snapshot = state.get_snapshot()

        # Use approx for float comparison due to Value wrapper precision
        assert snapshot["gyroscope"][0] == pytest.approx(0.1, rel=1e-5)
        assert snapshot["gyroscope"][1] == pytest.approx(0.2, rel=1e-5)
        assert snapshot["gyroscope"][2] == pytest.approx(0.3, rel=1e-5)

    def test_snapshot_includes_buttons(self):
        """get_snapshot() should include buttons."""
        state = ControllerState()
        state.buttons.value = 0x05

        snapshot = state.get_snapshot()

        assert snapshot["buttons"] == 0x05

    def test_snapshot_includes_trigger(self):
        """get_snapshot() should include trigger."""
        state = ControllerState()
        state.trigger.value = 200

        snapshot = state.get_snapshot()

        assert snapshot["trigger"] == 200

    def test_snapshot_includes_connected(self):
        """get_snapshot() should include connected status."""
        state = ControllerState()
        state.connected.value = 1  # Value wrapper uses int

        snapshot = state.get_snapshot()

        assert snapshot["connected"] == 1  # Value wrapper returns int

    def test_snapshot_calculates_age(self):
        """get_snapshot() should calculate age_ms."""
        state = ControllerState()
        state.timestamp.value = time.time() - 0.1  # 100ms ago

        snapshot = state.get_snapshot()

        # Should be around 100ms, allow some tolerance
        assert 90 < snapshot["age_ms"] < 200


class TestControllerStateFreshness:
    """Tests for ControllerState freshness checking."""

    def test_is_fresh_true_recent_update(self):
        """is_fresh() should return True for recent updates."""
        state = ControllerState()
        state.timestamp.value = time.time()

        assert state.is_fresh(max_age_ms=100.0) is True

    def test_is_fresh_false_old_update(self):
        """is_fresh() should return False for old updates."""
        state = ControllerState()
        state.timestamp.value = time.time() - 1.0  # 1 second ago

        assert state.is_fresh(max_age_ms=100.0) is False

    def test_is_fresh_false_no_timestamp(self):
        """is_fresh() should return False when no timestamp."""
        state = ControllerState()
        # timestamp stays at 0.0

        assert state.is_fresh(max_age_ms=100.0) is False


class TestControllerStateLEDs:
    """Tests for LED control."""

    def test_set_leds_updates_values(self):
        """set_leds() should update LED values."""
        state = ControllerState()

        state.set_leds(255, 128, 64)

        assert state.led_r.value == 255
        assert state.led_g.value == 128
        assert state.led_b.value == 64


class TestControllerStateRumble:
    """Tests for rumble control."""

    def test_set_rumble_updates_value(self):
        """set_rumble() should update rumble value."""
        state = ControllerState()

        state.set_rumble(200)

        assert state.rumble.value == 200


class TestControllerStateDisconnect:
    """Tests for disconnect handling."""

    def test_mark_disconnected(self):
        """mark_disconnected() should set connected to False."""
        state = ControllerState()
        state.connected.value = 1  # Value wrapper uses int

        state.mark_disconnected()

        assert state.connected.value == 0  # Value wrapper returns int


class TestControllerStateManagerInit:
    """Tests for ControllerStateManager initialization."""

    def test_init_empty_states(self):
        """Manager should start with empty states."""
        manager = ControllerStateManager()

        assert manager.states == {}

    def test_init_empty_mapping(self):
        """Manager should start with empty move_num mapping."""
        manager = ControllerStateManager()

        assert manager.move_num_to_serial == {}


class TestControllerStateManagerCreate:
    """Tests for ControllerStateManager create_state method."""

    def test_create_state_returns_state(self):
        """create_state() should return a ControllerState."""
        manager = ControllerStateManager()

        state = manager.create_state("serial_1", 0)

        assert isinstance(state, ControllerState)

    def test_create_state_adds_to_states(self):
        """create_state() should add state to manager."""
        manager = ControllerStateManager()

        manager.create_state("serial_1", 0)

        assert "serial_1" in manager.states

    def test_create_state_adds_mapping(self):
        """create_state() should add move_num mapping."""
        manager = ControllerStateManager()

        manager.create_state("serial_1", 5)

        assert manager.move_num_to_serial[5] == "serial_1"

    def test_create_state_returns_existing(self):
        """create_state() should return existing state if already exists."""
        manager = ControllerStateManager()

        state1 = manager.create_state("serial_1", 0)
        state2 = manager.create_state("serial_1", 1)

        assert state1 is state2


class TestControllerStateManagerGet:
    """Tests for ControllerStateManager get methods."""

    def test_get_state_returns_state(self):
        """get_state() should return state by serial."""
        manager = ControllerStateManager()
        created = manager.create_state("serial_1", 0)

        retrieved = manager.get_state("serial_1")

        assert retrieved is created

    def test_get_state_returns_none_missing(self):
        """get_state() should return None for missing serial."""
        manager = ControllerStateManager()

        result = manager.get_state("nonexistent")

        assert result is None

    def test_get_state_by_num(self):
        """get_state_by_num() should return state by move number."""
        manager = ControllerStateManager()
        created = manager.create_state("serial_1", 5)

        retrieved = manager.get_state_by_num(5)

        assert retrieved is created

    def test_get_state_by_num_returns_none_missing(self):
        """get_state_by_num() should return None for missing num."""
        manager = ControllerStateManager()

        result = manager.get_state_by_num(99)

        assert result is None


class TestControllerStateManagerRemove:
    """Tests for ControllerStateManager remove_state method."""

    def test_remove_state(self):
        """remove_state() should remove state from manager."""
        manager = ControllerStateManager()
        manager.create_state("serial_1", 0)

        manager.remove_state("serial_1")

        assert "serial_1" not in manager.states

    def test_remove_state_cleans_mapping(self):
        """remove_state() should clean up move_num mapping."""
        manager = ControllerStateManager()
        manager.create_state("serial_1", 5)

        manager.remove_state("serial_1")

        assert 5 not in manager.move_num_to_serial

    def test_remove_state_nonexistent_safe(self):
        """remove_state() should not raise for nonexistent serial."""
        manager = ControllerStateManager()

        # Should not raise
        manager.remove_state("nonexistent")


class TestControllerStateManagerBulk:
    """Tests for bulk operations."""

    def test_get_all_states(self):
        """get_all_states() should return copy of all states."""
        manager = ControllerStateManager()
        manager.create_state("serial_1", 0)
        manager.create_state("serial_2", 1)

        all_states = manager.get_all_states()

        assert len(all_states) == 2
        assert "serial_1" in all_states
        assert "serial_2" in all_states

    def test_get_fresh_states(self):
        """get_fresh_states() should return only fresh controllers."""
        manager = ControllerStateManager()
        state1 = manager.create_state("serial_1", 0)
        manager.create_state("serial_2", 1)  # state2 - leave stale

        # Make state1 fresh
        state1.timestamp.value = time.time()
        # Leave serial_2 stale (timestamp=0)

        fresh = manager.get_fresh_states(max_age_ms=100.0)

        assert "serial_1" in fresh
        assert "serial_2" not in fresh

    def test_get_stale_controllers(self):
        """get_stale_controllers() should return list of stale serials."""
        manager = ControllerStateManager()
        state1 = manager.create_state("serial_1", 0)
        manager.create_state("serial_2", 1)  # state2 - leave stale

        # Make state1 fresh
        state1.timestamp.value = time.time()
        # Leave serial_2 stale (timestamp=0)

        stale = manager.get_stale_controllers(max_age_ms=100.0)

        assert "serial_2" in stale
        assert "serial_1" not in stale
