"""
Menu gRPC Server for JoustMania

Manages the game selection menu and lobby experience:
- Game mode selection and cycling
- Controller lobby state (connected/ready)
- LED feedback based on game mode and player state
- Admin mode for in-game configuration
- Real-time event streaming for UI updates

See services/menu/README.md for full documentation.
"""

import asyncio
import logging
import os

# Import protobuf
import sys
import time

import grpc
import grpc.aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import contextlib

import psutil

# Prometheus metrics (Phase 38)
from prometheus_client import start_http_server

from proto import menu_pb2, menu_pb2_grpc
from services.menu import metrics

logger = logging.getLogger(__name__)


# Initialize OpenTelemetry
def init_telemetry():
    """Initialize OpenTelemetry with OTLP exporter."""
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    service_name = os.getenv("OTEL_SERVICE_NAME", "menu-service")

    resource = Resource(
        attributes={
            SERVICE_NAME: service_name,
            SERVICE_VERSION: "1.0.0",
            "service.namespace": "joustmania",
        }
    )

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
        """Initialize menu service (Phase 33 - using shared gRPC utilities)."""
        self.state = menu_pb2.MenuState.STOPPED
        self.current_selection = "JoustFFA"
        self.ready_controller_count = 0

        # Event streaming (Phase 34: async queue and lock)
        self.event_subscribers: dict[str, asyncio.Queue] = {}
        self.event_lock = asyncio.Lock()

        # Controller button monitoring (Phase 21)
        self.button_monitor_task = None
        self.button_monitor_running = False
        self.controller_button_states: dict[str, dict[str, bool]] = {}  # {serial: {trigger: bool, move: bool, ...}}
        self.last_button_press_time: dict[str, dict[str, float]] = {}  # {serial: {button: timestamp}}

        # Lobby state feedback (Phase 39)
        self.ready_controllers: set[str] = set()  # Controllers with trigger pressed (ready)
        self.connected_controllers: set[str] = set()  # All connected controllers
        self.controller_lobby_state: dict[str, str] = {}  # {serial: "connected"|"ready"|"admin"}
        self.last_lobby_feedback_update: dict[str, float] = {}  # {serial: timestamp}

        # Admin mode state (Phase 23)
        self.admin_mode_active = False
        self.admin_mode_controller = None  # Serial of controller that activated admin mode
        self.admin_mode_entry_time = 0
        self.admin_combo_shown = False  # Track if we've shown combo feedback

        # Admin mode option navigation (Phase 23 - enhanced)
        self.admin_current_option = 0  # 0=num_teams, 1=force_all_start
        self.admin_option_names = ["num_teams", "force_all_start"]
        self.admin_option_colors = [
            (0, 100, 255),  # Light blue for num_teams
            (150, 0, 255),  # Purple for force_all_start
        ]

        # Persistent gRPC channels (Phase 26 - Performance, Phase 33 - shared utilities)
        # Create channels once and reuse throughout service lifecycle
        # Use environment variables for service addresses (supports mock environment)
        from lib.grpc_utils import create_channel

        controller_host = os.getenv("CONTROLLER_MANAGER_HOST", "controller-manager")
        controller_port = os.getenv("CONTROLLER_MANAGER_PORT", "50052")
        settings_host = os.getenv("SETTINGS_HOST", "settings")
        settings_port = os.getenv("SETTINGS_PORT", "50051")
        game_coordinator_host = os.getenv("GAME_COORDINATOR_HOST", "game-coordinator")
        game_coordinator_port = os.getenv("GAME_COORDINATOR_PORT", "50053")
        audio_host = os.getenv("AUDIO_HOST", "audio")
        audio_port = os.getenv("AUDIO_PORT", "50056")

        self.controller_channel = create_channel(f"{controller_host}:{controller_port}")
        self.settings_channel = create_channel(f"{settings_host}:{settings_port}")
        self.game_coordinator_channel = create_channel(f"{game_coordinator_host}:{game_coordinator_port}")
        self.audio_channel = create_channel(f"{audio_host}:{audio_port}")

        # Phase 60: Voice actor setting (aaron or ivy)
        self.voice_actor = "aaron"

        logger.info("Menu service initialized with persistent gRPC channels")

    async def StartMenu(self, request, context):
        """Start the menu (Phase 34: async for _publish_event)."""
        start_time = time.time()
        with tracer.start_as_current_span("StartMenu") as span:
            try:
                if self.state == menu_pb2.MenuState.RUNNING:
                    metrics.grpc_requests_total.labels(method="StartMenu", status="already_running").inc()
                    return menu_pb2.StartMenuResponse(success=False, error="Menu already running")

                self.state = menu_pb2.MenuState.RUNNING
                self.current_selection = "JoustFFA"
                self.ready_controller_count = 0

                # Phase 60: Load voice actor preference
                await self._load_voice_actor_setting()

                # Publish menu_started event (Phase 34: await)
                await self._publish_event("menu_started", {})

                logger.info("Menu started")

                span.set_attribute("menu.state", "RUNNING")
                metrics.grpc_requests_total.labels(method="StartMenu", status="ok").inc()

                return menu_pb2.StartMenuResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"StartMenu error: {e}", exc_info=True)
                metrics.grpc_requests_total.labels(method="StartMenu", status="error").inc()
                return menu_pb2.StartMenuResponse(success=False, error=str(e))
            finally:
                metrics.grpc_request_duration_seconds.labels(method="StartMenu").observe(time.time() - start_time)

    async def StopMenu(self, request, context):
        """Stop the menu (Phase 34: async for _publish_event)."""
        start_time = time.time()
        with tracer.start_as_current_span("StopMenu") as span:
            try:
                if self.state == menu_pb2.MenuState.STOPPED:
                    metrics.grpc_requests_total.labels(method="StopMenu", status="already_stopped").inc()
                    return menu_pb2.StopMenuResponse(success=False, error="Menu already stopped")

                self.state = menu_pb2.MenuState.STOPPED

                # Phase 39: Clear lobby feedback state
                self.ready_controllers.clear()
                self.connected_controllers.clear()
                self.controller_lobby_state.clear()
                self.last_lobby_feedback_update.clear()
                self.ready_controller_count = 0

                # Publish menu_stopped event (Phase 34: await)
                await self._publish_event("menu_stopped", {})

                logger.info("Menu stopped")

                span.set_attribute("menu.state", "STOPPED")
                metrics.grpc_requests_total.labels(method="StopMenu", status="ok").inc()

                return menu_pb2.StopMenuResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"StopMenu error: {e}", exc_info=True)
                metrics.grpc_requests_total.labels(method="StopMenu", status="error").inc()
                return menu_pb2.StopMenuResponse(success=False, error=str(e))
            finally:
                metrics.grpc_request_duration_seconds.labels(method="StopMenu").observe(time.time() - start_time)

    async def GetMenuStatus(self, request, context):
        """Get current menu status (Phase 58: converted to async for consistency)."""
        start_time = time.time()
        with tracer.start_as_current_span("GetMenuStatus") as span:
            try:
                span.set_attribute("menu.state", self.state)
                span.set_attribute("menu.selection", self.current_selection)
                span.set_attribute("menu.ready_controllers", self.ready_controller_count)
                metrics.grpc_requests_total.labels(method="GetMenuStatus", status="ok").inc()

                return menu_pb2.GetMenuStatusResponse(
                    state=self.state,
                    current_selection=self.current_selection,
                    ready_controller_count=self.ready_controller_count,
                    success=True,
                    error="",
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"GetMenuStatus error: {e}", exc_info=True)
                metrics.grpc_requests_total.labels(method="GetMenuStatus", status="error").inc()
                return menu_pb2.GetMenuStatusResponse(
                    state=menu_pb2.MenuState.STOPPED,
                    current_selection="",
                    ready_controller_count=0,
                    success=False,
                    error=str(e),
                )
            finally:
                metrics.grpc_request_duration_seconds.labels(method="GetMenuStatus").observe(time.time() - start_time)

    async def ProcessInput(self, request, context):
        """Process menu input (Phase 34: async for _publish_event)."""
        start_time = time.time()
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
                        await self._publish_event("game_requested", {"game_name": self.current_selection})
                        logger.info(f"Game requested: {self.current_selection}")

                    elif button == "select":
                        # Move to next game (Phase 59: use GAME_MODES constant)
                        current_index = self.GAME_MODES.index(self.current_selection) if self.current_selection in self.GAME_MODES else 0
                        self.current_selection = self.GAME_MODES[(current_index + 1) % len(self.GAME_MODES)]
                        await self._publish_event("selection_changed", {"game_name": self.current_selection})
                        logger.info(f"Selection changed to: {self.current_selection}")

                elif input_type == "web_command":
                    command = data.get("command", "")
                    span.set_attribute("command", command)

                    if command == "start_game":
                        self.state = menu_pb2.MenuState.GAME_STARTING
                        await self._publish_event(
                            "game_requested", {"game_name": self.current_selection, "source": "web"}
                        )

                    # Phase 59: Add select_game command for web UI
                    elif command == "select_game":
                        game_name = data.get("game_name", "")
                        if game_name in self.GAME_MODES:
                            self.current_selection = game_name
                            await self._publish_event(
                                "selection_changed", {"game_name": game_name, "source": "web"}
                            )
                            # Phase 60: Play game mode voice announcement
                            voice_file = self.GAME_MODE_VOICE.get(game_name)
                            if voice_file:
                                await self._play_voice(voice_file)
                            # Clear lobby state to trigger color update on next frame
                            self.controller_lobby_state.clear()
                            self.last_lobby_feedback_update.clear()
                            logger.info(f"Game selected via web: {game_name}")
                        else:
                            logger.warning(f"Unknown game mode requested via web: {game_name}")

                # Phase 58: Handle menu reset (recover from GAME_STARTING if game fails to start)
                elif input_type == "reset_menu":
                    if self.state == menu_pb2.MenuState.GAME_STARTING:
                        self.state = menu_pb2.MenuState.RUNNING
                        await self._publish_event("game_start_cancelled", {})
                        logger.info("Menu reset to RUNNING state (game start cancelled)")

                metrics.grpc_requests_total.labels(method="ProcessInput", status="ok").inc()
                return menu_pb2.ProcessInputResponse(success=True, error="")

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"ProcessInput error: {e}", exc_info=True)
                metrics.grpc_requests_total.labels(method="ProcessInput", status="error").inc()
                return menu_pb2.ProcessInputResponse(success=False, error=str(e))
            finally:
                metrics.grpc_request_duration_seconds.labels(method="ProcessInput").observe(time.time() - start_time)

    async def StreamMenuEvents(self, request, context):
        """
        Stream menu events in real-time (async).
        Phase 34: Converted to asyncio.Queue.
        Phase 59: Added connection metrics.
        """
        subscriber_id = f"menu_events_{time.time()}"
        metrics.stream_connections_active.inc()  # Phase 59: Track active connections

        with tracer.start_as_current_span("StreamMenuEvents") as span:
            span.set_attribute("subscriber.id", subscriber_id)

            # Create queue for this subscriber (Phase 34: asyncio.Queue)
            event_queue = asyncio.Queue(maxsize=100)

            async with self.event_lock:  # Phase 34: async lock
                self.event_subscribers[subscriber_id] = event_queue

            logger.info(f"New menu event subscriber: {subscriber_id}")

            try:
                while not context.cancelled():
                    try:
                        # Phase 34: async wait with timeout
                        event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                        yield event

                    except TimeoutError:  # Phase 34: asyncio exception
                        # Keep connection alive
                        continue
                    except Exception as e:
                        logger.error(f"Stream error for {subscriber_id}: {e}")
                        break

            finally:
                # Cleanup (Phase 34: async lock)
                async with self.event_lock:
                    if subscriber_id in self.event_subscribers:
                        del self.event_subscribers[subscriber_id]

                metrics.stream_connections_active.dec()  # Phase 59: Decrement on disconnect
                logger.info(f"Menu event subscriber disconnected: {subscriber_id}")

    async def _publish_event(self, event_type: str, data: dict[str, str]):
        """Publish an event to all subscribers (Phase 34: async, Phase 59: metrics)."""
        metrics.stream_events_published_total.labels(event_type=event_type).inc()  # Phase 59

        with tracer.start_as_current_span("publish_menu_event") as span:
            span.set_attribute("event.type", event_type)

            event = menu_pb2.MenuEvent(event_type=event_type, data=data, timestamp=int(time.time() * 1000))

            async with self.event_lock:  # Phase 34: async lock
                subscriber_count = len(self.event_subscribers)
                span.set_attribute("subscribers.count", subscriber_count)

                for sub_id, event_queue in self.event_subscribers.items():
                    try:
                        event_queue.put_nowait(event)
                        logger.debug(f"Published {event_type} to subscriber {sub_id}")
                    except asyncio.QueueFull:  # Phase 34: asyncio exception
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
            with contextlib.suppress(asyncio.CancelledError):
                await self.button_monitor_task
            logger.info("Controller button monitor stopped")

    async def shutdown(self):
        """Cleanup resources on shutdown (Phase 26, Phase 60)."""
        logger.info("Shutting down Menu service, closing gRPC channels...")
        await self.controller_channel.close()
        await self.settings_channel.close()
        await self.game_coordinator_channel.close()
        await self.audio_channel.close()
        logger.info("Menu service gRPC channels closed")

    # Phase 60: Audio feedback helpers
    async def _play_sound(self, file_path: str, volume: float = 0.8):
        """
        Play a sound effect via the audio service (fire-and-forget).

        Args:
            file_path: Path to audio file (relative to /app/services/audio/assets/)
            volume: Volume level 0.0-1.0
        """
        try:
            from proto import audio_pb2, audio_pb2_grpc

            stub = audio_pb2_grpc.AudioServiceStub(self.audio_channel)
            await stub.PlaySound(
                audio_pb2.PlaySoundRequest(
                    file_path=f"/app/services/audio/assets/{file_path}",
                    volume=volume,
                    priority=audio_pb2.AudioPriority.HIGH,
                )
            )
            logger.debug(f"Played sound: {file_path}")
        except Exception as e:
            logger.debug(f"Could not play sound {file_path}: {e}")

    async def _play_voice(self, voice_file: str, volume: float = 0.9):
        """
        Play a voice announcement.

        Args:
            voice_file: Voice file name (without path, e.g., "instructions_on.wav")
            volume: Volume level 0.0-1.0
        """
        await self._play_sound(f"Menu/vox/{self.voice_actor}/{voice_file}", volume)

    async def _load_voice_actor_setting(self):
        """
        Load voice actor preference from settings service (Phase 60).

        Updates self.voice_actor to "aaron" or "ivy".
        """
        try:
            from proto import settings_pb2, settings_pb2_grpc

            stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
            response = await stub.GetSetting(settings_pb2.GetSettingRequest(key="voice_actor"))
            if response.value in ("aaron", "ivy"):
                self.voice_actor = response.value
                logger.info(f"Voice actor set to: {self.voice_actor}")
            else:
                logger.debug(f"Voice actor setting not found or invalid, using default: {self.voice_actor}")
        except Exception as e:
            logger.debug(f"Could not load voice actor setting: {e}, using default: {self.voice_actor}")

    async def _handle_controller_disconnect(self, serial: str):
        """
        Clean up state for a disconnected controller (Phase 58).

        Args:
            serial: Controller serial number
        """
        self.connected_controllers.discard(serial)
        self.ready_controllers.discard(serial)
        self.controller_button_states.pop(serial, None)
        self.last_button_press_time.pop(serial, None)
        self.controller_lobby_state.pop(serial, None)
        self.last_lobby_feedback_update.pop(serial, None)

        # Update ready count
        self.ready_controller_count = len(self.ready_controllers)

        # If admin mode controller disconnected, exit admin mode
        if self.admin_mode_active and serial == self.admin_mode_controller:
            logger.info(f"Admin mode controller {serial} disconnected, exiting admin mode")
            self.admin_mode_active = False
            self.admin_mode_controller = None
            self.admin_mode_entry_time = 0

        logger.info(f"Controller {serial} disconnected, state cleaned up")

    async def _button_monitor_loop(self):
        """
        Monitor controller buttons and trigger menu actions (Phase 21).

        Phase 56: Event-driven spans - Creates spans only for user button actions (trigger press,
        move press, admin mode), not for routine frame processing. Metrics track polling operations.
        Phase 58: Added automatic reconnection with exponential backoff.
        """
        # Import controller_manager protobuf
        from proto import (
            controller_manager_pb2,
            controller_manager_pb2_grpc,
        )

        retry_delay = 1.0
        max_retry_delay = 30.0

        while self.button_monitor_running:
            try:
                # Use persistent channel (Phase 26)
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                logger.info("Button monitor connected to Controller Manager")
                retry_delay = 1.0  # Reset delay on successful connection

                # Stream controller states at 30Hz (enough for button detection)
                stream_request = controller_manager_pb2.StreamRequest(update_frequency_hz=30)

                async for update in stub.StreamControllerStates(stream_request):
                    if not self.button_monitor_running:
                        return

                    # Track frame processing via metrics (no span for routine polling)
                    metrics.button_frames_processed_total.inc()

                    # Phase 58: Detect disconnected controllers
                    current_serials = {c.serial for c in update.controllers}
                    disconnected = self.connected_controllers - current_serials
                    for serial in disconnected:
                        await self._handle_controller_disconnect(serial)

                    # Only process buttons when menu is running
                    if self.state == menu_pb2.MenuState.RUNNING:
                        for controller in update.controllers:
                            await self._process_button_state(controller)
                            # Phase 39: Update lobby feedback for this controller
                            await self._update_lobby_feedback(controller, stub)
                            metrics.lobby_updates_total.inc()

                # Stream ended normally (server closed connection)
                if self.button_monitor_running:
                    logger.warning("Controller state stream ended, reconnecting...")

            except asyncio.CancelledError:
                logger.info("Button monitor task cancelled")
                raise
            except Exception as e:
                if not self.button_monitor_running:
                    return
                logger.error(f"Button monitor error: {e}, reconnecting in {retry_delay:.1f}s")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

    async def _process_button_state(self, controller):
        """
        Detect button press transitions and trigger menu actions (Phase 21 & 23).

        Args:
            controller: ControllerState protobuf message
        """
        serial = controller.serial
        current_time = time.time()

        # Initialize state tracking for this controller
        if serial not in self.controller_button_states:
            self.controller_button_states[serial] = {
                "trigger": False,
                "move": False,
                "cross": False,
                "circle": False,
                "square": False,
                "triangle": False,
                "ps": False,
            }
            self.last_button_press_time[serial] = {}

        prev_state = self.controller_button_states[serial]

        # Phase 23: Check for admin mode combo (all 4 front buttons)
        if self._check_admin_mode_combo(controller):
            if not self.admin_combo_shown:  # Only trigger once per combo
                await self._enter_admin_mode(serial)
                self.admin_combo_shown = True
        else:
            self.admin_combo_shown = False

        # Phase 23: Process admin mode commands if active
        if self.admin_mode_active and serial == self.admin_mode_controller:
            # Phase 58: Check for admin mode timeout (60 seconds)
            if current_time - self.admin_mode_entry_time > 60:
                logger.info("Admin mode timed out after 60 seconds")
                await self._exit_admin_mode()
                return

            await self._process_admin_commands(controller, prev_state, current_time)
            # Update all button states
            prev_state["trigger"] = controller.trigger_pressed
            prev_state["move"] = controller.move_pressed
            prev_state["cross"] = controller.cross_pressed
            prev_state["circle"] = controller.circle_pressed
            prev_state["square"] = controller.square_pressed
            prev_state["triangle"] = controller.triangle_pressed
            prev_state["ps"] = controller.ps_pressed
            return

        # Normal menu mode: Detect trigger press (False → True) - starts game
        if (
            controller.trigger_pressed
            and not prev_state["trigger"]
            and self._should_process_button(serial, "trigger", current_time)
        ):
            await self._handle_trigger_press(serial)

        # Normal menu mode: Detect move press (False → True) - cycles through games (SELECT)
        if (
            controller.move_pressed
            and not prev_state["move"]
            and self._should_process_button(serial, "move", current_time)
        ):
            await self._handle_select_press(serial)

        # Update all button states
        prev_state["trigger"] = controller.trigger_pressed
        prev_state["move"] = controller.move_pressed
        prev_state["cross"] = controller.cross_pressed
        prev_state["circle"] = controller.circle_pressed
        prev_state["square"] = controller.square_pressed
        prev_state["triangle"] = controller.triangle_pressed
        prev_state["ps"] = controller.ps_pressed

    # Game modes available in the menu (Phase 59: single source of truth)
    GAME_MODES = ["JoustFFA", "JoustTeams", "Tournament", "Werewolf", "NonstopJoust"]

    # Game mode voice announcements (Phase 60)
    GAME_MODE_VOICE = {
        "JoustFFA": "menu Joust FFA.wav",
        "JoustTeams": "menu Joust Teams.wav",
        "Tournament": "menu Tournament.wav",
        "Werewolf": "menu Werewolves.wav",
        "NonstopJoust": "menu NonStopJoust.wav",
    }

    # Game mode lobby colors (Phase 39)
    # Each game mode has a distinct color in the lobby
    GAME_MODE_COLORS = {
        "JoustFFA": (255, 140, 0),  # Orange - FFA
        "JoustTeams": (0, 100, 255),  # Blue - Team play
        "Tournament": (150, 0, 255),  # Purple - Competitive
        "Werewolf": (0, 255, 100),  # Green - Mysterious
        "NonstopJoust": (255, 50, 120),  # Pink - Intense/energetic
    }

    async def _update_lobby_feedback(self, controller, stub):
        """
        Update controller LED feedback based on lobby state and selected game mode (Phase 39).

        Colors are game-mode-specific:
        - Each game mode has its own base color (e.g., orange for FFA, blue for Teams)
        - Dim version (~50% brightness): Connected but not ready
        - Bright version (100% brightness): Ready (trigger pressed)
        - Green flash: Initial connection
        - White: Admin mode

        Args:
            controller: ControllerState protobuf message
            stub: ControllerManagerServiceStub for LED control
        """
        from proto import controller_manager_pb2

        serial = controller.serial
        current_time = time.time()

        # Skip admin mode controllers (handled separately)
        if self.admin_mode_active and serial == self.admin_mode_controller:
            return

        # Detect first connection (green flash welcome)
        if serial not in self.connected_controllers:
            self.connected_controllers.add(serial)
            # Flash green to acknowledge connection
            try:
                await stub.SetControllerColor(
                    controller_manager_pb2.SetControllerColorRequest(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=0, g=255, b=0),
                        duration_ms=300,
                    )
                )
                # Phase 60: Play connection sound
                await self._play_sound("Joust/sounds/join.wav", volume=0.6)
                logger.info(f"Controller {serial} connected - green flash")
            except Exception as e:
                logger.error(f"Failed to send connection flash for {serial}: {e}")

            # Set initial state to connected (will be updated below after flash)
            self.controller_lobby_state[serial] = "connected"
            self.last_lobby_feedback_update[serial] = current_time
            # Wait for green flash to complete, then normal state will be set on next update
            return

        # Detect trigger press to toggle ready state (Phase 39)
        # Press trigger once → become ready (and stay ready even after releasing)
        prev_state = self.controller_button_states.get(serial, {})

        # Detect trigger press event (False → True transition)
        if controller.trigger_pressed and not prev_state.get("trigger", False):
            # Toggle ready state on trigger press
            if serial in self.ready_controllers:
                # Already ready → pressing trigger starts game (handled by _process_button_state)
                # Don't update lobby feedback, let game start happen
                return
            # Not ready → mark as ready
            target_state = "ready"
        else:
            # No trigger press event → maintain current state
            # Once ready, stay ready (don't go back to connected when releasing trigger)
            target_state = "ready" if serial in self.ready_controllers else "connected"

        # Only update if state changed (avoid redundant SetControllerColor calls)
        if target_state == self.controller_lobby_state.get(serial, "unknown"):
            return

        # Rate limit updates (max 2 per second per controller)
        last_update = self.last_lobby_feedback_update.get(serial, 0)
        if current_time - last_update < 0.5:
            return

        # Update ready controller tracking
        if target_state == "ready" and serial not in self.ready_controllers:
            self.ready_controllers.add(serial)
            self.ready_controller_count = len(self.ready_controllers)
            # Phase 60: Play ready sound
            await self._play_sound("Joust/sounds/beep_loud.wav", volume=0.5)
            logger.info(f"Controller {serial} ready ({self.ready_controller_count} total)")

            # Phase 59: Auto-start logic respects force_all_start setting
            if len(self.ready_controllers) >= 2:
                should_auto_start = False
                all_ready = len(self.ready_controllers) == len(self.connected_controllers)

                if all_ready:
                    # All controllers ready - always auto-start
                    should_auto_start = True
                    logger.info("All controllers ready - auto-starting game!")
                else:
                    # Not all ready - check force_all_start setting
                    try:
                        from proto import settings_pb2, settings_pb2_grpc
                        settings_stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
                        response = await settings_stub.GetSetting(
                            settings_pb2.GetSettingRequest(key="force_all_start")
                        )
                        force_all = response.value == "true"

                        if not force_all:
                            # Don't require all controllers - auto-start with 2+ ready
                            should_auto_start = True
                            logger.info(f"{len(self.ready_controllers)} controllers ready (force_all_start=false) - auto-starting!")
                    except Exception as e:
                        logger.warning(f"Could not check force_all_start setting: {e}, waiting for all controllers")

                if should_auto_start:
                    await self._handle_trigger_press(serial)

        elif target_state == "connected" and serial in self.ready_controllers:
            self.ready_controllers.remove(serial)
            self.ready_controller_count = len(self.ready_controllers)
            logger.info(f"Controller {serial} unready ({self.ready_controller_count} total)")

        # Get base color for current game mode
        base_color = self.GAME_MODE_COLORS.get(
            self.current_selection,
            (255, 140, 0),  # Default to orange if game mode not found
        )

        # Set LED color based on state
        try:
            if target_state == "ready":
                # Bright version (100% brightness)
                color = controller_manager_pb2.RGB(r=base_color[0], g=base_color[1], b=base_color[2])
            else:
                # Dim version (~50% brightness)
                color = controller_manager_pb2.RGB(
                    r=int(base_color[0] * 0.5),
                    g=int(base_color[1] * 0.5),
                    b=int(base_color[2] * 0.5),
                )

            await stub.SetControllerColor(
                controller_manager_pb2.SetControllerColorRequest(
                    serial=serial,
                    color=color,
                    duration_ms=0,  # Persistent until changed
                )
            )

            # Update state tracking
            self.controller_lobby_state[serial] = target_state
            self.last_lobby_feedback_update[serial] = current_time

            logger.debug(f"Controller {serial} lobby state: {target_state} (game: {self.current_selection})")

        except Exception as e:
            logger.error(f"Failed to update lobby feedback for {serial}: {e}")

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
        metrics.button_presses_total.labels(button="trigger", action="press").inc()

        with tracer.start_as_current_span("handle_trigger_press") as span:
            span.set_attribute("controller.serial", serial)
            span.set_attribute("game.name", self.current_selection)

            self.state = menu_pb2.MenuState.GAME_STARTING
            await self._publish_event(  # Phase 34: await
                "game_requested",
                {"game_name": self.current_selection, "source": "controller", "serial": serial},
            )
            logger.info(f"Game requested via controller {serial}: {self.current_selection}")

    async def _handle_select_press(self, serial: str):
        """
        Handle select button press - cycle games (Phase 21).

        Args:
            serial: Controller serial number
        """
        metrics.button_presses_total.labels(button="move", action="press").inc()

        with tracer.start_as_current_span("handle_select_press") as span:
            span.set_attribute("controller.serial", serial)

            # Phase 59: Use GAME_MODES constant
            current_index = self.GAME_MODES.index(self.current_selection) if self.current_selection in self.GAME_MODES else 0
            self.current_selection = self.GAME_MODES[(current_index + 1) % len(self.GAME_MODES)]

            span.set_attribute("game.name", self.current_selection)

            await self._publish_event(  # Phase 34: await
                "selection_changed",
                {"game_name": self.current_selection, "source": "controller", "serial": serial},
            )
            logger.info(f"Selection changed via controller {serial}: {self.current_selection}")

            # Phase 60: Play game mode voice announcement
            voice_file = self.GAME_MODE_VOICE.get(self.current_selection)
            if voice_file:
                await self._play_voice(voice_file)

            # Phase 39: Force lobby color update for all controllers to reflect new game mode
            # Clear the state so colors update on next _update_lobby_feedback call
            self.controller_lobby_state.clear()
            self.last_lobby_feedback_update.clear()

    # ========== Admin Mode Methods (Phase 23) ==========

    def _check_admin_mode_combo(self, controller) -> bool:
        """
        Check if all 4 front buttons are pressed simultaneously (Phase 23).

        Args:
            controller: ControllerState protobuf message

        Returns:
            True if admin mode combo is active
        """
        return (
            controller.cross_pressed
            and controller.circle_pressed
            and controller.square_pressed
            and controller.triangle_pressed
        )

    async def _enter_admin_mode(self, serial: str):
        """
        Enter admin mode with visual feedback (Phase 23 & 39).

        Provides clear feedback:
        - White flash (3 times) to acknowledge entry
        - Persistent white LED while in admin mode

        Args:
            serial: Controller serial number
        """
        metrics.button_presses_total.labels(button="admin_combo", action="hold").inc()

        with tracer.start_as_current_span("enter_admin_mode") as span:
            span.set_attribute("controller.serial", serial)

            self.admin_mode_active = True
            self.admin_mode_controller = serial
            self.admin_mode_entry_time = time.time()
            self.admin_current_option = 0  # Reset to first option (team_size)

            # Visual feedback: Flash white 3 times, then set persistent white LED
            from proto import (
                controller_manager_pb2,
                controller_manager_pb2_grpc,
            )

            try:
                # Use persistent channel (Phase 26)
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                # Play flash effect in white
                effect_request = controller_manager_pb2.PlayControllerEffectRequest(
                    serial=serial,
                    effect=controller_manager_pb2.ControllerEffect.EFFECT_FLASH,
                    color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                    duration_ms=600,  # 3 flashes at ~5Hz
                    speed=5,
                )
                await stub.PlayControllerEffect(effect_request)

                # Wait for flash to complete, then set persistent white LED (Phase 39)
                await asyncio.sleep(0.7)  # 600ms flash + small buffer

                color_request = controller_manager_pb2.SetControllerColorRequest(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                    duration_ms=0,  # Persistent white
                )
                await stub.SetControllerColor(color_request)

                # Mark as admin in lobby state (prevents normal lobby feedback)
                self.controller_lobby_state[serial] = "admin"

                span.add_event("admin_mode_entered")
                logger.info(f"Admin mode entered by controller {serial} - white LED active")

            except Exception as e:
                logger.error(f"Error entering admin mode: {e}", exc_info=True)

    async def _exit_admin_mode(self):
        """Exit admin mode and restore lobby color (Phase 23 & 39)."""
        if self.admin_mode_active:
            with tracer.start_as_current_span("exit_admin_mode") as span:
                span.set_attribute("controller.serial", self.admin_mode_controller)
                span.set_attribute("duration_seconds", time.time() - self.admin_mode_entry_time)

                logger.info(f"Admin mode exited by controller {self.admin_mode_controller}")

                # Phase 39: Restore lobby color for the admin controller
                serial = self.admin_mode_controller
                if serial:
                    from proto import (
                        controller_manager_pb2,
                        controller_manager_pb2_grpc,
                    )

                    try:
                        stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                        # Get base color for current game mode
                        base_color = self.GAME_MODE_COLORS.get(
                            self.current_selection,
                            (255, 140, 0),  # Default to orange
                        )

                        # Determine if controller was ready before entering admin mode
                        if serial in self.ready_controllers:
                            # Bright version (ready)
                            color = controller_manager_pb2.RGB(r=base_color[0], g=base_color[1], b=base_color[2])
                        else:
                            # Dim version (connected but not ready)
                            color = controller_manager_pb2.RGB(
                                r=int(base_color[0] * 0.5),
                                g=int(base_color[1] * 0.5),
                                b=int(base_color[2] * 0.5),
                            )

                        # Restore lobby color
                        color_request = controller_manager_pb2.SetControllerColorRequest(
                            serial=serial,
                            color=color,
                            duration_ms=0,  # Persistent
                        )
                        await stub.SetControllerColor(color_request)

                        # Clear admin state
                        if serial in self.controller_lobby_state:
                            del self.controller_lobby_state[serial]

                        logger.info(f"Restored lobby color for {serial} after exiting admin mode")

                    except Exception as e:
                        logger.error(f"Error restoring lobby color after admin mode: {e}", exc_info=True)

                self.admin_mode_active = False
                self.admin_mode_controller = None
                self.admin_mode_entry_time = 0
                span.add_event("admin_mode_exited")

    async def _process_admin_commands(self, controller, prev_state: dict[str, bool], current_time: float):
        """
        Process admin mode commands (Phase 23).

        Admin option navigation:
        - MOVE button: Cycle through settings (num_teams, force_all_start)
        - TRIGGER button: Increase current setting value
        - CROSS button: Decrease current setting value

        Quick access commands:
        - Circle: Cycle sensitivity
        - Triangle: Show battery levels
        - Square: Toggle instructions
        - PlayStation: Exit admin mode

        Args:
            controller: ControllerState protobuf message
            prev_state: Previous button states
            current_time: Current timestamp
        """
        # MOVE button: Cycle through admin options
        if (
            controller.move_pressed
            and not prev_state["move"]
            and self._should_process_button(controller.serial, "move", current_time)
        ):
            await self._handle_admin_cycle_option(controller.serial)

        # TRIGGER button: Increase current setting value
        if (
            controller.trigger_pressed
            and not prev_state["trigger"]
            and self._should_process_button(controller.serial, "trigger", current_time)
        ):
            await self._handle_admin_increase_value(controller.serial)

        # CROSS button: Decrease current setting value
        if (
            controller.cross_pressed
            and not prev_state["cross"]
            and self._should_process_button(controller.serial, "cross", current_time)
        ):
            await self._handle_admin_decrease_value(controller.serial)

        # Circle button: Cycle sensitivity (quick access)
        if (
            controller.circle_pressed
            and not prev_state["circle"]
            and self._should_process_button(controller.serial, "circle", current_time)
        ):
            await self._handle_admin_sensitivity(controller.serial)

        # Triangle button: Show battery levels (quick access)
        if (
            controller.triangle_pressed
            and not prev_state["triangle"]
            and self._should_process_button(controller.serial, "triangle", current_time)
        ):
            await self._handle_admin_battery(controller.serial)

        # Square button: Toggle instructions (quick access)
        if (
            controller.square_pressed
            and not prev_state["square"]
            and self._should_process_button(controller.serial, "square", current_time)
        ):
            await self._handle_admin_instructions(controller.serial)

        # PlayStation button: Exit admin mode
        if (
            controller.ps_pressed
            and not prev_state["ps"]
            and self._should_process_button(controller.serial, "ps", current_time)
        ):
            await self._exit_admin_mode()

    async def _handle_admin_sensitivity(self, serial: str):
        """
        Handle sensitivity cycling in admin mode (Phase 28).

        Cycles through: Slow (0) → Medium (1) → Fast (2) → Slow

        Args:
            serial: Controller serial number
        """
        with tracer.start_as_current_span("admin_sensitivity") as span:
            span.set_attribute("controller.serial", serial)

            from proto import (
                controller_manager_pb2,
                controller_manager_pb2_grpc,
                settings_pb2,
                settings_pb2_grpc,
            )

            try:
                # Use persistent channels (Phase 26)
                settings_stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)

                # Get current sensitivity
                get_request = settings_pb2.GetSettingRequest(key="sensitivity")
                get_response = await settings_stub.GetSetting(get_request)
                current = int(get_response.value) if get_response.value else 1

                # Validate current value is in range
                if current < 0 or current > 2:
                    logger.warning(f"Invalid sensitivity value {current}, resetting to 1")
                    current = 1

                # Cycle: 0 (slow) → 1 (medium) → 2 (fast) → 0
                new_value = str((current + 1) % 3)

                # Update setting
                update_request = settings_pb2.UpdateSettingRequest(
                    key="sensitivity", value=new_value, source="admin_mode"
                )
                await settings_stub.UpdateSetting(update_request)

                # Visual feedback: Color by sensitivity level
                sensitivity_colors = [
                    (0, 0, 255),  # Slow: Blue
                    (0, 255, 0),  # Medium: Green
                    (255, 0, 0),  # Fast: Red
                ]
                color = sensitivity_colors[int(new_value)]

                # Use persistent controller channel for visual feedback
                controller_stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                # Show color pulse
                effect_request = controller_manager_pb2.PlayControllerEffectRequest(
                    serial=serial,
                    effect=controller_manager_pb2.ControllerEffect.EFFECT_PULSE,
                    color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
                    duration_ms=800,
                    speed=5,
                )
                await controller_stub.PlayControllerEffect(effect_request)

                sensitivity_names = ["Slow", "Medium", "Fast"]

                # Phase 60: Play sensitivity voice announcement
                sensitivity_sounds = ["slow_sensitivity.wav", "mid_sensitivity.wav", "fast_sensitivity.wav"]
                await self._play_sound(f"Menu/sounds/{sensitivity_sounds[int(new_value)]}")

                span.add_event(
                    "sensitivity_changed",
                    {
                        "old_value": current,
                        "new_value": new_value,
                        "sensitivity_name": sensitivity_names[int(new_value)],
                    },
                )
                logger.info(
                    f"Sensitivity changed by admin controller {serial}: {current} → {new_value} "
                    f"({sensitivity_names[int(new_value)]})"
                )

            except Exception as e:
                logger.error(f"Error changing sensitivity: {e}", exc_info=True)

    async def _handle_admin_battery(self, serial: str):
        """
        Handle battery display in admin mode (Phase 23).

        Shows battery level via LED color:
        - Green: >66%
        - Yellow: 33-66%
        - Red: <33%

        Args:
            serial: Controller serial number
        """
        with tracer.start_as_current_span("admin_battery") as span:
            span.set_attribute("controller.serial", serial)

            from proto import controller_manager_pb2, controller_manager_pb2_grpc

            try:
                # Use persistent channel (Phase 26)
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                # Get all controllers to show battery levels
                controllers_request = controller_manager_pb2.GetControllersRequest()
                controllers_response = await stub.GetControllers(controllers_request)

                # Show battery for each controller
                for ctrl in controllers_response.controllers:
                    battery_percent = ctrl.battery

                    # Determine color based on battery level
                    if battery_percent > 66:
                        color = controller_manager_pb2.RGB(r=0, g=255, b=0)  # Green
                    elif battery_percent > 33:
                        color = controller_manager_pb2.RGB(r=255, g=255, b=0)  # Yellow
                    else:
                        color = controller_manager_pb2.RGB(r=255, g=0, b=0)  # Red

                    # Show battery color for 2 seconds
                    color_request = controller_manager_pb2.SetControllerColorRequest(
                        serial=ctrl.serial, color=color, duration_ms=2000
                    )
                    await stub.SetControllerColor(color_request)

                    span.add_event(
                        "battery_displayed",
                        {"controller.serial": ctrl.serial, "battery.percent": battery_percent},
                    )

                logger.info(f"Battery levels displayed by admin controller {serial}")

            except Exception as e:
                logger.error(f"Error displaying battery: {e}", exc_info=True)

    async def _handle_admin_instructions(self, serial: str):
        """
        Handle instruction toggle in admin mode (Phase 28).

        Toggles instruction display on/off.

        Args:
            serial: Controller serial number
        """
        with tracer.start_as_current_span("admin_instructions") as span:
            span.set_attribute("controller.serial", serial)

            from proto import (
                controller_manager_pb2,
                controller_manager_pb2_grpc,
                settings_pb2,
                settings_pb2_grpc,
            )

            try:
                # Use persistent channels (Phase 26)
                settings_stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)

                # Get current instruction state
                get_request = settings_pb2.GetSettingRequest(key="instructions")
                get_response = await settings_stub.GetSetting(get_request)
                current = get_response.value if get_response.value else "true"

                # Toggle: true ↔ false
                new_value = "false" if current == "true" else "true"

                # Update setting
                update_request = settings_pb2.UpdateSettingRequest(
                    key="instructions", value=new_value, source="admin_mode"
                )
                await settings_stub.UpdateSetting(update_request)

                # Visual feedback: Green (enabled) or Red (disabled)
                if new_value == "true":
                    color = controller_manager_pb2.RGB(r=0, g=255, b=0)  # Green - enabled
                else:
                    color = controller_manager_pb2.RGB(r=255, g=0, b=0)  # Red - disabled

                # Use persistent controller channel for visual feedback
                controller_stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                # Show color pulse
                effect_request = controller_manager_pb2.PlayControllerEffectRequest(
                    serial=serial,
                    effect=controller_manager_pb2.ControllerEffect.EFFECT_PULSE,
                    color=color,
                    duration_ms=800,
                    speed=5,
                )
                await controller_stub.PlayControllerEffect(effect_request)

                # Phase 60: Play instructions toggle voice announcement
                voice_file = "instructions_on.wav" if new_value == "true" else "instructions_off.wav"
                await self._play_voice(voice_file)

                span.add_event(
                    "instructions_toggled",
                    {"old_value": current, "new_value": new_value, "enabled": new_value == "true"},
                )
                logger.info(f"Instructions toggled by admin controller {serial}: {current} → {new_value}")

            except Exception as e:
                logger.error(f"Error toggling instructions: {e}", exc_info=True)

    async def _handle_admin_cycle_option(self, serial: str):
        """
        Cycle through admin options (Phase 23 - enhanced).

        Options: num_teams → force_all_start → num_teams

        Args:
            serial: Controller serial number
        """
        with tracer.start_as_current_span("admin_cycle_option") as span:
            span.set_attribute("controller.serial", serial)

            # Cycle to next option
            self.admin_current_option = (self.admin_current_option + 1) % len(self.admin_option_names)
            option_name = self.admin_option_names[self.admin_current_option]
            option_color = self.admin_option_colors[self.admin_current_option]

            span.set_attribute("admin.option", option_name)

            from proto import controller_manager_pb2, controller_manager_pb2_grpc

            try:
                # Use persistent channel (Phase 26)
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                # Show option color for 1 second
                color_request = controller_manager_pb2.SetControllerColorRequest(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=option_color[0], g=option_color[1], b=option_color[2]),
                    duration_ms=1000,
                )
                await stub.SetControllerColor(color_request)

                # Phase 59: Schedule restore to white after option color finishes
                async def restore_white():
                    await asyncio.sleep(1.1)  # Wait for option color to finish
                    if self.admin_mode_active and serial == self.admin_mode_controller:
                        try:
                            white_request = controller_manager_pb2.SetControllerColorRequest(
                                serial=serial,
                                color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                                duration_ms=0,  # Persistent white
                            )
                            await stub.SetControllerColor(white_request)
                        except Exception as e:
                            logger.debug(f"Could not restore white LED: {e}")

                asyncio.create_task(restore_white())

                span.add_event(
                    "admin_option_changed",
                    {"option": option_name, "option_index": self.admin_current_option},
                )
                logger.info(f"Admin option changed to {option_name} by controller {serial}")

            except Exception as e:
                logger.error(f"Error cycling admin option: {e}", exc_info=True)

    async def _handle_admin_increase_value(self, serial: str):
        """
        Increase the value of the current admin option (Phase 23 - enhanced).

        Args:
            serial: Controller serial number
        """
        with tracer.start_as_current_span("admin_increase_value") as span:
            span.set_attribute("controller.serial", serial)

            option_name = self.admin_option_names[self.admin_current_option]
            span.set_attribute("admin.option", option_name)

            from proto import settings_pb2, settings_pb2_grpc

            try:
                # Use persistent channel (Phase 26)
                stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)

                # Get current value
                get_request = settings_pb2.GetSettingRequest(key=option_name)
                get_response = await stub.GetSetting(get_request)
                current_value = get_response.value

                # Calculate new value based on option type
                if option_name == "num_teams":
                    # Cycle: 2 → 3 → 4 → 5 → 6 → 2
                    current = int(current_value) if current_value else 2
                    # Validate range
                    if current < 2 or current > 6:
                        logger.warning(f"Invalid num_teams value {current}, resetting to 2")
                        current = 2
                    new_value = str((current % 6) + 1) if current < 6 else "2"
                elif option_name == "force_all_start":
                    # Toggle: true ↔ false
                    # Validate boolean
                    if current_value not in ["true", "false"]:
                        logger.warning(f"Invalid force_all_start value {current_value}, resetting to false")
                        current_value = "false"
                    new_value = "true" if current_value == "false" else "false"
                else:
                    new_value = current_value

                # Update setting
                update_request = settings_pb2.UpdateSettingRequest(
                    key=option_name, value=new_value, source="admin_mode"
                )
                await stub.UpdateSetting(update_request)

                # Visual feedback
                await self._show_value_feedback(serial, option_name, new_value)

                span.add_event(
                    "admin_value_increased",
                    {"option": option_name, "old_value": current_value, "new_value": new_value},
                )
                logger.info(f"Admin increased {option_name}: {current_value} → {new_value}")

            except Exception as e:
                logger.error(f"Error increasing admin value: {e}", exc_info=True)

    async def _handle_admin_decrease_value(self, serial: str):
        """
        Decrease the value of the current admin option (Phase 23 - enhanced).

        Args:
            serial: Controller serial number
        """
        with tracer.start_as_current_span("admin_decrease_value") as span:
            span.set_attribute("controller.serial", serial)

            option_name = self.admin_option_names[self.admin_current_option]
            span.set_attribute("admin.option", option_name)

            from proto import settings_pb2, settings_pb2_grpc

            try:
                # Use persistent channel (Phase 26)
                stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)

                # Get current value
                get_request = settings_pb2.GetSettingRequest(key=option_name)
                get_response = await stub.GetSetting(get_request)
                current_value = get_response.value

                # Calculate new value based on option type
                if option_name == "num_teams":
                    # Cycle: 6 → 5 → 4 → 3 → 2 → 6
                    current = int(current_value) if current_value else 2
                    # Validate range
                    if current < 2 or current > 6:
                        logger.warning(f"Invalid num_teams value {current}, resetting to 2")
                        current = 2
                    new_value = str(current - 1) if current > 2 else "6"
                elif option_name == "force_all_start":
                    # Toggle: true ↔ false
                    # Validate boolean
                    if current_value not in ["true", "false"]:
                        logger.warning(f"Invalid force_all_start value {current_value}, resetting to false")
                        current_value = "false"
                    new_value = "false" if current_value == "true" else "true"
                else:
                    new_value = current_value

                # Update setting
                update_request = settings_pb2.UpdateSettingRequest(
                    key=option_name, value=new_value, source="admin_mode"
                )
                await stub.UpdateSetting(update_request)

                # Visual feedback
                await self._show_value_feedback(serial, option_name, new_value)

                span.add_event(
                    "admin_value_decreased",
                    {"option": option_name, "old_value": current_value, "new_value": new_value},
                )
                logger.info(f"Admin decreased {option_name}: {current_value} → {new_value}")

            except Exception as e:
                logger.error(f"Error decreasing admin value: {e}", exc_info=True)

    async def _show_value_feedback(self, serial: str, option_name: str, value: str):
        """
        Show visual feedback for admin value change (Phase 23 - enhanced).

        For team_size: Flash N times (where N = team size)
        For force_all_start: Green (true) or Red (false)

        Args:
            serial: Controller serial number
            option_name: Name of the setting
            value: New value
        """
        from proto import controller_manager_pb2, controller_manager_pb2_grpc

        try:
            # Use persistent channel (Phase 26)
            stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

            if option_name == "num_teams":
                # Flash white N times (where N = team count)
                num_flashes = int(value)
                duration_ms = num_flashes * 200  # 200ms per flash
                effect_request = controller_manager_pb2.PlayControllerEffectRequest(
                    serial=serial,
                    effect=controller_manager_pb2.ControllerEffect.EFFECT_FLASH,
                    color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                    duration_ms=duration_ms,
                    speed=5,
                )
                await stub.PlayControllerEffect(effect_request)

            elif option_name == "force_all_start":
                # Green for true, Red for false
                if value == "true":
                    color = controller_manager_pb2.RGB(r=0, g=255, b=0)  # Green
                else:
                    color = controller_manager_pb2.RGB(r=255, g=0, b=0)  # Red

                color_request = controller_manager_pb2.SetControllerColorRequest(
                    serial=serial, color=color, duration_ms=800
                )
                await stub.SetControllerColor(color_request)

        except Exception as e:
            logger.error(f"Error showing value feedback: {e}", exc_info=True)


async def serve(port=50054, metrics_port=8000):
    """Start the Menu gRPC server."""
    # Configure logging with environment variable support
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Start Prometheus metrics HTTP server (Phase 38)
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics available at http://0.0.0.0:{metrics_port}/metrics")

    # Start system metrics collection task (Phase 38)
    async def collect_system_metrics():
        """
        Background task to collect system metrics every 10 seconds.
        Phase 34: Run psutil calls in thread pool to avoid blocking event loop.
        """
        process = psutil.Process()
        loop = asyncio.get_event_loop()

        while True:
            try:
                # Phase 34: Run blocking psutil calls in thread pool
                cpu_percent = await loop.run_in_executor(None, lambda: process.cpu_percent(interval=None))
                mem_info = await loop.run_in_executor(None, lambda: process.memory_info())
                thread_count = await loop.run_in_executor(None, process.num_threads)

                metrics.process_cpu_percent.set(cpu_percent)
                metrics.process_memory_mb.set(mem_info.rss / 1024 / 1024)
                metrics.process_threads.set(thread_count)
            except Exception as e:
                logger.error(f"Error collecting system metrics: {e}")
            await asyncio.sleep(10.0)

    # Phase 59: Track background tasks for cleanup
    background_tasks = []
    metrics_task = asyncio.create_task(collect_system_metrics())
    background_tasks.append(metrics_task)

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
    server.add_insecure_port(f"[::]:{port}")

    # Start server
    logger.info(f"Starting Menu gRPC server on port {port}")
    await server.start()

    # Start controller button monitoring (Phase 21)
    await menu_servicer.start_button_monitor()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Menu server...")

        # Phase 59: Cancel background tasks
        for task in background_tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        logger.info("Background tasks cancelled")

        await menu_servicer.stop_button_monitor()
        await menu_servicer.shutdown()  # Phase 26: Close persistent channels
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
