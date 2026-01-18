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

from services.menu.controller_events import ControllerEventLoop
from services.menu.event_publisher import EventPublisher
from services.menu.handlers import AdminModeHandler, ConnectedHandler, ReadyHandler
from services.menu.state_manager import StateManager
from services.menu.utils import AudioHelper, LedController, SettingsHelper
from services.menu.utils.audio import GAME_MODE_VOICE
from services.menu.utils.settings import GAME_MODES

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

        # Game event monitoring - stops controller event loop during games
        self.game_event_task = None
        self.game_event_monitor_running = False

        # Lobby state tracking (Phase 39)
        self.ready_controllers: set[str] = set()
        self.connected_controllers: set[str] = set()
        self.controller_lobby_state: dict[str, str] = {}
        self.last_lobby_feedback_update: dict[str, float] = {}

        # Persistent gRPC channels (Phase 26 - Performance, Phase 33 - shared utilities)
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

        # Utility classes (SOLID refactor)
        self.led = LedController(self.controller_channel)
        self.audio = AudioHelper(self.audio_channel)
        self.settings_helper = SettingsHelper(self.settings_channel)

        # Event publisher for streaming menu events
        self.event_publisher = EventPublisher(tracer, metrics)

        # State manager and handlers (SOLID refactor)
        self.state_manager = StateManager(
            led=self.led,
            audio=self.audio,
            settings=self.settings_helper,
            publish_event=self.event_publisher.publish,
        )

        # Register handlers with state manager
        self.connected_handler = ConnectedHandler()
        self.ready_handler = ReadyHandler(start_game_callback=self._start_game)
        self.state_manager.register_handler(self.connected_handler)
        self.state_manager.register_handler(self.ready_handler)

        # Phase 60: Voice actor setting (aaron or ivy)
        self.voice_actor = "ivy"  # Default matches settings schema

        # Admin mode handler
        self.admin_handler = AdminModeHandler(
            controller_channel=self.controller_channel,
            tracer=tracer,
            callbacks=self,  # Menu implements AdminModeCallbacks
            metrics=metrics,
        )
        self.state_manager.register_handler(self.admin_handler)

        # Controller event loop (handles button and connection events)
        self.controller_events = ControllerEventLoop(
            controller_channel=self.controller_channel,
            led=self.led,
            callbacks=self,  # Menu implements ControllerEventCallbacks
            metrics=metrics,
        )

        logger.info("Menu service initialized with persistent gRPC channels")

    # AdminModeCallbacks protocol implementation

    def set_menu_state(self, state) -> None:
        """Set the menu state (AdminModeCallbacks)."""
        self.state = state

    def get_game_options(self) -> list[str]:
        """Get list of available game options (AdminModeCallbacks)."""
        return self.game_options if hasattr(self, "game_options") else []

    # ControllerEventCallbacks protocol implementation

    def get_menu_state(self) -> int:
        """Get current menu state (ControllerEventCallbacks)."""
        return self.state

    async def on_connect(self, serial: str) -> None:
        """Handle controller connect event (ControllerEventCallbacks)."""
        self.connected_controllers.add(serial)
        await self.state_manager.on_controller_connected(serial)

    async def on_disconnect(self, serial: str) -> None:
        """Handle controller disconnect event (ControllerEventCallbacks)."""
        await self.state_manager.on_controller_disconnected(serial)
        self.connected_controllers.discard(serial)
        self.ready_controllers.discard(serial)
        self.controller_lobby_state.pop(serial, None)
        self.last_lobby_feedback_update.pop(serial, None)
        self.ready_controller_count = len(self.ready_controllers)

    async def on_button(self, serial: str, button: str, is_press: bool) -> None:
        """Handle button event (ControllerEventCallbacks)."""
        # Check for admin mode combo (all 4 face buttons pressed)
        button_state = self.state_manager.button_states.get(serial, {})
        if is_press and button in ["cross", "circle", "square", "triangle"]:
            # Preview what button state will be after this press
            preview_state = dict(button_state)
            preview_state[button] = True
            if self.admin_handler.check_combo_from_state(preview_state):
                if not self.admin_handler.combo_shown:
                    self.admin_handler.combo_shown = True
                    from services.menu.handlers.base import ControllerState

                    await self.state_manager.transition_to(serial, ControllerState.ADMIN)
                # Update button state but don't process as individual button
                await self.state_manager.handle_button_event(serial, button, is_press)
                return

        # Reset admin combo flag when any face button released
        if not is_press and button in ["cross", "circle", "square", "triangle"]:
            self.admin_handler.combo_shown = False

        # Route to StateManager
        await self.state_manager.handle_button_event(serial, button, is_press)

    async def StartMenu(self, request, context):
        """Start the menu (async)."""
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
                await self.audio.start_lobby_music()

                # Publish menu_started event (Phase 34: await)
                await self.event_publisher.publish("menu_started", {})

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
        """Stop the menu (async)."""
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
                await self.event_publisher.publish("menu_stopped", {})

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
        """Process menu input (async)."""
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
                        await self.event_publisher.publish(
                            "game_requested",
                            {"game_name": self.current_selection, "controllers": controllers},
                        )
                        logger.info(f"Game requested: {self.current_selection} with {len(controllers)} players")

                    elif button == "select":
                        # Move to next game (Phase 59: use GAME_MODES constant)
                        if self.current_selection in GAME_MODES:
                            current_index = GAME_MODES.index(self.current_selection)
                        else:
                            current_index = 0
                        self.current_selection = GAME_MODES[(current_index + 1) % len(GAME_MODES)]
                        self.state_manager.set_game_mode(self.current_selection)
                        await self.event_publisher.publish("selection_changed", {"game_name": self.current_selection})
                        await self._save_current_game_setting()
                        logger.info(f"Selection changed to: {self.current_selection}")

                elif input_type == "web_command":
                    command = data.get("command", "")
                    span.set_attribute("command", command)

                    if command == "start_game":
                        # Web start - use ready controllers
                        controllers = list(self.ready_controllers)
                        self.state = menu_pb2.MenuState.GAME_STARTING
                        await self.event_publisher.publish(
                            "game_requested",
                            {"game_name": self.current_selection, "source": "web", "controllers": controllers},
                        )
                        logger.info(f"Game requested via web: {self.current_selection} with {len(controllers)} players")

                    # Phase 59: Add select_game command for web UI
                    elif command == "select_game":
                        game_name = data.get("game_name", "")
                        if game_name in GAME_MODES:
                            self.current_selection = game_name
                            self.state_manager.set_game_mode(game_name)
                            await self.event_publisher.publish(
                                "selection_changed", {"game_name": game_name, "source": "web"}
                            )
                            await self._save_current_game_setting()
                            # Phase 60: Play game mode voice announcement
                            voice_file = GAME_MODE_VOICE.get(game_name)
                            if voice_file:
                                await self.audio.play_voice(voice_file)
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
                        await self.event_publisher.publish("game_start_cancelled", {})
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
        """Stream menu events in real-time."""
        subscriber_id = f"menu_events_{time.time()}"
        metrics.stream_connections_active.inc()

        with tracer.start_as_current_span("StreamMenuEvents") as span:
            span.set_attribute("subscriber.id", subscriber_id)

            event_queue = await self.event_publisher.subscribe(subscriber_id)

            try:
                while not context.cancelled():
                    try:
                        event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                        yield event
                    except TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"Stream error for {subscriber_id}: {e}")
                        break
            finally:
                await self.event_publisher.unsubscribe(subscriber_id)
                metrics.stream_connections_active.dec()

    async def start_button_monitor(self):
        """Start the controller event loop."""
        await self.controller_events.start()

    async def stop_button_monitor(self):
        """Stop the controller event loop."""
        await self.controller_events.stop()

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
                            await self.audio.stop_lobby_music()  # Phase 70: Stop lobby music
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

                        # Phase 70: Restart lobby music
                        await self.audio.start_lobby_music()

                        # Restart button monitor
                        await self.start_button_monitor()

                        # Publish event so UI knows game ended
                        await self.event_publisher.publish(GameEvent.GAME_ENDED, event.data)

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

            if response.value and response.value in GAME_MODES:
                self.current_selection = response.value
                self.state_manager.set_game_mode(response.value)
                logger.info(f"Loaded current game mode: {self.current_selection}")
            else:
                self.current_selection = "JoustFFA"
                self.state_manager.set_game_mode("JoustFFA")
                logger.debug(f"Current game setting not found, using default: {self.current_selection}")

        except Exception as e:
            self.current_selection = "JoustFFA"
            self.state_manager.set_game_mode("JoustFFA")
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

    async def _handle_controller_disconnect(self, serial: str):
        """
        Clean up state for a disconnected controller (Phase 58).

        Args:
            serial: Controller serial number
        """
        self.connected_controllers.discard(serial)
        self.ready_controllers.discard(serial)
        self.controller_lobby_state.pop(serial, None)
        self.last_lobby_feedback_update.pop(serial, None)

        # Update ready count
        self.ready_controller_count = len(self.ready_controllers)

        # If admin mode controller disconnected, reset admin mode state
        self.admin_handler.reset_on_disconnect(serial)

        logger.info(f"Controller {serial} disconnected, state cleaned up")

    async def _start_game(self, serial: str):
        """
        Start the game when all players are ready.

        Called by ReadyHandler when all controllers are ready.

        Args:
            serial: Serial of controller that triggered the start
        """
        metrics.button_presses_total.labels(button="trigger", action="press").inc()

        with tracer.start_as_current_span("start_game") as span:
            span.set_attribute("controller.serial", serial)
            span.set_attribute("game.name", self.current_selection)

            # Pass ready controllers directly - menu is source of truth
            controllers = list(self.ready_controllers)
            span.set_attribute("controller.count", len(controllers))

            self.state = menu_pb2.MenuState.GAME_STARTING
            await self.event_publisher.publish(
                "game_requested",
                {
                    "game_name": self.current_selection,
                    "source": "controller",
                    "serial": serial,
                    "controllers": controllers,
                },
            )
            logger.info(
                f"Game requested via controller {serial}: {self.current_selection} with {len(controllers)} players"
            )


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
