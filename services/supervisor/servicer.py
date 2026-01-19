"""
Supervisor Orchestrator for JoustMania

Orchestrates game lifecycle by:
- Subscribing to Menu events
- Starting games via GameCoordinator when requested

Note: This is a pure gRPC client service - it doesn't expose any endpoints.
"""

import asyncio
import contextlib
import json
import logging

import grpc
import grpc.aio
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from lib.grpc_utils import create_channel
from lib.telemetry import init_telemetry
from proto import (
    game_coordinator_pb2,
    game_coordinator_pb2_grpc,
    menu_pb2,
    menu_pb2_grpc,
)

logger = logging.getLogger(__name__)

# Initialize OpenTelemetry
tracer = init_telemetry()


class SupervisorOrchestrator:
    """
    Supervisor orchestrator for game lifecycle.

    Subscribes to Menu events and starts games via GameCoordinator.
    This is a pure client service - it doesn't expose any gRPC endpoints.
    """

    def __init__(self):
        """Initialize supervisor orchestrator."""
        # gRPC clients for orchestration
        self.menu_channel = None
        self.menu_stub = None
        self.game_coordinator_channel = None
        self.game_coordinator_stub = None

        # Orchestration state
        self.menu_event_task = None
        self.orchestration_running = False

        logger.info("Supervisor orchestrator initialized")

    async def _init_grpc_clients(self):
        """Initialize gRPC clients for orchestration with trace propagation."""
        try:
            # Menu service (with tracing for context propagation)
            self.menu_channel = create_channel("menu:50054")
            self.menu_stub = menu_pb2_grpc.MenuServiceStub(self.menu_channel)
            logger.info("Connected to Menu service for orchestration")

            # Game Coordinator service (with tracing for StartGame calls)
            self.game_coordinator_channel = create_channel("game-coordinator:50053")
            self.game_coordinator_stub = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(
                self.game_coordinator_channel
            )
            logger.info("Connected to Game Coordinator service for orchestration")

        except Exception as e:
            logger.error(f"Failed to initialize orchestration gRPC clients: {e}", exc_info=True)
            raise

    async def start_orchestration(self):
        """Start game orchestration - subscribe to menu events."""
        if self.orchestration_running:
            logger.warning("Orchestration already running")
            return

        try:
            # Initialize gRPC clients
            await self._init_grpc_clients()

            # Start menu event listener
            self.orchestration_running = True
            self.menu_event_task = asyncio.create_task(self._menu_event_listener())
            logger.info("Game orchestration started")

        except Exception as e:
            logger.error(f"Failed to start orchestration: {e}", exc_info=True)
            self.orchestration_running = False

    async def _menu_event_listener(self):
        """Listen to menu events and orchestrate game lifecycle."""
        try:
            # Subscribe to menu events
            request = menu_pb2.StreamMenuEventsRequest()

            logger.info("Subscribing to menu events...")

            async for event in self.menu_stub.StreamMenuEvents(request):
                # Extract W3C Trace Context from event data (injected by Menu service)
                # This links the Supervisor's spans to the Menu's trace
                propagator = TraceContextTextMapPropagator()
                carrier = {
                    "traceparent": event.data.get("_traceparent", ""),
                    "tracestate": event.data.get("_tracestate", ""),
                }
                ctx = propagator.extract(carrier)

                # Create span with extracted context as parent
                with tracer.start_as_current_span("handle_menu_event", context=ctx) as span:
                    span.set_attribute("event.type", event.event_type)
                    logger.info(f"Received menu event: {event.event_type}")

                    # Handle game_requested event
                    if event.event_type == "game_requested":
                        await self._handle_game_requested(event)

        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.CANCELLED:
                logger.info("Menu event stream cancelled")
            else:
                logger.error(f"Menu event stream error: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error in menu event listener: {e}", exc_info=True)
        finally:
            self.orchestration_running = False
            logger.info("Menu event listener stopped")

    async def _handle_game_requested(self, event: menu_pb2.MenuEvent):
        """
        Handle game_requested event from menu - start the game.

        This creates the trace link: Menu Event -> Supervisor -> StartGame -> Game

        The menu passes the controller list directly in the event - it is the
        source of truth for which controllers should participate in the game.
        """
        with tracer.start_as_current_span("orchestrate_game_start") as span:
            try:
                game_name = event.data.get("game_name", "JoustFFA")
                source = event.data.get("source", "unknown")
                span.set_attribute("game.name", game_name)
                span.set_attribute("game.source", source)

                logger.info(f"Orchestrating game start: {game_name} (source: {source})")

                # Get controllers from event - menu is source of truth
                # Controllers are JSON-encoded since MenuEvent.data is map<string, string>
                controllers_json = event.data.get("controllers", "[]")
                try:
                    controller_serials = json.loads(controllers_json) if controllers_json else []
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode controllers JSON: {controllers_json}")
                    controller_serials = []

                if not controller_serials:
                    logger.error("No controllers in event - Menu must provide controller list")
                    span.set_attribute("error", "no_controllers_in_event")
                    return

                logger.info(f"Starting game with {len(controller_serials)} controllers: {controller_serials}")

                # Convert controller serials to players
                players = []
                for i, serial in enumerate(controller_serials):
                    players.append(game_coordinator_pb2.Player(serial=serial, team=i % 2, alive=True, score=0))

                span.set_attribute("player.count", len(players))

                # Inject trace context into gRPC metadata for cross-service propagation
                propagator = TraceContextTextMapPropagator()
                carrier: dict[str, str] = {}
                propagator.inject(carrier)
                metadata = list(carrier.items())

                # Call game coordinator to start game with trace context
                start_response = await self.game_coordinator_stub.StartGame(
                    game_coordinator_pb2.StartGameRequest(game_name=game_name, players=players),
                    metadata=metadata,
                )

                if start_response.success:
                    logger.info(f"Game started successfully: {start_response.game_id}")
                    span.set_attribute("game.id", start_response.game_id)
                else:
                    logger.error(f"Failed to start game: {start_response.error}")
                    span.set_attribute("error", start_response.error)

            except Exception as e:
                logger.error(f"Error handling game_requested: {e}", exc_info=True)
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

    async def shutdown(self):
        """Shutdown the supervisor."""
        logger.info("Shutting down Supervisor...")
        self.orchestration_running = False

        # Cancel menu event listener task
        if self.menu_event_task:
            self.menu_event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.menu_event_task

        # Close gRPC channels
        if self.menu_channel:
            await self.menu_channel.close()
        if self.game_coordinator_channel:
            await self.game_coordinator_channel.close()
