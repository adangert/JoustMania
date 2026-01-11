"""
Random Teams Game Mode - gRPC-based implementation

Players are randomly assigned to teams and compete against other teams.
Team colors are shown before the game starts so players know their teams.
Last team standing wins.

This is Phase 13.2 - modern implementation using gRPC for all service communication.
"""

import asyncio
import logging
import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

# Game constants
UPDATE_FREQUENCY = 60  # Hz - game tick frequency
COUNTDOWN_DURATION = 3  # seconds
TEAM_FORMATION_DURATION = 5  # seconds - time to show team colors


# Sensitivity thresholds (will eventually come from settings)
class Sensitivity(Enum):
    SLOW = (1.3, 1.5)  # (warning_threshold, death_threshold)
    MEDIUM = (1.6, 1.8)
    FAST = (1.9, 2.8)


# Team colors (from utils/colors.py - first 8 colors)
TEAM_COLORS = [
    {"name": "Pink", "rgb": (255, 108, 108)},
    {"name": "Magenta", "rgb": (255, 0, 192)},
    {"name": "Orange", "rgb": (255, 64, 0)},
    {"name": "Yellow", "rgb": (255, 255, 0)},
    {"name": "Green", "rgb": (0, 255, 0)},
    {"name": "Turquoise", "rgb": (0, 255, 255)},
    {"name": "Blue", "rgb": (0, 0, 255)},
    {"name": "Purple", "rgb": (96, 0, 255)},
]


@dataclass
class Team:
    """Represents a team in the game."""

    team_num: int
    name: str
    color: tuple
    span: trace.Span | None = None  # OpenTelemetry span for team lifecycle


@dataclass
class Player:
    """Represents a player in the game."""

    serial: str
    team: int
    alive: bool = True
    color: tuple = (255, 255, 255)
    last_accel_mag: float = 0.0
    span: trace.Span | None = None  # OpenTelemetry span for player lifecycle


class GameState(Enum):
    """Game lifecycle states."""

    IDLE = "idle"
    STARTING = "starting"
    TEAM_FORMATION = "team_formation"  # New state for showing teams
    RUNNING = "running"
    ENDING = "ending"
    ENDED = "ended"


class RandomTeamsGame:
    """
    Random Teams game mode using gRPC communication.

    Players are randomly assigned to teams. Before the game starts, team colors
    are shown so players can identify their teammates. Last team standing wins.
    """

    def __init__(
        self,
        controller_manager_client,
        settings_client,
        event_publisher: Callable,
        game_id: str = "",
        num_teams: int = 2,
    ):
        """
        Initialize Random Teams game.

        Args:
            controller_manager_client: gRPC stub for ControllerManager service
            settings_client: gRPC stub for Settings service
            event_publisher: Callback function to publish game events
            game_id: Unique identifier for this game instance
            num_teams: Number of teams (default 2)
        """
        self.controller_client = controller_manager_client
        self.settings_client = settings_client
        self.event_publisher = event_publisher
        self.game_id = game_id or f"random_teams_{int(time.time())}"
        self.num_teams = num_teams

        # Game state
        self.state = GameState.IDLE
        self.players: dict[str, Player] = {}
        self.teams: dict[
            int, Team
        ] = {}  # team_num -> Team object (initialized after random generation)
        self.start_time = None
        self.running = False

        # Team tracking (will be set after random generation)
        self.team_colors = []

        # Settings (will be fetched from Settings service)
        self.sensitivity = Sensitivity.MEDIUM
        self.play_audio = True

        logger.info(f"Random Teams game initialized: {self.game_id} with {num_teams} teams")

    def _generate_random_team_colors(self):
        """Generate random team colors (shuffled from available colors)."""
        available_colors = TEAM_COLORS.copy()
        random.shuffle(available_colors)
        self.team_colors = available_colors[: self.num_teams]

        # Initialize team objects with random colors
        for i in range(self.num_teams):
            self.teams[i] = Team(
                team_num=i, name=self.team_colors[i]["name"], color=self.team_colors[i]["rgb"]
            )

        logger.info(f"Generated team colors: {[c['name'] for c in self.team_colors]}")

    def _assign_random_teams(self, player_serials: list[str]) -> dict[str, int]:
        """
        Randomly assign players to teams.

        Args:
            player_serials: List of player serial numbers

        Returns:
            Dictionary mapping serial to team number
        """
        # Create a pool of team numbers
        num_players = len(player_serials)
        teams_per_player = (num_players // self.num_teams) + 1
        team_pool = list(range(self.num_teams)) * teams_per_player

        # Shuffle the pool
        random.shuffle(team_pool)

        # Assign teams
        assignments = {}
        for idx, serial in enumerate(player_serials):
            assignments[serial] = team_pool[idx]

        logger.info(f"Random team assignments: {assignments}")
        return assignments

    async def _load_settings(self):
        """Fetch game settings from Settings service."""
        try:
            from proto import settings_pb2

            response = await self.settings_client.GetSettings(settings_pb2.GetSettingsRequest())

            if response.success:
                settings = response.settings
                logger.info(f"Loaded settings: {len(settings)} keys")

                # Parse sensitivity
                sens_str = settings.get("sensitivity", "MEDIUM").upper()
                if sens_str in Sensitivity.__members__:
                    self.sensitivity = Sensitivity[sens_str]

                # Parse audio setting
                self.play_audio = settings.get("play_audio", "true").lower() == "true"

            else:
                logger.warning(f"Failed to load settings: {response.error}")

        except Exception as e:
            logger.error(f"Error loading settings: {e}", exc_info=True)
            # Use defaults

    async def _initialize_players(self):
        """Get initial controller states and randomly assign players to teams."""
        try:
            from proto import controller_manager_pb2

            response = await self.controller_client.GetReadyControllers(
                controller_manager_pb2.GetReadyControllersRequest()
            )

            if response.success:
                controllers = list(response.controllers)
                player_serials = [c.serial for c in controllers]

                # Generate random team colors
                self._generate_random_team_colors()

                # Randomly assign players to teams
                team_assignments = self._assign_random_teams(player_serials)

                # Create player objects
                for controller in controllers:
                    team_num = team_assignments[controller.serial]
                    team_color = self.team_colors[team_num]["rgb"]

                    player = Player(
                        serial=controller.serial, team=team_num, alive=True, color=team_color
                    )
                    self.players[controller.serial] = player
                    logger.debug(
                        f"Added player: {controller.serial} to team {team_num} ({self.team_colors[team_num]['name']})"
                    )

                logger.info(
                    f"Initialized {len(self.players)} players across {self.num_teams} teams (random assignment)"
                )

                # Publish event with team assignments
                self.event_publisher(
                    "players_initialized",
                    {
                        "player_count": len(self.players),
                        "num_teams": self.num_teams,
                        "team_assignments": str(team_assignments),
                        "team_colors": str([c["name"] for c in self.team_colors]),
                        "serials": list(self.players.keys()),
                    },
                )

            else:
                logger.error(f"Failed to get controllers: {response.error}")
                raise RuntimeError(f"Failed to get controllers: {response.error}")

        except Exception as e:
            logger.error(f"Error initializing players: {e}", exc_info=True)
            raise

    async def _team_formation(self):
        """
        Team formation phase - show team colors to players.

        This gives players time to see who's on their team before the game starts.
        """
        logger.info("Starting team formation phase...")
        self.state = GameState.TEAM_FORMATION

        self.event_publisher(
            "team_formation_start",
            {
                "duration": TEAM_FORMATION_DURATION,
                "team_colors": str([c["name"] for c in self.team_colors]),
            },
        )

        # TODO: Set controller colors to team colors
        # TODO: Play "teams form" audio

        # Use shorter sleeps to allow force_end to interrupt
        for _ in range(TEAM_FORMATION_DURATION * 10):
            if not self.running:
                logger.info("Team formation interrupted by force_end")
                return
            await asyncio.sleep(0.1)

        self.event_publisher("team_formation_end", {})
        logger.info("Team formation complete")

    async def _countdown(self):
        """Run countdown before game starts."""
        logger.info("Starting countdown...")
        self.event_publisher("countdown_start", {"duration": COUNTDOWN_DURATION})

        # TODO: Set controller colors for countdown (Red -> Yellow -> Green)

        # Use shorter sleeps to allow force_end to interrupt
        for _ in range(COUNTDOWN_DURATION * 10):
            if not self.running:
                logger.info("Countdown interrupted by force_end")
                return
            await asyncio.sleep(0.1)

        self.event_publisher("countdown_end", {})
        logger.info("Countdown complete")

    async def _game_loop(self):
        """Main game loop - processes controller states and checks for deaths."""
        logger.info("Starting game loop...")

        try:
            from proto import controller_manager_pb2

            # Start per-team lifecycle spans (as children of game_loop span)
            for team_num, team in self.teams.items():
                team_span = tracer.start_span(
                    f"team_{team_num}_{team.name}_lifecycle",
                    attributes={
                        "team.number": team_num,
                        "team.name": team.name,
                        "team.color": str(team.color),
                        "game.mode": "RandomTeams",
                    },
                )
                team.span = team_span
                logger.debug(f"Started lifecycle span for team {team_num} ({team.name})")

            # Start per-player lifecycle spans (as children of their team span)
            for serial, player in self.players.items():
                team = self.teams[player.team]

                # Create player span as child of team span using context

                ctx = trace.set_span_in_context(team.span)

                player_span = tracer.start_span(
                    f"player_{serial}_lifecycle",
                    context=ctx,
                    attributes={
                        "player.serial": serial,
                        "player.team": player.team,
                        "player.team_name": team.name,
                        "player.color": str(player.color),
                        "game.mode": "RandomTeams",
                    },
                )
                player.span = player_span
                logger.debug(f"Started lifecycle span for player {serial} (Team {team.name})")

            # Start streaming controller states
            stream_request = controller_manager_pb2.StreamRequest(
                update_frequency_hz=UPDATE_FREQUENCY
            )

            alive_count = len([p for p in self.players.values() if p.alive])

            # Stream controller states and process game logic
            async for state_update in self.controller_client.StreamControllerStates(
                stream_request
            ):
                if not self.running:
                    break

                # Process each controller's state
                for controller_state in state_update.controllers:
                    await self._process_controller_state(controller_state)

                # Check win condition
                if self._check_win_condition():
                    break

                # Small sleep to maintain tick rate
                await asyncio.sleep(1.0 / UPDATE_FREQUENCY)

        except Exception as e:
            logger.error(f"Game loop error: {e}", exc_info=True)
            raise

    async def _process_controller_state(self, controller_state):
        """
        Process a single controller's state and check for death.

        Args:
            controller_state: ControllerState protobuf message
        """
        serial = controller_state.serial

        if serial not in self.players:
            return  # Unknown controller

        player = self.players[serial]

        if not player.alive:
            return  # Dead player, ignore

        # Calculate acceleration magnitude
        accel = controller_state.accel
        accel_mag = math.sqrt(accel.x**2 + accel.y**2 + accel.z**2)

        player.last_accel_mag = accel_mag

        # Get thresholds
        warn_threshold, death_threshold = self.sensitivity.value

        # Check for death
        if accel_mag > death_threshold:
            await self._kill_player(serial, accel_mag)

        # Check for warning (flash controller)
        elif accel_mag > warn_threshold:
            await self._warn_player(serial, accel_mag)

    async def _warn_player(self, serial: str, accel_mag: float):
        """
        Warn a player that they're moving too much.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that triggered warning
        """
        player = self.players.get(serial)
        if not player or not player.alive:
            return

        # Add warning event to player's lifecycle span
        if player.span:
            player.span.add_event(
                "player_warning",
                attributes={
                    "accel_magnitude": accel_mag,
                    "threshold": self.sensitivity.value[0],
                    "team": player.team,
                },
            )
            logger.debug(
                f"Player {serial} (Team {player.team}) triggered warning (accel: {accel_mag:.2f})"
            )

        # TODO: Flash controller LED
        # TODO: Vibrate controller

    async def _kill_player(self, serial: str, accel_mag: float):
        """
        Kill a player.

        Args:
            serial: Controller serial number
            accel_mag: Acceleration magnitude that caused death
        """
        player = self.players.get(serial)
        if not player or not player.alive:
            return

        player.alive = False
        team = self.teams[player.team]


        alive_count = len([p for p in self.players.values() if p.alive])
        alive_teams = self._get_alive_teams()

        # Check if this death eliminated the team
        team_eliminated = player.team not in alive_teams

        logger.info(
            f"Player died: {serial} (Team {player.team}), {alive_count} players remaining on {len(alive_teams)} teams"
        )

        # Add death event to player's lifecycle span and end it
        if player.span:
            player.span.add_event(
                "player_death",
                attributes={
                    "accel_magnitude": accel_mag,
                    "threshold": self.sensitivity.value[1],
                    "alive_count": alive_count,
                    "team_eliminated": team_eliminated,
                },
            )
            player.span.set_status(Status(StatusCode.OK))
            player.span.end()
            logger.debug(f"Ended lifecycle span for player {serial}")

        # If team eliminated, end team span
        if team_eliminated and team.span:
            team.span.add_event(
                "team_eliminated",
                attributes={"last_player": serial, "alive_teams_count": len(alive_teams)},
            )
            team.span.set_status(Status(StatusCode.OK))
            team.span.end()
            logger.info(f"Team {team.name} eliminated! Ended team lifecycle span")

        # Publish death event
        self.event_publisher(
            "player_death",
            {
                "serial": serial,
                "team": player.team,
                "team_name": self.team_colors[player.team]["name"],
                "accel_magnitude": accel_mag,
                "alive_count": alive_count,
                "alive_teams_count": len(alive_teams),
            },
        )

        # TODO: Set controller color to black/red
        # TODO: Play explosion sound

    def _get_alive_teams(self) -> set[int]:
        """Get set of teams that still have alive players."""
        alive_teams = set()
        for player in self.players.values():
            if player.alive:
                alive_teams.add(player.team)
        return alive_teams

    def _check_win_condition(self) -> bool:
        """
        Check if a team has won.

        Returns:
            True if game should end, False otherwise
        """
        alive_teams = self._get_alive_teams()

        if len(alive_teams) <= 1:
            # Game over - we have a winning team (or tie if 0)
            if len(alive_teams) == 1:
                winning_team = list(alive_teams)[0]
                team_name = self.team_colors[winning_team]["name"]

                # Get winning players
                winners = [
                    p.serial for p in self.players.values() if p.alive and p.team == winning_team
                ]

                logger.info(f"Team {winning_team} ({team_name}) wins with {len(winners)} players!")

                self.event_publisher(
                    "team_winner",
                    {
                        "team": winning_team,
                        "team_name": team_name,
                        "team_color": str(self.team_colors[winning_team]["rgb"]),
                        "winning_players": winners,
                        "winner_count": len(winners),
                    },
                )

            elif len(alive_teams) == 0:
                logger.info("No winner - all players died simultaneously")
                self.event_publisher("game_tie", {})

            return True

        return False

    async def _end_game(self):
        """Handle game ending - show winner, cleanup."""
        logger.info("Ending game...")
        self.state = GameState.ENDING

        # Determine winning team
        alive_teams = self._get_alive_teams()
        winning_team_num = list(alive_teams)[0] if len(alive_teams) == 1 else None

        # End spans for any surviving players
        for serial, player in self.players.items():
            if player.span and player.alive:
                is_winner = winning_team_num is not None and player.team == winning_team_num
                player.span.add_event(
                    "player_survived",
                    attributes={
                        "game_duration": time.time() - self.start_time
                        if self.start_time
                        else 0,
                        "winner": is_winner,
                        "team": player.team,
                    },
                )
                player.span.set_status(Status(StatusCode.OK))
                player.span.end()
                logger.debug(f"Ended lifecycle span for surviving player {serial}")

        # End spans for any surviving teams (winning team)
        for team_num, team in self.teams.items():
            if team.span and team_num in alive_teams:
                is_winning_team = winning_team_num is not None and team_num == winning_team_num
                team.span.add_event(
                    "team_victory" if is_winning_team else "team_survived",
                    attributes={
                        "game_duration": time.time() - self.start_time
                        if self.start_time
                        else 0,
                        "winner": is_winning_team,
                    },
                )
                team.span.set_status(Status(StatusCode.OK))
                team.span.end()
                logger.info(
                    f"Ended lifecycle span for team {team.name} ({'WINNER' if is_winning_team else 'survived'})"
                )

        # TODO: Show rainbow on winning team's controllers
        # TODO: Play victory sound for winning team

        # Show winner for a bit (interruptible by force_end)
        for _ in range(20):  # 2 seconds in 0.1s increments
            if not self.running:
                logger.info("End game interrupted by force_end")
                break
            await asyncio.sleep(0.1)

        self.state = GameState.ENDED
        self.event_publisher(
            "game_ended",
            {
                "game_id": self.game_id,
                "duration": time.time() - self.start_time if self.start_time else 0,
            },
        )

        logger.info("Game ended")

    async def run(self, game_context=None):
        """
        Main entry point to run the Random Teams game.

        This is the async method called by GameCoordinator.

        Args:
            game_context: Parent game_session span context for proper hierarchy
        """
        try:
            # IDLE -> STARTING
            self.state = GameState.STARTING
            self.running = True  # Set early to allow force_end during any phase
            self.event_publisher(
                "game_starting", {"game_id": self.game_id, "num_teams": self.num_teams}
            )

            # Initialization phase (load settings + initialize players)
            with tracer.start_as_current_span("initialization_phase", context=game_context) as init_span:
                init_span.set_attribute("game.id", self.game_id)
                init_span.set_attribute("game.mode", "RandomTeams")
                init_span.set_attribute("game.num_teams", self.num_teams)

                # Load settings
                await self._load_settings()

                # Initialize players (with random team assignment)
                await self._initialize_players()

                # Validate player count
                if len(self.players) < 2:
                    raise ValueError(f"Need at least 2 players, got {len(self.players)}")

                if len(self.players) < self.num_teams:
                    logger.warning(
                        f"Not enough players ({len(self.players)}) for {self.num_teams} teams"
                    )
                    # Adjust team count if needed
                    actual_teams = self._get_alive_teams()
                    if len(actual_teams) < 2:
                        raise ValueError(f"Need at least 2 teams, only have {len(actual_teams)}")

                init_span.set_attribute("player_count", len(self.players))
                init_span.set_attribute("actual_teams", len(self._get_alive_teams()))

            # Team formation phase (show colors)
            with tracer.start_as_current_span("team_formation_phase", context=game_context):
                await self._team_formation()

            # Countdown phase
            with tracer.start_as_current_span("countdown_phase", context=game_context):
                await self._countdown()

            # STARTING -> RUNNING
            self.state = GameState.RUNNING
            self.start_time = time.time()
            self.event_publisher(
                "game_started",
                {
                    "game_id": self.game_id,
                    "player_count": len(self.players),
                    "num_teams": self.num_teams,
                },
            )

            # Gameplay phase (main game loop)
            with tracer.start_as_current_span("gameplay_phase", context=game_context):
                await self._game_loop()

            # Teardown phase (end game)
            with tracer.start_as_current_span("teardown_phase", context=game_context):
                await self._end_game()

        except Exception as e:
            logger.error(f"Random Teams game error: {e}", exc_info=True)
            self.state = GameState.ENDED
            self.event_publisher("game_error", {"game_id": self.game_id, "error": str(e)})
            raise

        finally:
            self.running = False
            logger.info(f"Random Teams game finished: {self.game_id}")

    def force_end(self):
        """Force the game to end (called externally)."""
        logger.info("Force ending game...")
        self.running = False
