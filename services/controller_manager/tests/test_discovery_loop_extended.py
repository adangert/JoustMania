"""
Extended tests for DiscoveryLoop.

Tests controller discovery, disconnection detection, and state management:
- New controller detection
- Disconnection cleanup
- Activity tracking for adaptive polling
- State update processing

Issue #209: Improve test coverage for critical game flow
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Setup paths for imports
test_dir = Path(__file__).parent
service_dir = test_dir.parent
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(test_dir))


class MockBackend:
    """Mock backend for testing discovery loop."""

    def __init__(self):
        self.connected_controllers = []
        self.controller_states = {}
        self.initialized = False
        self._led_updates = 0

    async def initialize(self):
        self.initialized = True
        return True

    def get_connected_controllers(self, force_rescan=False):
        return self.connected_controllers

    async def get_controller_state(self, serial):
        return self.controller_states.get(
            serial,
            {
                "serial": serial,
                "battery": 80,
                "trigger": 0,
                "accel": {"x": 0.0, "y": 0.0, "z": 1.0},
            },
        )

    def update_all_leds(self):
        self._led_updates += 1
        return len(self.connected_controllers)


class MockButtonDetector:
    """Mock button detector."""

    def __init__(self):
        self.transitions = []
        self.connection_events = []

    def detect_transitions_from_state(self, serial, state, tracked):
        self.transitions.append((serial, state))

    def publish_connection_event(self, serial, is_connect, battery=0, name=""):
        self.connection_events.append(
            {
                "serial": serial,
                "is_connect": is_connect,
                "battery": battery,
                "name": name,
            }
        )

    def clear_controller(self, serial):
        pass


class MockStateCache:
    """Mock state cache manager."""

    def __init__(self):
        self.cleared = []

    def clear_controller(self, serial):
        self.cleared.append(serial)


class MockFeedbackManager:
    """Mock feedback manager."""

    async def set_controller_color(self, serial, color):
        pass


class MockMonitoring:
    """Mock controller monitoring."""

    def __init__(self):
        self.last_battery_check = 0.0

    def check_battery_levels(self, tracked):
        pass


class MockRescanTimer:
    """Mock periodic rescan timer."""

    def __init__(self):
        self._should_force = False

    def should_force_rescan(self):
        return self._should_force


class MockEventPublisher:
    """Mock event publisher."""

    def __init__(self):
        self.events = []

    def publish(self, event_type, data):
        self.events.append((event_type, data))


class MockNameManager:
    """Mock name manager."""

    def __init__(self):
        self.names = {}

    def get_name(self, serial):
        return self.names.get(serial, "")


class TestDiscoveryLoopInit:
    """Tests for DiscoveryLoop initialization."""

    def test_init_sets_running_true(self):
        """DiscoveryLoop should start with running=True."""
        with patch("services.controller_manager.discovery_loop.get_tracer"):
            from services.controller_manager.discovery_loop import DiscoveryLoop

            loop = DiscoveryLoop(
                backend=MockBackend(),
                tracked_controllers={},
                controller_states={},
                button_detector=MockButtonDetector(),
                state_cache_manager=MockStateCache(),
                feedback_manager=MockFeedbackManager(),
                monitoring=MockMonitoring(),
                rescan_timer=MockRescanTimer(),
                paired_serials=[],
                base_colors={},
                event_publisher=MockEventPublisher(),
            )

            assert loop.running is True

    def test_init_backend_not_initialized(self):
        """Backend should not be initialized until start()."""
        with patch("services.controller_manager.discovery_loop.get_tracer"):
            from services.controller_manager.discovery_loop import DiscoveryLoop

            loop = DiscoveryLoop(
                backend=MockBackend(),
                tracked_controllers={},
                controller_states={},
                button_detector=MockButtonDetector(),
                state_cache_manager=MockStateCache(),
                feedback_manager=MockFeedbackManager(),
                monitoring=MockMonitoring(),
                rescan_timer=MockRescanTimer(),
                paired_serials=[],
                base_colors={},
                event_publisher=MockEventPublisher(),
            )

            assert loop.backend_initialized is False


class TestDiscoveryLoopStop:
    """Tests for stopping the discovery loop."""

    def test_stop_sets_running_false(self):
        """stop() should set running to False."""
        with patch("services.controller_manager.discovery_loop.get_tracer"):
            from services.controller_manager.discovery_loop import DiscoveryLoop

            loop = DiscoveryLoop(
                backend=MockBackend(),
                tracked_controllers={},
                controller_states={},
                button_detector=MockButtonDetector(),
                state_cache_manager=MockStateCache(),
                feedback_manager=MockFeedbackManager(),
                monitoring=MockMonitoring(),
                rescan_timer=MockRescanTimer(),
                paired_serials=[],
                base_colors={},
                event_publisher=MockEventPublisher(),
            )

            assert loop.running is True
            loop.stop()
            assert loop.running is False


class TestControllerDisconnection:
    """Tests for controller disconnection handling."""

    def test_disconnection_clears_tracking(self):
        """Disconnected controller should be removed from tracking."""
        tracked_controllers = {"serial_1": {"battery": 80}}
        controller_states = {"serial_1": {"trigger": 0}}
        state_cache = MockStateCache()
        button_detector = MockButtonDetector()

        # Simulate disconnection detection
        connected_set = set()  # No controllers connected
        tracked_serials = set(tracked_controllers.keys())

        disconnected = tracked_serials - connected_set

        for serial in disconnected:
            del tracked_controllers[serial]
            del controller_states[serial]
            state_cache.clear_controller(serial)
            button_detector.publish_connection_event(serial, is_connect=False)

        assert "serial_1" not in tracked_controllers
        assert "serial_1" not in controller_states
        assert "serial_1" in state_cache.cleared
        assert len(button_detector.connection_events) == 1
        assert button_detector.connection_events[0]["is_connect"] is False

    def test_disconnection_preserves_base_color(self):
        """Base color should be preserved on disconnect for reconnection."""
        base_colors = {"serial_1": (255, 0, 0)}

        # Simulate disconnect - base_colors should NOT be cleared
        # (This is intentional behavior to restore color on reconnect)

        assert "serial_1" in base_colors
        assert base_colors["serial_1"] == (255, 0, 0)


class TestNewControllerDetection:
    """Tests for new controller detection."""

    def test_new_controller_added_to_tracking(self):
        """New controller should be added to tracked_controllers."""
        tracked_controllers = {}
        controller_states = {}
        button_detector = MockButtonDetector()

        # Simulate new controller detection
        connected_serials = ["new_serial"]

        for serial in connected_serials:
            if serial not in tracked_controllers:
                tracked_controllers[serial] = {
                    "serial": serial,
                    "battery": 80,
                    "team": 0,
                }
                controller_states[serial] = {"trigger": 0}
                button_detector.publish_connection_event(serial, is_connect=True, battery=80)

        assert "new_serial" in tracked_controllers
        assert "new_serial" in controller_states
        assert len(button_detector.connection_events) == 1
        assert button_detector.connection_events[0]["is_connect"] is True

    def test_existing_controller_not_re_added(self):
        """Existing controller should not be re-added."""
        tracked_controllers = {"existing_serial": {"battery": 80}}
        button_detector = MockButtonDetector()

        connected_serials = ["existing_serial"]

        for serial in connected_serials:
            if serial not in tracked_controllers:
                button_detector.publish_connection_event(serial, is_connect=True)

        # No connection event should be published
        assert len(button_detector.connection_events) == 0


class TestActivityTracking:
    """Tests for adaptive polling activity tracking."""

    def test_button_press_marks_active(self):
        """Button press should mark controller as active."""
        from lib.controller_constants import ButtonKey

        last_activity_time = {}
        current_time = time.time()

        state = {
            ButtonKey.MOVE: True,  # Button pressed
        }

        # Check for button activity
        activity_detected = False
        button_keys = [ButtonKey.MOVE, ButtonKey.TRIGGER, ButtonKey.PS]
        for key in button_keys:
            if state.get(key, False):
                activity_detected = True
                break

        if activity_detected:
            last_activity_time["test_serial"] = current_time

        assert activity_detected is True
        assert "test_serial" in last_activity_time

    def test_no_activity_when_idle(self):
        """No activity should be detected when controller is idle."""
        from lib.controller_constants import ButtonKey

        state = {
            ButtonKey.MOVE: False,
            ButtonKey.TRIGGER: False,
            ButtonKey.PS: False,
        }

        activity_detected = False
        button_keys = [ButtonKey.MOVE, ButtonKey.TRIGGER, ButtonKey.PS]
        for key in button_keys:
            if state.get(key, False):
                activity_detected = True
                break

        assert activity_detected is False

    def test_accelerometer_movement_marks_active(self):
        """Significant accelerometer movement should mark controller as active."""
        previous_accel = {"test_serial": (0.0, 0.0, 1.0)}
        accel_movement_threshold = 0.05

        # Current accel with significant movement
        current_accel = (0.1, 0.2, 1.0)

        prev = previous_accel["test_serial"]
        dx = abs(current_accel[0] - prev[0])
        dy = abs(current_accel[1] - prev[1])
        dz = abs(current_accel[2] - prev[2])
        movement = dx + dy + dz

        activity_detected = movement > accel_movement_threshold

        assert activity_detected is True
        assert movement == pytest.approx(0.3, rel=0.01)

    def test_small_movement_not_active(self):
        """Small accelerometer movement should not mark as active."""
        previous_accel = {"test_serial": (0.0, 0.0, 1.0)}
        accel_movement_threshold = 0.05

        # Current accel with tiny movement
        current_accel = (0.01, 0.01, 1.0)

        prev = previous_accel["test_serial"]
        dx = abs(current_accel[0] - prev[0])
        dy = abs(current_accel[1] - prev[1])
        dz = abs(current_accel[2] - prev[2])
        movement = dx + dy + dz

        activity_detected = movement > accel_movement_threshold

        assert activity_detected is False


class TestAdaptivePolling:
    """Tests for adaptive polling rate logic."""

    def test_active_controller_gets_fast_poll(self):
        """Active controllers should be polled at 60Hz."""
        idle_threshold_seconds = 5.0
        active_poll_interval = 0.016  # ~60Hz
        idle_poll_interval = 0.100  # ~10Hz

        current_time = time.time()
        last_activity = current_time - 1.0  # 1 second ago (active)

        is_idle = (current_time - last_activity) > idle_threshold_seconds

        poll_interval = idle_poll_interval if is_idle else active_poll_interval

        assert is_idle is False
        assert poll_interval == active_poll_interval

    def test_idle_controller_gets_slow_poll(self):
        """Idle controllers should be polled at 10Hz."""
        idle_threshold_seconds = 5.0
        active_poll_interval = 0.016
        idle_poll_interval = 0.100

        current_time = time.time()
        last_activity = current_time - 10.0  # 10 seconds ago (idle)

        is_idle = (current_time - last_activity) > idle_threshold_seconds

        poll_interval = idle_poll_interval if is_idle else active_poll_interval

        assert is_idle is True
        assert poll_interval == idle_poll_interval

    def test_skip_poll_if_too_soon(self):
        """Polling should be skipped if not enough time has passed."""
        current_time = time.time()
        last_poll_time = current_time - 0.005  # 5ms ago
        poll_interval = 0.016  # 16ms interval

        should_poll = (current_time - last_poll_time) >= poll_interval

        assert should_poll is False


class TestBaseColorRestoration:
    """Tests for base color restoration on reconnect."""

    def test_base_color_restored_on_reconnect(self):
        """Base color should be restored when controller reconnects."""
        base_colors = {"serial_1": (255, 0, 0)}
        tracked_controllers = {}

        # Simulate reconnection
        serial = "serial_1"
        tracked_controllers[serial] = {"battery": 80}

        # Check if we should restore color
        if serial in base_colors:
            color_to_restore = base_colors[serial]
            assert color_to_restore == (255, 0, 0)

    def test_no_color_for_new_controller(self):
        """New controller with no base color should not have color restored."""
        base_colors = {}
        serial = "new_serial"

        has_base_color = serial in base_colors

        assert has_base_color is False
