"""Event publishing and streaming for the Menu service."""

import asyncio
import logging
import time

from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from proto import menu_pb2

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Manages event streaming to subscribers.

    Handles the pub/sub pattern for menu events, allowing multiple
    subscribers to receive real-time event notifications.
    """

    def __init__(self, tracer, metrics):
        """
        Initialize event publisher.

        Args:
            tracer: OpenTelemetry tracer for distributed tracing
            metrics: Prometheus metrics module
        """
        self._tracer = tracer
        self._metrics = metrics
        self._subscribers: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, subscriber_id: str) -> asyncio.Queue:
        """
        Create a new subscription.

        Args:
            subscriber_id: Unique identifier for this subscriber

        Returns:
            Queue that will receive events
        """
        event_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers[subscriber_id] = event_queue
        logger.info(f"New event subscriber: {subscriber_id}")
        return event_queue

    async def unsubscribe(self, subscriber_id: str) -> None:
        """
        Remove a subscription.

        Args:
            subscriber_id: Identifier of subscriber to remove
        """
        async with self._lock:
            if subscriber_id in self._subscribers:
                del self._subscribers[subscriber_id]
        logger.info(f"Event subscriber disconnected: {subscriber_id}")

    async def publish(self, event_type: str, data: dict[str, str]) -> None:
        """
        Publish an event to all subscribers.

        Args:
            event_type: Type of event (e.g., "game_start", "selection_change")
            data: Event payload as key-value pairs
        """
        self._metrics.stream_events_published_total.labels(event_type=event_type).inc()

        # Use descriptive span name with event type
        span_name = f"menu_publish:{event_type}"
        with self._tracer.start_as_current_span(span_name) as span:
            span.set_attribute("event.type", event_type)

            # Inject W3C Trace Context into event data for cross-service propagation
            event_data = dict(data)  # Copy to avoid mutating original
            propagator = TraceContextTextMapPropagator()
            carrier: dict[str, str] = {}
            propagator.inject(carrier)
            if "traceparent" in carrier:
                event_data["_traceparent"] = carrier["traceparent"]
            if "tracestate" in carrier:
                event_data["_tracestate"] = carrier["tracestate"]

            event = menu_pb2.MenuEvent(
                event_type=event_type,
                data=event_data,
                timestamp=int(time.time() * 1000),
            )

            async with self._lock:
                subscriber_count = len(self._subscribers)
                span.set_attribute("subscribers.count", subscriber_count)

                for sub_id, event_queue in self._subscribers.items():
                    try:
                        event_queue.put_nowait(event)
                        logger.debug(f"Published {event_type} to subscriber {sub_id}")
                    except asyncio.QueueFull:
                        logger.warning(f"Subscriber {sub_id} queue full, skipping event")
                    except Exception as e:
                        logger.error(f"Error publishing to subscriber {sub_id}: {e}")

    @property
    def subscriber_count(self) -> int:
        """Get the number of active subscribers."""
        return len(self._subscribers)
