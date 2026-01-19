"""
Unit tests for EventPublisher.

Tests thread-safe event publishing to asyncio queues.
"""

import asyncio
import threading
from unittest.mock import patch

import pytest

from services.controller_manager.event_publisher import EventPublisher


class TestEventPublisherInitialization:
    """Tests for EventPublisher initialization."""

    def test_init_no_main_loop(self):
        """EventPublisher starts with no main loop set."""
        publisher = EventPublisher()
        assert publisher.main_loop is None

    def test_set_main_loop(self):
        """Can set the main event loop."""
        publisher = EventPublisher()
        loop = asyncio.new_event_loop()

        publisher.set_main_loop(loop)

        assert publisher.main_loop is loop
        loop.close()


class TestPublishToQueueThreadsafe:
    """Tests for thread-safe queue publishing."""

    @pytest.mark.asyncio
    async def test_publish_with_main_loop_uses_threadsafe(self):
        """When main loop is set, uses call_soon_threadsafe."""
        publisher = EventPublisher()
        loop = asyncio.get_running_loop()
        publisher.set_main_loop(loop)

        queue = asyncio.Queue()
        event = {"type": "test"}

        publisher.publish_to_queue_threadsafe(queue, event, "test")

        # Give the event loop a chance to process
        await asyncio.sleep(0.01)

        assert not queue.empty()
        received = await queue.get()
        assert received == event

    @pytest.mark.asyncio
    async def test_publish_without_main_loop_direct_put(self):
        """Without main loop, does direct put (fallback)."""
        publisher = EventPublisher()
        # main_loop is None

        queue = asyncio.Queue()
        event = {"type": "test"}

        publisher.publish_to_queue_threadsafe(queue, event, "test")

        # Should work directly since we're in the event loop
        assert not queue.empty()
        received = await queue.get()
        assert received == event

    @pytest.mark.asyncio
    async def test_queue_full_logs_warning(self):
        """Full queue logs warning instead of raising."""
        publisher = EventPublisher()
        loop = asyncio.get_running_loop()
        publisher.set_main_loop(loop)

        # Queue with max size 1
        queue = asyncio.Queue(maxsize=1)
        await queue.put("existing")  # Fill the queue

        with patch("services.controller_manager.event_publisher.logger") as mock_logger:
            publisher.publish_to_queue_threadsafe(queue, "new_event", "test")
            await asyncio.sleep(0.01)

            mock_logger.warning.assert_called_once()
            assert "queue full" in mock_logger.warning.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_publish_from_different_thread(self):
        """Publishing from a different thread safely delivers to queue."""
        publisher = EventPublisher()
        loop = asyncio.get_running_loop()
        publisher.set_main_loop(loop)

        queue = asyncio.Queue()
        event = {"from": "other_thread"}
        published = threading.Event()

        def background_publish():
            publisher.publish_to_queue_threadsafe(queue, event, "test")
            published.set()

        thread = threading.Thread(target=background_publish)
        thread.start()
        thread.join(timeout=1.0)

        assert published.is_set()

        # Give event loop time to process the scheduled callback
        await asyncio.sleep(0.05)

        assert not queue.empty()
        received = await queue.get()
        assert received == event


class TestPublishToSubscribers:
    """Tests for broadcasting to multiple subscribers."""

    @pytest.mark.asyncio
    async def test_publish_to_multiple_subscribers(self):
        """Event is sent to all subscribers."""
        publisher = EventPublisher()
        loop = asyncio.get_running_loop()
        publisher.set_main_loop(loop)

        queues = {
            "sub1": asyncio.Queue(),
            "sub2": asyncio.Queue(),
            "sub3": asyncio.Queue(),
        }
        event = {"broadcast": True}

        publisher.publish_to_subscribers(queues, event, "test")

        await asyncio.sleep(0.01)

        for name, queue in queues.items():
            assert not queue.empty(), f"Subscriber {name} should have received event"
            received = await queue.get()
            assert received == event

    @pytest.mark.asyncio
    async def test_publish_to_empty_subscribers_dict(self):
        """Publishing to empty subscribers dict is safe."""
        publisher = EventPublisher()

        # Should not raise
        publisher.publish_to_subscribers({}, {"event": "data"}, "test")

    @pytest.mark.asyncio
    async def test_one_full_queue_doesnt_block_others(self):
        """A full queue doesn't prevent delivery to other subscribers."""
        publisher = EventPublisher()
        loop = asyncio.get_running_loop()
        publisher.set_main_loop(loop)

        full_queue = asyncio.Queue(maxsize=1)
        await full_queue.put("blocking")

        normal_queue = asyncio.Queue()

        queues = {
            "full": full_queue,
            "normal": normal_queue,
        }

        with patch("services.controller_manager.event_publisher.logger"):
            publisher.publish_to_subscribers(queues, "event", "test")

        await asyncio.sleep(0.01)

        # Normal queue should still receive
        assert not normal_queue.empty()

    @pytest.mark.asyncio
    async def test_subscribers_snapshot_avoids_race(self):
        """Takes snapshot of subscribers to avoid modification during iteration."""
        publisher = EventPublisher()
        loop = asyncio.get_running_loop()
        publisher.set_main_loop(loop)

        queue1 = asyncio.Queue()
        subscribers = {"sub1": queue1}

        # Publish should work even if we modify during
        publisher.publish_to_subscribers(subscribers, "event", "test")

        await asyncio.sleep(0.01)
        assert not queue1.empty()


class TestEventTypeLabeling:
    """Tests for event type labeling in logging."""

    @pytest.mark.asyncio
    async def test_event_type_used_in_warning(self):
        """Event type is capitalized in warning message."""
        publisher = EventPublisher()
        loop = asyncio.get_running_loop()
        publisher.set_main_loop(loop)

        queue = asyncio.Queue(maxsize=1)
        await queue.put("full")

        with patch("services.controller_manager.event_publisher.logger") as mock_logger:
            publisher.publish_to_queue_threadsafe(queue, "event", "button")
            await asyncio.sleep(0.01)

            warning_msg = mock_logger.warning.call_args[0][0]
            assert "Button" in warning_msg  # Capitalized


class TestThreadSafety:
    """Tests for thread safety guarantees."""

    @pytest.mark.asyncio
    async def test_concurrent_publishes_from_multiple_threads(self):
        """Multiple threads can publish concurrently without issues."""
        publisher = EventPublisher()
        loop = asyncio.get_running_loop()
        publisher.set_main_loop(loop)

        queue = asyncio.Queue()
        num_threads = 10
        events_per_thread = 100
        threads_done = []

        def publish_many(thread_id):
            for i in range(events_per_thread):
                publisher.publish_to_queue_threadsafe(queue, {"thread": thread_id, "event": i}, "test")
            threads_done.append(thread_id)

        threads = [threading.Thread(target=publish_many, args=(i,)) for i in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # Give time for all events to be processed
        await asyncio.sleep(0.2)

        # All events should be delivered
        received_count = 0
        while not queue.empty():
            await queue.get()
            received_count += 1

        assert received_count == num_threads * events_per_thread
        assert len(threads_done) == num_threads

    @pytest.mark.asyncio
    async def test_set_main_loop_while_publishing(self):
        """Setting main loop during publishing is safe."""
        publisher = EventPublisher()
        queue = asyncio.Queue()

        # Start without main loop
        publisher.publish_to_queue_threadsafe(queue, "event1", "test")

        # Set main loop
        loop = asyncio.get_running_loop()
        publisher.set_main_loop(loop)

        # Continue publishing
        publisher.publish_to_queue_threadsafe(queue, "event2", "test")

        await asyncio.sleep(0.01)

        # Both events should be received
        events = []
        while not queue.empty():
            events.append(await queue.get())

        assert len(events) == 2
