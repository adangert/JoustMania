"""
Discovery loop for ControllerManager.

Background thread that handles:
- Controller discovery and tracking
- Battery monitoring
- State polling with adaptive frequency
- LED updates

Note: RSSI monitoring is handled by the host pairing-daemon which has
direct access to hcitool for reliable signal strength readings.
"""

import asyncio
import logging
import threading
import time
from typing import TYPE_CHECKING, Any

from opentelemetry import trace

from lib.controller_constants import (
    AxisKey,
    ButtonKey,
    ControllerInfoKey,
    StateKey,
)
from lib.telemetry import SpanAttr, get_tracer
from services.controller_manager import metrics

if TYPE_CHECKING:
    from services.controller_manager.backend_base import BackendBase
    from services.controller_manager.button_detector import ButtonDetector
    from services.controller_manager.discovery import PeriodicRescanTimer
    from services.controller_manager.event_publisher import EventPublisher
    from services.controller_manager.feedback_manager import FeedbackManager
    from services.controller_manager.monitoring import ControllerMonitoring
    from services.controller_manager.name_manager import NameManager
    from services.controller_manager.state_cache import StateCache

logger = logging.getLogger(__name__)

# Lazy telemetry initialization - defers OTLP setup until first span
tracer = get_tracer(__name__)


class DiscoveryLoop:
    """
    Background discovery thread for controller management.

    Handles controller discovery, state polling, battery monitoring,
    and LED updates in a dedicated thread.
    """

    def __init__(
        self,
        backend: "BackendBase",
        tracked_controllers: dict[str, dict],
        controller_states: dict[str, dict],
        state_lock: threading.RLock,
        button_detector: "ButtonDetector",
        state_cache_manager: "StateCache",
        feedback_manager: "FeedbackManager",
        monitoring: "ControllerMonitoring",
        rescan_timer: "PeriodicRescanTimer",
        paired_serials: list[str],
        base_colors: dict[str, tuple[int, int, int]],
        event_publisher: "EventPublisher",
        name_manager: "NameManager | None" = None,
    ):
        """
        Initialize the discovery loop.

        Args:
            backend: Controller backend implementation
            tracked_controllers: Dict of serial -> controller info
            controller_states: Dict of serial -> state dict
            state_lock: RLock for thread-safe access
            button_detector: Button transition detector
            state_cache_manager: State caching manager
            feedback_manager: LED/vibration feedback manager
            monitoring: Battery monitoring
            rescan_timer: Periodic rescan timer
            paired_serials: List of paired controller serials
            base_colors: Dict of serial -> base LED color
            event_publisher: Event publisher for cross-thread communication
            name_manager: Name manager for human-readable controller names (Issue #7)
        """
        self.backend = backend
        self.tracked_controllers = tracked_controllers
        self.controller_states = controller_states
        self.state_lock = state_lock
        self.button_detector = button_detector
        self.state_cache_manager = state_cache_manager
        self.feedback_manager = feedback_manager
        self.monitoring = monitoring
        self.rescan_timer = rescan_timer
        self.paired_serials = paired_serials
        self.base_colors = base_colors
        self.event_publisher = event_publisher
        self.name_manager = name_manager

        # Discovery thread state
        self.running = True
        self.backend_initialized = False
        self._loop_handle: asyncio.AbstractEventLoop | None = None

        # LED update timing (Phase 72: separated from polling)
        self._last_led_update = 0.0

        # Adaptive polling state
        self._last_activity_time: dict[str, float] = {}
        self._previous_accel: dict[str, tuple[float, float, float]] = {}
        self._last_poll_time: dict[str, float] = {}
        self._idle_threshold_seconds = 5.0
        self._active_poll_interval = 0.016  # ~60Hz
        self._idle_poll_interval = 0.100  # ~10Hz
        self._accel_movement_threshold = 0.05

        # Gameplay mode: when > 0, disable adaptive polling (all controllers at 60Hz)
        # This counter is incremented by StreamGameplayData and decremented on disconnect
        self._gameplay_stream_count = 0
        self._gameplay_stream_lock = threading.Lock()

        # Debug logging throttle
        self._last_controller_count_log = 0.0

        # Discovery thread
        self._thread = threading.Thread(target=self._discovery_loop, daemon=True)

    def start(self) -> None:
        """Start the discovery thread."""
        self._thread.start()
        logger.info("Discovery loop started")

    def enter_gameplay_mode(self) -> None:
        """Enter gameplay mode - disables adaptive polling for consistent 60Hz."""
        with self._gameplay_stream_lock:
            self._gameplay_stream_count += 1
            logger.info(f"Gameplay mode entered (active streams: {self._gameplay_stream_count})")

    def exit_gameplay_mode(self) -> None:
        """Exit gameplay mode - re-enables adaptive polling if no streams remain."""
        with self._gameplay_stream_lock:
            self._gameplay_stream_count = max(0, self._gameplay_stream_count - 1)
            logger.info(f"Gameplay mode exited (active streams: {self._gameplay_stream_count})")

    def is_gameplay_mode(self) -> bool:
        """Check if gameplay mode is active (any gameplay streams running)."""
        with self._gameplay_stream_lock:
            return self._gameplay_stream_count > 0

    def stop(self) -> None:
        """Stop the discovery loop."""
        self.running = False

    def join(self, timeout: float | None = None) -> None:
        """Wait for the discovery thread to complete."""
        self._thread.join(timeout=timeout)

    def run_coroutine(self, coro) -> Any:
        """
        Run an async coroutine in the discovery thread's event loop.

        This avoids creating a new event loop for each backend call.
        Must only be called from the discovery thread.
        """
        if self._loop_handle is None:
            raise RuntimeError("Discovery loop not initialized")
        return self._loop_handle.run_until_complete(coro)

    def _discovery_loop(self) -> None:
        """
        Background thread for controller discovery and battery monitoring.

        Phase 56: Event-driven spans - Only creates spans for actual events (controller connected),
        not for routine polling. Metrics track polling operations.
        Phase 57: Uses backend abstraction for platform independence.
        """
        # Performance: Use uvloop for discovery thread's event loop too
        try:
            import uvloop

            self._loop_handle = uvloop.new_event_loop()
            logger.debug("Discovery loop using uvloop")
        except ImportError:
            self._loop_handle = asyncio.new_event_loop()

        asyncio.set_event_loop(self._loop_handle)

        try:
            # Initialize backend
            self.backend_initialized = self._loop_handle.run_until_complete(self.backend.initialize())
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

    def _check_for_new_controllers(self) -> None:
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
                # Capture name before removing from tracked_controllers
                name = ""
                with self.state_lock:
                    if serial in self.tracked_controllers:
                        name = self.tracked_controllers[serial].get(ControllerInfoKey.NAME, "")
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
                self.button_detector.publish_connection_event(serial, is_connect=False, name=name)
                metrics.controller_disconnect_total.labels(serial=serial).inc()

            # Check for new controllers
            for serial in connected_serials:
                if serial not in self.tracked_controllers:
                    # New controller found - create event span
                    with tracer.start_as_current_span("controller_connected") as span:
                        span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)
                        span.set_attribute("controller.count_total", len(connected_serials))

                        logger.info(f"Discovered new controller: {serial}")

                        # Spawn tracking process
                        with tracer.start_as_current_span("spawn_controller_process") as spawn_span:
                            spawn_span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)
                            self._spawn_controller_process(serial)

                        # Publish connect event to button event stream subscribers
                        info = self.tracked_controllers.get(serial, {})
                        battery = info.get(ControllerInfoKey.BATTERY, 0)
                        name = info.get(ControllerInfoKey.NAME, "")
                        self.button_detector.publish_connection_event(
                            serial, is_connect=True, battery=battery, name=name
                        )

                        # Restore base color if we had one before (reconnection case)
                        if serial in self.base_colors:
                            color = self.base_colors[serial]
                            logger.info(f"Restoring base color for reconnected controller {serial}: {color}")
                            asyncio.run_coroutine_threadsafe(
                                self.feedback_manager.set_controller_color(serial, color),
                                self._loop_handle,
                            )

        except Exception as e:
            logger.error(f"Error discovering controllers: {e}", exc_info=True)

    def _update_controller_states(self) -> None:
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

            # Check if gameplay mode is active (disables adaptive polling)
            gameplay_mode = self.is_gameplay_mode()

            # Adaptive polling: Determine which controllers need polling this cycle
            # When in gameplay mode, all controllers poll at active rate (60Hz)
            serials_to_poll = []
            active_count = 0
            idle_count = 0
            skipped_count = 0

            for serial in all_serials:
                last_activity = self._last_activity_time.get(serial, current_time)
                last_poll = self._last_poll_time.get(serial, 0)
                is_idle = (current_time - last_activity) > self._idle_threshold_seconds

                # In gameplay mode, treat all controllers as active
                if gameplay_mode or not is_idle:
                    active_count += 1
                    poll_interval = self._active_poll_interval
                else:
                    idle_count += 1
                    poll_interval = self._idle_poll_interval

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
            if current_time - self._last_controller_count_log >= 5.0:
                logger.debug(
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
            results = self.run_coroutine(get_all_states())

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

    def _update_activity_tracking(self, serial: str, state: dict, current_time: float) -> None:
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

    def _spawn_controller_process(self, serial: str) -> None:
        """
        Spawn a tracking process for a controller.

        Phase 57: Simplified to use backend for state tracking.
        Uses shared discovery loop event loop for efficiency.
        """
        try:
            # Get initial state from backend using shared event loop
            state = self.run_coroutine(self.backend.get_controller_state(serial))

            if not state:
                logger.error(f"Failed to get initial state for controller {serial}")
                return

            battery = state.get(StateKey.BATTERY, 5)

            # Issue #7: Get human-readable name for controller
            name = ""
            if self.name_manager:
                name = self.name_manager.get_name(serial)

            # Track controller under lock
            with self.state_lock:
                self.tracked_controllers[serial] = {
                    ControllerInfoKey.SERIAL: serial,
                    ControllerInfoKey.BATTERY: battery,
                    ControllerInfoKey.TEAM: 0,
                    ControllerInfoKey.CONNECTED_AT: time.time(),
                    ControllerInfoKey.NAME: name,
                }

                # Store initial state
                self.controller_states[serial] = state

            # Add attributes to current span (this is called within "spawn_controller_process" span)
            current_span = trace.get_current_span()
            current_span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)
            current_span.set_attribute("controller.battery", battery)
            current_span.set_attribute("controller.name", name)
            current_span.add_event(
                "controller_added_to_tracking",
                {"serial": serial, "battery": battery, "name": name},
            )

            logger.info(f"Spawned tracking for controller {serial} ({name})")

            # Update metrics (Phase 38)
            metrics.active_controllers.inc()
            metrics.controller_connected.labels(serial=serial).set(1)
            metrics.controller_battery_level.labels(serial=serial).set(battery)
            # Controller info metric with human-readable name (Issue #74)
            # Use actual name from name_manager, fallback to serial suffix
            if name:
                controller_name = name
            elif len(serial) >= 4:
                controller_name = f"PS Move {serial[-4:]}"
            else:
                controller_name = serial
            metrics.controller_info.labels(serial=serial, name=controller_name).set(1)
            # Check if this is a reconnect
            if serial in self.paired_serials:
                metrics.controller_reconnect_total.labels(serial=serial).inc()

            # Note: Actual process spawning would happen here in production
            # For now, we track the controller info

        except Exception as e:
            logger.error(f"Error spawning controller process {serial}: {e}", exc_info=True)
