"""
ControllerManager gRPC servicer implementation.

Contains the ControllerManagerServicer class that handles all gRPC methods
for managing PS Move controllers.
"""

import asyncio
import logging
import os

# Import protobuf
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import contextlib

from lib.controller_constants import ControllerInfoKey
from lib.telemetry import get_tracer
from proto import controller_manager_pb2, controller_manager_pb2_grpc
from services.controller_manager import metrics

# Phase 57: Backend abstraction for platform independence
from services.controller_manager.backend_factory import create_backend
from services.controller_manager.button_detector import ButtonDetector
from services.controller_manager.discovery import PeriodicRescanTimer
from services.controller_manager.discovery_loop import DiscoveryLoop
from services.controller_manager.effects_base import ControllerEffectsBase
from services.controller_manager.event_publisher import EventPublisher as EventPublisherHelper
from services.controller_manager.feedback_manager import FeedbackManager
from services.controller_manager.monitoring import ControllerMonitoring
from services.controller_manager.name_manager import NameManager
from services.controller_manager.state_cache import StateCache

logger = logging.getLogger(__name__)

# Lazy telemetry initialization - defers OTLP setup until first span
tracer = get_tracer(__name__)


class ControllerManagerServicer(controller_manager_pb2_grpc.ControllerManagerServiceServicer, ControllerEffectsBase):
    """
    ControllerManager gRPC servicer.

    Manages PS Move controllers:
    - Discovery and pairing
    - Controller process spawning
    - State monitoring and streaming
    - Health checking

    Phase 40: Inherits from ControllerEffectsBase for shared effect logic.
    """

    def __init__(self):
        """Initialize controller manager."""
        ControllerEffectsBase.__init__(self)  # Initialize effects base class

        # Phase 57: Initialize backend (platform-agnostic)
        self.backend = create_backend()
        logger.info(f"Using controller backend: {self.backend.__class__.__name__}")

        self.tracked_controllers: dict[str, dict] = {}  # serial -> controller info
        self.controller_states: dict[str, dict] = {}  # serial -> state dict from backend
        self.paired_serials: list[str] = []
        self.controller_processes: dict[str, Any] = {}  # serial -> process (for cleanup)

        # Note: state_lock removed - no longer needed with async discovery loop
        # All operations run on the same event loop, so no cross-thread coordination required

        # Streaming subscribers (Phase 34: async queue and lock)
        self.stream_subscribers: dict[str, asyncio.Queue] = {}
        self.stream_lock = asyncio.Lock()

        # Button event streaming (Phase 41, Phase 34: async queue and lock)
        self.button_event_subscribers: dict[str, asyncio.Queue] = {}
        self.button_event_lock = asyncio.Lock()

        # Delta update tracking (Phase 26 - Part 3)
        # Store last sent state per subscriber per controller
        # Format: {subscriber_id: {serial: ControllerState}}
        self.last_sent_states: dict[str, dict[str, Any]] = {}

        # Event publisher for cross-thread communication (Phase refactor)
        self.event_publisher = EventPublisherHelper()

        # Battery monitoring - Phase 39, extracted to monitoring.py
        # NOTE: RSSI monitoring is handled by the host pairing-daemon
        # NOTE: Must be initialized before StateCache which depends on it
        self.monitoring = ControllerMonitoring(
            low_battery_threshold=1,
        )

        # State caching (Phase 18 - Task 1, refactored)
        self.state_cache_manager = StateCache(self.monitoring)
        self.state_cache_manager.set_controller_states(self.controller_states)

        # Button detector for button transitions (Phase 41, refactored)
        self.button_detector = ButtonDetector(self.event_publisher)
        self.button_detector.set_subscribers(self.button_event_subscribers)

        # Feedback manager for LED colors, vibration, and effects (Phase refactor)
        self.feedback_manager = FeedbackManager(
            backend=self.backend,
            tracked_controllers=self.tracked_controllers,
        )

        # Vibration tasks - tracks active asyncio vibration tasks per controller (Phase 57)
        self.vibration_tasks: dict[str, asyncio.Task] = {}

        # Phase 79: Periodic rescan timer for externally paired controllers
        self.rescan_timer = PeriodicRescanTimer(interval=5.0)

        # Issue #7: Name manager for human-readable controller names
        self.name_manager = NameManager()

        # Discovery loop (extracted to discovery_loop.py)
        # Note: start() must be called from async context (done in first stream handler)
        self.discovery_loop = DiscoveryLoop(
            backend=self.backend,
            tracked_controllers=self.tracked_controllers,
            controller_states=self.controller_states,
            button_detector=self.button_detector,
            state_cache_manager=self.state_cache_manager,
            feedback_manager=self.feedback_manager,
            monitoring=self.monitoring,
            rescan_timer=self.rescan_timer,
            paired_serials=self.paired_serials,
            base_colors=self.feedback_manager.base_colors,
            event_publisher=self.event_publisher,
            name_manager=self.name_manager,
        )
        self._discovery_started = False

        logger.info("ControllerManager initialized")

    def _ensure_discovery_started(self) -> None:
        """Start discovery loop if not already started.

        Must be called from async context (event loop must be running).
        """
        if not self._discovery_started:
            self.discovery_loop.start()
            self._discovery_started = True

    async def _set_led_color(self, serial: str, color: tuple[int, int, int]):
        """Set LED color on a controller (async).

        Implements abstract method from ControllerEffectsBase.
        Delegates to feedback_manager for actual LED control.

        Args:
            serial: Controller serial number
            color: RGB tuple (0-255, 0-255, 0-255)
        """
        await self.feedback_manager._set_led_color(serial, color)

    async def StreamButtonEvents(self, request_iterator, context):
        """
        Stream button press/release events as they occur (Phase 41).
        Phase XX: Made bidirectional for LED state ownership - menu can send base colors and effects.

        This is an event-driven stream - events are only sent when buttons
        change state (press or release), not on every frame.
        """
        # Ensure discovery loop is running (async task, needs event loop)
        self._ensure_discovery_started()

        subscriber_id = f"button_stream_{time.time()}"

        # Set main event loop reference for event publisher (used by button detector)
        if self.event_publisher.main_loop is None:
            self.event_publisher.set_main_loop(asyncio.get_running_loop())

        # Note: We manually manage the span instead of using context manager
        # because GeneratorExit during stream disconnect causes context token issues
        span = tracer.start_span("StreamButtonEvents")
        span.set_attribute("subscriber.id", subscriber_id)

        # Create queue for this subscriber (Phase 34: asyncio.Queue)
        # Increased from 100 to 500 to prevent event drops with many controllers
        event_queue = asyncio.Queue(maxsize=500)

        async with self.button_event_lock:  # Phase 34: async lock
            self.button_event_subscribers[subscriber_id] = event_queue

        # Update stream metrics (Phase 38)
        metrics.active_streams.inc()

        # Note: Don't clear base_colors here - effects may still be running and need
        # to restore to current base color. Menu will overwrite colors when it sends
        # new base_color commands for each controller.

        # Send initial connection events for all currently tracked controllers
        # This allows new subscribers to immediately know about existing controllers
        for serial, info in self.tracked_controllers.items():
            battery = info.get(ControllerInfoKey.BATTERY, 0)
            name = info.get(ControllerInfoKey.NAME, "")
            connect_event = controller_manager_pb2.ButtonEvent(
                serial=serial,
                timestamp=int(time.time() * 1000),
                battery=battery,
                event_type=controller_manager_pb2.EVENT_CONNECT,
                name=name,
            )
            try:
                event_queue.put_nowait(connect_event)
                logger.debug(f"[{subscriber_id}] Sent initial connection event for {serial} ({name})")
            except asyncio.QueueFull:
                logger.warning(f"[{subscriber_id}] Queue full, skipping initial event for {serial}")

        logger.info(f"[{subscriber_id}] Sent initial connection events for {len(self.tracked_controllers)} controllers")

        # Phase XX: Background task to read client control messages
        async def read_client_controls():
            try:
                async for control_msg in request_iterator:
                    if control_msg.HasField("config"):
                        # Initial configuration (currently empty, for future use)
                        logger.info(f"[{subscriber_id}] Button stream configured")

                    elif control_msg.HasField("base_color"):
                        # Phase XX: Set base color for a controller
                        cmd = control_msg.base_color
                        serial = cmd.serial
                        color = (cmd.color.r, cmd.color.g, cmd.color.b)

                        if serial and serial in self.tracked_controllers:
                            # Only cancel effect if it's marked as cancellable
                            async with self.feedback_manager.effect_lock:
                                if serial in self.feedback_manager.active_effects:
                                    effect_type = self.feedback_manager.active_effect_types.get(serial)
                                    if effect_type in self.feedback_manager.cancellable_effects:
                                        self.feedback_manager.active_effects[serial].cancel()
                                        with contextlib.suppress(asyncio.CancelledError):
                                            await self.feedback_manager.active_effects[serial]
                                        del self.feedback_manager.active_effects[serial]
                                        self.feedback_manager.active_effect_types.pop(serial, None)
                                        # Clear effect active flag
                                        self.backend.set_effect_active(serial, False)
                                        logger.debug(f"Cancelled cancellable effect for {serial}")

                            # Store base color (will be used when effect completes)
                            self.feedback_manager.base_colors[serial] = color

                            # Only set LED immediately if no effect is running
                            if serial not in self.feedback_manager.active_effects:
                                await self.feedback_manager.set_controller_color(serial, color)
                                logger.info(f"[ButtonStream] Applied base color for {serial}: {color}")
                            else:
                                effect_type = self.feedback_manager.active_effect_types.get(serial, "unknown")
                                logger.warning(
                                    f"[ButtonStream] Base color for {serial} blocked by active effect: {effect_type}"
                                )

                            logger.debug(f"[{subscriber_id}] Base color set: serial={serial}, rgb={color}")

                        metrics.stream_commands_total.labels(command_type="base_color").inc()

                    elif control_msg.HasField("game_effect"):
                        # Phase XX: Trigger semantic game effect
                        cmd = control_msg.game_effect
                        # Extract optional color if provided
                        effect_color = None
                        if cmd.HasField("color"):
                            effect_color = (cmd.color.r, cmd.color.g, cmd.color.b)
                        await self.feedback_manager.handle_game_effect(
                            cmd.serial,
                            cmd.effect,
                            subscriber_id,
                            color=effect_color,
                            duration_ms=cmd.duration_ms,
                            speed=cmd.speed,
                            trace_parent=cmd.trace_parent,
                            trace_state=cmd.trace_state,
                        )

                        effect_name = controller_manager_pb2.GameEffect.Name(cmd.effect)
                        logger.debug(
                            f"[{subscriber_id}] Game effect: serial={cmd.serial or 'all'}, effect={effect_name}"
                        )

                        metrics.stream_commands_total.labels(command_type="game_effect").inc()

            except Exception as e:
                logger.error(f"[{subscriber_id}] Error reading client controls: {e}", exc_info=True)

        # Start background task to read client controls
        control_task = asyncio.create_task(read_client_controls())

        logger.info(f"New button event subscriber: {subscriber_id}")

        try:
            while not context.cancelled():
                try:
                    # Wait for button events (Phase 34: async wait with timeout)
                    # Check for events every 1s to stay responsive to cancellation
                    try:
                        event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                        yield event
                        # Track stream update (Phase 38)
                        metrics.stream_updates_total.labels(stream_type="button_events").inc()
                    except TimeoutError:  # Phase 34: asyncio exception
                        # No events, continue loop to check cancellation
                        continue

                except Exception as e:
                    logger.error(f"Button event stream error for {subscriber_id}: {e}")
                    break

        finally:
            # End span manually (avoids context token issues on GeneratorExit)
            span.end()

            # Cleanup: Cancel background task
            control_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await control_task

            # Cleanup (Phase 34: async lock)
            async with self.button_event_lock:
                if subscriber_id in self.button_event_subscribers:
                    del self.button_event_subscribers[subscriber_id]

            # Update stream metrics (Phase 38)
            metrics.active_streams.dec()

            logger.info(f"Button event subscriber disconnected: {subscriber_id}")

    async def StreamGameplayData(self, request_iterator, context):
        """
        Stream gameplay data with dynamic filtering via bidirectional communication (Phase 45).

        Client can send filter updates at any time to adjust which controllers
        are being monitored without restarting the stream. Supports color commands,
        game effects, and other stream-based feedback.

        Args:
            request_iterator: AsyncIterator of GameplayStreamControl messages from client
            context: gRPC context

        Yields:
            GameplayDataUpdate messages with filtered controller data
        """
        # Ensure discovery loop is running (async task, needs event loop)
        self._ensure_discovery_started()

        subscriber_id = f"gameplay_stream_{time.time()}"

        # Note: We manually manage the span instead of using context manager
        # because GeneratorExit during stream disconnect causes context token issues
        span = tracer.start_span("StreamGameplayData")
        span.set_attribute("subscriber.id", subscriber_id)

        # Update stream metrics
        metrics.active_streams.inc()

        # Stream state (updated by client messages)
        current_hz = 30  # Default Hz
        current_filter = None  # None = all controllers

        # Background task to read client updates
        async def read_client_updates():
            nonlocal current_hz, current_filter

            try:
                async for control_msg in request_iterator:
                    if control_msg.HasField("config"):
                        # Initial configuration
                        current_hz = control_msg.config.update_frequency_hz or 30

                        # Extract filter from colors if provided
                        if control_msg.config.colors:
                            # Use serials from colors as filter
                            current_filter = set()
                            for color_config in control_msg.config.colors:
                                serial = color_config.serial
                                if serial:
                                    current_filter.add(serial)
                                    # Store base color and set LED
                                    color = (color_config.color.r, color_config.color.g, color_config.color.b)
                                    self.feedback_manager.base_colors[serial] = color
                                    if serial in self.tracked_controllers:
                                        await self.feedback_manager.set_controller_color(serial, color)
                            logger.info(f"[{subscriber_id}] Set base colors for {len(current_filter)} controllers")
                        else:
                            current_filter = None  # All controllers

                        logger.info(
                            f"[{subscriber_id}] Stream configured: {current_hz}Hz, "
                            f"filter={len(current_filter) if current_filter else 'all'} controllers"
                        )
                        span.set_attribute("update_frequency_hz", current_hz)
                        span.set_attribute("initial_filter_count", len(current_filter) if current_filter else 0)

                    elif control_msg.HasField("filter_update"):
                        # Mid-stream filter update
                        new_filter = (
                            set(control_msg.filter_update.serials) if control_msg.filter_update.serials else None
                        )

                        if new_filter != current_filter:
                            old_count = len(current_filter) if current_filter else 0
                            new_count = len(new_filter) if new_filter else 0

                            logger.info(f"[{subscriber_id}] Filter updated: {old_count} → {new_count} controllers")

                            current_filter = new_filter

                            # Add span event for filter update
                            span.add_event(
                                "filter_updated",
                                {
                                    "previous_count": old_count,
                                    "new_count": new_count,
                                },
                            )

                    elif control_msg.HasField("base_color"):
                        # Phase XX: Set base color for a controller (LED state ownership)
                        cmd = control_msg.base_color
                        serial = cmd.serial
                        color = (cmd.color.r, cmd.color.g, cmd.color.b)

                        if serial and serial in self.tracked_controllers:
                            # Only cancel effect if it's marked as cancellable
                            async with self.feedback_manager.effect_lock:
                                if serial in self.feedback_manager.active_effects:
                                    effect_type = self.feedback_manager.active_effect_types.get(serial)
                                    if effect_type in self.feedback_manager.cancellable_effects:
                                        self.feedback_manager.active_effects[serial].cancel()
                                        with contextlib.suppress(asyncio.CancelledError):
                                            await self.feedback_manager.active_effects[serial]
                                        del self.feedback_manager.active_effects[serial]
                                        self.feedback_manager.active_effect_types.pop(serial, None)
                                        # Clear effect active flag
                                        self.backend.set_effect_active(serial, False)
                                        logger.debug(f"Cancelled cancellable effect for {serial}")

                            # Store base color (will be used when effect completes)
                            self.feedback_manager.base_colors[serial] = color

                            # Only set LED immediately if no effect is running
                            if serial not in self.feedback_manager.active_effects:
                                await self.feedback_manager.set_controller_color(serial, color)
                                logger.info(f"[GameplayStream] Applied base color for {serial}: {color}")
                            else:
                                effect_type = self.feedback_manager.active_effect_types.get(serial, "unknown")
                                logger.warning(
                                    f"[GameplayStream] Base color for {serial} blocked by active effect: {effect_type}"
                                )

                            logger.debug(f"[{subscriber_id}] Base color set: serial={serial}, rgb={color}")

                        metrics.stream_commands_total.labels(command_type="base_color").inc()

                    elif control_msg.HasField("game_effect"):
                        # Phase XX: Trigger semantic game effect (LED state ownership)
                        cmd = control_msg.game_effect
                        # Extract optional color if provided
                        effect_color = None
                        if cmd.HasField("color"):
                            effect_color = (cmd.color.r, cmd.color.g, cmd.color.b)
                        await self.feedback_manager.handle_game_effect(
                            cmd.serial,
                            cmd.effect,
                            subscriber_id,
                            color=effect_color,
                            duration_ms=cmd.duration_ms,
                            speed=cmd.speed,
                            trace_parent=cmd.trace_parent,
                            trace_state=cmd.trace_state,
                        )

                        effect_name = controller_manager_pb2.GameEffect.Name(cmd.effect)
                        logger.debug(
                            f"[{subscriber_id}] Game effect: serial={cmd.serial or 'all'}, effect={effect_name}"
                        )

                        metrics.stream_commands_total.labels(command_type="game_effect").inc()

            except Exception as e:
                logger.error(f"[{subscriber_id}] Error reading client updates: {e}", exc_info=True)

        # Start background task to read client updates
        update_task = asyncio.create_task(read_client_updates())

        logger.info(f"New gameplay subscriber: {subscriber_id}")

        try:
            # Stream gameplay data with consistent frame timing
            # Uses monotonic clock to account for processing time, reducing jitter
            next_frame_time = time.monotonic()

            while not context.cancelled():
                try:
                    # Calculate interval from current Hz
                    interval = 1.0 / current_hz

                    # Build data for each controller (respecting filter)
                    gameplay_data = []
                    for serial, info in self.tracked_controllers.items():
                        # Apply filter if present
                        if current_filter is not None and serial not in current_filter:
                            continue  # Skip filtered controller

                        # Get full controller state
                        full_state = self.state_cache_manager.build_or_get_cached_state(serial, info)

                        # Convert to GameplayData (no buttons)
                        gd = controller_manager_pb2.GameplayData(
                            serial=full_state.serial,
                            move_num=full_state.move_num,
                            battery=full_state.battery,
                            team=full_state.team,
                            color=full_state.color,
                            accel=full_state.accel,
                            gyro=full_state.gyro,
                            rssi=full_state.rssi,  # Signal strength for gameplay adaptation
                            name=full_state.name,  # Human-readable name (Issue #7)
                        )
                        gameplay_data.append(gd)

                    # Send update
                    update = controller_manager_pb2.GameplayDataUpdate(
                        controllers=gameplay_data, timestamp=int(time.time() * 1000)
                    )
                    yield update

                    # Track stream update
                    if gameplay_data:
                        metrics.stream_updates_total.labels(stream_type="gameplay_data").inc()
                        # Track number of controllers streamed per frame (Phase 45)
                        metrics.streamed_controllers.observe(len(gameplay_data))

                    # Fixed frame timing: sleep until next scheduled frame time
                    # This accounts for processing time to maintain consistent frame rate
                    next_frame_time += interval
                    sleep_time = next_frame_time - time.monotonic()

                    # If we're behind schedule, reset timing (prevents spiral of catch-up)
                    if sleep_time < 0:
                        next_frame_time = time.monotonic() + interval
                        sleep_time = interval
                        metrics.stream_frame_overruns_total.inc()

                    await asyncio.sleep(sleep_time)

                except Exception as e:
                    logger.error(f"[{subscriber_id}] Gameplay stream error: {e}", exc_info=True)
                    break

        finally:
            # End span manually (avoids context token issues on GeneratorExit)
            span.end()

            # Cleanup: Cancel background task
            update_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await update_task

            # Update stream metrics
            metrics.active_streams.dec()

            logger.info(f"Gameplay subscriber disconnected: {subscriber_id}")

    async def _schedule_vibration_stop(self, serial: str, duration_ms: int):
        """Schedule vibration to stop after duration using asyncio task (Phase 57 async migration)."""
        # Cancel existing task for this controller
        if serial in self.vibration_tasks:
            self.vibration_tasks[serial].cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.vibration_tasks[serial]

        async def stop_after_delay():
            await asyncio.sleep(duration_ms / 1000.0)
            # Clean up task tracking
            if serial in self.vibration_tasks:
                del self.vibration_tasks[serial]
            # Skip if controller was removed
            if serial not in self.tracked_controllers:
                logger.debug(f"Vibration task expired for removed controller {serial}")
                return
            await self.backend.set_rumble(serial, 0)
            logger.debug(f"Vibration stopped on {serial} (duration expired)")

        self.vibration_tasks[serial] = asyncio.create_task(stop_after_delay())

    # NOTE: Internal feedback methods moved to feedback_manager.py
    # NOTE: State cache methods moved to state_cache.py
    # NOTE: Button detection methods moved to button_detector.py
    # NOTE: Event publishing methods moved to event_publisher.py

    async def RenameController(self, request, _context):
        """Rename a controller with a custom human-readable name (Issue #7)."""
        with tracer.start_as_current_span("RenameController") as span:
            span.set_attribute("serial", request.serial)
            span.set_attribute("name", request.name)

            try:
                if not request.serial:
                    return controller_manager_pb2.RenameControllerResponse(
                        success=False, error="Serial number is required"
                    )
                if not request.name:
                    return controller_manager_pb2.RenameControllerResponse(success=False, error="Name is required")

                # Update the name
                self.name_manager.set_name(request.serial, request.name)

                # Update tracked_controllers if the controller is currently connected
                if request.serial in self.tracked_controllers:
                    self.tracked_controllers[request.serial][ControllerInfoKey.NAME] = request.name

                logger.info(f"Renamed controller {request.serial} to '{request.name}'")
                return controller_manager_pb2.RenameControllerResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                logger.error(f"RenameController error: {e}", exc_info=True)
                return controller_manager_pb2.RenameControllerResponse(success=False, error=str(e))

    async def shutdown(self):
        """Shutdown the controller manager."""
        logger.info("Shutting down ControllerManager...")

        # Stop discovery loop
        self.discovery_loop.stop()

        # Stop all controller processes
        for _serial, proc in self.controller_processes.items():
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2.0)

        await self.discovery_loop.wait_stopped(timeout_seconds=5.0)
