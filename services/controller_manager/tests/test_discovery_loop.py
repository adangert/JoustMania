"""
Unit tests for DiscoveryLoop.

Tests activity tracking and adaptive polling logic.
"""

import time
from unittest.mock import MagicMock

from lib.controller_constants import AxisKey, ButtonKey, StateKey


class TestActivityTracking:
    """Tests for _update_activity_tracking method."""

    def _create_discovery_loop(self):
        """Create a DiscoveryLoop instance with mocked dependencies."""
        # Import here to avoid import errors during collection
        from services.controller_manager.discovery_loop import DiscoveryLoop

        # Mock all dependencies
        backend = MagicMock()
        tracked_controllers = {}
        controller_states = {}
        button_detector = MagicMock()
        state_cache_manager = MagicMock()
        feedback_manager = MagicMock()
        monitoring = MagicMock()
        monitoring.last_battery_check = 0
        rescan_timer = MagicMock()
        paired_serials = []
        base_colors = {}
        event_publisher = MagicMock()

        # Don't start the task - just return the instance
        return DiscoveryLoop(
            backend=backend,
            tracked_controllers=tracked_controllers,
            controller_states=controller_states,
            button_detector=button_detector,
            state_cache_manager=state_cache_manager,
            feedback_manager=feedback_manager,
            monitoring=monitoring,
            rescan_timer=rescan_timer,
            paired_serials=paired_serials,
            base_colors=base_colors,
            event_publisher=event_publisher,
        )

    def test_button_press_triggers_activity(self):
        """Any button press should be detected as activity."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        # Test each button
        button_keys = [
            ButtonKey.MOVE,
            ButtonKey.TRIGGER,
            ButtonKey.PS,
            ButtonKey.CROSS,
            ButtonKey.CIRCLE,
            ButtonKey.SQUARE,
            ButtonKey.TRIANGLE,
            ButtonKey.SELECT,
            ButtonKey.START,
        ]

        for button in button_keys:
            loop._last_activity_time = {}  # Reset
            state = {button: True}

            loop._update_activity_tracking(serial, state, current_time)

            assert serial in loop._last_activity_time, f"Button {button} should trigger activity"
            assert loop._last_activity_time[serial] == current_time

    def test_no_button_no_activity(self):
        """No buttons pressed should not trigger activity (without accel)."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        state = {
            ButtonKey.MOVE: False,
            ButtonKey.TRIGGER: False,
        }

        loop._update_activity_tracking(serial, state, current_time)

        # No activity tracked without accelerometer movement
        assert serial not in loop._last_activity_time

    def test_accelerometer_movement_triggers_activity(self):
        """Significant accelerometer change should trigger activity."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        # Set previous accelerometer reading
        loop._previous_accel[serial] = (0.0, 0.0, 1.0)

        # Significant movement (threshold is 0.05)
        state = {
            StateKey.ACCEL: {
                AxisKey.X: 0.1,  # Change of 0.1
                AxisKey.Y: 0.0,
                AxisKey.Z: 1.0,
            }
        }

        loop._update_activity_tracking(serial, state, current_time)

        assert serial in loop._last_activity_time
        assert loop._last_activity_time[serial] == current_time

    def test_small_accelerometer_change_no_activity(self):
        """Small accelerometer change (below threshold) should not trigger activity."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        # Set previous accelerometer reading
        loop._previous_accel[serial] = (0.0, 0.0, 1.0)

        # Small movement (below 0.05 threshold)
        state = {
            StateKey.ACCEL: {
                AxisKey.X: 0.01,
                AxisKey.Y: 0.01,
                AxisKey.Z: 1.01,
            }
        }

        loop._update_activity_tracking(serial, state, current_time)

        assert serial not in loop._last_activity_time

    def test_first_accel_reading_stores_without_activity(self):
        """First accelerometer reading should be stored but not trigger activity."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        # No previous reading
        assert serial not in loop._previous_accel

        state = {
            StateKey.ACCEL: {
                AxisKey.X: 0.5,
                AxisKey.Y: 0.5,
                AxisKey.Z: 1.0,
            }
        }

        loop._update_activity_tracking(serial, state, current_time)

        # Should store accel but not trigger activity (no comparison possible)
        assert loop._previous_accel[serial] == (0.5, 0.5, 1.0)
        assert serial not in loop._last_activity_time

    def test_accel_stored_after_tracking(self):
        """Accelerometer values should be stored for next comparison."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        loop._previous_accel[serial] = (0.0, 0.0, 1.0)

        state = {
            StateKey.ACCEL: {
                AxisKey.X: 0.2,
                AxisKey.Y: 0.3,
                AxisKey.Z: 0.9,
            }
        }

        loop._update_activity_tracking(serial, state, current_time)

        # New values should be stored
        assert loop._previous_accel[serial] == (0.2, 0.3, 0.9)


class TestAdaptivePollingLogic:
    """Tests for adaptive polling interval selection."""

    def _create_discovery_loop(self):
        """Create a DiscoveryLoop instance with mocked dependencies."""
        from services.controller_manager.discovery_loop import DiscoveryLoop

        backend = MagicMock()
        tracked_controllers = {}
        controller_states = {}
        button_detector = MagicMock()
        state_cache_manager = MagicMock()
        feedback_manager = MagicMock()
        monitoring = MagicMock()
        monitoring.last_battery_check = 0
        rescan_timer = MagicMock()
        paired_serials = []
        base_colors = {}
        event_publisher = MagicMock()

        return DiscoveryLoop(
            backend=backend,
            tracked_controllers=tracked_controllers,
            controller_states=controller_states,
            button_detector=button_detector,
            state_cache_manager=state_cache_manager,
            feedback_manager=feedback_manager,
            monitoring=monitoring,
            rescan_timer=rescan_timer,
            paired_serials=paired_serials,
            base_colors=base_colors,
            event_publisher=event_publisher,
        )

    def test_idle_threshold_default(self):
        """Default idle threshold is 5 seconds."""
        loop = self._create_discovery_loop()
        assert loop._idle_threshold_seconds == 5.0

    def test_poll_interval_default(self):
        """Default poll interval is 100Hz (10ms) - always fast polling."""
        loop = self._create_discovery_loop()
        assert loop._poll_interval == 0.010

    def test_accel_movement_threshold_default(self):
        """Default accelerometer movement threshold is 0.05."""
        loop = self._create_discovery_loop()
        assert loop._accel_movement_threshold == 0.05

    def test_controller_idle_after_threshold(self):
        """Controller is considered idle after threshold time without activity."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        # Last activity was 6 seconds ago (beyond 5s threshold)
        loop._last_activity_time[serial] = current_time - 6.0

        is_idle = (current_time - loop._last_activity_time.get(serial, current_time)) > loop._idle_threshold_seconds
        assert is_idle is True

    def test_controller_active_within_threshold(self):
        """Controller is considered active within threshold time."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        # Last activity was 2 seconds ago (within 5s threshold)
        loop._last_activity_time[serial] = current_time - 2.0

        is_idle = (current_time - loop._last_activity_time.get(serial, current_time)) > loop._idle_threshold_seconds
        assert is_idle is False

    def test_new_controller_defaults_to_active(self):
        """Controller with no activity record defaults to active (current time)."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        # No entry in _last_activity_time
        last_activity = loop._last_activity_time.get(serial, current_time)

        is_idle = (current_time - last_activity) > loop._idle_threshold_seconds
        assert is_idle is False  # New controllers are active


class TestDiscoveryLoopLifecycle:
    """Tests for DiscoveryLoop start/stop lifecycle."""

    def _create_discovery_loop(self):
        """Create a DiscoveryLoop instance with mocked dependencies."""
        from services.controller_manager.discovery_loop import DiscoveryLoop

        backend = MagicMock()
        backend.initialize = MagicMock(return_value=False)  # Prevent actual init
        tracked_controllers = {}
        controller_states = {}
        button_detector = MagicMock()
        state_cache_manager = MagicMock()
        feedback_manager = MagicMock()
        monitoring = MagicMock()
        monitoring.last_battery_check = 0
        rescan_timer = MagicMock()
        paired_serials = []
        base_colors = {}
        event_publisher = MagicMock()

        return DiscoveryLoop(
            backend=backend,
            tracked_controllers=tracked_controllers,
            controller_states=controller_states,
            button_detector=button_detector,
            state_cache_manager=state_cache_manager,
            feedback_manager=feedback_manager,
            monitoring=monitoring,
            rescan_timer=rescan_timer,
            paired_serials=paired_serials,
            base_colors=base_colors,
            event_publisher=event_publisher,
        )

    def test_init_sets_running_true(self):
        """DiscoveryLoop initializes with running=True."""
        loop = self._create_discovery_loop()
        assert loop.running is True

    def test_init_backend_not_initialized(self):
        """DiscoveryLoop initializes with backend_initialized=False."""
        loop = self._create_discovery_loop()
        assert loop.backend_initialized is False

    def test_stop_sets_running_false(self):
        """stop() sets running to False."""
        loop = self._create_discovery_loop()
        loop.stop()
        assert loop.running is False


class TestPollingStateCleanup:
    """Tests for polling state cleanup on controller disconnect."""

    def _create_discovery_loop(self):
        """Create a DiscoveryLoop instance with mocked dependencies."""
        from services.controller_manager.discovery_loop import DiscoveryLoop

        backend = MagicMock()
        tracked_controllers = {}
        controller_states = {}
        button_detector = MagicMock()
        state_cache_manager = MagicMock()
        feedback_manager = MagicMock()
        monitoring = MagicMock()
        monitoring.last_battery_check = 0
        rescan_timer = MagicMock()
        paired_serials = []
        base_colors = {}
        event_publisher = MagicMock()

        return DiscoveryLoop(
            backend=backend,
            tracked_controllers=tracked_controllers,
            controller_states=controller_states,
            button_detector=button_detector,
            state_cache_manager=state_cache_manager,
            feedback_manager=feedback_manager,
            monitoring=monitoring,
            rescan_timer=rescan_timer,
            paired_serials=paired_serials,
            base_colors=base_colors,
            event_publisher=event_publisher,
        )

    def test_adaptive_polling_state_initialized_empty(self):
        """Adaptive polling state dicts start empty."""
        loop = self._create_discovery_loop()

        assert loop._last_activity_time == {}
        assert loop._previous_accel == {}

    def test_activity_state_can_be_cleaned_up(self):
        """Activity tracking state can be removed using dict.pop()."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"

        # Set up state
        loop._last_activity_time[serial] = time.time()
        loop._previous_accel[serial] = (0.0, 0.0, 1.0)

        # Cleanup (as done in _check_for_new_controllers for disconnects)
        loop._last_activity_time.pop(serial, None)
        loop._previous_accel.pop(serial, None)

        assert serial not in loop._last_activity_time
        assert serial not in loop._previous_accel

    def test_cleanup_nonexistent_serial_safe(self):
        """Cleanup is safe for non-existent serials."""
        loop = self._create_discovery_loop()
        serial = "NONEXISTENT"

        # Should not raise
        loop._last_activity_time.pop(serial, None)
        loop._previous_accel.pop(serial, None)


class TestAccelerometerMovementCalculation:
    """Tests for accelerometer movement magnitude calculation."""

    def _create_discovery_loop(self):
        """Create a DiscoveryLoop instance with mocked dependencies."""
        from services.controller_manager.discovery_loop import DiscoveryLoop

        backend = MagicMock()
        tracked_controllers = {}
        controller_states = {}
        button_detector = MagicMock()
        state_cache_manager = MagicMock()
        feedback_manager = MagicMock()
        monitoring = MagicMock()
        monitoring.last_battery_check = 0
        rescan_timer = MagicMock()
        paired_serials = []
        base_colors = {}
        event_publisher = MagicMock()

        return DiscoveryLoop(
            backend=backend,
            tracked_controllers=tracked_controllers,
            controller_states=controller_states,
            button_detector=button_detector,
            state_cache_manager=state_cache_manager,
            feedback_manager=feedback_manager,
            monitoring=monitoring,
            rescan_timer=rescan_timer,
            paired_serials=paired_serials,
            base_colors=base_colors,
            event_publisher=event_publisher,
        )

    def test_movement_uses_manhattan_distance(self):
        """Movement is calculated as sum of absolute differences (Manhattan distance)."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        # Previous: (0, 0, 0)
        loop._previous_accel[serial] = (0.0, 0.0, 0.0)

        # Current: (0.02, 0.02, 0.02) -> total movement = 0.06 > 0.05 threshold
        state = {
            StateKey.ACCEL: {
                AxisKey.X: 0.02,
                AxisKey.Y: 0.02,
                AxisKey.Z: 0.02,
            }
        }

        loop._update_activity_tracking(serial, state, current_time)

        # 0.02 + 0.02 + 0.02 = 0.06 > 0.05, should trigger activity
        assert serial in loop._last_activity_time

    def test_movement_exactly_at_threshold(self):
        """Movement exactly at threshold should not trigger activity."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        loop._previous_accel[serial] = (0.0, 0.0, 0.0)

        # Exactly 0.05 movement
        state = {
            StateKey.ACCEL: {
                AxisKey.X: 0.05,
                AxisKey.Y: 0.0,
                AxisKey.Z: 0.0,
            }
        }

        loop._update_activity_tracking(serial, state, current_time)

        # 0.05 is not > 0.05, should NOT trigger activity
        assert serial not in loop._last_activity_time

    def test_movement_just_above_threshold(self):
        """Movement just above threshold should trigger activity."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        loop._previous_accel[serial] = (0.0, 0.0, 0.0)

        # Just above 0.05 movement
        state = {
            StateKey.ACCEL: {
                AxisKey.X: 0.051,
                AxisKey.Y: 0.0,
                AxisKey.Z: 0.0,
            }
        }

        loop._update_activity_tracking(serial, state, current_time)

        # 0.051 > 0.05, should trigger activity
        assert serial in loop._last_activity_time

    def test_negative_movement_uses_absolute_value(self):
        """Negative direction movement should use absolute value."""
        loop = self._create_discovery_loop()
        serial = "SERIAL1"
        current_time = time.time()

        loop._previous_accel[serial] = (0.1, 0.1, 0.1)

        # Movement in negative direction
        state = {
            StateKey.ACCEL: {
                AxisKey.X: 0.0,  # -0.1 change
                AxisKey.Y: 0.1,
                AxisKey.Z: 0.1,
            }
        }

        loop._update_activity_tracking(serial, state, current_time)

        # |0.0 - 0.1| = 0.1 > 0.05, should trigger activity
        assert serial in loop._last_activity_time
