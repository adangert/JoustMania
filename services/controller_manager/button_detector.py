"""
Button transition detection for ControllerManager.

Detects button press/release transitions and publishes button events
to stream subscribers. Also handles connection/disconnection events.

Phase 41: Button event streaming.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from lib.controller_constants import ButtonKey, ButtonTrackingKey
from proto import controller_manager_pb2
from services.controller_manager import metrics
from services.controller_manager.event_publisher import EventPublisher

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ButtonDetector:
    """
    Detects button state transitions and publishes events.

    Tracks button states per controller and generates events when
    buttons are pressed or released.
    """

    def __init__(self, event_publisher: EventPublisher):
        """
        Initialize button detector.

        Args:
            event_publisher: EventPublisher for cross-thread event publishing
        """
        self.event_publisher = event_publisher

        # Button state tracking: {serial: {button_name: pressed}}
        self._button_states: dict[str, dict[str, bool]] = {}

        # Button event subscribers (set by servicer)
        self._subscribers: dict[str, asyncio.Queue] = {}

    @property
    def button_states(self) -> dict[str, dict[str, bool]]:
        """Get the button states dict."""
        return self._button_states

    def set_subscribers(self, subscribers: dict[str, asyncio.Queue]) -> None:
        """Set reference to button event subscribers dict."""
        self._subscribers = subscribers

    def clear_controller(self, serial: str) -> None:
        """Clear button state tracking for a controller."""
        if serial in self._button_states:
            del self._button_states[serial]

    def detect_transitions_from_state(self, serial: str, state: dict, tracked_controllers: dict) -> None:
        """
        Detect button transitions from polled state dict.

        Called from discovery loop for immediate button detection at polling frequency.
        This ensures button events are detected as fast as we poll, not limited by
        gRPC stream frequency.

        Args:
            serial: Controller serial number
            state: State dict from backend polling
            tracked_controllers: Dict of tracked controller info
        """
        if not state:
            return

        trigger = state.get(ButtonKey.TRIGGER, False)
        move = state.get(ButtonKey.MOVE, False)
        cross = state.get(ButtonKey.CROSS, False)
        circle = state.get(ButtonKey.CIRCLE, False)
        square = state.get(ButtonKey.SQUARE, False)
        triangle = state.get(ButtonKey.TRIANGLE, False)
        ps = state.get(ButtonKey.PS, False)
        select = state.get(ButtonKey.SELECT, False)
        start = state.get(ButtonKey.START, False)

        info = tracked_controllers.get(serial, {})
        self._detect_button_transitions(serial, info, trigger, move, cross, circle, square, triangle, ps, select, start)

    def _detect_button_transitions(
        self,
        serial: str,
        info: dict,
        trigger: bool,
        move: bool,
        cross: bool,
        circle: bool,
        square: bool,
        triangle: bool,
        ps: bool,
        select: bool = False,
        start: bool = False,
    ) -> None:
        """
        Detect button press/release transitions and publish button events (Phase 41).

        Args:
            serial: Controller serial number
            info: Controller info dict (for battery, color)
            trigger, move, cross, circle, square, triangle, ps, select, start: Current button states
        """
        # Initialize button state tracking for this controller if needed
        if serial not in self._button_states:
            self._button_states[serial] = {
                ButtonTrackingKey.TRIGGER: False,
                ButtonTrackingKey.MOVE: False,
                ButtonTrackingKey.CROSS: False,
                ButtonTrackingKey.CIRCLE: False,
                ButtonTrackingKey.SQUARE: False,
                ButtonTrackingKey.TRIANGLE: False,
                ButtonTrackingKey.PS: False,
                ButtonTrackingKey.SELECT: False,
                ButtonTrackingKey.START: False,
            }
            logger.info(f"Initialized button tracking for {serial} (current: move={move}, trigger={trigger})")

        prev_states = self._button_states[serial]

        current_states = {
            ButtonTrackingKey.TRIGGER: trigger,
            ButtonTrackingKey.MOVE: move,
            ButtonTrackingKey.CROSS: cross,
            ButtonTrackingKey.CIRCLE: circle,
            ButtonTrackingKey.SQUARE: square,
            ButtonTrackingKey.TRIANGLE: triangle,
            ButtonTrackingKey.PS: ps,
            ButtonTrackingKey.SELECT: select,
            ButtonTrackingKey.START: start,
        }

        # Map button names to ButtonType enum
        button_type_map = {
            ButtonTrackingKey.TRIGGER: controller_manager_pb2.BUTTON_TRIGGER,
            ButtonTrackingKey.MOVE: controller_manager_pb2.BUTTON_MOVE,
            ButtonTrackingKey.CROSS: controller_manager_pb2.BUTTON_CROSS,
            ButtonTrackingKey.CIRCLE: controller_manager_pb2.BUTTON_CIRCLE,
            ButtonTrackingKey.SQUARE: controller_manager_pb2.BUTTON_SQUARE,
            ButtonTrackingKey.TRIANGLE: controller_manager_pb2.BUTTON_TRIANGLE,
            ButtonTrackingKey.PS: controller_manager_pb2.BUTTON_PS,
            ButtonTrackingKey.SELECT: controller_manager_pb2.BUTTON_SELECT,
            ButtonTrackingKey.START: controller_manager_pb2.BUTTON_START,
        }

        # Detect transitions and create events
        events = []
        for button_name, current_pressed in current_states.items():
            prev_pressed = prev_states[button_name]

            if current_pressed != prev_pressed:
                # State changed - create event
                action = (
                    controller_manager_pb2.ACTION_PRESS if current_pressed else controller_manager_pb2.ACTION_RELEASE
                )
                button_type = button_type_map[button_name]

                event = controller_manager_pb2.ButtonEvent(
                    serial=serial,
                    timestamp=int(time.time() * 1000),
                    button=button_type,
                    action=action,
                    battery=info.get("battery", 0),
                    color=controller_manager_pb2.RGB(r=0, g=0, b=255),
                )
                events.append(event)

                # Track button event (Phase 38)
                action_str = "press" if current_pressed else "release"
                metrics.button_events_total.labels(serial=serial, button=button_name, action=action_str).inc()

                # Update tracked state
                prev_states[button_name] = current_pressed

        # Log all button states when any transition occurred
        if events:
            logger.info(
                f"Button event {serial}: T={trigger} M={move} X={cross} O={circle} []={square} /\\={triangle} PS={ps}"
            )

        # Publish events to all subscribers
        if events:
            for event in events:
                self.event_publisher.publish_to_subscribers(self._subscribers, event, "button")

    def publish_connection_event(self, serial: str, is_connect: bool, battery: int = 0) -> None:
        """
        Publish a connection or disconnection event to all button event subscribers.

        This allows the menu service to track controller connections via the same
        stream used for button events, eliminating the need for a separate polling loop.

        Args:
            serial: Controller serial number
            is_connect: True for connect, False for disconnect
            battery: Battery level (only available for connect events)
        """
        event_type = controller_manager_pb2.EVENT_CONNECT if is_connect else controller_manager_pb2.EVENT_DISCONNECT

        event = controller_manager_pb2.ButtonEvent(
            serial=serial,
            timestamp=int(time.time() * 1000),
            battery=battery,
            event_type=event_type,
            # button and action fields are left unset for connection events
        )

        self.event_publisher.publish_to_subscribers(self._subscribers, event, "connection")

        action_str = "connected" if is_connect else "disconnected"
        logger.info(f"Published connection event: {serial} {action_str}")
