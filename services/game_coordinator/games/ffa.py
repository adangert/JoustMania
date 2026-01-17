"""
FFA (Free-For-All) Game Mode - gRPC-based implementation

Modern implementation using gRPC for controller states and settings,
async/await patterns, proper state machine, and event publishing.

Phase 36b: Refactored to extend BaseGameMode, eliminating ~550 lines of duplicate code.
"""

import asyncio
import logging
import time

from opentelemetry.trace import Status, StatusCode

from lib.types import GameEvent
from services.game_coordinator.games.base import BaseGameMode, Phase

logger = logging.getLogger(__name__)


class FFAGame(BaseGameMode):
    """
    Free-For-All game mode using gRPC communication.

    Players try to keep their controllers still while jostling others.
    Last player standing wins.

    Phase 36b: Extends BaseGameMode to inherit:
    - Span orchestration (run() template method)
    - Common game operations (_load_settings, _countdown, _process_controller_state, etc.)
    - Consistent OpenTelemetry span hierarchy

    Implements FFA-specific behavior:
    - All players on team=0 (no teams)
    - Flat player hierarchy (players directly under gameplay_phase)
    - Last player standing win condition
    - Players stay dead permanently (spans end on death)
    """

    def get_game_name(self) -> str:
        """Return game mode identifier."""
        return "FFA"

    async def _initialize_players_impl(self, controllers: list):
        """
        Initialize players for FFA - all players on team=0.

        Args:
            controllers: List of controller protobuf messages from GetReadyControllers
        """
        from services.game_coordinator.games.base import Player

        for controller in controllers:
            player = Player(
                serial=controller.serial,
                team=0,  # FFA - everyone on their own team
                alive=True,
                color=(255, 255, 255),
            )
            self.players[controller.serial] = player
            logger.debug(f"Added player: {controller.serial}")

    def _create_player_spans(self, game_context):
        """
        Create flat player lifecycle spans (directly under gameplay_phase).

        Args:
            game_context: Parent span context for proper hierarchy
        """
        for serial, player in self.players.items():
            player.span = self._create_player_lifecycle_span(serial, game_context)
            logger.debug(f"Started lifecycle span for player {serial}")

    def _check_win_condition(self) -> bool:
        """
        Check if game has a winner (last player standing).

        Returns:
            True if game should end, False otherwise
        """
        alive_players = [p for p in self.players.values() if p.alive]

        if len(alive_players) <= 1:
            # Game over - we have a winner (or tie if 0)
            if len(alive_players) == 1:
                winner = alive_players[0]
                logger.info(f"Winner: {winner.serial}")

                self.event_publisher(GameEvent.GAME_WINNER, {"serial": winner.serial})

            elif len(alive_players) == 0:
                logger.info("No winner - all players died simultaneously")

                self.event_publisher(GameEvent.GAME_TIE, {})

            return True

        return False

    async def _kill_player_impl(self, serial: str, accel_mag: float):
        """
        Kill a player permanently (end their lifecycle span).

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        player = self.players[serial]
        player.alive = False

        alive_count = len([p for p in self.players.values() if p.alive])

        # Add death event to player's lifecycle span and end it
        if player.span:
            player.span.add_event(
                "player_death",
                attributes={
                    "accel_magnitude": accel_mag,
                    "threshold": self.sensitivity.value[1],
                    "alive_count": alive_count,
                },
            )
            player.span.set_status(Status(StatusCode.OK))
            player.span.end()
            logger.debug(f"Ended lifecycle span for player {serial}")

    async def _assign_ffa_colors(self):
        """
        Assign unique colors to each player in FFA mode.

        Colors are assigned to player objects but NOT displayed yet.
        Players see their colors when the game starts (after countdown),
        matching the original JoustMania behavior.
        """
        from lib.colors import generate_colors

        logger.info("Assigning unique FFA colors...")

        try:
            # Generate unique colors for each player
            unique_colors = generate_colors(len(self.players))

            # Assign colors to players (LEDs set when gameplay stream starts)
            for idx, (_serial, player) in enumerate(self.players.items()):
                color = unique_colors[idx]
                player.color = color  # Update player's color attribute

            logger.info(f"Assigned {len(self.players)} unique colors (will display at game start)")

        except Exception as e:
            logger.error(f"Failed to assign FFA colors: {e}", exc_info=True)

    def _get_additional_phases(self) -> list:
        """
        Return phases to execute before countdown.

        FFA assigns colors silently - players see them at game start (after countdown),
        matching original JoustMania behavior.
        """
        return [Phase(name="ffa_color_assignment", execute=self._assign_ffa_colors)]

    async def _end_game_impl(self):
        """Handle game ending - show winner, cleanup."""
        from proto import controller_manager_pb2
        from services.game_coordinator.games.base import GameState

        logger.info("Ending game...")
        self.state = GameState.ENDING

        # Find winner (if any)
        alive_players = [p for p in self.players.values() if p.alive]
        winner_serial = alive_players[0].serial if len(alive_players) == 1 else None

        # Phase XX: Show rainbow effect on winner's controller via game effect
        if winner_serial:
            if self.gameplay_stream:
                effect_cmd = controller_manager_pb2.GameplayStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=winner_serial,
                        effect=controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW,
                    )
                )
                await self.gameplay_stream.write(effect_cmd)
            else:
                # Fallback to RPC
                rainbow_request = controller_manager_pb2.PlayControllerEffectRequest(
                    serial=winner_serial,
                    effect=controller_manager_pb2.EFFECT_RAINBOW,
                    color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                    duration_ms=3000,
                    speed=5,
                )
                await self.controller_client.PlayControllerEffect(rainbow_request)

            # Play victory sound (Phase 29)
            await self._play_sound("Joust/sounds/wolfdown.wav", priority=2)

        # Show winner for a bit (interruptible by force_end)
        for _ in range(20):  # 2 seconds in 0.1s increments
            if not self.running:
                logger.info("End game interrupted by force_end")
                break
            await asyncio.sleep(0.1)

        # End spans for surviving players AFTER the celebration
        # This ensures winner's span is longer than losers'
        for serial, player in self.players.items():
            if player.span and player.alive:
                player.span.add_event(
                    "victory",
                    attributes={
                        "game_duration": time.time() - self.start_time if self.start_time else 0,
                        "winner": serial == winner_serial,
                    },
                )
                player.span.set_status(Status(StatusCode.OK))
                player.span.end()
                logger.debug(f"Ended lifecycle span for surviving player {serial}")

        self.state = GameState.ENDED
        self.event_publisher(
            GameEvent.GAME_ENDED,
            {
                "game_id": self.game_id,
                "duration": time.time() - self.start_time if self.start_time else 0,
            },
        )

        logger.info("Game ended")
