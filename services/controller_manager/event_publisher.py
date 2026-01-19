"""
Thread-safe event publishing for ControllerManager.

Handles cross-thread event publishing from the discovery thread to
async gRPC stream subscribers using asyncio's call_soon_threadsafe().
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Thread-safe event publisher for cross-thread communication.

    The discovery thread runs in a separate thread from the gRPC async handlers.
    This class encapsulates the call_soon_threadsafe() pattern needed to safely
    publish events from the discovery thread to async subscriber queues.
    """

    def __init__(self):
        """Initialize the event publisher."""
        # Main event loop reference (for cross-thread queue operations)
        # Set lazily when first gRPC handler runs
        self._main_loop: asyncio.AbstractEventLoop | None = None

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Set the main event loop for cross-thread publishing.

        Args:
            loop: The main asyncio event loop (from gRPC server)
        """
        self._main_loop = loop

    @property
    def main_loop(self) -> asyncio.AbstractEventLoop | None:
        """Get the main event loop."""
        return self._main_loop

    def publish_to_queue_threadsafe(self, queue: asyncio.Queue, event: Any, event_type: str) -> None:
        """
        Publish an event to an asyncio.Queue from any thread.

        This method safely publishes events to async queues from the discovery
        thread by using call_soon_threadsafe() when the main event loop is known.

        Args:
            queue: The asyncio.Queue to publish to
            event: The event object to publish
            event_type: Description for logging (e.g., "button", "connection")
        """

        def _put_event():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"{event_type.capitalize()} event queue full for subscriber")

        if self._main_loop is not None:
            # Safe cross-thread publishing via event loop
            self._main_loop.call_soon_threadsafe(_put_event)
        else:
            # Fallback: direct put (may work if called from main loop context)
            # This shouldn't happen in practice since _main_loop is set when
            # the first subscriber connects
            _put_event()

    def publish_to_subscribers(self, subscribers: dict[str, asyncio.Queue], event: Any, event_type: str) -> None:
        """
        Publish an event to all subscriber queues.

        Takes a snapshot of subscriber queues to avoid race conditions during iteration.

        Args:
            subscribers: Dict mapping subscriber_id to their Queue
            event: The event object to publish
            event_type: Description for logging
        """
        subscriber_queues = list(subscribers.values())
        for queue in subscriber_queues:
            self.publish_to_queue_threadsafe(queue, event, event_type)
