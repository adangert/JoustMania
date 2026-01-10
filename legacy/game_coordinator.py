"""
GameCoordinator Process for JoustMania

Manages game lifecycle as a separate process:
- Initialize games
- Execute game instances
- Monitor game state
- Coordinate with ControllerManager
- Signal events to Menu

This is part of the microservices refactoring (Phase 2).
"""

import logging
import random
import time
from multiprocessing import Process

import controller_manager
from common import Games
from games import (
    commander,
    ffa,
    fight_club,
    joust_ffa,
    joust_non_stop,
    joust_random_teams,
    joust_teams,
    speed_bomb,
    swapper,
    tournament,
    traitor,
    werewolf,
    zombie,
)
from piaudio import Audio, Music

logger = logging.getLogger(__name__)


class GameCoordinatorProcess(Process):
    """
    GameCoordinator running as separate process.

    Responsibilities:
    - Initialize game instances
    - Execute games (blocking)
    - Detect game end
    - Coordinate with ControllerManager for controller info
    - Send events to Menu process

    IPC Protocol:
    - Command Queue: Receives commands from Menu
    - Response Queue: Sends responses back to Menu
    - Event Queue: Sends events to Menu (game_started, game_ended, etc.)
    """

    def __init__(
        self,
        command_queue,
        response_queue,
        event_queue,
        controller_cmd_queue,
        controller_resp_queue,
        menu_flag,
        restart_flag,
        music_speed,
        red_on_kill,
        show_team_colors,
        revive,
        controller_game_mode,
        ns,
        experimental=False,
    ):
        """
        Initialize GameCoordinator process.

        Args:
            command_queue: Queue for receiving commands from Menu
            response_queue: Queue for sending responses to Menu
            event_queue: Queue for sending events to Menu
            controller_cmd_queue: Queue for sending commands to ControllerManager
            controller_resp_queue: Queue for receiving responses from ControllerManager
            menu_flag: Shared flag for menu mode (1) or game mode (0)
            restart_flag: Shared flag for restart state
            music_speed: Shared music speed value
            red_on_kill: Shared flag for red on kill
            show_team_colors: Shared flag for team color display
            revive: Shared flag for revival enabled
            controller_game_mode: Shared game mode value
            ns: Shared namespace for settings
            experimental: Use experimental FFA mode
        """
        super().__init__(name="GameCoordinator")

        # IPC
        self.command_queue = command_queue
        self.response_queue = response_queue
        self.event_queue = event_queue
        self.controller_cmd_queue = controller_cmd_queue
        self.controller_resp_queue = controller_resp_queue

        # Shared flags from main process
        self.menu = menu_flag
        self.restart = restart_flag
        self.music_speed = music_speed
        self.red_on_kill = red_on_kill
        self.show_team_colors = show_team_colors
        self.revive = revive
        self.controller_game_mode = controller_game_mode
        self.ns = ns

        # Game state
        self.current_game_mode = Games[ns.settings.get("current_game", "JoustFFA")]
        self.old_game_mode = self.current_game_mode
        self.random_history = []  # Track recently played modes for random
        self.game_in_progress = False
        self.experimental = experimental

        # Music
        self.joust_music = None
        self.zombie_music = None
        self.commander_music = None

        # Controller state (will be passed to games)
        # These are set up when we receive controller state references
        self.controller_teams = {}
        self.controller_colors = {}
        self.dead_moves = {}
        self.invincible_moves = {}
        self.force_color = {}
        self.game_opts = {}

        # Running flag
        self.running = True

        logger.info("GameCoordinator process initialized")

    def run(self):
        """
        Main process loop.

        Handles:
        - IPC command processing
        - Game execution (blocking)
        """
        logger.info("GameCoordinator process started")

        # Load music
        self.load_music()

        try:
            while self.running:
                # Process IPC commands (non-blocking)
                self.process_commands()

                # Brief sleep to avoid busy loop
                time.sleep(0.01)

        except KeyboardInterrupt:
            logger.info("GameCoordinator received interrupt")
        except Exception as e:
            logger.error(f"GameCoordinator error: {e}", exc_info=True)
        finally:
            self.shutdown()

        logger.info("GameCoordinator process stopped")

    def load_music(self):
        """Load game music."""
        try:
            self.joust_music = Music("joust")
            self.zombie_music = Music("zombie")
            self.commander_music = Music("commander")

            self.joust_music.load_audio("audio/Joust/music/*")
            self.zombie_music.load_audio("audio/Zombie/music/*")
            self.commander_music.load_audio("audio/Commander/music/*")

            logger.info("Game music loaded")
        except Exception as e:
            logger.error(f"Error loading music: {e}", exc_info=True)

    def process_commands(self):
        """
        Process commands from command queue (non-blocking).

        Commands:
        - start_game: Start a new game
        - get_game_status: Return current game status
        - force_end_game: Force current game to end
        - shutdown: Shutdown coordinator
        """
        try:
            while not self.command_queue.empty():
                message = self.command_queue.get_nowait()
                command = message.get("command")
                params = message.get("params", {})
                request_id = message.get("request_id")

                logger.debug(f"Processing command: {command}")

                # Dispatch command
                if command == "start_game":
                    response = self.handle_start_game(params)
                elif command == "get_game_status":
                    response = self.handle_get_game_status()
                elif command == "force_end_game":
                    response = self.handle_force_end_game()
                elif command == "update_controller_state":
                    response = self.handle_update_controller_state(params)
                elif command == "shutdown":
                    self.running = False
                    response = {"status": "success", "data": {}}
                else:
                    response = {"status": "error", "error": f"Unknown command: {command}"}

                # Send response
                response["request_id"] = request_id
                response["timestamp"] = time.time()
                self.response_queue.put(response)

        except Exception as e:
            logger.error(f"Error processing commands: {e}", exc_info=True)

    def handle_start_game(self, params: dict) -> dict:
        """
        Handle start_game command.

        Args:
            params: {
                'game_mode': Optional game mode name
                'random_mode': bool - whether to use random mode
                'force_all': bool - force start with all controllers
            }

        Returns:
            Response dict with game start info
        """
        try:
            random_mode = params.get("random_mode", False)
            requested_mode = params.get("game_mode")
            force_all = params.get("force_all", False)

            # Get ready controllers from ControllerManager
            ctrl_response = controller_manager.send_command(
                self.controller_cmd_queue,
                self.controller_resp_queue,
                "get_ready_controllers",
                {"force_all": force_all},
            )

            if ctrl_response["status"] != "success":
                return {"status": "error", "error": "Failed to get ready controllers"}

            game_moves = ctrl_response["data"]["controllers"]

            # Select game mode
            if random_mode:
                game_mode = self.select_random_game_mode(len(game_moves))
            elif requested_mode:
                game_mode = Games[requested_mode]
            else:
                game_mode = self.current_game_mode

            # Check minimum players
            if len(game_moves) < game_mode.minimum_players and self.ns.settings.get(
                "enforce_minimum", True
            ):
                if self.ns.settings.get("play_audio", True):
                    Audio(
                        "audio/Menu/vox/" + self.ns.settings["menu_voice"] + "/notenoughplayers.wav"
                    ).start_effect()
                return {
                    "status": "error",
                    "error": f"Not enough players (need {game_mode.minimum_players}, have {len(game_moves)})",
                }

            # Get teams
            teams = self.get_game_teams(game_moves)

            # Update game state
            self.current_game_mode = game_mode
            self.game_in_progress = True

            # Set shared flags
            self.menu.value = 0
            self.restart.value = 1
            self.controller_game_mode.value = game_mode.value

            # Play instructions
            if self.ns.settings.get("play_instructions", False) and self.ns.settings.get(
                "play_audio", True
            ):
                self.play_instructions(game_mode)

            # Send game_started event
            self.event_queue.put(
                {
                    "event": "game_started",
                    "data": {
                        "game_mode": game_mode.name,
                        "player_count": len(game_moves),
                        "random_mode": random_mode,
                    },
                    "timestamp": time.time(),
                }
            )

            # Create and run game instance (blocking)
            logger.info(f"Starting game: {game_mode.name} with {len(game_moves)} players")
            game_instance = self.create_game_instance(game_mode, game_moves, teams)

            # Game has ended (constructor returned)
            logger.info(f"Game ended: {game_mode.name}")

            # Cleanup
            self.cleanup_game(random_mode)

            return {
                "status": "success",
                "data": {
                    "game_started": True,
                    "game_mode": game_mode.name,
                    "player_count": len(game_moves),
                },
            }

        except Exception as e:
            logger.error(f"Error starting game: {e}", exc_info=True)
            self.game_in_progress = False
            self.menu.value = 1
            self.restart.value = 0
            return {"status": "error", "error": str(e)}

    def handle_get_game_status(self) -> dict:
        """Get current game status."""
        return {
            "status": "success",
            "data": {
                "game_in_progress": self.game_in_progress,
                "game_mode": self.current_game_mode.name if self.current_game_mode else None,
            },
        }

    def handle_force_end_game(self) -> dict:
        """Force current game to end."""
        if self.game_in_progress:
            self.menu.value = 1
            self.restart.value = 0
            self.game_in_progress = False
            return {"status": "success", "data": {"forced": True}}
        return {
            "status": "success",
            "data": {"forced": False, "message": "No game in progress"},
        }

    def handle_update_controller_state(self, params: dict) -> dict:
        """
        Update controller state references.

        Called by Menu to pass controller state dictionaries.
        """
        self.controller_teams = params.get("controller_teams", {})
        self.controller_colors = params.get("controller_colors", {})
        self.dead_moves = params.get("dead_moves", {})
        self.invincible_moves = params.get("invincible_moves", {})
        self.force_color = params.get("force_color", {})
        self.game_opts = params.get("game_opts", {})

        return {"status": "success", "data": {"updated": True}}

    def select_random_game_mode(self, player_count: int) -> Games:
        """
        Select random game mode avoiding recent repeats.

        Args:
            player_count: Number of players

        Returns:
            Selected game mode
        """
        # Get available random modes from settings
        random_mode_names = self.ns.settings.get("random_modes", [])
        available_modes = [Games[name] for name in random_mode_names if name in Games.__members__]

        # Filter by minimum players if enforcing
        if self.ns.settings.get("enforce_minimum", True):
            available_modes = [
                mode for mode in available_modes if mode.minimum_players <= player_count
            ]

        # If no valid modes, default to FFA
        if len(available_modes) == 0:
            return Games.JoustFFA

        # If only one mode, use it
        if len(available_modes) == 1:
            return available_modes[0]

        # Reset history if we've played all modes
        if len(self.random_history) >= len(available_modes):
            self.random_history = [self.old_game_mode]

        # Pick random mode not in recent history
        selected = random.choice(available_modes)
        while selected in self.random_history:
            selected = random.choice(available_modes)

        self.old_game_mode = selected
        self.random_history.append(selected)

        return selected

    def get_game_teams(self, game_moves: list[str]) -> dict:
        """
        Get team assignments for game.

        Args:
            game_moves: List of controller serials

        Returns:
            Dict mapping serial to team number
        """
        # For now, return empty dict
        # Teams are managed by individual game classes
        # This is a placeholder for future team management
        return {}

    def play_instructions(self, game_mode: Games):
        """Play instruction audio for game mode."""
        voice = self.ns.settings.get("menu_voice", "en")

        instruction_files = {
            Games.JoustFFA: f"audio/Menu/vox/{voice}/FFA-instructions.wav",
            Games.JoustRandomTeams: f"audio/Menu/vox/{voice}/Teams-instructions.wav",
            Games.Traitor: f"audio/Menu/vox/{voice}/Traitor-instructions.wav",
            Games.Werewolf: f"audio/Menu/vox/{voice}/werewolf-instructions.wav",
            Games.Zombies: f"audio/Menu/vox/{voice}/zombie-instructions.wav",
            Games.Commander: f"audio/Menu/vox/{voice}/commander-instructions.wav",
            Games.Ninja: f"audio/Menu/vox/{voice}/Ninjabomb-instructions.wav",
        }

        if game_mode in instruction_files:
            try:
                Audio(instruction_files[game_mode]).start_effect_and_wait()
            except Exception as e:
                logger.warning(f"Could not play instructions: {e}")

    def create_game_instance(self, game_mode: Games, moves: list[str], teams: dict):
        """
        Create and run game instance.

        This method blocks until the game completes.

        Args:
            game_mode: Game mode to play
            moves: List of controller serials
            teams: Team assignments

        Returns:
            Game instance (after game completes)
        """
        # Select music
        if game_mode == Games.Zombies:
            music = self.zombie_music
        elif game_mode in [Games.Commander, Games.Ninja]:
            music = self.commander_music
        elif game_mode == Games.FightClub:
            # Random music for fight club
            music = self.commander_music if random.random() > 0.2 else self.joust_music
        else:
            music = self.joust_music

        # Common game constructor args
        common_args = {
            "moves": moves,
            "command_queue": self.command_queue,
            "ns": self.ns,
            "red_on_kill": self.red_on_kill,
            "music": music,
            "teams": teams,
            "game_mode": game_mode,
            "controller_teams": self.controller_teams,
            "controller_colors": self.controller_colors,
            "dead_moves": self.dead_moves,
            "invincible_moves": self.invincible_moves,
            "force_move_colors": self.force_color,
            "music_speed": self.music_speed,
            "show_team_colors": self.show_team_colors,
            "restart": self.restart,
            "revive": self.revive,
        }

        # Add opts for games that need it
        if game_mode in [
            Games.Zombies,
            Games.Commander,
            Games.NonStop,
            Games.FightClub,
            Games.Ninja,
        ]:
            common_args["opts"] = self.game_opts

        # Create appropriate game instance
        # Note: Game constructors are blocking and run the game loop
        if game_mode == Games.JoustFFA:
            if self.experimental:
                logger.info("Using experimental FFA mode")
                import common as common_module

                moves_objs = [
                    common_module.get_move(serial, num) for num, serial in enumerate(moves)
                ]
                return ffa.FreeForAll(moves_objs, music)
            return joust_ffa.Joust(**common_args)

        if game_mode == Games.JoustTeams:
            return joust_teams.Joust(**common_args)

        if game_mode == Games.JoustRandomTeams:
            return joust_random_teams.Joust(**common_args)

        if game_mode == Games.Traitor:
            return traitor.Joust(**common_args)

        if game_mode == Games.Werewolf:
            return werewolf.Joust(**common_args)

        if game_mode == Games.Zombies:
            return zombie.Joust(**common_args)

        if game_mode == Games.Commander:
            return commander.Joust(**common_args)

        if game_mode == Games.Swapper:
            return swapper.Joust(**common_args)

        if game_mode == Games.FightClub:
            return fight_club.Joust(**common_args)

        if game_mode == Games.Tournament:
            return tournament.Joust(**common_args)

        if game_mode == Games.NonStop:
            return joust_non_stop.Joust(**common_args)

        if game_mode == Games.Ninja:
            return speed_bomb.Joust(**common_args)

        logger.error(f"Unknown game mode: {game_mode}")
        return None

    def cleanup_game(self, was_random_mode: bool):
        """
        Cleanup after game ends.

        Args:
            was_random_mode: Whether this was a random mode game
        """
        # Reload music for variety
        try:
            self.joust_music.load_audio("audio/Joust/music/*")
            self.zombie_music.load_audio("audio/Zombie/music/*")
            self.commander_music.load_audio("audio/Commander/music/*")
        except Exception as e:
            logger.warning(f"Could not reload music: {e}")

        # Reset game state
        self.game_in_progress = False
        self.menu.value = 1
        self.restart.value = 0

        # If was random mode, play transition audio
        if was_random_mode:
            self.current_game_mode = Games.Random
            if self.ns.settings.get("play_instructions", False) and self.ns.settings.get(
                "play_audio", True
            ):
                try:
                    voice = self.ns.settings.get("menu_voice", "en")
                    Audio(f"audio/Menu/vox/{voice}/tradeoff2.wav").start_effect_and_wait()
                except Exception as e:
                    logger.warning(f"Could not play transition audio: {e}")

        # Reset controller state via ControllerManager
        ctrl_response = controller_manager.send_command(
            self.controller_cmd_queue, self.controller_resp_queue, "reset_state"
        )

        if ctrl_response["status"] != "success":
            logger.warning("Failed to reset controller state")

        # Send game_ended event
        self.event_queue.put(
            {
                "event": "game_ended",
                "data": {"game_mode": self.current_game_mode.name},
                "timestamp": time.time(),
            }
        )

        logger.info("Game cleanup complete")

    def shutdown(self):
        """Shutdown GameCoordinator gracefully."""
        logger.info("Shutting down GameCoordinator")

        # Stop any music
        try:
            if self.joust_music:
                self.joust_music.stop_audio()
            if self.zombie_music:
                self.zombie_music.stop_audio()
            if self.commander_music:
                self.commander_music.stop_audio()
        except:
            pass

        logger.info("GameCoordinator shutdown complete")


def send_command(
    command_queue, response_queue, command: str, params: dict = None, timeout: float = 1.0
) -> dict:
    """
    Helper function to send command to GameCoordinator and wait for response.

    Args:
        command_queue: Queue to send commands
        response_queue: Queue to receive responses
        command: Command name
        params: Command parameters
        timeout: Response timeout in seconds

    Returns:
        Response dict with status and data
    """
    import uuid

    request_id = str(uuid.uuid4())
    message = {
        "command": command,
        "params": params or {},
        "request_id": request_id,
        "timestamp": time.time(),
    }

    # Send command
    command_queue.put(message)

    # Wait for response
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = response_queue.get(timeout=0.1)
            if response.get("request_id") == request_id:
                return response
        except:
            continue

    # Timeout
    return {"status": "error", "error": "Request timeout"}
