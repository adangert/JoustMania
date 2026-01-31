"""Menu gRPC Servicer for JoustMania."""

import asyncio
import logging
import os
import time

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from lib.telemetry import get_tracer
from lib.types import Games
from proto import menu_pb2, menu_pb2_grpc
from services.menu import metrics
from services.menu.controller_events import ControllerEventLoop
from services.menu.event_publisher import EventPublisher
from services.menu.handlers import AdminModeHandler, ConnectedHandler, ReadyHandler
from services.menu.handlers.base import ControllerState
from services.menu.state_manager import StateManager
from services.menu.utils import AudioHelper, LedController, SettingsHelper
from services.menu.utils.audio import GAME_MODE_VOICE
from services.menu.utils.settings import GAME_MODES

logger = logging.getLogger(__name__)

# Lazy telemetry initialization - defers OTLP setup until first span
tracer = get_tracer(__name__)


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
        self.current_selection: Games = Games.JoustFFA

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
        await self.state_manager.on_controller_connected(serial)

    async def on_disconnect(self, serial: str) -> None:
        """Handle controller disconnect event (ControllerEventCallbacks)."""
        await self.state_manager.on_controller_disconnected(serial)

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

    # Controller state properties (delegate to state_manager as single source of truth)

    @property
    def ready_controllers(self) -> set[str]:
        """Controllers in READY state (delegates to state_manager)."""
        return self.state_manager.ready_controllers

    @property
    def connected_controllers(self) -> set[str]:
        """All connected controllers (delegates to state_manager)."""
        return self.state_manager.connected_controllers

    @property
    def ready_controller_count(self) -> int:
        """Number of ready controllers (computed from state_manager)."""
        return len(self.state_manager.ready_controllers)

    def _clear_ready_state(self) -> None:
        """Clear ready controllers and associated metrics.

        Transitions all READY controllers back to CONNECTED state and
        clears associated metrics. Used when game starts or menu stops.
        """
        # Transition ready controllers back to connected
        for serial in list(self.state_manager.ready_controllers):
            self.state_manager.controller_states[serial] = ControllerState.CONNECTED

        # Clear metrics
        metrics.player_ready.clear()
        logger.debug("Ready state cleared")

    # gRPC service methods (names defined by proto)

    async def StartMenu(self, _request, _context):
        """Start the menu."""
        start_time = time.time()
        with tracer.start_as_current_span("StartMenu") as span:
            try:
                if self.state == menu_pb2.MenuState.RUNNING:
                    metrics.grpc_requests_total.labels(method="StartMenu", status="already_running").inc()
                    return menu_pb2.StartMenuResponse(success=False, error="Menu already running")

                self.state = menu_pb2.MenuState.RUNNING
                self._clear_ready_state()

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

    async def StopMenu(self, _request, _context):
        """Stop the menu."""
        start_time = time.time()
        with tracer.start_as_current_span("StopMenu") as span:
            try:
                if self.state == menu_pb2.MenuState.STOPPED:
                    metrics.grpc_requests_total.labels(method="StopMenu", status="already_stopped").inc()
                    return menu_pb2.StopMenuResponse(success=False, error="Menu already stopped")

                self.state = menu_pb2.MenuState.STOPPED

                # Clear all lobby state
                self._clear_ready_state()
                self.state_manager.controller_states.clear()

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

    async def ProcessInput(self, request, _context):
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

    async def StreamMenuEvents(self, _request, context):
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
            self.current_selection = self.settings_helper.get_next_game_mode(self.current_selection)
            self.state_manager.set_game_mode(self.current_selection)
            await self.event_publisher.publish("selection_changed", {"game_name": self.current_selection.name})
            await self.settings_helper.save_current_game(self.current_selection)
            logger.info(f"Selection changed to: {self.current_selection.name}")

    async def _handle_web_command(self, data: dict, span) -> None:
        """Handle web_command input type."""
        command = data.get("command", "")
        span.set_attribute("command", command)

        if command == "start_game":
            await self._start_game(serial="web", source="web")

        elif command == "select_game":
            game_name = data.get("game_name", "")
            game_mode = Games.from_name(game_name)
            if game_mode is not None and game_name in GAME_MODES:
                self.current_selection = game_mode
                self.state_manager.set_game_mode(game_mode)
                await self.event_publisher.publish("selection_changed", {"game_name": game_mode.name, "source": "web"})
                await self.settings_helper.save_current_game(game_mode)
                voice_file = GAME_MODE_VOICE.get(game_mode.name)
                if voice_file:
                    await self.audio.play_voice(voice_file)
                logger.info(f"Game selected via web: {game_mode.name}")
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
            span.set_attribute("game.name", self.current_selection.name)
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
            metrics.player_ready.clear()
            logger.info("Button monitor and lobby music stopped for game start")

            self.state = menu_pb2.MenuState.GAME_STARTING

            # Build player list for GameCoordinator
            players = [
                game_coordinator_pb2.Player(serial=s, team=i % 2, alive=True, score=0)
                for i, s in enumerate(controllers)
            ]

            # Build typed start config (current_selection is already a Games enum)
            config = self._build_game_config(self.current_selection, players)

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
                f"{self.current_selection.name} with {len(controllers)} players"
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

                        # Clear ready state now that game has started (Issue #256)
                        # This ensures dead players don't show in player insights dashboard
                        self._clear_ready_state()
                        logger.info("Ready state cleared on game start confirmation")

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
            # Reset state_manager and re-register controllers (sets lobby colors)
            await self.state_manager.reset()

        with tracer.start_as_current_span("restart_lobby_music"):
            await self.audio.start_lobby_music()

        logger.info("Lobby restarted after game")

    def _build_game_config(self, game_mode, players: list):
        """
        Build typed StartGameConfig for a game mode.

        Args:
            game_mode: Games enum value from lib.types
            players: List of Player protobuf messages

        Returns:
            StartGameConfig with appropriate mode-specific config
        """
        from proto import game_coordinator_pb2

        # Get game settings from state_manager (set via admin mode)
        settings = getattr(self.state_manager, "game_settings", {})
        sensitivity = settings.get("sensitivity", 2)

        # Build base config with the game mode's name
        config = game_coordinator_pb2.StartGameConfig(
            game_name=game_mode.name,
            players=players,
            sensitivity=sensitivity,
        )

        # Build mode-specific config using pattern matching
        match game_mode:
            case Games.JoustFFA:
                config.ffa_config.CopyFrom(game_coordinator_pb2.FFAConfig())

            case Games.JoustTeams:
                config.teams_config.CopyFrom(
                    game_coordinator_pb2.TeamsConfig(
                        num_teams=settings.get("num_teams", 2),
                        random_assignment=settings.get("random_assignment", True),
                    )
                )

            case Games.JoustRandomTeams:
                config.random_teams_config.CopyFrom(
                    game_coordinator_pb2.RandomTeamsConfig(
                        num_teams=settings.get("num_teams", 2),
                    )
                )

            case Games.NonStop:
                config.nonstop_config.CopyFrom(
                    game_coordinator_pb2.NonstopConfig(
                        time_limit_seconds=settings.get("nonstop_time_limit", 0),
                    )
                )

            case Games.Tournament:
                config.tournament_config.CopyFrom(
                    game_coordinator_pb2.TournamentConfig(
                        invincibility_seconds=settings.get("invincibility", 4.0),
                    )
                )

            case Games.FightClub:
                config.fight_club_config.CopyFrom(
                    game_coordinator_pb2.FightClubConfig(
                        invincibility_seconds=settings.get("invincibility", 4.0),
                        min_rounds=settings.get("fight_club_min_rounds", 10),
                    )
                )

            case Games.Werewolf:
                config.werewolf_config.CopyFrom(
                    game_coordinator_pb2.WerewolfConfig(
                        reveal_time_seconds=settings.get("werewolf_reveal_time", 35.0),
                    )
                )

            case Games.Zombies:
                config.zombie_config.CopyFrom(game_coordinator_pb2.ZombieConfig())

            case Games.Swapper:
                config.swapper_config.CopyFrom(game_coordinator_pb2.SwapperConfig())

            case Games.Traitor:
                config.traitor_config.CopyFrom(
                    game_coordinator_pb2.TraitorConfig(
                        num_teams=settings.get("traitor_num_teams", 0),
                    )
                )

        return config
