"""Menu gRPC Servicer for JoustMania."""

import asyncio
import logging
import os
import time

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from lib.telemetry import init_telemetry
from proto import menu_pb2, menu_pb2_grpc
from services.menu import metrics
from services.menu.controller_events import ControllerEventLoop
from services.menu.event_publisher import EventPublisher
from services.menu.handlers import AdminModeHandler, ConnectedHandler, ReadyHandler
from services.menu.state_manager import StateManager
from services.menu.utils import AudioHelper, LedController, SettingsHelper
from services.menu.utils.audio import GAME_MODE_VOICE
from services.menu.utils.settings import GAME_MODES

logger = logging.getLogger(__name__)

# Initialize OpenTelemetry
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
        self.state = menu_pb2.MenuState.STOPPED
        self.current_selection = "JoustFFA"
        self.ready_controller_count = 0

        # Lobby state tracking
        self.ready_controllers: set[str] = set()
        self.connected_controllers: set[str] = set()
        self.controller_lobby_state: dict[str, str] = {}
        self.last_lobby_feedback_update: dict[str, float] = {}

        # Persistent gRPC channels
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

        # Utility classes
        self.led = LedController(self.controller_channel)
        self.audio = AudioHelper(self.audio_channel)
        self.settings_helper = SettingsHelper(self.settings_channel)

        # Event publisher for streaming menu events
        self.event_publisher = EventPublisher(tracer, metrics)

        # State manager and handlers
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

        # Voice actor setting (aaron or ivy)
        self.voice_actor = "ivy"

        # Admin mode handler
        self.admin_handler = AdminModeHandler(
            controller_channel=self.controller_channel,
            tracer=tracer,
            callbacks=self,
            metrics=metrics,
        )
        self.state_manager.register_handler(self.admin_handler)

        # Controller event loop (handles button and connection events)
        self.controller_events = ControllerEventLoop(
            controller_channel=self.controller_channel,
            led=self.led,
            callbacks=self,
            metrics=metrics,
        )

        logger.info("Menu service initialized")

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

    def update_battery(self, serial: str, battery: int) -> None:
        """Update battery level for a controller (ControllerEventCallbacks)."""
        self.state_manager.update_battery(serial, battery)

    async def on_button(self, serial: str, button: str, is_press: bool) -> None:
        """Handle button event (ControllerEventCallbacks)."""
        # Check for admin mode combo (all 4 face buttons pressed)
        button_state = self.state_manager.button_states.get(serial, {})
        if is_press and button in ["cross", "circle", "square", "triangle"]:
            preview_state = dict(button_state)
            preview_state[button] = True
            if self.admin_handler.check_combo_from_state(preview_state):
                if not self.admin_handler.combo_shown:
                    self.admin_handler.combo_shown = True
                    from services.menu.handlers.base import ControllerState

                    await self.state_manager.transition_to(serial, ControllerState.ADMIN)
                await self.state_manager.handle_button_event(serial, button, is_press)
                return

        # Reset admin combo flag when any face button released
        if not is_press and button in ["cross", "circle", "square", "triangle"]:
            self.admin_handler.combo_shown = False

        await self.state_manager.handle_button_event(serial, button, is_press)

    # gRPC service methods (names defined by proto)

    async def StartMenu(self, request, context):  # noqa: N802, ARG002
        """Start the menu."""
        start_time = time.time()
        with tracer.start_as_current_span("StartMenu") as span:
            try:
                if self.state == menu_pb2.MenuState.RUNNING:
                    metrics.grpc_requests_total.labels(method="StartMenu", status="already_running").inc()
                    return menu_pb2.StartMenuResponse(success=False, error="Menu already running")

                self.state = menu_pb2.MenuState.RUNNING
                self.ready_controller_count = 0

                # Load settings
                self.voice_actor = await self.settings_helper.load_voice_actor()
                self.current_selection = await self.settings_helper.load_current_game()
                self.state_manager.set_game_mode(self.current_selection)

                await self.audio.start_lobby_music()
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

    async def StopMenu(self, request, context):  # noqa: N802, ARG002
        """Stop the menu."""
        start_time = time.time()
        with tracer.start_as_current_span("StopMenu") as span:
            try:
                if self.state == menu_pb2.MenuState.STOPPED:
                    metrics.grpc_requests_total.labels(method="StopMenu", status="already_stopped").inc()
                    return menu_pb2.StopMenuResponse(success=False, error="Menu already stopped")

                self.state = menu_pb2.MenuState.STOPPED

                # Clear lobby state
                self.ready_controllers.clear()
                self.connected_controllers.clear()
                self.controller_lobby_state.clear()
                self.last_lobby_feedback_update.clear()
                self.ready_controller_count = 0

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

    async def ProcessInput(self, request, context):  # noqa: N802, ARG002
        """Process menu input."""
        start_time = time.time()
        with tracer.start_as_current_span("ProcessInput") as span:
            span.set_attribute("input.type", request.input_type)

            try:
                input_type = request.input_type
                data = dict(request.data)

                if input_type == "button_press":
                    await self._handle_button_input(data, span)
                elif input_type == "web_command":
                    await self._handle_web_command(data, span)
                elif input_type == "reset_menu":
                    await self._handle_reset_menu()

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

    async def StreamMenuEvents(self, request, context):  # noqa: N802, ARG002
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

    # Input handlers

    async def _handle_button_input(self, data: dict, span) -> None:
        """Handle button_press input type."""
        button = data.get("button", "")
        span.set_attribute("button", button)

        if button == "trigger":
            await self._start_game(serial="process_input", source="button_input")

        elif button == "select":
            current_index = GAME_MODES.index(self.current_selection) if self.current_selection in GAME_MODES else 0
            self.current_selection = GAME_MODES[(current_index + 1) % len(GAME_MODES)]
            self.state_manager.set_game_mode(self.current_selection)
            await self.event_publisher.publish("selection_changed", {"game_name": self.current_selection})
            await self.settings_helper.save_current_game(self.current_selection)
            logger.info(f"Selection changed to: {self.current_selection}")

    async def _handle_web_command(self, data: dict, span) -> None:
        """Handle web_command input type."""
        command = data.get("command", "")
        span.set_attribute("command", command)

        if command == "start_game":
            await self._start_game(serial="web", source="web")

        elif command == "select_game":
            game_name = data.get("game_name", "")
            if game_name in GAME_MODES:
                self.current_selection = game_name
                self.state_manager.set_game_mode(game_name)
                await self.event_publisher.publish("selection_changed", {"game_name": game_name, "source": "web"})
                await self.settings_helper.save_current_game(self.current_selection)
                voice_file = GAME_MODE_VOICE.get(game_name)
                if voice_file:
                    await self.audio.play_voice(voice_file)
                self.controller_lobby_state.clear()
                self.last_lobby_feedback_update.clear()
                logger.info(f"Game selected via web: {game_name}")
            else:
                logger.warning(f"Unknown game mode requested via web: {game_name}")

    async def _handle_reset_menu(self) -> None:
        """Handle reset_menu input type."""
        if self.state == menu_pb2.MenuState.GAME_STARTING:
            self.state = menu_pb2.MenuState.RUNNING
            await self.event_publisher.publish("game_start_cancelled", {})
            logger.info("Menu reset to RUNNING state (game start cancelled)")

    # Lifecycle methods

    async def start_button_monitor(self):
        """Start the controller event loop."""
        await self.controller_events.start()

    async def stop_button_monitor(self):
        """Stop the controller event loop."""
        await self.controller_events.stop()

    @property
    def button_monitor_running(self) -> bool:
        """Check if button monitor is running."""
        return self.controller_events.is_running

    async def start_game_event_monitor(self):
        """Start the game event monitoring task (no-op, kept for compatibility)."""
        # Game events are now handled by _start_game() stream directly
        # No separate persistent subscription needed
        logger.info("Game event monitor: events handled by game stream")

    async def stop_game_event_monitor(self):
        """Stop the game event monitoring task (no-op, kept for compatibility)."""
        logger.info("Game event monitor stopped")

    async def shutdown(self):
        """Cleanup resources on shutdown."""
        logger.info("Shutting down Menu service, closing gRPC channels...")
        await self.controller_channel.close()
        await self.settings_channel.close()
        await self.game_coordinator_channel.close()
        await self.audio_channel.close()
        logger.info("Menu service gRPC channels closed")

    async def _start_game(self, serial: str, source: str = "controller"):
        """
        Schedule game start as a background task.

        This is called from button event handlers, so we can't block or stop
        the button monitor synchronously. Instead, schedule the game lifecycle
        to run after a brief delay.

        Args:
            serial: Controller serial that triggered the start (for logging)
            source: Source of the start request ("controller" or "web")
        """
        # Schedule game lifecycle as background task to avoid blocking button monitor
        task = asyncio.create_task(self._run_game_lifecycle(serial, source))

        # Log any exceptions from the background task
        def _log_exception(t):
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(f"Game lifecycle task failed: {exc}", exc_info=exc)

        task.add_done_callback(_log_exception)

    async def _run_game_lifecycle(self, serial: str, source: str = "controller"):
        """
        Run the full game lifecycle via StreamGameEvents.

        This function:
        1. Stops button monitor and lobby music
        2. Creates game event stream with start_config
        3. Handles all game events until game ends
        4. Restarts button monitor and lobby music when done

        Args:
            serial: Controller serial that triggered the start (for logging)
            source: Source of the start request ("controller" or "web")
        """
        from lib.types import GameEvent
        from proto import game_coordinator_pb2, game_coordinator_pb2_grpc

        # Brief delay to let button monitor finish current event dispatch
        await asyncio.sleep(0.1)

        metrics.button_presses_total.labels(button="trigger", action="press").inc()

        # Determine trace context for the game:
        # - Web source: inherit current context (connects to dashboard trace)
        # - Controller/button sources: fresh context (prevents chaining to previous game)
        span_ctx = None if source == "web" else otel_context.Context()
        with tracer.start_as_current_span("start_game", context=span_ctx) as span:
            span.set_attribute("controller.serial", serial)
            span.set_attribute("game.name", self.current_selection)
            span.set_attribute("game.source", source)

            # Get controllers from state_manager (source of truth)
            controllers = list(self.state_manager.ready_controllers)
            span.set_attribute("controller.count", len(controllers))

            if len(controllers) < 2:
                logger.warning(f"Not enough players to start game: {len(controllers)}")
                return

            # Stop button monitor and lobby music before starting game
            with tracer.start_as_current_span("stop_lobby_music"):
                await self.audio.stop_lobby_music()

            with tracer.start_as_current_span("stop_button_monitor"):
                await self.stop_button_monitor()

            # Clear menu_player_ready metrics so dashboard only shows game_player_alive
            metrics.player_ready._metrics.clear()
            logger.info("Button monitor and lobby music stopped for game start")

            self.state = menu_pb2.MenuState.GAME_STARTING

            # Build player list for GameCoordinator
            players = [
                game_coordinator_pb2.Player(serial=s, team=i % 2, alive=True, score=0)
                for i, s in enumerate(controllers)
            ]

            # Create start config
            config = game_coordinator_pb2.StartGameConfig(
                game_name=self.current_selection,
                players=players,
                settings={},
            )

            # Inject trace context into gRPC metadata
            propagator = TraceContextTextMapPropagator()
            carrier: dict[str, str] = {}
            propagator.inject(carrier)
            metadata = list(carrier.items())

            # Call GameCoordinator.StreamGameEvents with start_config
            stub = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(self.game_coordinator_channel)
            request = game_coordinator_pb2.StreamEventsRequest(start_config=config)

            logger.info(
                f"Starting game via GameCoordinator stream ({source}): "
                f"{self.current_selection} with {len(controllers)} players"
            )

            stream = None
            try:
                # Create stream and iterate through events
                stream = stub.StreamGameEvents(request, metadata=metadata)
                first_event_received = False

                async for event in stream:
                    if not first_event_received:
                        # First event - check if game started successfully
                        first_event_received = True

                        if event.event_type == "game_start_error":
                            error = event.data.get("error", "Unknown error")
                            logger.error(f"Game start failed: {error}")
                            span.set_attribute("error", error)
                            self.state = menu_pb2.MenuState.RUNNING
                            # Restart lobby on error
                            await self._restart_lobby()
                            return

                        logger.info(f"Game started successfully: {event.event_type}")
                        span.set_attribute("game.started", True)

                    logger.info(f"Game event received: {event.event_type}")

                    if GameEvent.is_game_ending(event.event_type):
                        logger.info(f"Game ended: {event.event_type}")
                        # Publish game ended event for other subscribers
                        await self.event_publisher.publish(GameEvent.GAME_ENDED, event.data)
                        break

                # Game ended normally - restart lobby
                await self._restart_lobby()

            except asyncio.CancelledError:
                logger.info("Game stream cancelled")
                raise
            except Exception as e:
                logger.error(f"Game stream error: {e}", exc_info=True)
                span.record_exception(e)
                # Restart lobby on error
                await self._restart_lobby()
            finally:
                # Ensure stream is closed
                if stream is not None:
                    stream.cancel()

    async def _restart_lobby(self):
        """Restart lobby state after game ends."""
        self.state = menu_pb2.MenuState.RUNNING

        # Start button monitor with fresh trace context (not chained to game trace)
        with tracer.start_as_current_span("restart_button_monitor", context=otel_context.Context()):
            await self.start_button_monitor()
            await self.controller_events.wait_for_connection()

        # Reset lobby state
        with tracer.start_as_current_span("reset_lobby_state"):
            self.ready_controllers.clear()
            self.connected_controllers.clear()
            self.controller_lobby_state.clear()
            self.last_lobby_feedback_update.clear()
            self.ready_controller_count = 0
            # Reset state_manager and re-register controllers (sets lobby colors)
            re_registered = await self.state_manager.reset()
            self.connected_controllers.update(re_registered)

        with tracer.start_as_current_span("restart_lobby_music"):
            await self.audio.start_lobby_music()

        logger.info("Lobby restarted after game")
