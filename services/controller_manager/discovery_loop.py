"""
Discovery loop for ControllerManager.

Async task that handles:
- Controller discovery and tracking
- Battery monitoring
- State polling at fixed intervals
- LED updates

Uses asyncio.to_thread() for blocking USB I/O operations to avoid
blocking the main event loop.

Note: RSSI monitoring is handled by the host pairing-daemon which has
direct access to hcitool for reliable signal strength readings.
"""

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

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
    from services.controller_manager.backend import ControllerBackend
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
    Async discovery task for controller management.

    Handles controller discovery, state polling, battery monitoring,
    and LED updates as an async task on the main event loop.

    Uses fixed interval scheduling for consistent timing and
    asyncio.to_thread() for blocking USB I/O operations.
    """

    def __init__(
        self,
        backend: "ControllerBackend",
        tracked_controllers: dict[str, dict],
        controller_states: dict[str, dict],
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
        self.button_detector = button_detector
        self.state_cache_manager = state_cache_manager
        self.feedback_manager = feedback_manager
        self.monitoring = monitoring
        self.rescan_timer = rescan_timer
        self.paired_serials = paired_serials
        self.base_colors = base_colors
        self.event_publisher = event_publisher
        self.name_manager = name_manager

        # Discovery task state
        self.running = True
        self.backend_initialized = False
        self._task: asyncio.Task | None = None
        self._initialized_event: asyncio.Event | None = None

        # LED update timing (Phase 72: separated from polling)
        self._last_led_update = 0.0

        # Fixed interval polling configuration - always 100Hz
        # There's always either a menu or game stream active, so no need for idle mode
        self._poll_interval = 0.010  # 100Hz

        # Activity tracking for metrics
        self._last_activity_time: dict[str, float] = {}
        self._previous_accel: dict[str, tuple[float, float, float]] = {}
        self._idle_threshold_seconds = 5.0
        self._accel_movement_threshold = 0.05

        # Debug logging throttle
        self._last_controller_count_log = 0.0

    def start(self) -> None:
        """Start the discovery task.

        Must be called from an async context (after event loop is running).
        """
        self._initialized_event = asyncio.Event()
        self._task = asyncio.create_task(self._discovery_loop())
        logger.info("Discovery loop started as async task")

    async def wait_initialized(self, timeout_seconds: float = 10.0) -> bool:
        """Wait for the backend to be initialized.

        Args:
            timeout_seconds: Maximum time to wait for initialization.

        Returns:
            True if initialized successfully, False if timed out or failed.
        """
        if self._initialized_event is None:
            return False
        try:
            await asyncio.wait_for(self._initialized_event.wait(), timeout=timeout_seconds)
            return self.backend_initialized
        except TimeoutError:
            logger.error(f"Backend initialization timed out after {timeout_seconds}s")
            return False

    def stop(self) -> None:
        """Stop the discovery loop."""
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def wait_stopped(self, timeout_seconds: float | None = None) -> None:
        """Wait for the discovery task to complete."""
        if self._task:
            with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout_seconds)

    async def _discovery_loop(self) -> None:
        """
        Async task for controller discovery and battery monitoring.

        Uses fixed interval scheduling for consistent timing:
        - Gameplay mode (streams active): 100Hz polling for fast button detection
        - Idle mode (no streams): 10Hz polling to save resources

        Blocking USB I/O operations are run via asyncio.to_thread() to avoid
        blocking the main event loop.

        Phase 56: Event-driven spans - Only creates spans for actual events (controller connected),
        not for routine polling. Metrics track polling operations.
        Phase 57: Uses backend abstraction for platform independence.
        """
        try:
            # Initialize backend
            self.backend_initialized = await self.backend.initialize()
            if not self.backend_initialized:
                logger.error("Backend initialization failed - discovery loop will not run")
                if self._initialized_event:
                    self._initialized_event.set()  # Signal even on failure so waiters don't hang
                return
            logger.info("Backend initialized successfully")
            if self._initialized_event:
                self._initialized_event.set()
        except Exception as e:
            logger.error(f"Failed to initialize backend: {e}", exc_info=True)
            if self._initialized_event:
                self._initialized_event.set()  # Signal even on failure so waiters don't hang
            return

        # Fixed interval scheduling
        next_poll_time = time.monotonic()

        while self.running:
            try:
                current_time = time.time()

                # Fixed 100Hz polling - there's always either a menu or game stream active
                poll_interval = self._poll_interval

                # Update polling metrics
                metrics.polling_mode.set(1)  # Always in "gameplay mode" now
                metrics.polling_target_hz.set(100)

                # Check for new controllers (metrics, no span)
                # Run in thread pool since get_connected_controllers() has blocking USB calls
                with metrics.discovery_check_duration_seconds.time():
                    await self._check_for_new_controllers()
                    metrics.discovery_checks_total.inc()

                # Update controller states from backend
                await self._update_controller_states()

                # Check battery levels every 30 seconds (Phase 39 - Task 4, Phase 70)
                # Note: Battery display/warnings moved to menu service (Phase 70)
                if current_time - self.monitoring.last_battery_check >= 30.0:
                    with metrics.battery_check_duration_seconds.time():
                        self.monitoring.check_battery_levels(self.tracked_controllers)
                        metrics.battery_checks_total.inc()
                    self.monitoring.last_battery_check = current_time

                # Phase 72: Update LEDs at 20Hz (every 50ms) - separated from polling
                if current_time - self._last_led_update >= 0.05:
                    # Run in thread pool since update_all_leds() has blocking USB calls
                    updated_count = await asyncio.to_thread(self.backend.update_all_leds)
                    self._last_led_update = current_time
                    # Track LED batch update efficiency
                    metrics.led_batch_updates_total.inc()
                    metrics.led_controllers_updated_per_batch.observe(updated_count)

                # Fixed interval sleep - precise timing using monotonic clock
                next_poll_time += poll_interval
                sleep_time = next_poll_time - time.monotonic()

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                else:
                    # Behind schedule - reset to avoid spiral
                    next_poll_time = time.monotonic()

            except asyncio.CancelledError:
                logger.info("Discovery loop cancelled")
                break
            except Exception as e:
                logger.error(f"Discovery loop error: {e}", exc_info=True)
                await asyncio.sleep(5.0)

    async def _check_for_new_controllers(self) -> None:
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
            # Run in thread pool since this has blocking USB calls
            connected_serials = await asyncio.to_thread(self.backend.get_connected_controllers, force_rescan)
            connected_set = set(connected_serials)

            # Check for disconnected controllers (in tracked but not in connected)
            tracked_serials = set(self.tracked_controllers.keys())

            disconnected_serials = tracked_serials - connected_set
            for serial in disconnected_serials:
                logger.info(f"Controller {serial} disconnected - cleaning up server tracking")
                # Capture name before removing from tracked_controllers
                name = ""
                if serial in self.tracked_controllers:
                    name = self.tracked_controllers[serial].get(ControllerInfoKey.NAME, "")
                    del self.tracked_controllers[serial]
                if serial in self.controller_states:
                    del self.controller_states[serial]
                self.state_cache_manager.clear_controller(serial)
                self.button_detector.clear_controller(serial)
                # Note: Keep base_colors[serial] so we can restore on reconnect!
                # Activity tracking cleanup
                self._last_activity_time.pop(serial, None)
                self._previous_accel.pop(serial, None)
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
                            await self._spawn_controller_process(serial)

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
                            await self.feedback_manager.set_controller_color(serial, color)

        except Exception as e:
            logger.error(f"Error discovering controllers: {e}", exc_info=True)

    async def _update_controller_states(self) -> None:
        """
        Update states for all tracked controllers from backend.

        Polls all controllers in parallel using asyncio.gather().
        Called at fixed intervals (100Hz gameplay, 10Hz idle) for consistent timing.
        """
        if not self.backend_initialized:
            return

        try:
            # Get list of serials
            all_serials = list(self.tracked_controllers.keys())

            if not all_serials:
                return

            current_time = time.time()

            # Count active vs idle controllers for metrics (based on recent activity)
            active_count = 0
            idle_count = 0
            for serial in all_serials:
                last_activity = self._last_activity_time.get(serial, current_time)
                is_idle = (current_time - last_activity) > self._idle_threshold_seconds
                if is_idle:
                    idle_count += 1
                else:
                    active_count += 1

            # Update activity metrics
            metrics.adaptive_polling_active_controllers.set(active_count)
            metrics.adaptive_polling_idle_controllers.set(idle_count)

            # Debug: Log tracked controller count periodically (every 5 seconds)
            if current_time - self._last_controller_count_log >= 5.0:
                logger.info(
                    f"Polling {len(all_serials)} controllers at 100Hz, active={active_count}, idle={idle_count}"
                )
                self._last_controller_count_log = current_time

            # Parallel polling - read all controllers concurrently
            start_time = time.time()

            # Gather all states in parallel
            coros = [self.backend.get_controller_state(serial) for serial in all_serials]
            results = await asyncio.gather(*coros, return_exceptions=True)

            # Record metrics
            poll_duration = time.time() - start_time
            metrics.poll_batch_duration_seconds.observe(poll_duration)
            metrics.poll_batch_size.observe(len(all_serials))

            # Process all results
            for serial, state in zip(all_serials, results, strict=False):
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

                # Track activity for metrics
                self._update_activity_tracking(serial, state, current_time)

        except Exception as e:
            logger.error(f"Error updating controller states: {e}", exc_info=True)

    def _update_activity_tracking(self, serial: str, state: dict, current_time: float) -> None:
        """
        Update activity tracking for adaptive polling.

        Activity is detected when:
        - Any button is pressed
        - Accelerometer values change significantly (movement detected)

        Issue #62: Also records acceleration metrics for 100Hz visualization.
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
        if StateKey.ACCEL in state:
            accel = state[StateKey.ACCEL]
            ax = accel.get(AxisKey.X, 0)
            ay = accel.get(AxisKey.Y, 0)
            az = accel.get(AxisKey.Z, 0)
            current_accel = (ax, ay, az)

            # Issue #62: Record acceleration metrics for 100Hz visualization
            # Calculate magnitude for easier threshold-based alerts
            import math

            magnitude = math.sqrt(ax * ax + ay * ay + az * az)
            metrics.controller_accel_magnitude.labels(serial=serial).set(magnitude)
            metrics.controller_accel_x.labels(serial=serial).set(ax)
            metrics.controller_accel_y.labels(serial=serial).set(ay)
            metrics.controller_accel_z.labels(serial=serial).set(az)

            prev_accel = self._previous_accel.get(serial)
            if prev_accel and not activity_detected:
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

    async def _spawn_controller_process(self, serial: str) -> None:
        """
        Start tracking a newly connected controller.

        Phase 57: Simplified to use backend for state tracking.
        """
        try:
            # Get initial state from backend
            state = await self.backend.get_controller_state(serial)

            if not state:
                logger.error(f"Failed to get initial state for controller {serial}")
                return

            battery = state.get(StateKey.BATTERY, 5)

            # Issue #7: Get human-readable name for controller
            name = ""
            if self.name_manager:
                name = self.name_manager.get_name(serial)

            # Track controller
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

            logger.info(f"Started tracking controller {serial} ({name})")

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

        except Exception as e:
            logger.error(f"Error starting controller tracking {serial}: {e}", exc_info=True)
