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
import threading
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import contextlib

from lib.controller_constants import ControllerInfoKey
from lib.telemetry import init_telemetry
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
from services.controller_manager.state_cache import StateCache

logger = logging.getLogger(__name__)


# Initialize OpenTelemetry
tracer = init_telemetry()


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

        # Thread safety: RLock for shared state accessed by discovery thread and gRPC handlers
        # Protects: tracked_controllers, controller_states, button_states
        self.state_lock = threading.RLock()

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

        # Monitoring (battery and RSSI) - Phase 39, Phase 48, extracted to monitoring.py
        # NOTE: Must be initialized before StateCache which depends on it
        self.monitoring = ControllerMonitoring(
            low_battery_threshold=1,
            rssi_check_interval=10.0,
            weak_signal_threshold=-80,
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
            state_lock=self.state_lock,
        )

        # Vibration tasks - tracks active asyncio vibration tasks per controller (Phase 57)
        self.vibration_tasks: dict[str, asyncio.Task] = {}

        # Phase 79: Periodic rescan timer for externally paired controllers
        self.rescan_timer = PeriodicRescanTimer(interval=5.0)

        # Discovery loop (extracted to discovery_loop.py)
        self.discovery_loop = DiscoveryLoop(
            backend=self.backend,
            tracked_controllers=self.tracked_controllers,
            controller_states=self.controller_states,
            state_lock=self.state_lock,
            button_detector=self.button_detector,
            state_cache_manager=self.state_cache_manager,
            feedback_manager=self.feedback_manager,
            monitoring=self.monitoring,
            rescan_timer=self.rescan_timer,
            paired_serials=self.paired_serials,
            base_colors=self.feedback_manager.base_colors,
            event_publisher=self.event_publisher,
        )
        self.discovery_loop.start()

        logger.info("ControllerManager initialized")

    async def _set_led_color(self, serial: str, color: tuple[int, int, int]):
        """Set LED color on a controller (async).

        Implements abstract method from ControllerEffectsBase.
        Delegates to feedback_manager for actual LED control.

        Args:
            serial: Controller serial number
            color: RGB tuple (0-255, 0-255, 0-255)
        """
        await self.feedback_manager._set_led_color(serial, color)

    async def StreamButtonEvents(self, request_iterator, context):  # noqa: N802, ARG002
        """
        Stream button press/release events as they occur (Phase 41).
        Phase XX: Made bidirectional for LED state ownership - menu can send base colors and effects.

        This is an event-driven stream - events are only sent when buttons
        change state (press or release), not on every frame.
        """
        subscriber_id = f"button_stream_{time.time()}"

        # Capture main event loop for cross-thread queue operations
        # The discovery thread needs this to safely publish events to async queues
        if self.event_publisher.main_loop is None:
            self.event_publisher.set_main_loop(asyncio.get_running_loop())

        # Note: We manually manage the span instead of using context manager
        # because GeneratorExit during stream disconnect causes context token issues
        span = tracer.start_span("StreamButtonEvents")
        span.set_attribute("subscriber.id", subscriber_id)

        # Create queue for this subscriber (Phase 34: asyncio.Queue)
        event_queue = asyncio.Queue(maxsize=100)

        async with self.button_event_lock:  # Phase 34: async lock
            self.button_event_subscribers[subscriber_id] = event_queue

        # Update stream metrics (Phase 38)
        metrics.active_streams.inc()

        # Send initial connection events for all currently tracked controllers
        # This allows new subscribers to immediately know about existing controllers
        for serial, info in self.tracked_controllers.items():
            battery = info.get(ControllerInfoKey.BATTERY, 0)
            connect_event = controller_manager_pb2.ButtonEvent(
                serial=serial,
                timestamp=int(time.time() * 1000),
                battery=battery,
                event_type=controller_manager_pb2.EVENT_CONNECT,
            )
            try:
                event_queue.put_nowait(connect_event)
                logger.debug(f"[{subscriber_id}] Sent initial connection event for {serial}")
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

                            logger.debug(f"[{subscriber_id}] Base color set: serial={serial}, rgb={color}")

                        metrics.stream_commands_total.labels(command_type="base_color").inc()

                    elif control_msg.HasField("game_effect"):
                        # Phase XX: Trigger semantic game effect
                        cmd = control_msg.game_effect
                        await self.feedback_manager.handle_game_effect(cmd.serial, cmd.effect, subscriber_id)

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

    async def StreamGameplayData(self, request, context):  # noqa: N802, ARG002
        """
        Stream gameplay data (acceleration/gyro only) in real-time (Phase 41).

        This stream excludes button states and is optimized for game modes
        that only need motion data.
        """
        subscriber_id = f"gameplay_stream_{time.time()}"

        # Note: We manually manage the span instead of using context manager
        # because GeneratorExit during stream disconnect causes context token issues
        span = tracer.start_span("StreamGameplayData")
        span.set_attribute("subscriber.id", subscriber_id)
        span.set_attribute("update_frequency_hz", request.update_frequency_hz or 60)

        # Update stream metrics (Phase 38)
        metrics.active_streams.inc()

        logger.info(f"New gameplay data subscriber: {subscriber_id}")

        try:
            frequency = request.update_frequency_hz or 60
            interval = 1.0 / frequency

            while not context.cancelled():
                try:
                    # Build gameplay data for all controllers
                    gameplay_data = []
                    for serial, info in self.tracked_controllers.items():
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
                        )
                        gameplay_data.append(gd)

                    # Send update
                    update = controller_manager_pb2.GameplayDataUpdate(
                        controllers=gameplay_data, timestamp=int(time.time() * 1000)
                    )
                    yield update

                    # Track stream update (Phase 38)
                    if gameplay_data:
                        metrics.stream_updates_total.labels(stream_type="gameplay_data").inc()

                    await asyncio.sleep(interval)

                except Exception as e:
                    logger.error(f"Gameplay stream error for {subscriber_id}: {e}")
                    break

        finally:
            # End span manually (avoids context token issues on GeneratorExit)
            span.end()

            # Update stream metrics (Phase 38)
            metrics.active_streams.dec()

            logger.info(f"Gameplay data subscriber disconnected: {subscriber_id}")

    async def StreamGameplayDataDynamic(self, request_iterator, context):  # noqa: N802, ARG002
        """
        Stream gameplay data with dynamic filtering via bidirectional communication (Phase 45).

        Client can send filter updates at any time to adjust which controllers
        are being monitored without restarting the stream.

        Args:
            request_iterator: AsyncIterator of GameplayStreamControl messages from client
            context: gRPC context

        Yields:
            GameplayDataUpdate messages with filtered controller data
        """
        subscriber_id = f"gameplay_dynamic_stream_{time.time()}"

        # Note: We manually manage the span instead of using context manager
        # because GeneratorExit during stream disconnect causes context token issues
        span = tracer.start_span("StreamGameplayDataDynamic")
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

                    elif control_msg.HasField("color_command"):
                        # Phase 46: Process color command via stream
                        cmd = control_msg.color_command
                        target_serial = cmd.serial if cmd.serial else None

                        # Apply to target serial or all controllers (broadcast)
                        serials_to_update = [target_serial] if target_serial else list(self.tracked_controllers.keys())

                        for serial in serials_to_update:
                            if serial in self.tracked_controllers:
                                await self.feedback_manager.set_controller_color(
                                    serial, (cmd.color.r, cmd.color.g, cmd.color.b)
                                )

                        logger.debug(
                            f"[{subscriber_id}] Color command: "
                            f"serial={cmd.serial or 'all'}, "
                            f"rgb=({cmd.color.r},{cmd.color.g},{cmd.color.b})"
                        )

                        # Metric (Phase 46)
                        metrics.stream_commands_total.labels(command_type="color").inc()

                    elif control_msg.HasField("effect_command"):
                        # Phase 46: Process effect command via stream
                        cmd = control_msg.effect_command
                        target_serial = cmd.serial if cmd.serial else None

                        # Apply to target serial or all controllers (broadcast)
                        serials_to_update = [target_serial] if target_serial else list(self.tracked_controllers.keys())

                        color_rgb = (
                            (cmd.color.r, cmd.color.g, cmd.color.b)
                            if cmd.color.r or cmd.color.g or cmd.color.b
                            else (255, 255, 255)
                        )
                        duration_ms = cmd.duration_ms or 1000

                        for serial in serials_to_update:
                            if serial in self.tracked_controllers:
                                await self.feedback_manager.play_effect(
                                    serial, cmd.effect, color_rgb, duration_ms, speed=5
                                )

                        effect_name = controller_manager_pb2.ControllerEffect.Name(cmd.effect)
                        logger.debug(
                            f"[{subscriber_id}] Effect command: serial={cmd.serial or 'all'}, effect={effect_name}"
                        )

                        # Metric (Phase 46)
                        metrics.stream_commands_total.labels(command_type="effect").inc()

                    elif control_msg.HasField("vibration_command"):
                        # Phase 46: Process vibration command via stream
                        cmd = control_msg.vibration_command
                        target_serial = cmd.serial if cmd.serial else None

                        # Apply to target serial or all controllers (broadcast)
                        serials_to_update = [target_serial] if target_serial else list(self.tracked_controllers.keys())

                        for serial in serials_to_update:
                            if serial in self.tracked_controllers:
                                await self.feedback_manager.set_vibration(serial, cmd.intensity, cmd.duration_ms)

                        logger.debug(
                            f"[{subscriber_id}] Vibration command: "
                            f"serial={cmd.serial or 'all'}, "
                            f"intensity={cmd.intensity}, duration={cmd.duration_ms}ms"
                        )

                        # Metric (Phase 46)
                        metrics.stream_commands_total.labels(command_type="vibration").inc()

                    elif control_msg.HasField("combined_feedback"):
                        # Phase 46: Process combined color + vibration command
                        cmd = control_msg.combined_feedback
                        target_serial = cmd.serial if cmd.serial else None

                        # Apply to target serial or all controllers (broadcast)
                        serials_to_update = [target_serial] if target_serial else list(self.tracked_controllers.keys())

                        for serial in serials_to_update:
                            if serial in self.tracked_controllers:
                                # Set color and vibration atomically
                                await self.feedback_manager.set_controller_color(
                                    serial, (cmd.color.r, cmd.color.g, cmd.color.b)
                                )
                                if cmd.vibration_intensity > 0:
                                    await self.feedback_manager.set_vibration(
                                        serial,
                                        cmd.vibration_intensity,
                                        cmd.vibration_duration_ms,
                                    )

                        logger.debug(
                            f"[{subscriber_id}] Combined feedback: "
                            f"serial={cmd.serial or 'all'}, "
                            f"rgb=({cmd.color.r},{cmd.color.g},{cmd.color.b}), "
                            f"vib={cmd.vibration_intensity}@{cmd.vibration_duration_ms}ms"
                        )

                        # Metric (Phase 46)
                        metrics.stream_commands_total.labels(command_type="combined").inc()

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

                            logger.debug(f"[{subscriber_id}] Base color set: serial={serial}, rgb={color}")

                        metrics.stream_commands_total.labels(command_type="base_color").inc()

                    elif control_msg.HasField("game_effect"):
                        # Phase XX: Trigger semantic game effect (LED state ownership)
                        cmd = control_msg.game_effect
                        await self.feedback_manager.handle_game_effect(cmd.serial, cmd.effect, subscriber_id)

                        effect_name = controller_manager_pb2.GameEffect.Name(cmd.effect)
                        logger.debug(
                            f"[{subscriber_id}] Game effect: serial={cmd.serial or 'all'}, effect={effect_name}"
                        )

                        metrics.stream_commands_total.labels(command_type="game_effect").inc()

            except Exception as e:
                logger.error(f"[{subscriber_id}] Error reading client updates: {e}", exc_info=True)

        # Start background task to read client updates
        update_task = asyncio.create_task(read_client_updates())

        logger.info(f"New dynamic gameplay subscriber: {subscriber_id}")

        try:
            # Stream gameplay data
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
                        )
                        gameplay_data.append(gd)

                    # Send update
                    update = controller_manager_pb2.GameplayDataUpdate(
                        controllers=gameplay_data, timestamp=int(time.time() * 1000)
                    )
                    yield update

                    # Track stream update
                    if gameplay_data:
                        metrics.stream_updates_total.labels(stream_type="gameplay_data_dynamic").inc()
                        # Track number of controllers streamed per frame (Phase 45)
                        metrics.streamed_controllers.observe(len(gameplay_data))

                    await asyncio.sleep(interval)

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

            logger.info(f"Dynamic gameplay subscriber disconnected: {subscriber_id}")

    async def SetControllerColor(self, request, context):  # noqa: N802, ARG002
        """Set LED color on controller(s) - Phase 19 feedback feature, Phase 57 backend (async)."""
        with tracer.start_as_current_span("SetControllerColor") as span:
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("color.r", request.color.r)
            span.set_attribute("color.g", request.color.g)
            span.set_attribute("color.b", request.color.b)

            try:
                # Determine which controllers to update (under lock)
                with self.state_lock:
                    serials = [request.serial] if request.serial else list(self.tracked_controllers.keys())

                controllers_updated = 0
                controllers_failed = 0

                for serial in serials:
                    with self.state_lock:
                        controller_exists = serial in self.tracked_controllers
                    if controller_exists:
                        success = await self.backend.set_led_color(
                            serial, request.color.r, request.color.g, request.color.b
                        )
                        if success:
                            controllers_updated += 1
                            logger.debug(
                                f"Set color on {serial}: RGB({request.color.r},{request.color.g},{request.color.b})"
                            )
                        else:
                            controllers_failed += 1

                span.set_attribute("controllers_updated", controllers_updated)
                span.set_attribute("controllers_failed", controllers_failed)

                # Return success only if at least one controller was updated and none failed
                if controllers_failed > 0:
                    return controller_manager_pb2.SetControllerColorResponse(
                        success=False, error=f"Failed to set color on {controllers_failed} controller(s)"
                    )
                if controllers_updated == 0 and len(serials) > 0:
                    return controller_manager_pb2.SetControllerColorResponse(
                        success=False, error="No controllers found to update"
                    )
                return controller_manager_pb2.SetControllerColorResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                logger.error(f"SetControllerColor error: {e}", exc_info=True)
                return controller_manager_pb2.SetControllerColorResponse(success=False, error=str(e))

    async def SetControllerVibration(self, request, context):  # noqa: N802, ARG002
        """Set vibration on controller(s) - Phase 19 feedback feature, Phase 57 async."""
        with tracer.start_as_current_span("SetControllerVibration") as span:
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("intensity", request.intensity)
            span.set_attribute("duration_ms", request.duration_ms)

            try:
                # Determine which controllers to update
                with self.state_lock:
                    serials = [request.serial] if request.serial else list(self.tracked_controllers.keys())

                controllers_updated = 0
                controllers_failed = 0

                for serial in serials:
                    with self.state_lock:
                        controller_exists = serial in self.tracked_controllers
                        if not controller_exists:
                            continue

                    success = await self.backend.set_rumble(serial, request.intensity)
                    if success:
                        controllers_updated += 1
                        logger.debug(f"Set vibration on {serial}: intensity={request.intensity}")

                        # Schedule vibration stop if duration is specified (using asyncio task)
                        if request.duration_ms > 0 and request.intensity > 0:
                            await self._schedule_vibration_stop(serial, request.duration_ms)
                    else:
                        controllers_failed += 1

                span.set_attribute("controllers_updated", controllers_updated)
                span.set_attribute("controllers_failed", controllers_failed)

                # Return success only if at least one controller was updated and none failed
                if controllers_failed > 0:
                    return controller_manager_pb2.SetControllerVibrationResponse(
                        success=False, error=f"Failed to set vibration on {controllers_failed} controller(s)"
                    )
                if controllers_updated == 0 and len(serials) > 0:
                    return controller_manager_pb2.SetControllerVibrationResponse(
                        success=False, error="No controllers found to update"
                    )
                return controller_manager_pb2.SetControllerVibrationResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                logger.error(f"SetControllerVibration error: {e}", exc_info=True)
                return controller_manager_pb2.SetControllerVibrationResponse(success=False, error=str(e))

    async def _schedule_vibration_stop(self, serial: str, duration_ms: int):
        """Schedule vibration to stop after duration using asyncio task (Phase 57 async migration)."""
        # Cancel existing task for this controller
        if serial in self.vibration_tasks:
            self.vibration_tasks[serial].cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.vibration_tasks[serial]

        async def stop_after_delay():
            await asyncio.sleep(duration_ms / 1000.0)
            with self.state_lock:
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

    async def PlayControllerEffect(self, request, context):  # noqa: N802, ARG002
        """Play visual effect on controller(s) - Phase 31/40 implementation.

        Uses effect methods inherited from ControllerEffectsBase.
        Adds tracing and thread-safe task management.
        """
        with tracer.start_as_current_span("PlayControllerEffect") as span:
            effect_name = controller_manager_pb2.ControllerEffect.Name(request.effect)
            span.set_attribute("serial", request.serial or "all")
            span.set_attribute("effect", effect_name)
            span.set_attribute("duration_ms", request.duration_ms)
            span.set_attribute("speed", request.speed)

            try:
                # Determine which controllers to update
                serials = [request.serial] if request.serial else list(self.tracked_controllers.keys())

                # Color as tuple for effect methods
                color = (request.color.r, request.color.g, request.color.b) if request.color else (255, 255, 255)
                duration_ms = request.duration_ms or 1000  # Default 1 second
                speed = request.speed or 5  # Default medium speed

                controllers_updated = 0
                for serial in serials:
                    if serial not in self.tracked_controllers:
                        continue

                    # Cancel any existing effect on this controller (Phase 34: async lock)
                    async with self.feedback_manager.effect_lock:
                        if serial in self.feedback_manager.active_effects:
                            self.feedback_manager.active_effects[serial].cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await self.feedback_manager.active_effects[serial]
                            del self.feedback_manager.active_effects[serial]

                    # Start the appropriate effect (methods inherited from ControllerEffectsBase - Phase 40)
                    if request.effect == controller_manager_pb2.EFFECT_NONE:
                        # Solid color (no animation)
                        await self.feedback_manager._set_led_color(serial, color)

                    elif request.effect == controller_manager_pb2.EFFECT_FLASH:
                        task = asyncio.create_task(self._effect_flash(serial, color, duration_ms, speed))
                        async with self.feedback_manager.effect_lock:  # Phase 34: async lock
                            self.feedback_manager.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_PULSE:
                        task = asyncio.create_task(self._effect_pulse(serial, color, duration_ms, speed))
                        async with self.feedback_manager.effect_lock:  # Phase 34: async lock
                            self.feedback_manager.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_RAINBOW:
                        task = asyncio.create_task(self._effect_rainbow(serial, duration_ms, speed))
                        async with self.feedback_manager.effect_lock:  # Phase 34: async lock
                            self.feedback_manager.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_FADE_OUT:
                        task = asyncio.create_task(self._effect_fade_out(serial, color, duration_ms))
                        async with self.feedback_manager.effect_lock:  # Phase 34: async lock
                            self.feedback_manager.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_FADE_IN:
                        task = asyncio.create_task(self._effect_fade_in(serial, color, duration_ms))
                        async with self.feedback_manager.effect_lock:  # Phase 34: async lock
                            self.feedback_manager.active_effects[serial] = task

                    else:
                        logger.warning(f"Unknown effect: {effect_name}")
                        continue

                    controllers_updated += 1

                span.set_attribute("controllers_updated", controllers_updated)
                logger.info(f"PlayControllerEffect: {effect_name} on {controllers_updated} controller(s)")

                return controller_manager_pb2.PlayControllerEffectResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                logger.error(f"PlayControllerEffect error: {e}", exc_info=True)
                return controller_manager_pb2.PlayControllerEffectResponse(success=False, error=str(e))

    # NOTE: Internal feedback methods moved to feedback_manager.py
    # NOTE: State cache methods moved to state_cache.py
    # NOTE: Button detection methods moved to button_detector.py
    # NOTE: Event publishing methods moved to event_publisher.py

    def shutdown(self):
        """Shutdown the controller manager."""
        logger.info("Shutting down ControllerManager...")

        # Stop discovery loop
        self.discovery_loop.stop()

        # Stop all controller processes
        for _serial, proc in self.controller_processes.items():
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2.0)

        self.discovery_loop.join(timeout=5.0)
