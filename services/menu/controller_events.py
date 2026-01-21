"""Controller event handling for the Menu service."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Protocol

from proto import controller_manager_pb2, controller_manager_pb2_grpc, menu_pb2

logger = logging.getLogger(__name__)

# Button type name mapping
BUTTON_TYPE_NAMES = {
    controller_manager_pb2.BUTTON_TRIGGER: "trigger",
    controller_manager_pb2.BUTTON_MOVE: "move",
    controller_manager_pb2.BUTTON_CROSS: "cross",
    controller_manager_pb2.BUTTON_CIRCLE: "circle",
    controller_manager_pb2.BUTTON_SQUARE: "square",
    controller_manager_pb2.BUTTON_TRIANGLE: "triangle",
    controller_manager_pb2.BUTTON_PS: "ps",
    controller_manager_pb2.BUTTON_SELECT: "select",
    controller_manager_pb2.BUTTON_START: "start",
}


class ControllerEventCallbacks(Protocol):
    """Protocol for controller event callbacks."""

    async def on_connect(self, serial: str) -> None:
        """Called when a controller connects."""
        ...

    async def on_disconnect(self, serial: str) -> None:
        """Called when a controller disconnects."""
        ...

    async def on_button(self, serial: str, button: str, is_press: bool) -> None:
        """Called when a button event occurs."""
        ...

    def update_battery(self, serial: str, battery: int) -> None:
        """Update battery level for a controller."""
        ...

    def get_menu_state(self) -> int:
        """Get current menu state."""
        ...


if TYPE_CHECKING:
    import grpc.aio

    from services.menu.utils import LedController


class ControllerEventLoop:
    """
    Manages the bidirectional button event stream with controller manager.

    Handles:
    - Connection events (connect/disconnect)
    - Button events (press/release)
    - LED state via bidirectional stream
    """

    def __init__(
        self,
        controller_channel: grpc.aio.Channel,
        led: LedController,
        callbacks: ControllerEventCallbacks,
        metrics,
    ):
        """
        Initialize controller event loop.

        Args:
            controller_channel: gRPC channel to controller manager
            led: LED controller for setting colors
            callbacks: Callback handler for events
            metrics: Prometheus metrics module
        """
        self._channel = controller_channel
        self._led = led
        self._callbacks = callbacks
        self._metrics = metrics

        self._running = False
        self._task: asyncio.Task | None = None
        self._stream: grpc.aio.StreamStreamCall | None = None
        self._stream_lock = asyncio.Lock()
        self._stream_queue: asyncio.Queue | None = None

    async def start(self) -> None:
        """Start the event loop."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run())
            logger.info("Controller event loop started")

    async def stop(self) -> None:
        """Stop the event loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Controller event loop stopped")

    @property
    def is_running(self) -> bool:
        """Check if the event loop is running."""
        return self._running

    async def _run(self) -> None:
        """Main event loop with reconnection logic."""
        retry_delay = 1.0
        max_retry_delay = 30.0

        while self._running:
            try:
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self._channel)

                logger.info("Connecting to Controller Manager (bidirectional stream)...")

                # Create bidirectional stream with async generator for outbound messages
                request_queue: asyncio.Queue = asyncio.Queue()

                async def request_generator(queue=request_queue):
                    """Async generator that yields ButtonEventStreamControl messages."""
                    # Send initial config
                    initial_config = controller_manager_pb2.ButtonEventStreamControl(
                        config=controller_manager_pb2.ButtonEventStreamConfig()
                    )
                    yield initial_config

                    # Then yield messages from queue
                    while self._running:
                        try:
                            msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                            yield msg
                        except TimeoutError:
                            continue
                        except asyncio.CancelledError:
                            return

                # Start bidirectional stream
                stream = stub.StreamButtonEvents(request_generator())

                # Store stream reference and queue for sending messages
                async with self._stream_lock:
                    self._stream = stream
                    self._stream_queue = request_queue
                    # Wire LED controller to use the same stream
                    self._led.set_stream(request_queue, self._stream_lock)

                logger.info("Connected to Controller Manager")
                retry_delay = 1.0

                # Process incoming events
                async for event in stream:
                    if not self._running:
                        return

                    await self._dispatch_event(event)

                if self._running:
                    logger.warning("Button event stream ended, reconnecting...")

            except asyncio.CancelledError:
                logger.info("Controller event loop cancelled")
                raise
            except Exception as e:
                if not self._running:
                    return
                logger.error(f"Controller event loop error: {e}, reconnecting in {retry_delay:.1f}s")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
            finally:
                # Clear stream reference on disconnect
                async with self._stream_lock:
                    self._stream = None
                    self._stream_queue = None
                    self._led.set_stream(None)

    async def _dispatch_event(self, event) -> None:
        """
        Dispatch an event to the appropriate handler.

        Args:
            event: ButtonEvent from the stream
        """
        serial = event.serial

        # Update battery level from event (available on all event types)
        if event.battery > 0:
            self._callbacks.update_battery(serial, event.battery)

        if event.event_type == controller_manager_pb2.EVENT_CONNECT:
            await self._callbacks.on_connect(serial)
            self._metrics.button_frames_processed_total.inc()
        elif event.event_type == controller_manager_pb2.EVENT_DISCONNECT:
            await self._callbacks.on_disconnect(serial)
            self._metrics.button_frames_processed_total.inc()
        else:
            # Regular button event (EVENT_BUTTON is default, 0)
            # Only process when menu is running
            if self._callbacks.get_menu_state() != menu_pb2.MenuState.RUNNING:
                return

            is_press = event.action == controller_manager_pb2.ACTION_PRESS
            button_name = BUTTON_TYPE_NAMES.get(event.button, "unknown")

            logger.debug(f"Button event: {serial} {button_name}={'PRESS' if is_press else 'RELEASE'}")
            await self._callbacks.on_button(serial, button_name, is_press)
