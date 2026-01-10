"""
Menu gRPC Server for JoustMania

Manages menu UI and user interactions as a gRPC service:
- Start/stop menu
- Process input (button presses, web commands)
- Track menu state
- Stream menu events

This replaces the Queue-based IPC with gRPC (Phase 8a).
"""

import logging
import time
import threading
import queue
from typing import Dict
from concurrent import futures
import grpc
import grpc.aio
import asyncio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer

# Import protobuf
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.menu import menu_pb2, menu_pb2_grpc

logger = logging.getLogger(__name__)

# Initialize OpenTelemetry
def init_telemetry():
    """Initialize OpenTelemetry with OTLP exporter."""
    otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4317')
    service_name = os.getenv('OTEL_SERVICE_NAME', 'menu-service')

    resource = Resource(attributes={
        SERVICE_NAME: service_name,
        SERVICE_VERSION: "1.0.0",
        "service.namespace": "joustmania",
    })

    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    GrpcInstrumentorServer().instrument()

    logger.info(f"OpenTelemetry initialized: {service_name} -> {otlp_endpoint}")
    return trace.get_tracer(__name__)

tracer = init_telemetry()


class MenuServicer(menu_pb2_grpc.MenuServiceServicer):
    """
    Menu gRPC servicer.

    Manages menu UI and interactions:
    - Start/stop menu
    - Process input
    - Stream events
    """

    def __init__(self):
        """Initialize menu service."""
        # gRPC channel options for better performance and reliability
        channel_options = [
            # Keep-alive settings to detect dead connections
            ('grpc.keepalive_time_ms', 30000),  # Send keepalive ping every 30s
            ('grpc.keepalive_timeout_ms', 5000),  # Wait 5s for keepalive ack
            ('grpc.keepalive_permit_without_calls', True),  # Allow keepalive pings when no calls
            ('grpc.http2.max_pings_without_data', 2),  # Allow 2 pings without data

            # Connection and timeout settings
            ('grpc.initial_reconnect_backoff_ms', 1000),  # 1s initial backoff
            ('grpc.max_reconnect_backoff_ms', 5000),  # 5s max backoff

            # Message size limits (10MB for large messages)
            ('grpc.max_receive_message_length', 10 * 1024 * 1024),
            ('grpc.max_send_message_length', 10 * 1024 * 1024),
        ]

        self.state = menu_pb2.MenuState.STOPPED
        self.current_selection = "JoustFFA"
        self.ready_controller_count = 0

        # Event streaming
        self.event_subscribers: Dict[str, queue.Queue] = {}
        self.event_lock = threading.Lock()

        # Controller button monitoring (Phase 21)
        self.button_monitor_task = None
        self.button_monitor_running = False
        self.controller_button_states: Dict[str, Dict[str, bool]] = {}  # {serial: {trigger: bool, move: bool}}
        self.last_button_press_time: Dict[str, Dict[str, float]] = {}  # {serial: {button: timestamp}}
        self.channel_options = channel_options

        logger.info("Menu service initialized")

    def StartMenu(self, request, context):
        """Start the menu."""
        with tracer.start_as_current_span("StartMenu") as span:
            try:
                if self.state == menu_pb2.MenuState.RUNNING:
                    return menu_pb2.StartMenuResponse(
                        success=False,
                        error="Menu already running"
                    )

                self.state = menu_pb2.MenuState.RUNNING
                self.current_selection = "JoustFFA"
                self.ready_controller_count = 0

                # Publish menu_started event
                self._publish_event("menu_started", {})

                logger.info("Menu started")

                span.set_attribute("menu.state", "RUNNING")

                return menu_pb2.StartMenuResponse(
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"StartMenu error: {e}", exc_info=True)
                return menu_pb2.StartMenuResponse(
                    success=False,
                    error=str(e)
                )

    def StopMenu(self, request, context):
        """Stop the menu."""
        with tracer.start_as_current_span("StopMenu") as span:
            try:
                if self.state == menu_pb2.MenuState.STOPPED:
                    return menu_pb2.StopMenuResponse(
                        success=False,
                        error="Menu already stopped"
                    )

                self.state = menu_pb2.MenuState.STOPPED

                # Publish menu_stopped event
                self._publish_event("menu_stopped", {})

                logger.info("Menu stopped")

                span.set_attribute("menu.state", "STOPPED")

                return menu_pb2.StopMenuResponse(
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"StopMenu error: {e}", exc_info=True)
                return menu_pb2.StopMenuResponse(
                    success=False,
                    error=str(e)
                )

    def GetMenuStatus(self, request, context):
        """Get current menu status."""
        with tracer.start_as_current_span("GetMenuStatus") as span:
            try:
                span.set_attribute("menu.state", self.state)
                span.set_attribute("menu.selection", self.current_selection)
                span.set_attribute("menu.ready_controllers", self.ready_controller_count)

                return menu_pb2.GetMenuStatusResponse(
                    state=self.state,
                    current_selection=self.current_selection,
                    ready_controller_count=self.ready_controller_count,
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetMenuStatus error: {e}", exc_info=True)
                return menu_pb2.GetMenuStatusResponse(
                    state=menu_pb2.MenuState.STOPPED,
                    current_selection="",
                    ready_controller_count=0,
                    success=False,
                    error=str(e)
                )

    def ProcessInput(self, request, context):
        """Process menu input."""
        with tracer.start_as_current_span("ProcessInput") as span:
            span.set_attribute("input.type", request.input_type)

            try:
                input_type = request.input_type
                data = dict(request.data)

                # Handle different input types
                if input_type == "button_press":
                    button = data.get("button", "")
                    span.set_attribute("button", button)

                    if button == "trigger":
                        # Game requested
                        self.state = menu_pb2.MenuState.GAME_STARTING
                        self._publish_event("game_requested", {
                            "game_name": self.current_selection
                        })
                        logger.info(f"Game requested: {self.current_selection}")

                    elif button == "select":
                        # Move to next game (includes NonstopJoust - Phase 22 prep)
                        games = ["JoustFFA", "JoustTeams", "Tournament", "Werewolf", "NonstopJoust"]
                        current_index = games.index(self.current_selection) if self.current_selection in games else 0
                        self.current_selection = games[(current_index + 1) % len(games)]
                        self._publish_event("selection_changed", {
                            "game_name": self.current_selection
                        })
                        logger.info(f"Selection changed to: {self.current_selection}")

                elif input_type == "web_command":
                    command = data.get("command", "")
                    span.set_attribute("command", command)

                    if command == "start_game":
                        self.state = menu_pb2.MenuState.GAME_STARTING
                        self._publish_event("game_requested", {
                            "game_name": self.current_selection,
                            "source": "web"
                        })

                return menu_pb2.ProcessInputResponse(
                    success=True,
                    error=""
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"ProcessInput error: {e}", exc_info=True)
                return menu_pb2.ProcessInputResponse(
                    success=False,
                    error=str(e)
                )

    async def StreamMenuEvents(self, request, context):
        """Stream menu events in real-time (async)."""
        subscriber_id = f"menu_events_{time.time()}"

        with tracer.start_as_current_span("StreamMenuEvents") as span:
            span.set_attribute("subscriber.id", subscriber_id)

            # Create queue for this subscriber
            event_queue = queue.Queue(maxsize=100)

            with self.event_lock:
                self.event_subscribers[subscriber_id] = event_queue

            logger.info(f"New menu event subscriber: {subscriber_id}")

            try:
                while not context.cancelled():
                    try:
                        # Non-blocking get with short timeout
                        event = event_queue.get(timeout=0.1)
                        yield event

                    except queue.Empty:
                        # Yield control to event loop
                        await asyncio.sleep(0.1)
                        continue
                    except Exception as e:
                        logger.error(f"Stream error for {subscriber_id}: {e}")
                        break

            finally:
                # Cleanup
                with self.event_lock:
                    if subscriber_id in self.event_subscribers:
                        del self.event_subscribers[subscriber_id]

                logger.info(f"Menu event subscriber disconnected: {subscriber_id}")

    def _publish_event(self, event_type: str, data: Dict[str, str]):
        """Publish an event to all subscribers."""
        with tracer.start_as_current_span("publish_menu_event") as span:
            span.set_attribute("event.type", event_type)

            event = menu_pb2.MenuEvent(
                event_type=event_type,
                data=data,
                timestamp=int(time.time() * 1000)
            )

            with self.event_lock:
                subscriber_count = len(self.event_subscribers)
                span.set_attribute("subscribers.count", subscriber_count)

                for sub_id, event_queue in self.event_subscribers.items():
                    try:
                        event_queue.put_nowait(event)
                        logger.debug(f"Published {event_type} to subscriber {sub_id}")
                    except queue.Full:
                        logger.warning(f"Subscriber {sub_id} queue full, skipping event")
                    except Exception as e:
                        logger.error(f"Error publishing to subscriber {sub_id}: {e}")

    async def start_button_monitor(self):
        """Start the controller button monitoring task (Phase 21)."""
        if not self.button_monitor_running:
            self.button_monitor_running = True
            self.button_monitor_task = asyncio.create_task(self._button_monitor_loop())
            logger.info("Controller button monitor started")

    async def stop_button_monitor(self):
        """Stop the controller button monitoring task."""
        self.button_monitor_running = False
        if self.button_monitor_task:
            self.button_monitor_task.cancel()
            try:
                await self.button_monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("Controller button monitor stopped")

    async def _button_monitor_loop(self):
        """Monitor controller buttons and trigger menu actions (Phase 21)."""
        with tracer.start_as_current_span("button_monitor_loop"):
            try:
                # Import controller_manager protobuf
                from services.controller_manager import controller_manager_pb2, controller_manager_pb2_grpc

                # Connect to Controller Manager
                channel = grpc.aio.insecure_channel(
                    'controller-manager:50052',
                    options=self.channel_options
                )
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

                logger.info("Button monitor connected to Controller Manager")

                # Stream controller states at 30Hz (enough for button detection)
                stream_request = controller_manager_pb2.StreamRequest(update_frequency_hz=30)

                async for update in stub.StreamControllerStates(stream_request):
                    if not self.button_monitor_running:
                        break

                    # Only process buttons when menu is running
                    if self.state == menu_pb2.MenuState.RUNNING:
                        for controller in update.controllers:
                            await self._process_button_state(controller)

                await channel.close()

            except asyncio.CancelledError:
                logger.info("Button monitor task cancelled")
                raise
            except Exception as e:
                logger.error(f"Button monitor error: {e}", exc_info=True)

    async def _process_button_state(self, controller):
        """
        Detect button press transitions and trigger menu actions (Phase 21).

        Args:
            controller: ControllerState protobuf message
        """
        serial = controller.serial
        current_time = time.time()

        # Initialize state tracking for this controller
        if serial not in self.controller_button_states:
            self.controller_button_states[serial] = {
                'trigger': False,
                'move': False
            }
            self.last_button_press_time[serial] = {}

        prev_state = self.controller_button_states[serial]

        # Detect trigger press (False → True) - starts game
        if controller.trigger_pressed and not prev_state['trigger']:
            if self._should_process_button(serial, 'trigger', current_time):
                await self._handle_trigger_press(serial)

        # Detect move press (False → True) - cycles through games (SELECT)
        if controller.move_pressed and not prev_state['move']:
            if self._should_process_button(serial, 'move', current_time):
                await self._handle_select_press(serial)

        # Update state
        prev_state['trigger'] = controller.trigger_pressed
        prev_state['move'] = controller.move_pressed

    def _should_process_button(self, serial: str, button: str, current_time: float) -> bool:
        """
        Check if button press should be processed (debouncing).

        Args:
            serial: Controller serial number
            button: Button name ('trigger' or 'move')
            current_time: Current timestamp

        Returns:
            True if button press should be processed, False if debouncing
        """
        last_press = self.last_button_press_time[serial].get(button, 0)
        if current_time - last_press < 0.2:  # 200ms debounce
            return False
        self.last_button_press_time[serial][button] = current_time
        return True

    async def _handle_trigger_press(self, serial: str):
        """
        Handle trigger button press - start game (Phase 21).

        Args:
            serial: Controller serial number
        """
        with tracer.start_as_current_span("handle_trigger_press") as span:
            span.set_attribute("controller.serial", serial)
            span.set_attribute("game.name", self.current_selection)

            self.state = menu_pb2.MenuState.GAME_STARTING
            self._publish_event("game_requested", {
                "game_name": self.current_selection,
                "source": "controller",
                "serial": serial
            })
            logger.info(f"Game requested via controller {serial}: {self.current_selection}")

    async def _handle_select_press(self, serial: str):
        """
        Handle select button press - cycle games (Phase 21).

        Args:
            serial: Controller serial number
        """
        with tracer.start_as_current_span("handle_select_press") as span:
            span.set_attribute("controller.serial", serial)

            # Game list includes NonstopJoust (Phase 22 prep)
            games = ["JoustFFA", "JoustTeams", "Tournament", "Werewolf", "NonstopJoust"]
            current_index = games.index(self.current_selection) if self.current_selection in games else 0
            self.current_selection = games[(current_index + 1) % len(games)]

            span.set_attribute("game.name", self.current_selection)

            self._publish_event("selection_changed", {
                "game_name": self.current_selection,
                "source": "controller",
                "serial": serial
            })
            logger.info(f"Selection changed via controller {serial}: {self.current_selection}")


async def serve(port=50054):
    """Start the Menu gRPC server."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create server
    server = grpc.aio.server()

    # Add servicer
    menu_servicer = MenuServicer()
    menu_pb2_grpc.add_MenuServiceServicer_to_server(menu_servicer, server)

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the Menu service as SERVING
    await health_servicer.set("menu.MenuService", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # Overall health

    # Bind to port
    server.add_insecure_port(f'[::]:{port}')

    # Start server
    logger.info(f"Starting Menu gRPC server on port {port}")
    await server.start()

    # Start controller button monitoring (Phase 21)
    await menu_servicer.start_button_monitor()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Menu server...")
        await menu_servicer.stop_button_monitor()
        await server.stop(grace=5)


if __name__ == '__main__':
    asyncio.run(serve())
