"""
Unit tests for ButtonDetector.

Tests button state transition detection and event publishing.
"""

import asyncio
from unittest.mock import MagicMock, patch

from lib.controller_constants import ButtonKey, ButtonTrackingKey
from proto import controller_manager_pb2
from services.controller_manager.button_detector import ButtonDetector
from services.controller_manager.event_publisher import EventPublisher


class TestButtonDetectorInitialization:
    """Tests for ButtonDetector initialization."""

    def test_init_creates_empty_state(self):
        """Button detector starts with no tracked button states."""
        publisher = EventPublisher()
        detector = ButtonDetector(publisher)

        assert detector.button_states == {}
        assert detector._subscribers == {}

    def test_set_subscribers(self):
        """Can set subscriber dict reference."""
        publisher = EventPublisher()
        detector = ButtonDetector(publisher)
        subscribers = {"sub1": asyncio.Queue()}

        detector.set_subscribers(subscribers)

        assert detector._subscribers is subscribers


class TestButtonStateTracking:
    """Tests for button state tracking per controller."""

    def test_first_poll_initializes_state(self):
        """First poll for a controller initializes button tracking."""
        publisher = EventPublisher()
        detector = ButtonDetector(publisher)

        state = {ButtonKey.MOVE: False, ButtonKey.TRIGGER: False}
        detector.detect_transitions_from_state("SERIAL1", state, {})

        assert "SERIAL1" in detector.button_states
        assert detector.button_states["SERIAL1"][ButtonTrackingKey.MOVE] is False
        assert detector.button_states["SERIAL1"][ButtonTrackingKey.TRIGGER] is False

    def test_all_buttons_tracked(self):
        """All 9 buttons are tracked for each controller."""
        publisher = EventPublisher()
        detector = ButtonDetector(publisher)

        # State must have at least one key to not be skipped (empty dict is falsy)
        state = {ButtonKey.MOVE: False}
        detector.detect_transitions_from_state("SERIAL1", state, {})

        expected_buttons = [
            ButtonTrackingKey.TRIGGER,
            ButtonTrackingKey.MOVE,
            ButtonTrackingKey.CROSS,
            ButtonTrackingKey.CIRCLE,
            ButtonTrackingKey.SQUARE,
            ButtonTrackingKey.TRIANGLE,
            ButtonTrackingKey.PS,
            ButtonTrackingKey.SELECT,
            ButtonTrackingKey.START,
        ]
        for button in expected_buttons:
            assert button in detector.button_states["SERIAL1"]

    def test_clear_controller_removes_state(self):
        """clear_controller removes button state for a controller."""
        publisher = EventPublisher()
        detector = ButtonDetector(publisher)

        # Initialize state
        state = {ButtonKey.MOVE: True}
        detector.detect_transitions_from_state("SERIAL1", state, {})
        assert "SERIAL1" in detector.button_states

        # Clear
        detector.clear_controller("SERIAL1")
        assert "SERIAL1" not in detector.button_states

    def test_clear_nonexistent_controller_safe(self):
        """clear_controller is safe to call for non-tracked controllers."""
        publisher = EventPublisher()
        detector = ButtonDetector(publisher)

        # Should not raise
        detector.clear_controller("NONEXISTENT")

    def test_empty_state_skipped(self):
        """Empty/None state dict is ignored (falsy values skip processing)."""
        publisher = EventPublisher()
        detector = ButtonDetector(publisher)

        detector.detect_transitions_from_state("SERIAL1", None, {})
        detector.detect_transitions_from_state("SERIAL1", {}, {})

        # Both None and empty dict are falsy, so both skip processing
        assert "SERIAL1" not in detector.button_states


class TestButtonTransitionDetection:
    """Tests for detecting button press/release transitions."""

    @patch("services.controller_manager.button_detector.metrics")
    def test_press_transition_detected(self, _mock_metrics):
        """Button press (False -> True) generates press event."""
        publisher = MagicMock(spec=EventPublisher)
        detector = ButtonDetector(publisher)
        detector._subscribers = {"sub1": MagicMock()}

        # First poll - initialize with move=False
        state1 = {ButtonKey.MOVE: False}
        detector.detect_transitions_from_state("SERIAL1", state1, {})

        # Second poll - move pressed
        state2 = {ButtonKey.MOVE: True}
        detector.detect_transitions_from_state("SERIAL1", state2, {})

        # Verify event was published
        assert publisher.publish_to_subscribers.called
        call_args = publisher.publish_to_subscribers.call_args
        event = call_args[0][1]  # Second positional arg is the event

        assert event.serial == "SERIAL1"
        assert event.button == controller_manager_pb2.BUTTON_MOVE
        assert event.action == controller_manager_pb2.ACTION_PRESS

    @patch("services.controller_manager.button_detector.metrics")
    def test_release_transition_detected(self, _mock_metrics):
        """Button release (True -> False) generates release event."""
        publisher = MagicMock(spec=EventPublisher)
        detector = ButtonDetector(publisher)
        detector._subscribers = {"sub1": MagicMock()}

        # First poll - initialize with trigger=True
        state1 = {ButtonKey.TRIGGER: True}
        detector.detect_transitions_from_state("SERIAL1", state1, {})
        publisher.reset_mock()

        # Second poll - trigger released
        state2 = {ButtonKey.TRIGGER: False}
        detector.detect_transitions_from_state("SERIAL1", state2, {})

        # Verify release event
        call_args = publisher.publish_to_subscribers.call_args
        event = call_args[0][1]

        assert event.action == controller_manager_pb2.ACTION_RELEASE
        assert event.button == controller_manager_pb2.BUTTON_TRIGGER

    @patch("services.controller_manager.button_detector.metrics")
    def test_no_event_when_state_unchanged(self, _mock_metrics):
        """No event published when button state doesn't change."""
        publisher = MagicMock(spec=EventPublisher)
        detector = ButtonDetector(publisher)
        detector._subscribers = {"sub1": MagicMock()}

        # First poll
        state = {ButtonKey.MOVE: True}
        detector.detect_transitions_from_state("SERIAL1", state, {})
        publisher.reset_mock()

        # Second poll - same state
        detector.detect_transitions_from_state("SERIAL1", state, {})

        # No event should be published
        assert not publisher.publish_to_subscribers.called

    @patch("services.controller_manager.button_detector.metrics")
    def test_multiple_transitions_in_single_poll(self, _mock_metrics):
        """Multiple button changes generate multiple events."""
        publisher = MagicMock(spec=EventPublisher)
        detector = ButtonDetector(publisher)
        detector._subscribers = {"sub1": MagicMock()}

        # Initialize all buttons as unpressed
        state1 = {}
        detector.detect_transitions_from_state("SERIAL1", state1, {})
        publisher.reset_mock()

        # Press move and trigger simultaneously
        state2 = {ButtonKey.MOVE: True, ButtonKey.TRIGGER: True}
        detector.detect_transitions_from_state("SERIAL1", state2, {})

        # Should have 2 calls (one per button)
        assert publisher.publish_to_subscribers.call_count == 2

    @patch("services.controller_manager.button_detector.metrics")
    def test_all_button_types_map_correctly(self, _mock_metrics):
        """Each button type maps to correct protobuf enum."""
        publisher = MagicMock(spec=EventPublisher)
        detector = ButtonDetector(publisher)
        detector._subscribers = {"sub1": MagicMock()}

        button_mapping = {
            ButtonKey.TRIGGER: controller_manager_pb2.BUTTON_TRIGGER,
            ButtonKey.MOVE: controller_manager_pb2.BUTTON_MOVE,
            ButtonKey.CROSS: controller_manager_pb2.BUTTON_CROSS,
            ButtonKey.CIRCLE: controller_manager_pb2.BUTTON_CIRCLE,
            ButtonKey.SQUARE: controller_manager_pb2.BUTTON_SQUARE,
            ButtonKey.TRIANGLE: controller_manager_pb2.BUTTON_TRIANGLE,
            ButtonKey.PS: controller_manager_pb2.BUTTON_PS,
            ButtonKey.SELECT: controller_manager_pb2.BUTTON_SELECT,
            ButtonKey.START: controller_manager_pb2.BUTTON_START,
        }

        for button_key, expected_type in button_mapping.items():
            # Reset detector state
            detector._button_states = {}
            publisher.reset_mock()

            # Initialize, then press button
            detector.detect_transitions_from_state("SERIAL1", {}, {})
            publisher.reset_mock()

            state = {button_key: True}
            detector.detect_transitions_from_state("SERIAL1", state, {})

            call_args = publisher.publish_to_subscribers.call_args
            event = call_args[0][1]
            assert event.button == expected_type, f"Button {button_key} should map to {expected_type}"

    @patch("services.controller_manager.button_detector.metrics")
    def test_battery_included_in_event(self, _mock_metrics):
        """Button events include battery level from controller info."""
        publisher = MagicMock(spec=EventPublisher)
        detector = ButtonDetector(publisher)
        detector._subscribers = {"sub1": MagicMock()}

        tracked_controllers = {"SERIAL1": {"battery": 4}}

        # Initialize and press
        detector.detect_transitions_from_state("SERIAL1", {}, tracked_controllers)
        publisher.reset_mock()

        state = {ButtonKey.MOVE: True}
        detector.detect_transitions_from_state("SERIAL1", state, tracked_controllers)

        call_args = publisher.publish_to_subscribers.call_args
        event = call_args[0][1]
        assert event.battery == 4

    @patch("services.controller_manager.button_detector.metrics")
    def test_state_persists_after_transition(self, _mock_metrics):
        """Button state is updated after transition detection."""
        publisher = MagicMock(spec=EventPublisher)
        detector = ButtonDetector(publisher)

        # Initialize with move=False
        detector.detect_transitions_from_state("SERIAL1", {ButtonKey.MOVE: False}, {})
        assert detector.button_states["SERIAL1"][ButtonTrackingKey.MOVE] is False

        # Press move
        detector.detect_transitions_from_state("SERIAL1", {ButtonKey.MOVE: True}, {})
        assert detector.button_states["SERIAL1"][ButtonTrackingKey.MOVE] is True

        # Release move
        detector.detect_transitions_from_state("SERIAL1", {ButtonKey.MOVE: False}, {})
        assert detector.button_states["SERIAL1"][ButtonTrackingKey.MOVE] is False


class TestConnectionEvents:
    """Tests for connection/disconnection event publishing."""

    def test_connect_event_published(self):
        """publish_connection_event sends connect event with correct fields."""
        publisher = MagicMock(spec=EventPublisher)
        detector = ButtonDetector(publisher)
        detector._subscribers = {"sub1": MagicMock()}

        detector.publish_connection_event("SERIAL1", is_connect=True, battery=5)

        call_args = publisher.publish_to_subscribers.call_args
        event = call_args[0][1]

        assert event.serial == "SERIAL1"
        assert event.event_type == controller_manager_pb2.EVENT_CONNECT
        assert event.battery == 5
        assert event.timestamp > 0

    def test_disconnect_event_published(self):
        """publish_connection_event sends disconnect event."""
        publisher = MagicMock(spec=EventPublisher)
        detector = ButtonDetector(publisher)
        detector._subscribers = {"sub1": MagicMock()}

        detector.publish_connection_event("SERIAL1", is_connect=False)

        call_args = publisher.publish_to_subscribers.call_args
        event = call_args[0][1]

        assert event.event_type == controller_manager_pb2.EVENT_DISCONNECT
        assert event.battery == 0  # Default for disconnect

    def test_connection_event_uses_correct_event_type_label(self):
        """Connection events are published with 'connection' event type label."""
        publisher = MagicMock(spec=EventPublisher)
        detector = ButtonDetector(publisher)
        detector._subscribers = {"sub1": MagicMock()}

        detector.publish_connection_event("SERIAL1", is_connect=True)

        call_args = publisher.publish_to_subscribers.call_args
        event_type = call_args[0][2]  # Third positional arg
        assert event_type == "connection"


class TestMultipleControllers:
    """Tests for handling multiple controllers."""

    @patch("services.controller_manager.button_detector.metrics")
    def test_independent_state_tracking(self, _mock_metrics):
        """Each controller has independent button state."""
        publisher = MagicMock(spec=EventPublisher)
        detector = ButtonDetector(publisher)
        detector._subscribers = {"sub1": MagicMock()}

        # Initialize both controllers
        detector.detect_transitions_from_state("SERIAL1", {ButtonKey.MOVE: False}, {})
        detector.detect_transitions_from_state("SERIAL2", {ButtonKey.MOVE: False}, {})

        # Press move on SERIAL1 only
        publisher.reset_mock()
        detector.detect_transitions_from_state("SERIAL1", {ButtonKey.MOVE: True}, {})
        detector.detect_transitions_from_state("SERIAL2", {ButtonKey.MOVE: False}, {})

        # Only one event (from SERIAL1)
        assert publisher.publish_to_subscribers.call_count == 1
        call_args = publisher.publish_to_subscribers.call_args
        event = call_args[0][1]
        assert event.serial == "SERIAL1"

    def test_clear_one_controller_preserves_others(self):
        """Clearing one controller doesn't affect others."""
        publisher = EventPublisher()
        detector = ButtonDetector(publisher)

        # Initialize both (need non-empty state to not be skipped)
        detector.detect_transitions_from_state("SERIAL1", {ButtonKey.MOVE: False}, {})
        detector.detect_transitions_from_state("SERIAL2", {ButtonKey.MOVE: False}, {})

        # Clear one
        detector.clear_controller("SERIAL1")

        assert "SERIAL1" not in detector.button_states
        assert "SERIAL2" in detector.button_states
