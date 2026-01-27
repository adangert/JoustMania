"""
FFA (Free-For-All) Game Mode - gRPC-based implementation

Modern implementation using gRPC for controller states and settings,
async/await patterns, proper state machine, and event publishing.

Phase 36b: Refactored to extend BaseGameMode, eliminating ~550 lines of duplicate code.
"""

import logging
import time

from opentelemetry.trace import Status, StatusCode

from lib.telemetry import inject_trace_context
from lib.types import GameEvent, Sound
from services.game_coordinator.games.analytics import PlayerAnalytics
from services.game_coordinator.games.base import BaseGameMode, Phase
from services.game_coordinator.runtime_config import get_config_manager

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

        config = get_config_manager().get_config()
        game_start_time = time.time()

        for controller in controllers:
            # Initialize analytics if enabled
            analytics = None
            if config.analytics.enabled:
                analytics = PlayerAnalytics(
                    serial=controller.serial,
                    game_start_time=game_start_time,
                )

            player = Player(
                serial=controller.serial,
                team=0,  # FFA - everyone on their own team
                alive=True,
                color=(255, 255, 255),
                analytics=analytics,
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
                    "sensitivity": self.sensitivity.name,
                    "alive_count": alive_count,
                },
            )
            player.span.set_status(Status(StatusCode.OK))
            player.span.end()
            player.span = None  # Mark as closed to prevent double-ending
            logger.debug(f"Ended lifecycle span for player {serial}")

    async def _assign_ffa_colors(self):
        """
        Assign unique colors to each player in FFA mode.

        Colors are assigned to player objects but NOT displayed yet.
        Players see their colors when the game starts (after countdown),
        matching the original JoustMania behavior.
        """
        from lib.colors import generate_colors

        logger.info("Assigning unique colors...")

        try:
            # Generate unique colors for each player
            unique_colors = generate_colors(len(self.players))

            # Assign colors to players (LEDs set when gameplay stream starts)
            for idx, (_serial, player) in enumerate(self.players.items()):
                color = unique_colors[idx]
                player.color = color  # Update player's color attribute

            logger.info(f"Assigned {len(self.players)} unique colors (will display at game start)")

        except Exception as e:
            logger.error(f"Failed to assign colors: {e}", exc_info=True)

    def _get_additional_phases(self) -> list:
        """
        Return phases to execute before countdown.

        FFA assigns colors silently - players see them at game start (after countdown),
        matching original JoustMania behavior.
        """
        return [Phase(name="color_assignment", execute=self._assign_ffa_colors)]

    def _close_all_player_spans(self):
        """
        Close all player lifecycle spans with analytics data.

        Override base implementation to add victory event and analytics
        summary to surviving players' spans.
        """
        # Find winner for victory event
        alive_players = [p for p in self.players.values() if p.alive]
        winner_serial = alive_players[0].serial if len(alive_players) == 1 else None

        for serial, player in self.players.items():
            if player.span:
                # Build attributes including analytics summary if available
                if player.alive:
                    victory_attrs = {
                        "game_duration": time.time() - self.start_time if self.start_time else 0,
                        "winner": serial == winner_serial,
                    }

                    # Add analytics summary to span
                    if player.analytics is not None:
                        analytics_summary = player.analytics.get_summary()
                        for key, value in analytics_summary.items():
                            victory_attrs[f"analytics.{key}"] = value

                    player.span.add_event("victory", attributes=victory_attrs)

                player.span.set_status(Status(StatusCode.OK))
                player.span.end()
                player.span = None  # Mark as closed
                logger.debug(f"Closed lifecycle span for player {serial}")

    async def _end_game_impl(self):
        """Handle game ending - show winner, cleanup."""
        from proto import controller_manager_pb2
        from services.game_coordinator import metrics
        from services.game_coordinator.games.base import GameState

        logger.info("Ending game...")
        self.state = GameState.ENDING

        # Find winner (if any)
        alive_players = [p for p in self.players.values() if p.alive]
        winner_serial = alive_players[0].serial if len(alive_players) == 1 else None
        logger.info(f"End game: winner_serial={winner_serial}, gameplay_stream={self.gameplay_stream is not None}")

        # Show rainbow effect on winner's controller and play victory sound
        if winner_serial and self.gameplay_stream:
            logger.info(f"Sending WINNER_RAINBOW effect for {winner_serial}")
            trace_parent, trace_state = inject_trace_context()
            effect_cmd = controller_manager_pb2.GameplayStreamControl(
                game_effect=controller_manager_pb2.GameEffectCommand(
                    serial=winner_serial,
                    effect=controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW,
                    trace_parent=trace_parent,
                    trace_state=trace_state,
                )
            )
            await self.gameplay_stream.write(effect_cmd)
            logger.info(f"WINNER_RAINBOW effect sent for {winner_serial}")
            await self._play_sound(Sound.VOX_CONGRATULATIONS, priority=2)
        else:
            logger.warning(
                f"Skipping rainbow effect: winner_serial={winner_serial}, "
                f"stream_valid={self.gameplay_stream is not None}"
            )

        # Wait for rainbow effect to complete
        await self._wait_for_rainbow_effect()

        # Note: Player spans are already closed by _close_all_player_spans()
        # at the end of gameplay_phase (before teardown_phase starts)

        # Publish analytics summaries for all players
        for serial, player in self.players.items():
            if player.analytics is not None:
                summary = player.analytics.get_summary()
                summary["game_id"] = self.game_id
                summary["winner"] = serial == winner_serial
                summary["survival_time_ms"] = player.analytics.total_time_ms

                # Publish player analytics event
                self.event_publisher(GameEvent.PLAYER_ANALYTICS, summary)

                # Update Prometheus metrics
                metrics.game_analytics_samples_total.labels(game_mode=self.get_game_name()).inc(
                    player.analytics.sample_count
                )
                metrics.near_death_events_total.labels(serial=serial, game_mode=self.get_game_name()).inc(
                    player.analytics.near_death_count
                )

                logger.info(
                    f"Player {serial} analytics: peak={summary['peak_accel']:.2f}g, "
                    f"playstyle={summary['playstyle']}, near_deaths={summary['near_death_count']}"
                )

        self.state = GameState.ENDED
        self.event_publisher(
            GameEvent.GAME_ENDED,
            {
                "game_id": self.game_id,
                "duration": time.time() - self.start_time if self.start_time else 0,
            },
        )

        logger.info("Game ended")
