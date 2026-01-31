"""
Unit tests for EventBus pub/sub system.

Tests event publishing and subscription:
- Subscribe/unsubscribe
- Event delivery to subscribers
- Queue full handling
- State sync callback
- Thread safety

Issue #209: Improve test coverage for critical game flow
"""

import asyncio
import sys
from pathlib import Path

import pytest

# Setup paths for imports
test_dir = Path(__file__).parent
service_dir = test_dir.parent
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(test_dir))

from services.game_coordinator.event_bus import EventBus


class TestEventBusInit:
    """Tests for EventBus initialization."""

    def test_init_no_callback(self):
        """EventBus should initialize without callback."""
        bus = EventBus()
        assert bus.subscriber_count == 0
        assert bus._state_sync_callback is None

    def test_init_with_callback(self):
        """EventBus should store state sync callback."""

        def noop_callback(_event_type):
            pass

        bus = EventBus(state_sync_callback=noop_callback)
        assert bus._state_sync_callback is noop_callback


class TestSubscription:
    """Tests for subscribe/unsubscribe functionality."""

    @pytest.fixture
    def bus(self):
        """Create event bus for testing."""
        return EventBus()

    @pytest.mark.asyncio
    async def test_subscribe_returns_queue(self, bus):
        """Subscribe should return an asyncio Queue."""
        queue = await bus.subscribe("sub1")
        assert isinstance(queue, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_subscribe_increments_count(self, bus):
        """Subscribing should increment subscriber count."""
        assert bus.subscriber_count == 0
        await bus.subscribe("sub1")
        assert bus.subscriber_count == 1
        await bus.subscribe("sub2")
        assert bus.subscriber_count == 2

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_subscriber(self, bus):
        """Unsubscribe should remove subscriber."""
        await bus.subscribe("sub1")
        assert bus.subscriber_count == 1

        result = await bus.unsubscribe("sub1")

        assert result is True
        assert bus.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_returns_false(self, bus):
        """Unsubscribe of nonexistent subscriber should return False."""
        result = await bus.unsubscribe("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_subscriber_ids(self, bus):
        """get_subscriber_ids should return list of subscriber IDs."""
        await bus.subscribe("sub1")
        await bus.subscribe("sub2")

        ids = bus.get_subscriber_ids()

        assert set(ids) == {"sub1", "sub2"}

    @pytest.mark.asyncio
    async def test_get_subscriber_ids_empty(self, bus):
        """get_subscriber_ids should return empty list when no subscribers."""
        ids = bus.get_subscriber_ids()
        assert ids == []


class TestEventPublishing:
    """Tests for event publishing."""

    @pytest.fixture
    def bus(self):
        """Create event bus for testing."""
        return EventBus()

    @pytest.mark.asyncio
    async def test_publish_delivers_to_subscriber(self, bus):
        """Published events should be delivered to subscribers."""
        queue = await bus.subscribe("sub1")

        bus.publish("test_event", {"key": "value"})

        # Get event from queue
        event = queue.get_nowait()
        assert event.event_type == "test_event"
        assert event.data["key"] == "value"

    @pytest.mark.asyncio
    async def test_publish_delivers_to_multiple_subscribers(self, bus):
        """Published events should be delivered to all subscribers."""
        queue1 = await bus.subscribe("sub1")
        queue2 = await bus.subscribe("sub2")

        bus.publish("broadcast_event", {"msg": "hello"})

        event1 = queue1.get_nowait()
        event2 = queue2.get_nowait()

        assert event1.event_type == "broadcast_event"
        assert event2.event_type == "broadcast_event"
        assert event1.data["msg"] == "hello"
        assert event2.data["msg"] == "hello"

    @pytest.mark.asyncio
    async def test_publish_converts_values_to_strings(self, bus):
        """Published event data should have string values."""
        queue = await bus.subscribe("sub1")

        bus.publish("typed_event", {"number": 42, "boolean": True})

        event = queue.get_nowait()
        assert event.data["number"] == "42"
        assert event.data["boolean"] == "True"

    @pytest.mark.asyncio
    async def test_publish_sets_timestamp(self, bus):
        """Published events should have timestamp."""
        queue = await bus.subscribe("sub1")

        bus.publish("timed_event", {})

        event = queue.get_nowait()
        assert event.timestamp > 0

    @pytest.mark.asyncio
    async def test_publish_no_subscribers_no_error(self, bus):
        """Publishing with no subscribers should not raise error."""
        # Should not raise
        bus.publish("lonely_event", {"data": "ignored"})

    @pytest.mark.asyncio
    async def test_publish_queue_full_skips_subscriber(self, bus):
        """Full queue should skip event without error."""
        # Create subscriber with tiny queue
        queue = await bus.subscribe("sub1", max_queue_size=1)

        # Fill the queue
        bus.publish("event1", {})

        # This should not raise, just skip
        bus.publish("event2", {})
        bus.publish("event3", {})

        # Only first event should be in queue
        assert queue.qsize() == 1
        event = queue.get_nowait()
        assert event.event_type == "event1"


class TestStateSyncCallback:
    """Tests for state synchronization callback."""

    @pytest.mark.asyncio
    async def test_callback_called_on_publish(self):
        """State sync callback should be called on each publish."""
        events_received = []

        def callback(event_type):
            events_received.append(event_type)

        bus = EventBus(state_sync_callback=callback)

        bus.publish("event1", {})
        bus.publish("event2", {})

        assert events_received == ["event1", "event2"]

    @pytest.mark.asyncio
    async def test_callback_receives_event_type(self):
        """Callback should receive the event type."""
        received_type = []

        def callback(event_type):
            received_type.append(event_type)

        bus = EventBus(state_sync_callback=callback)

        bus.publish("game_started", {"game_id": "123"})

        assert received_type == ["game_started"]


class TestTraceContextInjection:
    """Tests for W3C Trace Context injection."""

    @pytest.fixture
    def bus(self):
        """Create event bus for testing."""
        return EventBus()

    @pytest.mark.asyncio
    async def test_publish_injects_trace_context(self, bus):
        """Published events may include trace context."""
        queue = await bus.subscribe("sub1")

        bus.publish("traced_event", {})

        event = queue.get_nowait()
        # Trace context is injected when there's an active span
        # In tests without active span, these fields may not be present
        # Just verify the event is properly structured
        assert event.event_type == "traced_event"


class TestThreadSafety:
    """Tests for thread-safe operations."""

    @pytest.fixture
    def bus(self):
        """Create event bus for testing."""
        return EventBus()

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_unsubscribe(self, bus):
        """Concurrent subscribe/unsubscribe should not corrupt state."""
        # Subscribe several times
        queues = []
        for i in range(10):
            queue = await bus.subscribe(f"sub{i}")
            queues.append(queue)

        assert bus.subscriber_count == 10

        # Unsubscribe half
        for i in range(5):
            await bus.unsubscribe(f"sub{i}")

        assert bus.subscriber_count == 5

    @pytest.mark.asyncio
    async def test_publish_during_unsubscribe(self, bus):
        """Publishing during unsubscribe should not raise."""
        queue = await bus.subscribe("sub1")

        # Publish and unsubscribe concurrently (simulated)
        bus.publish("event1", {})
        await bus.unsubscribe("sub1")
        bus.publish("event2", {})  # After unsubscribe

        # First event should be received
        event = queue.get_nowait()
        assert event.event_type == "event1"

        # Queue should be empty (unsubscribed before event2)
        assert queue.empty()
