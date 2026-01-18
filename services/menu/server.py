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

# OpenTelemetry (trace API for span operations)
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from lib.types import Sound
from services.menu.handlers.admin import AdminModeHandler
from services.menu.utils import AudioHelper, LedController, SettingsHelper

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import contextlib

from prometheus_client import start_http_server

from lib.system_metrics import start_system_metrics_collector
from lib.telemetry import init_telemetry
from proto import menu_pb2, menu_pb2_grpc
from services.menu import metrics

logger = logging.getLogger(__name__)


# Initialize OpenTelemetry with gRPC client instrumentation
# Menu calls ControllerManager, Settings, and Audio services
tracer = init_telemetry(instrument_grpc_client=True)


# Button type enum to name mapping (for state tracking)
# Maps controller_manager_pb2.BUTTON_* enum values to state dict keys
BUTTON_TYPE_NAMES = {
    0: "trigger",  # BUTTON_TRIGGER
    1: "move",  # BUTTON_MOVE
    2: "cross",  # BUTTON_CROSS
    3: "circle",  # BUTTON_CIRCLE
    4: "square",  # BUTTON_SQUARE
    5: "triangle",  # BUTTON_TRIANGLE
    6: "ps",  # BUTTON_PS
    7: "select",  # BUTTON_SELECT
    8: "start",  # BUTTON_START
}


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

        # Game event monitoring - stops button monitor during games
        self.game_event_task = None
        self.game_event_monitor_running = False
        self.controller_button_states: dict[str, dict[str, bool]] = {}  # {serial: {trigger: bool, move: bool, ...}}
        self.last_button_press_time: dict[str, dict[str, float]] = {}  # {serial: {button: timestamp}}

        # Lobby state feedback (Phase 39)
        self.ready_controllers: set[str] = set()  # Controllers with trigger pressed (ready)
        self.connected_controllers: set[str] = set()  # All connected controllers
        self.controller_lobby_state: dict[str, str] = {}  # {serial: "connected"|"ready"|"admin"}
        self.last_lobby_feedback_update: dict[str, float] = {}  # {serial: timestamp}
        self.last_controller_seen: dict[str, float] = {}  # {serial: timestamp} for timeout-based disconnect

        # Phase XX: Bidirectional button event stream for LED state ownership
        self.button_stream: grpc.aio.StreamStreamCall | None = None
        self.button_stream_lock = asyncio.Lock()
        self._button_stream_queue: asyncio.Queue | None = None

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

        # Utility classes (Phase XX: SOLID refactor)
        self.led = LedController(self.controller_channel)
        self.audio = AudioHelper(self.audio_channel)
        self.settings_helper = SettingsHelper(self.settings_channel)

        # Phase 60: Voice actor setting (aaron or ivy)
        self.voice_actor = "ivy"  # Default matches settings schema

        # Admin mode handler (provides callbacks to access Menu methods)
        self.admin_handler = AdminModeHandler(
            controller_channel=self.controller_channel,
            settings_channel=self.settings_channel,
            tracer=tracer,
            callbacks=self,  # Menu implements AdminModeCallbacks protocol
            metrics=metrics,
        )

        logger.info("Menu service initialized with persistent gRPC channels")

    # AdminModeCallbacks protocol implementation
    # These methods provide the interface that AdminModeHandler uses

    async def play_voice(self, sound: Sound) -> None:
        """Play a voice announcement (AdminModeCallbacks)."""
        await self._play_voice(sound)

    async def send_game_effect(self, serial: str, effect: int) -> bool:
        """Send a game effect to a controller (AdminModeCallbacks)."""
        return await self._send_game_effect(serial, effect)

    async def send_base_color(self, serial: str, color: tuple[int, int, int]) -> bool:
        """Send a base color to a controller (AdminModeCallbacks)."""
        return await self._send_base_color(serial, color)

    async def publish_event(self, event_type: str, data: dict) -> None:
        """Publish an event to subscribers (AdminModeCallbacks)."""
        await self._publish_event(event_type, data)

    def get_current_selection(self) -> str:
        """Get the currently selected game mode (AdminModeCallbacks)."""
        return self.current_selection

    def get_connected_controllers(self) -> set[str]:
        """Get set of connected controller serials (AdminModeCallbacks)."""
        return self.connected_controllers

    def get_ready_controllers(self) -> set[str]:
        """Get set of ready controller serials (AdminModeCallbacks)."""
        return self.ready_controllers

    def set_menu_state(self, state) -> None:
        """Set the menu state (AdminModeCallbacks)."""
        self.state = state

    def get_game_options(self) -> list[str]:
        """Get list of available game options (AdminModeCallbacks)."""
        return self.game_options if hasattr(self, "game_options") else []

    async def StartMenu(self, request, context):
        """Start the menu (Phase 34: async for _publish_event)."""
        start_time = time.time()
        with tracer.start_as_current_span("StartMenu") as span:
            try:
                if self.state == menu_pb2.MenuState.RUNNING:
                    metrics.grpc_requests_total.labels(method="StartMenu", status="already_running").inc()
                    return menu_pb2.StartMenuResponse(success=False, error="Menu already running")

                self.state = menu_pb2.MenuState.RUNNING
                self.ready_controller_count = 0

                # Load settings (voice, play_audio, current_game)
                await self._load_voice_actor_setting()
                await self._load_current_game_setting()

                # Phase 70: Start lobby music
                await self._start_lobby_music()

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
                        # Game requested - pass ready controllers
                        controllers = list(self.ready_controllers)
                        self.state = menu_pb2.MenuState.GAME_STARTING
                        await self._publish_event(
                            "game_requested",
                            {"game_name": self.current_selection, "controllers": controllers},
                        )
                        logger.info(f"Game requested: {self.current_selection} with {len(controllers)} players")

                    elif button == "select":
                        # Move to next game (Phase 59: use GAME_MODES constant)
                        if self.current_selection in self.GAME_MODES:
                            current_index = self.GAME_MODES.index(self.current_selection)
                        else:
                            current_index = 0
                        self.current_selection = self.GAME_MODES[(current_index + 1) % len(self.GAME_MODES)]
                        await self._publish_event("selection_changed", {"game_name": self.current_selection})
                        await self._save_current_game_setting()
                        logger.info(f"Selection changed to: {self.current_selection}")

                elif input_type == "web_command":
                    command = data.get("command", "")
                    span.set_attribute("command", command)

                    if command == "start_game":
                        # Web start - use ready controllers
                        controllers = list(self.ready_controllers)
                        self.state = menu_pb2.MenuState.GAME_STARTING
                        await self._publish_event(
                            "game_requested",
                            {"game_name": self.current_selection, "source": "web", "controllers": controllers},
                        )
                        logger.info(f"Game requested via web: {self.current_selection} with {len(controllers)} players")

                    # Phase 59: Add select_game command for web UI
                    elif command == "select_game":
                        game_name = data.get("game_name", "")
                        if game_name in self.GAME_MODES:
                            self.current_selection = game_name
                            await self._publish_event("selection_changed", {"game_name": game_name, "source": "web"})
                            await self._save_current_game_setting()
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

        # Use descriptive span name with event type
        span_name = f"menu_publish:{event_type}"
        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("event.type", event_type)

            # Inject W3C Trace Context into event data for cross-service propagation
            # This allows the Supervisor to link its spans to this trace
            event_data = dict(data)  # Copy to avoid mutating original
            propagator = TraceContextTextMapPropagator()
            carrier: dict[str, str] = {}
            propagator.inject(carrier)
            if "traceparent" in carrier:
                event_data["_traceparent"] = carrier["traceparent"]
            if "tracestate" in carrier:
                event_data["_tracestate"] = carrier["tracestate"]

            event = menu_pb2.MenuEvent(event_type=event_type, data=event_data, timestamp=int(time.time() * 1000))

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
        """Start the controller button monitoring tasks.

        Two parallel loops:
        - Button event loop: Primary handler for all button actions (edge-triggered)
        - Button monitor loop: Connection tracking and LED feedback (state polling)
        """
        if not self.button_monitor_running:
            self.button_monitor_running = True
            # Primary: Button event stream for immediate button handling
            self.button_event_task = asyncio.create_task(self._button_event_loop())
            # Secondary: State stream for connection tracking and LED updates
            self.button_monitor_task = asyncio.create_task(self._button_monitor_loop())
            logger.info("Button monitors started (event stream + state stream)")

    async def stop_button_monitor(self):
        """Stop the controller button monitoring task."""
        self.button_monitor_running = False
        if self.button_monitor_task:
            self.button_monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.button_monitor_task
        if hasattr(self, "button_event_task") and self.button_event_task:
            self.button_event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.button_event_task
        logger.info("Controller button monitor stopped")

    async def start_game_event_monitor(self):
        """Start the game event monitoring task."""
        if not self.game_event_monitor_running:
            self.game_event_monitor_running = True
            self.game_event_task = asyncio.create_task(self._game_event_loop())
            logger.info("Game event monitor started")

    async def stop_game_event_monitor(self):
        """Stop the game event monitoring task."""
        self.game_event_monitor_running = False
        if self.game_event_task:
            self.game_event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.game_event_task
        logger.info("Game event monitor stopped")

    async def _game_event_loop(self):
        """
        Monitor game events from game coordinator.

        Stops button monitor when game starts, restarts when game ends.
        This ensures menu doesn't interfere with game controller handling.
        """
        from lib.types import GameEvent
        from proto import game_coordinator_pb2, game_coordinator_pb2_grpc

        retry_delay = 1.0
        max_retry_delay = 30.0

        while self.game_event_monitor_running:
            try:
                stub = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(self.game_coordinator_channel)

                logger.info("Game event monitor connected to Game Coordinator")
                retry_delay = 1.0  # Reset delay on successful connection

                # Subscribe to game events
                async for event in stub.StreamGameEvents(game_coordinator_pb2.StreamEventsRequest()):
                    if not self.game_event_monitor_running:
                        return

                    is_starting = GameEvent.is_game_starting(event.event_type)
                    logger.info(
                        f"Game event received: {event.event_type} "
                        f"(is_starting={is_starting}, monitor_running={self.button_monitor_running})"
                    )

                    if GameEvent.is_game_starting(event.event_type):
                        # Game is starting - stop button monitoring and lobby music
                        # Handle all start events to catch it as early as possible
                        if self.button_monitor_running:
                            logger.info(f"Game event '{event.event_type}' - stopping button monitor and lobby music")
                            self.state = menu_pb2.MenuState.GAME_STARTING
                            await self._stop_lobby_music()  # Phase 70: Stop lobby music
                            await self.stop_button_monitor()
                            logger.info("Button monitor and lobby music stopped")

                    elif GameEvent.is_game_ending(event.event_type):
                        # Game ended - restart button monitoring and lobby music
                        logger.info(f"Game event '{event.event_type}' - restarting button monitor and lobby music")
                        self.state = menu_pb2.MenuState.RUNNING

                        # Reset lobby state
                        self.ready_controllers.clear()
                        self.connected_controllers.clear()
                        self.controller_lobby_state.clear()
                        self.last_lobby_feedback_update.clear()
                        self.ready_controller_count = 0
                        self.controller_button_states.clear()
                        self.last_button_press_time.clear()

                        # Phase 70: Restart lobby music
                        await self._start_lobby_music()

                        # Restart button monitor
                        await self.start_button_monitor()

                        # Publish event so UI knows game ended
                        await self._publish_event(GameEvent.GAME_ENDED, event.data)

                if self.game_event_monitor_running:
                    logger.warning("Game event stream ended, reconnecting...")

            except asyncio.CancelledError:
                logger.info("Game event monitor task cancelled")
                raise
            except Exception as e:
                if not self.game_event_monitor_running:
                    return
                logger.error(f"Game event monitor error: {e}, reconnecting in {retry_delay:.1f}s")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

    async def shutdown(self):
        """Cleanup resources on shutdown (Phase 26, Phase 60)."""
        logger.info("Shutting down Menu service, closing gRPC channels...")
        await self.controller_channel.close()
        await self.settings_channel.close()
        await self.game_coordinator_channel.close()
        await self.audio_channel.close()
        logger.info("Menu service gRPC channels closed")

    # Phase 60: Audio feedback helpers
    async def _play_sound(self, sound: str | Sound, volume: float = 0.8):
        """
        Play a sound effect via the audio service (fire-and-forget).

        Args:
            sound: Sound enum or relative path to audio file
            volume: Volume level 0.0-1.0
        """
        try:
            from proto import audio_pb2, audio_pb2_grpc

            # Convert Sound enum to string value if needed
            sound_name = sound.value if isinstance(sound, Sound) else sound

            stub = audio_pb2_grpc.AudioServiceStub(self.audio_channel)
            # Send sound name - audio service resolves to its assets directory
            await stub.PlaySound(
                audio_pb2.PlaySoundRequest(
                    file_path=sound_name,
                    volume=volume,
                    priority=audio_pb2.AudioPriority.HIGH,
                )
            )
            logger.debug(f"Played sound: {sound_name}")
        except Exception as e:
            logger.debug(f"Could not play sound {sound}: {e}")

    async def _play_voice(self, voice: str | Sound, volume: float = 0.9):
        """
        Play a voice announcement.

        Args:
            voice: Sound enum or voice file name (audio service resolves the path)
            volume: Volume level 0.0-1.0
        """
        await self._play_sound(voice, volume)

    async def _load_voice_actor_setting(self):
        """
        Load voice actor preference from settings service (Phase 60).

        Updates self.voice_actor to "aaron" or "ivy".
        """
        try:
            from proto import settings_pb2, settings_pb2_grpc

            stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
            response = await stub.GetSetting(settings_pb2.GetSettingRequest(key="menu_voice"))
            if response.value in ("aaron", "ivy"):
                self.voice_actor = response.value
                logger.info(f"Voice actor set to: {self.voice_actor}")
            else:
                logger.debug(f"Voice actor setting not found or invalid, using default: {self.voice_actor}")
        except Exception as e:
            logger.debug(f"Could not load voice actor setting: {e}, using default: {self.voice_actor}")

    async def _load_current_game_setting(self):
        """Load current game mode from settings service."""
        try:
            from proto import settings_pb2, settings_pb2_grpc

            stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
            response = await stub.GetSetting(settings_pb2.GetSettingRequest(key="current_game"))

            if response.value and response.value in self.GAME_MODES:
                self.current_selection = response.value
                logger.info(f"Loaded current game mode: {self.current_selection}")
            else:
                self.current_selection = "JoustFFA"
                logger.debug(f"Current game setting not found, using default: {self.current_selection}")

        except Exception as e:
            self.current_selection = "JoustFFA"
            logger.debug(f"Could not load current game setting: {e}, using default")

    async def _save_current_game_setting(self):
        """Save current game mode to settings service."""
        try:
            from proto import settings_pb2, settings_pb2_grpc

            stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
            await stub.UpdateSetting(
                settings_pb2.UpdateSettingRequest(
                    key="current_game",
                    value=self.current_selection,
                    source="menu",
                )
            )
            logger.debug(f"Saved current game mode: {self.current_selection}")

        except Exception as e:
            logger.debug(f"Could not save current game setting: {e}")

    # Phase 70: Lobby music control
    async def _start_lobby_music(self):
        """
        Start quiet background music for the lobby/menu.

        Uses a lower volume than game music for a relaxed atmosphere.
        """
        try:
            from proto import audio_pb2, audio_pb2_grpc

            stub = audio_pb2_grpc.AudioServiceStub(self.audio_channel)

            # Set lobby volume (quieter than game)
            await stub.SetVolume(audio_pb2.SetVolumeRequest(volume=0.4))

            # Start lobby music
            response = await stub.PlayMusic(
                audio_pb2.PlayMusicRequest(
                    file_pattern="Menu/music/*.wav",
                    loop=True,
                    tempo=1.0,
                    priority=audio_pb2.AudioPriority.LOW,
                )
            )

            if response.success:
                self.lobby_music_track_id = response.track_id
                logger.info(f"Lobby music started: {response.track_id}")
            else:
                logger.warning(f"Failed to start lobby music: {response.error}")

        except Exception as e:
            logger.debug(f"Could not start lobby music: {e}")

    async def _stop_lobby_music(self):
        """Stop lobby music when game starts."""
        try:
            from proto import audio_pb2, audio_pb2_grpc

            stub = audio_pb2_grpc.AudioServiceStub(self.audio_channel)

            # Stop music (empty track_id stops any playing music)
            await stub.StopMusic(audio_pb2.StopMusicRequest(track_id=""))
            self.lobby_music_track_id = None
            logger.info("Lobby music stopped")

        except Exception as e:
            logger.debug(f"Could not stop lobby music: {e}")

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

        # If admin mode controller disconnected, reset admin mode state
        self.admin_handler.reset_on_disconnect(serial)

        logger.info(f"Controller {serial} disconnected, state cleaned up")

    async def _button_monitor_loop(self):
        """
        Secondary monitor for connection tracking and LED feedback.

        This loop handles:
        - Controller connection detection (first-seen)
        - LED color updates based on ready state
        - Heartbeat/presence tracking

        Button actions are handled by _button_event_loop (edge-triggered events).
        """
        from proto import (
            controller_manager_pb2,
            controller_manager_pb2_grpc,
        )

        retry_delay = 1.0
        max_retry_delay = 30.0

        while self.button_monitor_running:
            try:
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                logger.info("State monitor connected to Controller Manager")
                retry_delay = 1.0

                # Stream at lower rate - only need connection tracking and LED updates
                stream_request = controller_manager_pb2.StreamRequest(update_frequency_hz=20)

                async for update in stub.StreamControllerStates(stream_request):
                    if not self.button_monitor_running:
                        return

                    metrics.button_frames_processed_total.inc()

                    for controller in update.controllers:
                        serial = controller.serial

                        # Track connection (button event loop also does this, but state stream
                        # catches controllers that haven't pressed any buttons yet)
                        if serial not in self.connected_controllers:
                            self.connected_controllers.add(serial)
                            logger.info(f"Controller {serial} connected (via state stream)")

                        # Update LED feedback based on current ready state
                        await self._update_lobby_led(controller, stub)
                        metrics.lobby_updates_total.inc()

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

    async def _update_lobby_led(self, controller, stub):
        """
        Update controller LED based on current ready state.

        This is a simplified LED-only update - button state changes are handled
        by _button_event_loop. This method only sets the LED color based on
        whether the controller is in ready_controllers or not.

        Args:
            controller: ControllerState protobuf message
            stub: ControllerManagerServiceStub for LED control (fallback)
        """
        from proto import controller_manager_pb2

        serial = controller.serial

        # Skip admin mode controllers (handled separately)
        if self.admin_handler.is_admin_controller(serial):
            return

        # Determine target state based on ready set (updated by button events)
        target_state = "ready" if serial in self.ready_controllers else "connected"

        # Only update if state changed (avoid redundant SetControllerColor calls)
        if target_state == self.controller_lobby_state.get(serial, "unknown"):
            return

        # Get base color for current game mode
        base_color = self.GAME_MODE_COLORS.get(
            self.current_selection,
            (255, 140, 0),  # Default to orange
        )

        # Calculate final color based on state
        if target_state == "ready":
            final_color = base_color  # Full brightness
        else:
            final_color = (
                int(base_color[0] * 0.3),
                int(base_color[1] * 0.3),
                int(base_color[2] * 0.3),
            )

        # Try to send via bidirectional stream first, fall back to RPC
        if await self._send_base_color(serial, final_color):
            self.controller_lobby_state[serial] = target_state
            logger.debug(f"Controller {serial} LED: {target_state} via stream")
        else:
            try:
                await stub.SetControllerColor(
                    controller_manager_pb2.SetControllerColorRequest(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=final_color[0], g=final_color[1], b=final_color[2]),
                        duration_ms=0,
                    )
                )
                self.controller_lobby_state[serial] = target_state
                logger.debug(f"Controller {serial} LED: {target_state} via RPC")
            except Exception as e:
                logger.error(f"Failed to update LED for {serial}: {e}")

    async def _button_event_loop(self):
        """
        Primary button handler using edge-triggered events.

        This is the main button handling loop - all button actions go through here.
        The state stream (_button_monitor_loop) only handles connection tracking and LED updates.

        Handles:
        - Trigger: ready state toggle, game start (when all ready)
        - Move: game mode cycling, un-ready
        - Admin mode combo detection (all 4 face buttons)
        - Admin mode commands (when active)

        Phase XX: Bidirectional - sends base colors and effects to controller manager.
        """
        from proto import (
            controller_manager_pb2,
            controller_manager_pb2_grpc,
        )

        retry_delay = 1.0
        max_retry_delay = 30.0

        while self.button_monitor_running:
            try:
                stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

                logger.info("Button event loop connecting to Controller Manager (bidirectional)...")

                # Create bidirectional stream with async generator for outbound messages
                request_queue = asyncio.Queue()

                async def request_generator(queue=request_queue):
                    """Async generator that yields ButtonEventStreamControl messages."""
                    # Send initial config
                    initial_config = controller_manager_pb2.ButtonEventStreamControl(
                        config=controller_manager_pb2.ButtonEventStreamConfig()
                    )
                    yield initial_config

                    # Then yield messages from queue
                    while self.button_monitor_running:
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
                async with self.button_stream_lock:
                    self.button_stream = stream
                    self._button_stream_queue = request_queue
                    # Wire LED controller to use the same stream
                    self.led.set_stream(request_queue, self.button_stream_lock)

                logger.info("Button event loop connected to Controller Manager")
                retry_delay = 1.0

                # Process incoming button events
                async for event in stream:
                    if not self.button_monitor_running:
                        return

                    serial = event.serial
                    is_press = event.action == controller_manager_pb2.ACTION_PRESS
                    button_name = BUTTON_TYPE_NAMES.get(event.button, "unknown")

                    # Log button events for debugging
                    action_str = "PRESS" if is_press else "RELEASE"
                    logger.debug(f"Button event: {serial} {button_name}={action_str}")

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
                            "select": False,
                            "start": False,
                        }
                        self.last_button_press_time[serial] = {}

                    # Update button state from event (for combo detection)
                    self.controller_button_states[serial][button_name] = is_press

                    # Track controller as connected
                    if serial not in self.connected_controllers:
                        self.connected_controllers.add(serial)
                        logger.info(f"Controller {serial} connected (via button event)")

                    # Only process button presses (not releases) for actions
                    if not is_press:
                        # Reset admin combo flag when any face button released
                        if button_name in ["cross", "circle", "square", "triangle"]:
                            self.admin_handler.combo_shown = False
                        continue

                    # Check for admin mode combo (all 4 face buttons pressed)
                    is_face_button = button_name in ["cross", "circle", "square", "triangle"]
                    button_state = self.controller_button_states.get(serial, {})
                    if is_face_button and self.admin_handler.check_combo_from_state(button_state):
                        if not self.admin_handler.combo_shown:
                            self.admin_handler.combo_shown = True
                            await self.admin_handler.enter(serial)
                        continue  # Don't process as individual button

                    # Handle button based on current mode
                    if self.admin_handler.is_admin_controller(serial):
                        # Admin mode: process admin commands
                        await self.admin_handler.handle_button_event(serial, button_name)
                    elif self.state == menu_pb2.MenuState.RUNNING:
                        # Normal menu mode: process menu actions
                        await self._handle_menu_button_event(serial, button_name, stub)

                if self.button_monitor_running:
                    logger.warning("Button event stream ended, reconnecting...")

            except asyncio.CancelledError:
                logger.info("Button event loop task cancelled")
                raise
            except Exception as e:
                if not self.button_monitor_running:
                    return
                logger.error(f"Button event loop error: {e}, reconnecting in {retry_delay:.1f}s")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
            finally:
                # Clear stream reference on disconnect
                async with self.button_stream_lock:
                    self.button_stream = None
                    self._button_stream_queue = None
                    self.led.set_stream(None)

    async def _handle_menu_button_event(self, serial: str, button: str, stub):
        """
        Handle button press in normal menu mode.

        Args:
            serial: Controller serial number
            button: Button name (trigger, move, etc.)
            stub: ControllerManagerServiceStub for LED control
        """
        current_time = time.time()

        if button == "trigger":
            # Trigger press: ready toggle or game start
            if not self._should_process_button(serial, "trigger", current_time):
                return
            logger.info(f"Trigger PRESS event: {serial}")
            await self._handle_button_event_trigger(serial)

        elif button == "move":
            # Move press: cycle game modes OR un-ready if ready
            if not self._should_process_button(serial, "move", current_time):
                return
            if serial in self.ready_controllers:
                # Un-ready the controller
                await self._handle_button_event_unready(serial, stub)
            else:
                # Cycle game modes
                await self._handle_select_press(serial)

    async def _handle_button_event_unready(self, serial: str, stub):
        """
        Handle move button press to un-ready a controller.

        Args:
            serial: Controller serial number
            stub: ControllerManagerServiceStub for LED control
        """
        if serial not in self.ready_controllers:
            return

        self.ready_controllers.remove(serial)
        self.ready_controller_count = len(self.ready_controllers)
        logger.info(f"Controller {serial} un-readied via Move button ({self.ready_controller_count} ready)")

        # Update LED to dim color (not ready)
        base_color = self.GAME_MODE_COLORS.get(self.current_selection, (255, 140, 0))
        dim_color = (
            int(base_color[0] * 0.3),
            int(base_color[1] * 0.3),
            int(base_color[2] * 0.3),
        )

        # Try bidirectional stream first, fall back to RPC
        if not await self._send_base_color(serial, dim_color):
            from proto import controller_manager_pb2

            try:
                await stub.SetControllerColor(
                    controller_manager_pb2.SetControllerColorRequest(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=dim_color[0], g=dim_color[1], b=dim_color[2]),
                        duration_ms=0,
                    )
                )
            except Exception as e:
                logger.error(f"Failed to set dim color for {serial}: {e}")

        # Update lobby state
        self.controller_lobby_state[serial] = "connected"

    async def _send_base_color(self, serial: str, color: tuple[int, int, int]) -> bool:
        """
        Send base color via bidirectional button stream (Phase XX).

        Args:
            serial: Controller serial number
            color: RGB tuple (r, g, b)

        Returns:
            True if sent successfully, False if stream not available
        """
        from proto import controller_manager_pb2

        async with self.button_stream_lock:
            if self._button_stream_queue is None:
                return False

            try:
                msg = controller_manager_pb2.ButtonEventStreamControl(
                    base_color=controller_manager_pb2.ControllerColorConfig(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
                    )
                )
                self._button_stream_queue.put_nowait(msg)
                logger.debug(f"Sent base color for {serial}: {color}")
                return True
            except asyncio.QueueFull:
                logger.warning(f"Button stream queue full, could not send base color for {serial}")
                return False

    async def _send_game_effect(self, serial: str, effect: int) -> bool:
        """
        Send game effect via bidirectional button stream (Phase XX).

        Args:
            serial: Controller serial number
            effect: GameEffect enum value

        Returns:
            True if sent successfully, False if stream not available
        """
        from proto import controller_manager_pb2

        async with self.button_stream_lock:
            if self._button_stream_queue is None:
                return False

            try:
                msg = controller_manager_pb2.ButtonEventStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=serial,
                        effect=effect,
                    )
                )
                self._button_stream_queue.put_nowait(msg)
                logger.debug(f"Sent game effect for {serial}: {effect}")
                return True
            except asyncio.QueueFull:
                logger.warning(f"Button stream queue full, could not send game effect for {serial}")
                return False

    async def _handle_button_event_trigger(self, serial: str):
        """
        Handle trigger press event for ready state toggle.

        This is called from the button event stream for immediate response,
        bypassing the state stream latency.

        Phase XX: Uses bidirectional stream to send base colors instead of RPC.
        """
        current_time = time.time()

        # Debounce - ignore if we just processed this (100ms to prevent double-triggers)
        last_press = self.last_button_press_time.get(serial, {}).get("trigger_event", 0)
        if current_time - last_press < 0.1:
            return
        if serial not in self.last_button_press_time:
            self.last_button_press_time[serial] = {}
        self.last_button_press_time[serial]["trigger_event"] = current_time

        # Track controller as connected if not already
        if serial not in self.connected_controllers:
            self.connected_controllers.add(serial)
            logger.info(f"Controller {serial} connected (via button event)")

        # Toggle ready state
        if serial in self.ready_controllers:
            # Already ready - trigger press starts game
            if self.state == menu_pb2.MenuState.RUNNING:
                # Check if all are ready
                ready_count = len(self.ready_controllers)
                all_ready = ready_count == len(self.connected_controllers) and ready_count >= 2
                if all_ready:
                    logger.info(f"All ready, starting game via button event from {serial}")
                    await self._handle_trigger_press(serial)
        else:
            # Not ready - mark as ready
            self.ready_controllers.add(serial)
            self.ready_controller_count = len(self.ready_controllers)
            await self._play_sound(Sound.SFX_BEEP_LOUD, volume=0.5)
            logger.info(f"Controller {serial} ready via button event ({self.ready_controller_count} total)")

            # Update LED to bright (ready) color via stream
            base_color = self.GAME_MODE_COLORS.get(self.current_selection, (255, 140, 0))
            if not await self._send_base_color(serial, base_color):
                # Fallback to RPC if stream not available
                from proto import controller_manager_pb2, controller_manager_pb2_grpc

                try:
                    stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)
                    await stub.SetControllerColor(
                        controller_manager_pb2.SetControllerColorRequest(
                            serial=serial,
                            color=controller_manager_pb2.RGB(r=base_color[0], g=base_color[1], b=base_color[2]),
                            duration_ms=0,
                        )
                    )
                except Exception as e:
                    logger.error(f"Failed to set ready color for {serial}: {e}")

            # Check if all ready - auto start with feedback delay
            all_ready = len(self.ready_controllers) == len(self.connected_controllers)
            logger.info(
                f"Ready check (event): ready={len(self.ready_controllers)} connected={len(self.connected_controllers)} "
                f"all_ready={all_ready}"
            )
            if all_ready and len(self.ready_controllers) >= 2:
                logger.info("All controllers ready - showing feedback before game start")
                # Brief delay so last player sees their LED go bright
                await asyncio.sleep(0.3)
                logger.info("Starting game after feedback delay")
                await self._handle_trigger_press(serial)

    # Game modes available in the menu (Phase 59: single source of truth)
    GAME_MODES = [
        "JoustFFA",
        "JoustTeams",
        "JoustRandomTeams",
        "Swapper",
        "Werewolf",
        "Traitor",
        "Zombie",
        "Commander",
        "FightClub",
        "Tournament",
        "NonstopJoust",
        "SpeedBomb",
    ]

    # Game mode voice announcements (Phase 60)
    GAME_MODE_VOICE = {
        "JoustFFA": Sound.MENU_VOX_JOUST_FFA,
        "JoustTeams": Sound.MENU_VOX_JOUST_TEAMS,
        "JoustRandomTeams": Sound.MENU_VOX_RANDOM_TEAMS,
        "Swapper": Sound.MENU_VOX_SWAPPER,
        "Werewolf": Sound.MENU_VOX_WEREWOLVES,
        "Traitor": Sound.MENU_VOX_TRAITOR,
        "Zombie": Sound.MENU_VOX_ZOMBIES,
        "Commander": Sound.MENU_VOX_COMMANDER,
        "FightClub": Sound.MENU_VOX_FIGHT_CLUB,
        "Tournament": Sound.MENU_VOX_TOURNAMENT,
        "NonstopJoust": Sound.MENU_VOX_NONSTOP_JOUST,
        "SpeedBomb": Sound.MENU_VOX_NINJABOMB,
    }

    # Game mode lobby colors (Phase 39)
    # Each game mode has a distinct color in the lobby
    GAME_MODE_COLORS = {
        "JoustFFA": (255, 140, 0),  # Orange - FFA
        "JoustTeams": (0, 100, 255),  # Blue - Team play
        "JoustRandomTeams": (0, 200, 255),  # Cyan - Random teams
        "Swapper": (255, 0, 255),  # Magenta - Team switching
        "Werewolf": (0, 255, 100),  # Green - Mysterious
        "Traitor": (128, 0, 128),  # Dark purple - Betrayal
        "Zombie": (100, 100, 100),  # Gray - Undead
        "Commander": (255, 0, 0),  # Red - Leadership
        "FightClub": (255, 255, 0),  # Yellow - Arena combat
        "Tournament": (150, 0, 255),  # Purple - Competitive
        "NonstopJoust": (255, 50, 120),  # Pink - Intense/energetic
        "SpeedBomb": (255, 100, 0),  # Orange-red - Explosive
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

        Phase XX: Uses bidirectional stream to send base colors with RPC fallback.

        Args:
            controller: ControllerState protobuf message
            stub: ControllerManagerServiceStub for LED control (fallback)
        """
        from proto import controller_manager_pb2

        serial = controller.serial
        current_time = time.time()

        # Skip admin mode controllers (handled separately)
        if self.admin_handler.is_admin_controller(serial):
            return

        # Track first connection (no flash, just set initial state)
        if serial not in self.connected_controllers:
            self.connected_controllers.add(serial)
            logger.info(f"Controller {serial} connected")
            # Set initial state to trigger immediate color update
            self.controller_lobby_state[serial] = "new"
            # Don't set last_lobby_feedback_update - allow immediate color update

        # Detect button presses for ready state changes (Phase 39)
        # - Trigger press → become ready
        # - Move press → become un-ready (more purposeful action)
        prev_state = self.controller_button_states.get(serial, {})

        # Detect trigger press event (False → True transition) → become ready
        trigger_edge = controller.trigger_pressed and not prev_state.get("trigger", False)

        if trigger_edge:
            if serial in self.ready_controllers:
                # Already ready → pressing trigger starts game (handled by _process_button_state)
                # Don't update lobby feedback, let game start happen
                return
            # Not ready → mark as ready
            target_state = "ready"
        # Detect move press event (False → True transition) → become un-ready
        elif controller.move_pressed and not prev_state.get("move", False):
            if serial in self.ready_controllers:
                # Ready → pressing Move button un-readies
                target_state = "connected"
                logger.info(f"Controller {serial} un-readied via Move button")
            else:
                # Not ready → stay connected
                target_state = "connected"
        else:
            # No relevant button press → maintain current state
            target_state = "ready" if serial in self.ready_controllers else "connected"

        # Only update if state changed (avoid redundant SetControllerColor calls)
        if target_state == self.controller_lobby_state.get(serial, "unknown"):
            return

        # Update ready controller tracking IMMEDIATELY (no rate limiting for state changes)
        if target_state == "ready" and serial not in self.ready_controllers:
            self.ready_controllers.add(serial)
            self.ready_controller_count = len(self.ready_controllers)
            # Phase 60: Play ready sound
            await self._play_sound(Sound.SFX_BEEP_LOUD, volume=0.5)
            logger.info(f"Controller {serial} ready ({self.ready_controller_count} total)")

            # Sync with controller manager to detect disconnects before checking ready
            await self._sync_connected_controllers(stub)

            # Auto-start only when ALL connected controllers are ready (minimum 2)
            all_ready = len(self.ready_controllers) == len(self.connected_controllers)
            logger.info(
                f"Ready check: ready={len(self.ready_controllers)} connected={len(self.connected_controllers)} "
                f"all_ready={all_ready} ready_set={self.ready_controllers} connected_set={self.connected_controllers}"
            )
            if all_ready and len(self.ready_controllers) >= 2:
                logger.info("All controllers ready - auto-starting game!")
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

        # Calculate final color based on state
        if target_state == "ready":
            # Bright version (100% brightness) - ready state
            final_color = base_color
        else:
            # Dim version (30% brightness) - connected but not ready
            final_color = (
                int(base_color[0] * 0.3),
                int(base_color[1] * 0.3),
                int(base_color[2] * 0.3),
            )

        # Phase XX: Try to send via bidirectional stream first
        if await self._send_base_color(serial, final_color):
            # Update state tracking
            self.controller_lobby_state[serial] = target_state
            self.last_lobby_feedback_update[serial] = current_time
            logger.debug(f"Controller {serial} lobby state: {target_state} (game: {self.current_selection}) via stream")
        else:
            # Fallback to RPC if stream not available
            try:
                await stub.SetControllerColor(
                    controller_manager_pb2.SetControllerColorRequest(
                        serial=serial,
                        color=controller_manager_pb2.RGB(r=final_color[0], g=final_color[1], b=final_color[2]),
                        duration_ms=0,  # Persistent until changed
                    )
                )

                # Update state tracking
                self.controller_lobby_state[serial] = target_state
                self.last_lobby_feedback_update[serial] = current_time

                logger.debug(f"Controller {serial} lobby state: {target_state} (game: {self.current_selection})")

            except Exception as e:
                logger.error(f"Failed to update lobby feedback for {serial}: {e}")

    async def _sync_connected_controllers(self, stub):
        """
        Sync connected_controllers with controller manager to detect disconnects.

        Calls GetControllers and removes any controllers from our sets
        that are no longer present in the controller manager.

        Args:
            stub: ControllerManagerServiceStub
        """
        from proto import controller_manager_pb2

        try:
            response = await stub.GetControllers(controller_manager_pb2.GetControllersRequest())
            if not response.success:
                logger.warning(f"GetControllers failed: {response.error}")
                return

            # Get set of currently connected controller serials
            current_serials = {c.serial for c in response.controllers}

            # Find controllers that disconnected
            disconnected = self.connected_controllers - current_serials
            if disconnected:
                logger.info(f"Controllers disconnected: {disconnected}")
                for serial in disconnected:
                    self.connected_controllers.discard(serial)
                    self.ready_controllers.discard(serial)
                    self.controller_lobby_state.pop(serial, None)
                    self.controller_button_states.pop(serial, None)
                    self.last_button_press_time.pop(serial, None)
                    self.last_lobby_feedback_update.pop(serial, None)

                self.ready_controller_count = len(self.ready_controllers)
                connected = len(self.connected_controllers)
                ready = len(self.ready_controllers)
                logger.info(f"After disconnect cleanup: connected={connected} ready={ready}")

        except Exception as e:
            logger.warning(f"Failed to sync controllers: {e}")

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
        if current_time - last_press < 0.1:  # 100ms debounce (original had none)
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

            # Pass ready controllers directly - menu is source of truth
            controllers = list(self.ready_controllers)
            span.set_attribute("controller.count", len(controllers))

            self.state = menu_pb2.MenuState.GAME_STARTING
            await self._publish_event(  # Phase 34: await
                "game_requested",
                {
                    "game_name": self.current_selection,
                    "source": "controller",
                    "serial": serial,
                    "controllers": controllers,
                },
            )
            logger.info(
                f"Game requested via controller {serial}: {self.current_selection} " f"with {len(controllers)} players"
            )

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
            if self.current_selection in self.GAME_MODES:
                current_index = self.GAME_MODES.index(self.current_selection)
            else:
                current_index = 0
            self.current_selection = self.GAME_MODES[(current_index + 1) % len(self.GAME_MODES)]

            span.set_attribute("game.name", self.current_selection)

            await self._publish_event(  # Phase 34: await
                "selection_changed",
                {"game_name": self.current_selection, "source": "controller", "serial": serial},
            )
            await self._save_current_game_setting()
            logger.info(f"Selection changed via controller {serial}: {self.current_selection}")

            # Phase 60: Play game mode voice announcement
            voice_file = self.GAME_MODE_VOICE.get(self.current_selection)
            if voice_file:
                await self._play_voice(voice_file)

            # Phase 39: Force lobby color update for all controllers to reflect new game mode
            # Clear the state so colors update on next _update_lobby_feedback call
            self.controller_lobby_state.clear()
            self.last_lobby_feedback_update.clear()


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

    # Start system metrics collection (Phase 61: extracted to lib/system_metrics.py)
    # Phase 59: Track background tasks for cleanup
    background_tasks = []
    metrics_task = start_system_metrics_collector(
        cpu_gauge=metrics.process_cpu_percent,
        memory_gauge=metrics.process_memory_mb,
        threads_gauge=metrics.process_threads,
    )
    background_tasks.append(metrics_task)

    # Create server with keepalive options to match client settings
    from lib.grpc_utils import get_server_options

    server = grpc.aio.server(options=get_server_options())

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

    # Start game event monitoring (stops button monitor during games)
    await menu_servicer.start_game_event_monitor()

    # Auto-start menu (so controllers light up immediately)
    auto_start = os.getenv("MENU_AUTO_START", "true").lower() == "true"
    if auto_start:
        menu_servicer.state = menu_pb2.MenuState.RUNNING
        menu_servicer.current_selection = "JoustFFA"
        logger.info("Menu auto-started (MENU_AUTO_START=true)")

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
        await menu_servicer.stop_game_event_monitor()
        await menu_servicer.shutdown()  # Phase 26: Close persistent channels
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
