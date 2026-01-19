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

# OpenTelemetry (trace API for span operations)
from opentelemetry import trace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import contextlib

from lib.controller_constants import (
    AxisKey,
    ButtonKey,
    ControllerInfoKey,
    StateKey,
)
from lib.telemetry import init_telemetry
from proto import controller_manager_pb2, controller_manager_pb2_grpc
from services.controller_manager import metrics

# Phase 57: Backend abstraction for platform independence
from services.controller_manager.backend_factory import create_backend
from services.controller_manager.button_detector import ButtonDetector
from services.controller_manager.discovery import PeriodicRescanTimer
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

        # State caching (Phase 18 - Task 1, refactored)
        self.state_cache_manager = StateCache(self.monitoring)
        self.state_cache_manager.set_controller_states(self.controller_states)

        # Button detector for button transitions (Phase 41, refactored)
        self.button_detector = ButtonDetector(self.event_publisher)
        self.button_detector.set_subscribers(self.button_event_subscribers)

        # Monitoring (battery and RSSI) - Phase 39, Phase 48, extracted to monitoring.py
        self.monitoring = ControllerMonitoring(
            low_battery_threshold=1,
            rssi_check_interval=10.0,
            weak_signal_threshold=-80,
        )

        # Feedback manager for LED colors, vibration, and effects (Phase refactor)
        self.feedback_manager = FeedbackManager(
            backend=self.backend,
            tracked_controllers=self.tracked_controllers,
            state_lock=self.state_lock,
        )

        # Backward compatibility aliases (will be removed in later phases)
        self.effect_lock = self.feedback_manager.effect_lock
        self.base_colors = self.feedback_manager.base_colors
        self.active_effects = self.feedback_manager.active_effects
        self.active_effect_types = self.feedback_manager.active_effect_types
        self.cancellable_effects = self.feedback_manager.cancellable_effects

        # Vibration duration timers - tracks active vibration timers per controller
        self.vibration_timers: dict[str, threading.Timer] = {}

        # Shared event loop for discovery thread (avoids creating new loop per call)
        self._discovery_loop_handle: asyncio.AbstractEventLoop | None = None

        # Main event loop reference (for cross-thread queue operations)
        # Set lazily when first gRPC handler runs via event_publisher

        # Phase 72: LED update timing (separated from polling)
        self._last_led_update = 0.0

        # Adaptive polling (Quick Win optimization)
        # Track activity per controller to reduce polling frequency when idle
        # - Active: poll at 60Hz (16ms) - controller has button/motion activity
        # - Idle: poll at 10Hz (100ms) - no activity for >5 seconds
        self._last_activity_time: dict[str, float] = {}  # serial -> last activity timestamp
        self._previous_accel: dict[str, tuple[float, float, float]] = {}  # for motion detection
        self._last_poll_time: dict[str, float] = {}  # serial -> last poll timestamp
        self._idle_threshold_seconds = 5.0  # Seconds of inactivity before going to idle mode
        self._active_poll_interval = 0.016  # ~60Hz
        self._idle_poll_interval = 0.100  # ~10Hz
        self._accel_movement_threshold = 0.05  # Minimum accel change to count as activity

        # Phase 79: Periodic rescan timer for externally paired controllers
        self.rescan_timer = PeriodicRescanTimer(interval=5.0)

        # Discovery thread
        self.running = True
        self.backend_initialized = False  # Phase 57: Track backend init status
        self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.discovery_thread.start()

        logger.info("ControllerManager initialized")

    def _run_in_discovery_loop(self, coro):
        """
        Run an async coroutine in the discovery thread's event loop.

        This avoids creating a new event loop for each backend call.
        Must only be called from the discovery thread.
        """
        if self._discovery_loop_handle is None:
            raise RuntimeError("Discovery loop not initialized")
        return self._discovery_loop_handle.run_until_complete(coro)

    def _discovery_loop(self):
        """
        Background thread for controller discovery and battery monitoring.

        Phase 56: Event-driven spans - Only creates spans for actual events (controller connected),
        not for routine polling. Metrics track polling operations.
        Phase 57: Uses backend abstraction for platform independence.
        """
        import asyncio

        # Performance: Use uvloop for discovery thread's event loop too
        try:
            import uvloop

            self._discovery_loop_handle = uvloop.new_event_loop()
            logger.debug("Discovery loop using uvloop")
        except ImportError:
            self._discovery_loop_handle = asyncio.new_event_loop()

        asyncio.set_event_loop(self._discovery_loop_handle)

        try:
            # Initialize backend
            self.backend_initialized = self._discovery_loop_handle.run_until_complete(self.backend.initialize())
            if not self.backend_initialized:
                logger.error("Backend initialization failed - discovery loop will not run")
                return
            logger.info("Backend initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize backend: {e}", exc_info=True)
            return

        while self.running:
            try:
                current_time = time.time()

                # Check for new controllers every second (metrics, no span)
                with metrics.discovery_check_duration_seconds.time():
                    self._check_for_new_controllers()
                    metrics.discovery_checks_total.inc()

                # Phase 57: Update controller states from backend
                self._update_controller_states()

                # Check battery levels every 30 seconds (Phase 39 - Task 4, Phase 70)
                # Note: Battery display/warnings moved to menu service (Phase 70)
                if current_time - self.monitoring.last_battery_check >= 30.0:
                    with metrics.battery_check_duration_seconds.time():
                        self.monitoring.check_battery_levels(self.tracked_controllers)
                        metrics.battery_checks_total.inc()
                    self.monitoring.last_battery_check = current_time

                # Check RSSI every 10 seconds (Phase 48)
                if current_time - self.monitoring.last_rssi_check >= self.monitoring.rssi_check_interval:
                    with metrics.rssi_check_duration_seconds.time():
                        self.monitoring.check_rssi_levels(
                            self.tracked_controllers,
                            self.backend,
                            self._run_in_discovery_loop,
                        )
                        metrics.rssi_checks_total.inc()
                    self.monitoring.last_rssi_check = current_time

                # Phase 72: Update LEDs at 20Hz (every 50ms) - separated from polling
                if current_time - self._last_led_update >= 0.05:
                    updated_count = self.backend.update_all_leds()
                    self._last_led_update = current_time
                    # Track LED batch update efficiency
                    metrics.led_batch_updates_total.inc()
                    metrics.led_controllers_updated_per_batch.observe(updated_count)

                # No sleep - poll as fast as possible for button responsiveness

            except Exception as e:
                logger.error(f"Discovery loop error: {e}", exc_info=True)
                time.sleep(5.0)

    def _check_for_new_controllers(self):
        """
        Check for newly connected controllers (hardware).

        Phase 56: Event-driven spans - Only creates spans when NEW controllers are discovered.
        Routine checks are tracked via metrics only (no spans).
        Phase 57: Uses backend abstraction instead of direct psmove.
        Phase 79: Periodic forced rescan to catch externally paired controllers.
        """
        if not self.backend_initialized:
            return

        try:
            # Phase 79: Check if it's time for a forced rescan
            force_rescan = self.rescan_timer.should_force_rescan()

            # Get list of connected controllers from backend
            connected_serials = self.backend.get_connected_controllers(force_rescan)
            connected_set = set(connected_serials)

            # Check for disconnected controllers (in tracked but not in connected)
            with self.state_lock:
                tracked_serials = set(self.tracked_controllers.keys())

            disconnected_serials = tracked_serials - connected_set
            for serial in disconnected_serials:
                logger.info(f"Controller {serial} disconnected - cleaning up server tracking")
                with self.state_lock:
                    if serial in self.tracked_controllers:
                        del self.tracked_controllers[serial]
                    if serial in self.controller_states:
                        del self.controller_states[serial]
                    self.state_cache_manager.clear_controller(serial)
                    self.button_detector.clear_controller(serial)
                    # Note: Keep base_colors[serial] so we can restore on reconnect!
                    # Adaptive polling cleanup
                    self._last_activity_time.pop(serial, None)
                    self._previous_accel.pop(serial, None)
                    self._last_poll_time.pop(serial, None)
                # Publish disconnect event to button event stream subscribers
                self.button_detector.publish_connection_event(serial, is_connect=False)
                metrics.controller_disconnect_total.labels(serial=serial).inc()

            # Check for new controllers
            for serial in connected_serials:
                if serial not in self.tracked_controllers:
                    # New controller found - create event span
                    with tracer.start_as_current_span("controller_connected") as span:
                        span.set_attribute("controller.serial", serial)
                        span.set_attribute("controller.count_total", len(connected_serials))

                        logger.info(f"Discovered new controller: {serial}")

                        # Spawn tracking process
                        with tracer.start_as_current_span("spawn_controller_process") as spawn_span:
                            spawn_span.set_attribute("controller.serial", serial)
                            self._spawn_controller_process(serial)

                        # Publish connect event to button event stream subscribers
                        battery = self.tracked_controllers.get(serial, {}).get(ControllerInfoKey.BATTERY, 0)
                        self.button_detector.publish_connection_event(serial, is_connect=True, battery=battery)

                        # Restore base color if we had one before (reconnection case)
                        if serial in self.base_colors:
                            color = self.base_colors[serial]
                            logger.info(f"Restoring base color for reconnected controller {serial}: {color}")
                            asyncio.run_coroutine_threadsafe(
                                self.feedback_manager.set_controller_color(serial, color),
                                self._discovery_loop,
                            )

        except Exception as e:
            logger.error(f"Error discovering controllers: {e}", exc_info=True)

    def _update_controller_states(self):
        """
        Update states for all tracked controllers from backend.

        Phase 62: Uses parallel polling with asyncio.gather() to read all
        controllers concurrently. This reduces latency from O(n × latency)
        to O(latency), enabling support for large player counts.

        Adaptive polling: Controllers are polled at different rates based on activity:
        - Active (recent button/motion activity): 60Hz
        - Idle (no activity for 5+ seconds): 10Hz

        Called frequently (~60 Hz) to keep states fresh for streaming.
        Uses shared discovery loop event loop for efficiency.
        """
        if not self.backend_initialized:
            return

        try:
            # Get list of serials (dict.keys() is atomic in Python due to GIL)
            all_serials = list(self.tracked_controllers.keys())

            if not all_serials:
                return

            current_time = time.time()

            # Adaptive polling: Determine which controllers need polling this cycle
            serials_to_poll = []
            active_count = 0
            idle_count = 0
            skipped_count = 0

            for serial in all_serials:
                last_activity = self._last_activity_time.get(serial, current_time)
                last_poll = self._last_poll_time.get(serial, 0)
                is_idle = (current_time - last_activity) > self._idle_threshold_seconds

                if is_idle:
                    idle_count += 1
                    poll_interval = self._idle_poll_interval
                else:
                    active_count += 1
                    poll_interval = self._active_poll_interval

                # Check if enough time has passed since last poll
                if (current_time - last_poll) >= poll_interval:
                    serials_to_poll.append(serial)
                    self._last_poll_time[serial] = current_time
                else:
                    skipped_count += 1

            # Update adaptive polling metrics
            metrics.adaptive_polling_active_controllers.set(active_count)
            metrics.adaptive_polling_idle_controllers.set(idle_count)
            if skipped_count > 0:
                metrics.adaptive_polling_skipped_total.inc(skipped_count)

            if not serials_to_poll:
                return

            # Debug: Log tracked controller count periodically (every 5 seconds)
            if not hasattr(self, "_last_controller_count_log"):
                self._last_controller_count_log = 0
            if current_time - self._last_controller_count_log >= 5.0:
                logger.info(
                    f"Polling {len(serials_to_poll)}/{len(all_serials)} controllers "
                    f"(active={active_count}, idle={idle_count}): {serials_to_poll}"
                )
                self._last_controller_count_log = current_time

            # Phase 62: Parallel polling - read all controllers concurrently
            start_time = time.time()

            async def get_all_states():
                """Gather all controller states in parallel."""
                coros = [self.backend.get_controller_state(serial) for serial in serials_to_poll]
                return await asyncio.gather(*coros, return_exceptions=True)

            # Single blocking call for ALL controllers (instead of one per controller)
            results = self._run_in_discovery_loop(get_all_states())

            # Record metrics
            poll_duration = time.time() - start_time
            metrics.poll_batch_duration_seconds.observe(poll_duration)
            metrics.poll_batch_size.observe(len(serials_to_poll))

            # Process all results (no lock needed - dict operations atomic due to GIL)
            for serial, state in zip(serials_to_poll, results, strict=False):
                # Skip if controller was removed during polling
                if serial not in self.tracked_controllers:
                    continue

                # Handle exceptions from individual controller reads
                if isinstance(state, Exception):
                    logger.debug(f"Error updating state for {serial}: {state}")
                    continue

                if not state:
                    continue

                # Update stored state
                self.controller_states[serial] = state

                # Update battery in tracked_controllers info
                if StateKey.BATTERY in state:
                    self.tracked_controllers[serial][ControllerInfoKey.BATTERY] = state[StateKey.BATTERY]

                # Detect button transitions immediately after polling (not in gRPC handlers)
                # This ensures button events are detected at polling frequency, not stream frequency
                self.button_detector.detect_transitions_from_state(serial, state, self.tracked_controllers)

                # Adaptive polling: Detect activity to update polling rate
                self._update_activity_tracking(serial, state, current_time)

        except Exception as e:
            logger.error(f"Error updating controller states: {e}", exc_info=True)

    def _update_activity_tracking(self, serial: str, state: dict, current_time: float):
        """
        Update activity tracking for adaptive polling.

        Activity is detected when:
        - Any button is pressed
        - Accelerometer values change significantly (movement detected)
        """
        activity_detected = False

        # Check for any button activity
        button_keys = [
            ButtonKey.MOVE,
            ButtonKey.TRIGGER,
            ButtonKey.PS,
            ButtonKey.CROSS,
            ButtonKey.CIRCLE,
            ButtonKey.SQUARE,
            ButtonKey.TRIANGLE,
            ButtonKey.SELECT,
            ButtonKey.START,
        ]
        for key in button_keys:
            if state.get(key, False):
                activity_detected = True
                break

        # Check for accelerometer movement if no button pressed
        if not activity_detected and StateKey.ACCEL in state:
            accel = state[StateKey.ACCEL]
            current_accel = (
                accel.get(AxisKey.X, 0),
                accel.get(AxisKey.Y, 0),
                accel.get(AxisKey.Z, 0),
            )

            prev_accel = self._previous_accel.get(serial)
            if prev_accel:
                # Calculate magnitude of acceleration change
                dx = abs(current_accel[0] - prev_accel[0])
                dy = abs(current_accel[1] - prev_accel[1])
                dz = abs(current_accel[2] - prev_accel[2])
                movement = dx + dy + dz

                if movement > self._accel_movement_threshold:
                    activity_detected = True

            self._previous_accel[serial] = current_accel

        # Update last activity time if activity detected
        if activity_detected:
            self._last_activity_time[serial] = current_time

    def _spawn_controller_process(self, serial: str):
        """
        Spawn a tracking process for a controller.

        Phase 57: Simplified to use backend for state tracking.
        Uses shared discovery loop event loop for efficiency.
        """
        try:
            # Get initial state from backend using shared event loop
            state = self._run_in_discovery_loop(self.backend.get_controller_state(serial))

            if not state:
                logger.error(f"Failed to get initial state for controller {serial}")
                return

            battery = state.get(StateKey.BATTERY, 5)

            # Track controller under lock
            with self.state_lock:
                self.tracked_controllers[serial] = {
                    ControllerInfoKey.SERIAL: serial,
                    ControllerInfoKey.BATTERY: battery,
                    ControllerInfoKey.TEAM: 0,
                    ControllerInfoKey.CONNECTED_AT: time.time(),
                }

                # Store initial state
                self.controller_states[serial] = state

            # Add attributes to current span (this is called within "spawn_controller_process" span)
            current_span = trace.get_current_span()
            current_span.set_attribute("controller.serial", serial)
            current_span.set_attribute("controller.battery", battery)
            current_span.add_event(
                "controller_added_to_tracking",
                {"serial": serial, "battery": battery},
            )

            logger.info(f"Spawned tracking for controller {serial}")

            # Update metrics (Phase 38)
            metrics.active_controllers.inc()
            metrics.controller_connected.labels(serial=serial).set(1)
            metrics.controller_battery_level.labels(serial=serial).set(battery)
            # Check if this is a reconnect
            if serial in self.paired_serials:
                metrics.controller_reconnect_total.labels(serial=serial).inc()

            # Note: Actual process spawning would happen here in production
            # For now, we track the controller info

        except Exception as e:
            logger.error(f"Error spawning controller process {serial}: {e}", exc_info=True)

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
                            async with self.effect_lock:
                                if serial in self.active_effects:
                                    effect_type = self.active_effect_types.get(serial)
                                    if effect_type in self.cancellable_effects:
                                        self.active_effects[serial].cancel()
                                        with contextlib.suppress(asyncio.CancelledError):
                                            await self.active_effects[serial]
                                        del self.active_effects[serial]
                                        self.active_effect_types.pop(serial, None)
                                        # Clear effect active flag
                                        self.backend.set_effect_active(serial, False)
                                        logger.debug(f"Cancelled cancellable effect for {serial}")

                            # Store base color (will be used when effect completes)
                            self.base_colors[serial] = color

                            # Only set LED immediately if no effect is running
                            if serial not in self.active_effects:
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

                        # Phase XX: Extract filter from colors if provided, fallback to serials
                        if control_msg.config.colors:
                            # Use serials from colors as filter
                            current_filter = set()
                            for color_config in control_msg.config.colors:
                                serial = color_config.serial
                                if serial:
                                    current_filter.add(serial)
                                    # Store base color and set LED
                                    color = (color_config.color.r, color_config.color.g, color_config.color.b)
                                    self.base_colors[serial] = color
                                    if serial in self.tracked_controllers:
                                        await self.feedback_manager.set_controller_color(serial, color)
                            logger.info(f"[{subscriber_id}] Set base colors for {len(current_filter)} controllers")
                        elif control_msg.config.serials:
                            # Legacy: use serials field directly
                            current_filter = set(control_msg.config.serials)
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
                            async with self.effect_lock:
                                if serial in self.active_effects:
                                    effect_type = self.active_effect_types.get(serial)
                                    if effect_type in self.cancellable_effects:
                                        self.active_effects[serial].cancel()
                                        with contextlib.suppress(asyncio.CancelledError):
                                            await self.active_effects[serial]
                                        del self.active_effects[serial]
                                        self.active_effect_types.pop(serial, None)
                                        # Clear effect active flag
                                        self.backend.set_effect_active(serial, False)
                                        logger.debug(f"Cancelled cancellable effect for {serial}")

                            # Store base color (will be used when effect completes)
                            self.base_colors[serial] = color

                            # Only set LED immediately if no effect is running
                            if serial not in self.active_effects:
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

                        # Cancel any existing vibration timer for this controller (under lock)
                        if serial in self.vibration_timers:
                            self.vibration_timers[serial].cancel()
                            del self.vibration_timers[serial]

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
                    async with self.effect_lock:
                        if serial in self.active_effects:
                            self.active_effects[serial].cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await self.active_effects[serial]
                            del self.active_effects[serial]

                    # Start the appropriate effect (methods inherited from ControllerEffectsBase - Phase 40)
                    if request.effect == controller_manager_pb2.EFFECT_NONE:
                        # Solid color (no animation)
                        await self.feedback_manager._set_led_color(serial, color)

                    elif request.effect == controller_manager_pb2.EFFECT_FLASH:
                        task = asyncio.create_task(self._effect_flash(serial, color, duration_ms, speed))
                        async with self.effect_lock:  # Phase 34: async lock
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_PULSE:
                        task = asyncio.create_task(self._effect_pulse(serial, color, duration_ms, speed))
                        async with self.effect_lock:  # Phase 34: async lock
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_RAINBOW:
                        task = asyncio.create_task(self._effect_rainbow(serial, duration_ms, speed))
                        async with self.effect_lock:  # Phase 34: async lock
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_FADE_OUT:
                        task = asyncio.create_task(self._effect_fade_out(serial, color, duration_ms))
                        async with self.effect_lock:  # Phase 34: async lock
                            self.active_effects[serial] = task

                    elif request.effect == controller_manager_pb2.EFFECT_FADE_IN:
                        task = asyncio.create_task(self._effect_fade_in(serial, color, duration_ms))
                        async with self.effect_lock:  # Phase 34: async lock
                            self.active_effects[serial] = task

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
        self.running = False

        # Stop all controller processes
        for _serial, proc in self.controller_processes.items():
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2.0)

        self.discovery_thread.join(timeout=5.0)
