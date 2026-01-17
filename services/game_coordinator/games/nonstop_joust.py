"""
Nonstop Joust Game Mode - Endless respawn with scoring

Players respawn after death, compete for highest score.
Features:
- 3-second respawn countdown
- 2-second spawn protection
- Kill/death/streak tracking
- Time-limited or manual stop

Phase 36b: Refactored to extend BaseGameMode, eliminating ~450 lines of duplicate code.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from lib.types import GameEvent
from services.game_coordinator.games.base import BaseGameMode, Phase, Player

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

# Game constants
# UPDATE_FREQUENCY is now read from runtime_config (Phase 43)
RESPAWN_DURATION = 3.0  # seconds to respawn
SPAWN_PROTECTION_DURATION = 2.0  # seconds of invulnerability after spawn


@dataclass
class NonstopPlayer(Player):
    """Represents a player in Nonstop Joust with scoring and respawn state."""

    # Scoring (Phase 22)
    kills: int = 0
    deaths: int = 0
    current_streak: int = 0
    best_streak: int = 0
    score: int = 0

    # Respawn state (Phase 22)
    respawn_timer: float = 0.0  # Time until respawn (seconds)
    spawn_protected: bool = False
    spawn_protection_end: float = 0.0


class NonstopJoustGame(BaseGameMode):
    """
    Nonstop Joust game mode - endless respawn with scoring.

    Players compete for highest score in time-limited or endless matches.
    Features respawn mechanics, spawn protection, and kill tracking.

    Phase 36b: Extends BaseGameMode to inherit:
    - Span orchestration (run() template method)
    - Common game operations (_load_settings, _countdown, _process_controller_state, etc.)
    - Consistent OpenTelemetry span hierarchy

    Implements Nonstop-specific behavior:
    - NonstopPlayer with scoring fields (kills, deaths, score, streaks)
    - Time-based win condition (time_limit setting)
    - Respawn mechanics (players don't stay dead)
    - Spawn protection (2 seconds after respawn)
    - Player spans stay open (death events only, no span end)
    """

    def __init__(
        self,
        controller_manager_client,
        settings_client,
        event_publisher,
        audio_client=None,
        game_id: str = "",
    ):
        """
        Initialize Nonstop Joust game.

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events
            audio_client: gRPC stub for Audio service (Phase 29)
            game_id: Unique identifier for this game instance
        """
        super().__init__(
            controller_manager_client=controller_manager_client,
            settings_client=settings_client,
            event_publisher=event_publisher,
            audio_client=audio_client,
            game_id=game_id,
        )

        # Nonstop-specific settings
        self.time_limit = 0  # 0 = unlimited, otherwise seconds
        self.players: dict[str, NonstopPlayer] = {}  # Override type hint

    def get_game_name(self) -> str:
        """Return game mode identifier."""
        return "Nonstop Joust"

    async def _load_settings(self):
        """Load settings with Nonstop-specific time_limit."""
        # Call parent to load base settings (sensitivity, play_audio)
        await super()._load_settings()

        # Parse Nonstop-specific time limit (0 = unlimited)
        self.time_limit = int(self.settings.get("nonstop_time_limit", "0"))
        logger.info(f"Loaded Nonstop settings: time_limit={self.time_limit}s")

    async def _initialize_players_impl(self, controllers: list):
        """
        Initialize players using NonstopPlayer with scoring fields.

        Args:
            controllers: List of controller protobuf messages from GetReadyControllers
        """
        for controller in controllers:
            player = NonstopPlayer(serial=controller.serial, team=0, alive=True, color=(255, 255, 255))
            self.players[controller.serial] = player
            logger.debug(f"Added player: {controller.serial}")

    def _create_player_spans(self, game_context):
        """
        Create flat player lifecycle spans (stay open for entire game).

        Nonstop Joust spans don't end on death - players respawn.

        Args:
            game_context: Parent span context for proper hierarchy
        """
        for serial, player in self.players.items():
            player.span = self._create_player_lifecycle_span(serial, game_context)
            logger.debug(f"Started lifecycle span for player {serial} (stays open)")

    def _check_win_condition(self) -> bool:
        """
        Check if time limit has been reached.

        Returns:
            True if game should end (time limit reached), False otherwise
        """
        if self.time_limit == 0:
            return False  # Unlimited mode

        if not self.start_time:
            return False

        elapsed = time.time() - self.start_time
        if elapsed >= self.time_limit:
            logger.info(f"Time limit reached: {elapsed:.1f}s / {self.time_limit}s")
            return True

        return False

    async def _process_controller_state(self, controller_state):
        """
        Process controller state with spawn protection check.

        Override parent to skip death checks during spawn protection.

        Args:
            controller_state: ControllerState protobuf message
        """
        serial = controller_state.serial

        if serial not in self.players:
            return  # Unknown controller

        player = self.players[serial]

        if not player.alive:
            return  # Dead player, ignore

        # Skip death checks during spawn protection (Nonstop-specific)
        if player.spawn_protected:
            return

        # Call parent for standard acceleration processing
        await super()._process_controller_state(controller_state)

    async def _kill_player_impl(self, serial: str, accel_mag: float):
        """
        Kill a player and start respawn timer (DON'T end span).

        Nonstop Joust players respawn, so their lifecycle spans stay open.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        player = self.players[serial]
        player.alive = False
        player.deaths += 1
        player.current_streak = 0
        player.respawn_timer = RESPAWN_DURATION

        logger.info(f"Player died: {serial} (kills: {player.kills}, deaths: {player.deaths}, score: {player.score})")

        # Add death event to player's lifecycle span (DON'T end span)
        if player.span:
            player.span.add_event(
                "player_death",
                attributes={
                    "accel_magnitude": accel_mag,
                    "threshold": self.sensitivity.value[1],
                    "kills": player.kills,
                    "deaths": player.deaths,
                    "score": player.score,
                },
            )

        # Publish death event (unique to Nonstop)
        self.event_publisher(
            "player_death",
            {
                "serial": serial,
                "accel_magnitude": accel_mag,
                "kills": player.kills,
                "deaths": player.deaths,
                "score": player.score,
            },
        )

    async def _game_loop(self):
        """Override game loop to add respawn timer updates and dynamic filtering."""
        logger.info("Starting Nonstop game loop with respawn mechanics and dynamic filtering...")

        try:
            from proto import controller_manager_pb2

            # Create player spans (pass None to use current active span context)
            self._create_player_spans(None)

            # Get runtime config (Phase 43: Dynamic Hz adjustment like base class)
            from services.game_coordinator.runtime_config import get_config_manager

            config = get_config_manager().get_config()
            update_frequency_hz = config.update_frequency_hz

            logger.info(f"Starting Nonstop game loop at {update_frequency_hz}Hz")

            # Create bidirectional stream (Phase 45 - dynamic filtering, Phase 46 - feedback commands)
            self.gameplay_stream = self.controller_client.StreamGameplayDataDynamic()

            # Send initial configuration
            initial_config = controller_manager_pb2.GameplayStreamControl(
                config=controller_manager_pb2.GameplayStreamConfig(
                    update_frequency_hz=update_frequency_hz,
                    serials=[],  # Start with all controllers
                )
            )
            await self.gameplay_stream.write(initial_config)

            # Track current alive set for detecting changes (Phase 45)
            last_alive_serials = {p.serial for p in self.players.values() if p.alive}
            logger.info(f"Initial alive players: {len(last_alive_serials)}")

            # Store Hz for respawn timer calculations
            self._current_update_frequency = update_frequency_hz

            # Stream gameplay data and process game logic
            async for gameplay_update in self.gameplay_stream:
                if not self.running:
                    break

                # Process each controller's gameplay data
                for gameplay_data in gameplay_update.controllers:
                    await self._process_controller_state(gameplay_data)

                # Update respawn timers (Nonstop-specific)
                await self._update_respawn_timers()

                # Check if alive players changed (Phase 45 - dynamic filtering)
                # Note: Nonstop has frequent changes due to respawns
                current_alive_serials = {p.serial for p in self.players.values() if p.alive}

                if current_alive_serials != last_alive_serials:
                    # Send filter update to server
                    filter_msg = controller_manager_pb2.GameplayStreamControl(
                        filter_update=controller_manager_pb2.FilterUpdate(serials=list(current_alive_serials))
                    )
                    await self.gameplay_stream.write(filter_msg)

                    logger.info(
                        f"Nonstop filter updated: {len(last_alive_serials)} → "
                        f"{len(current_alive_serials)} alive players"
                    )

                    # Emit filter metrics (Phase 45)
                    from services.game_coordinator import metrics

                    metrics.filter_updates_total.labels(game_mode=self.get_game_name()).inc()
                    metrics.active_controllers.set(len(current_alive_serials))
                    metrics.filtered_controllers.set(len(self.players) - len(current_alive_serials))

                    last_alive_serials = current_alive_serials

                # Check win condition (time limit)
                if self._check_win_condition():
                    break

                # Small sleep to maintain tick rate
                await asyncio.sleep(1.0 / update_frequency_hz)

        except Exception as e:
            logger.error(f"Game loop error: {e}", exc_info=True)
            raise
        finally:
            # Cleanup stream reference (Phase 46)
            self.gameplay_stream = None

    async def _update_respawn_timers(self):
        """Update respawn timers and respawn players (Nonstop-specific)."""
        from proto import controller_manager_pb2

        current_time = time.time()

        # Use current update frequency (Phase 43: dynamic from runtime config)
        update_frequency = getattr(self, "_current_update_frequency", 30)

        for serial, player in self.players.items():
            # Handle respawn countdown
            if not player.alive and player.respawn_timer > 0:
                player.respawn_timer -= 1.0 / update_frequency

                # Show respawn countdown colors
                await self._show_respawn_countdown(serial, player.respawn_timer)

                # Respawn when timer reaches 0
                if player.respawn_timer <= 0:
                    await self._respawn_player(serial)

            # Check spawn protection expiration
            if player.spawn_protected and current_time >= player.spawn_protection_end:
                player.spawn_protected = False
                # Return to normal white color
                color_request = controller_manager_pb2.SetControllerColorRequest(
                    serial=serial,
                    color=controller_manager_pb2.RGB(r=255, g=255, b=255),  # White
                    duration_ms=0,
                )
                await self.controller_client.SetControllerColor(color_request)

    async def _show_respawn_countdown(self, serial: str, time_remaining: float):
        """
        Show respawn countdown colors (Nonstop-specific).

        Args:
            serial: Controller serial number
            time_remaining: Seconds until respawn
        """
        from proto import controller_manager_pb2

        # Countdown colors: Gray -> Yellow -> Green
        if time_remaining > 2.0:
            color = (128, 128, 128)  # Gray (3s)
        elif time_remaining > 1.0:
            color = (255, 255, 0)  # Yellow (2s)
        else:
            color = (0, 255, 0)  # Green (1s)

        # Only update if color changed (avoid spamming)
        player = self.players[serial]
        if not hasattr(player, "_last_respawn_color") or player._last_respawn_color != color:
            player._last_respawn_color = color

            # Play respawn countdown beep (Phase 29)
            await self._play_sound("Joust/sounds/beep_loud.wav", priority=1)

            color_request = controller_manager_pb2.SetControllerColorRequest(
                serial=serial,
                color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
                duration_ms=0,
            )
            await self.controller_client.SetControllerColor(color_request)

    async def _respawn_player(self, serial: str):
        """
        Respawn a dead player (Nonstop-specific).

        Args:
            serial: Controller serial number
        """
        from proto import controller_manager_pb2

        player = self.players[serial]
        player.alive = True
        player.spawn_protected = True
        player.spawn_protection_end = time.time() + SPAWN_PROTECTION_DURATION
        # Reset warning state for clean respawn
        player.warning_until = 0.0
        player.smoothed_accel = 0.0

        # Add respawn event to player's lifecycle span
        if player.span:
            player.span.add_event(
                "player_respawned",
                {"kills": player.kills, "deaths": player.deaths, "score": player.score},
            )

        logger.info(f"Player respawned: {serial} (spawn protection active)")

        # Play respawn sound (Phase 29)
        await self._play_sound("Joust/sounds/join.wav", priority=2)

        # White color during spawn protection
        protection_color_request = controller_manager_pb2.SetControllerColorRequest(
            serial=serial,
            color=controller_manager_pb2.RGB(r=255, g=255, b=255),  # White
            duration_ms=0,
        )
        await self.controller_client.SetControllerColor(protection_color_request)

        # Publish respawn event
        self.event_publisher(
            "player_respawned",
            {
                "serial": serial,
                "kills": player.kills,
                "deaths": player.deaths,
                "score": player.score,
            },
        )

    async def _set_unique_colors(self):
        """
        Set unique colors for each player in Nonstop Joust (Phase 39 - Task 3).

        Each player gets a distinct color so they can be identified during gameplay.
        Uses HSV color generation for maximum distinction.
        """
        from lib.colors import generate_colors

        logger.info("Assigning unique Nonstop colors...")

        try:
            # Generate unique colors for each player
            unique_colors = generate_colors(len(self.players))

            # Assign colors to players (LEDs set when gameplay stream starts)
            for idx, (_serial, player) in enumerate(self.players.items()):
                color = unique_colors[idx]
                player.color = color  # Update player's color attribute

            logger.info(f"Assigned {len(self.players)} unique colors (will display at game start)")

        except Exception as e:
            logger.error(f"Failed to assign Nonstop colors: {e}", exc_info=True)

    def _get_additional_phases(self) -> list:
        """
        Return phases to execute before countdown.

        Nonstop assigns colors silently - players see them at game start (after countdown),
        matching original JoustMania behavior.
        """
        return [Phase(name="nonstop_color_assignment", execute=self._set_unique_colors)]

    async def _end_game_impl(self):
        """Handle game ending with scoring calculation."""
        from proto import controller_manager_pb2
        from services.game_coordinator.games.base import GameState

        logger.info("Ending game...")
        self.state = GameState.ENDING

        # Calculate final scores (inverse of deaths - fewer deaths = higher score)
        # Score = 100 - (deaths * 10), minimum 0
        for player in self.players.values():
            player.score = max(0, 100 - (player.deaths * 10))

        # Determine winner (highest score, tie-break by fewest deaths)
        winner = max(self.players.values(), key=lambda p: (p.score, -p.deaths), default=None)

        if winner:
            logger.info(f"Winner: {winner.serial} with score {winner.score} (K:{winner.kills} D:{winner.deaths})")

            # Phase XX: Show rainbow effect on winner's controller via game effect
            if self.gameplay_stream:
                effect_cmd = controller_manager_pb2.GameplayStreamControl(
                    game_effect=controller_manager_pb2.GameEffectCommand(
                        serial=winner.serial,
                        effect=controller_manager_pb2.GAME_EFFECT_WINNER_RAINBOW,
                    )
                )
                await self.gameplay_stream.write(effect_cmd)
            else:
                # Fallback to RPC
                rainbow_request = controller_manager_pb2.PlayControllerEffectRequest(
                    serial=winner.serial,
                    effect=controller_manager_pb2.EFFECT_RAINBOW,
                    color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                    duration_ms=3000,
                    speed=5,
                )
                await self.controller_client.PlayControllerEffect(rainbow_request)

            # Play victory sound (Phase 29)
            await self._play_sound("Joust/sounds/wolfdown.wav", priority=2)

            self.event_publisher(
                GameEvent.GAME_WINNER,
                {
                    "serial": winner.serial,
                    "score": winner.score,
                    "kills": winner.kills,
                    "deaths": winner.deaths,
                },
            )

        # Show winner for a bit (interruptible by force_end)
        for _ in range(20):  # 2 seconds in 0.1s increments
            if not self.running:
                logger.info("End game interrupted by force_end")
                break
            await asyncio.sleep(0.1)

        # End all player lifecycle spans AFTER the celebration
        # This ensures winner's span is longer than losers'
        for serial, player in self.players.items():
            if player.span:
                player.span.add_event(
                    "final_score",
                    {
                        "score": player.score,
                        "kills": player.kills,
                        "deaths": player.deaths,
                        "game_duration": time.time() - self.start_time if self.start_time else 0,
                    },
                )
                player.span.set_status(Status(StatusCode.OK))
                player.span.end()
                logger.debug(f"Ended lifecycle span for player {serial}")

        self.state = GameState.ENDED
        self.event_publisher(
            GameEvent.GAME_ENDED,
            {
                "game_id": self.game_id,
                "duration": time.time() - self.start_time if self.start_time else 0,
            },
        )

        logger.info("Game ended")
