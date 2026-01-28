"""
Event publishing for ControllerManager.

Handles event publishing from the discovery loop to async gRPC stream subscribers.

Note: Since the discovery loop now runs as an async task on the same event loop
as gRPC handlers (not in a separate thread), we use direct queue.put_nowait()
instead of call_soon_threadsafe().
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Event publisher for async event distribution.

    Publishes events from the discovery loop to subscriber queues.
    Since all code runs on the same event loop, no thread-safety measures needed.
    """

    def __init__(self):
        """Initialize the event publisher."""
        # Main event loop reference (kept for API compatibility, but not strictly needed)
        self._main_loop: asyncio.AbstractEventLoop | None = None

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Set the main event loop reference.

        Args:
            loop: The main asyncio event loop (from gRPC server)
        """
        self._main_loop = loop

    @property
    def main_loop(self) -> asyncio.AbstractEventLoop | None:
        """Get the main event loop."""
        return self._main_loop

    def publish_to_queue(self, queue: asyncio.Queue, event: Any, event_type: str) -> None:
        """
        Publish an event to an asyncio.Queue.

        Since the discovery loop runs on the same event loop as gRPC handlers,
        we can safely use queue.put_nowait() directly.

        Args:
            queue: The asyncio.Queue to publish to
            event: The event object to publish
            event_type: Description for logging (e.g., "button", "connection")
        """
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"{event_type.capitalize()} event queue full for subscriber")

    # Keep old name as alias for compatibility
    publish_to_queue_threadsafe = publish_to_queue

    def publish_to_subscribers(self, subscribers: dict[str, asyncio.Queue], event: Any, event_type: str) -> None:
        """
        Publish an event to all subscriber queues.

        Takes a snapshot of subscriber queues to avoid modification during iteration.

        Args:
            subscribers: Dict mapping subscriber_id to their Queue
            event: The event object to publish
            event_type: Description for logging
        """
        subscriber_queues = list(subscribers.values())
        for queue in subscriber_queues:
            self.publish_to_queue(queue, event, event_type)
