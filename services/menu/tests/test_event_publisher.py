"""Unit tests for EventPublisher."""

import asyncio
from unittest.mock import MagicMock

import pytest

from services.menu.event_publisher import EventPublisher


@pytest.fixture
def mock_tracer():
    """Create a mock tracer."""
    tracer = MagicMock()
    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    tracer.start_as_current_span.return_value = span
    return tracer


@pytest.fixture
def mock_metrics():
    """Create mock metrics."""
    metrics = MagicMock()
    metrics.stream_events_published_total.labels.return_value.inc = MagicMock()
    return metrics


@pytest.fixture
def publisher(mock_tracer, mock_metrics):
    """Create EventPublisher instance."""
    return EventPublisher(mock_tracer, mock_metrics)


class TestEventPublisherSubscription:
    """Test subscription management."""

    @pytest.mark.asyncio
    async def test_subscribe_creates_queue(self, publisher):
        """Subscribe should create and return an asyncio.Queue."""
        queue = await publisher.subscribe("sub1")
        assert isinstance(queue, asyncio.Queue)
        assert publisher.subscriber_count == 1

    @pytest.mark.asyncio
    async def test_subscribe_multiple(self, publisher):
        """Multiple subscriptions should be tracked separately."""
        await publisher.subscribe("sub1")
        await publisher.subscribe("sub2")
        await publisher.subscribe("sub3")
        assert publisher.subscriber_count == 3

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_subscriber(self, publisher):
        """Unsubscribe should remove the subscriber."""
        await publisher.subscribe("sub1")
        await publisher.subscribe("sub2")
        assert publisher.subscriber_count == 2

        await publisher.unsubscribe("sub1")
        assert publisher.subscriber_count == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_unknown_subscriber(self, publisher):
        """Unsubscribing unknown subscriber should not raise."""
        await publisher.unsubscribe("unknown")
        assert publisher.subscriber_count == 0


class TestEventPublisherPublish:
    """Test event publishing."""

    @pytest.mark.asyncio
    async def test_publish_to_single_subscriber(self, publisher):
        """Events should be published to subscribers."""
        queue = await publisher.subscribe("sub1")

        await publisher.publish("test_event", {"key": "value"})

        assert not queue.empty()
        event = queue.get_nowait()
        assert event.event_type == "test_event"
        assert "key" in event.data
        assert event.data["key"] == "value"

    @pytest.mark.asyncio
    async def test_publish_to_multiple_subscribers(self, publisher):
        """Events should be published to all subscribers."""
        queue1 = await publisher.subscribe("sub1")
        queue2 = await publisher.subscribe("sub2")

        await publisher.publish("test_event", {"key": "value"})

        assert not queue1.empty()
        assert not queue2.empty()

    @pytest.mark.asyncio
    async def test_publish_increments_metric(self, publisher, mock_metrics):
        """Publishing should increment the metric counter."""
        await publisher.subscribe("sub1")
        await publisher.publish("test_event", {})

        mock_metrics.stream_events_published_total.labels.assert_called_with(event_type="test_event")

    @pytest.mark.asyncio
    async def test_publish_creates_span(self, publisher, mock_tracer):
        """Publishing should create a tracing span."""
        await publisher.subscribe("sub1")
        await publisher.publish("test_event", {})

        mock_tracer.start_as_current_span.assert_called_with("menu_publish:test_event")

    @pytest.mark.asyncio
    async def test_publish_includes_timestamp(self, publisher):
        """Events should include a timestamp."""
        queue = await publisher.subscribe("sub1")
        await publisher.publish("test_event", {})

        event = queue.get_nowait()
        assert event.timestamp > 0

    @pytest.mark.asyncio
    async def test_publish_handles_full_queue(self, publisher):
        """Publishing should handle full queues gracefully."""
        queue = await publisher.subscribe("sub1")

        # Fill the queue (maxsize=100)
        for _ in range(100):
            queue.put_nowait(MagicMock())

        # This should not raise, just log a warning
        await publisher.publish("test_event", {})

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self, publisher):
        """Publishing with no subscribers should not raise."""
        await publisher.publish("test_event", {"key": "value"})
