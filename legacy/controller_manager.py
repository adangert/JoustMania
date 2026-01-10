"""
Controller Manager Process for JoustMania

Manages Move controller lifecycle as a separate process:
- Discover and pair controllers
- Spawn controller processes
- Monitor controller health
- Provide query interface via IPC

This is part of the microservices refactoring to separate concerns.
"""

import logging
import time
from multiprocessing import Array, Process, Value

import controller_process
import pair
import psmove
from common import Opts, Status
from controller_state import ControllerState

logger = logging.getLogger(__name__)


class ControllerManagerProcess(Process):
    """
    Controller Manager running as separate process.

    Responsibilities:
    - Discover new controllers (USB/Bluetooth)
    - Pair and spawn controller processes
    - Monitor controller health
    - Handle IPC requests from Menu process

    IPC Protocol:
    - Command Queue: Receives commands from other processes
    - Response Queue: Sends responses back
    - Shared Memory: ControllerState instances
    """

    def __init__(
        self,
        command_queue,
        response_queue,
        menu_flag,
        restart_flag,
        dead_count,
        music_speed,
        show_battery,
        show_team_colors,
        red_on_kill,
        revive,
        controller_game_mode,
        ns,
        use_state_based_tracking=True,
    ):
        """
        Initialize ControllerManager process.

        Args:
            command_queue: Queue for receiving commands
            response_queue: Queue for sending responses
            menu_flag: Shared flag for menu mode (1) or game mode (0)
            restart_flag: Shared flag for restart state
            dead_count: Shared counter for dead controllers
            music_speed: Shared music speed value
            show_battery: Shared flag for battery display
            show_team_colors: Shared flag for team color display
            red_on_kill: Shared flag for red on kill
            revive: Shared flag for revival enabled
            controller_game_mode: Shared game mode value
            ns: Shared namespace for settings
            use_state_based_tracking: Whether to use state-based tracking
        """
        super().__init__(name="ControllerManager")

        # IPC
        self.command_queue = command_queue
        self.response_queue = response_queue

        # Shared flags from main process
        self.menu = menu_flag
        self.restart = restart_flag
        self.dead_count = dead_count
        self.music_speed = music_speed
        self.show_battery = show_battery
        self.show_team_colors = show_team_colors
        self.red_on_kill = red_on_kill
        self.revive = revive
        self.controller_game_mode = controller_game_mode
        self.ns = ns

        # Feature flag
        self.use_state_based_tracking = use_state_based_tracking

        # Controller tracking
        self.tracked_moves: dict[str, Process] = {}
        self.controller_states: dict[str, ControllerState] = {}
        self.paired_moves: list[str] = []
        self.out_moves: dict[str, int] = {}

        # Per-controller state (shared memory)
        self.menu_opts: dict[str, Array] = {}
        self.game_opts: dict[str, Array] = {}
        self.force_color: dict[str, Array] = {}
        self.controller_teams: dict[str, Value] = {}
        self.controller_colors: dict[str, Array] = {}
        self.controller_sensitivity: dict[str, Value] = {}
        self.dead_moves: dict[str, Value] = {}
        self.invincible_moves: dict[str, Value] = {}
        self.kill_controller_proc: dict[str, Value] = {}

        # Pairing
        self.pair = pair.Pair()

        # Running flag
        self.running = True

        logger.info("ControllerManager process initialized")

    def run(self):
        """
        Main process loop.

        Handles:
        - Controller discovery
        - IPC command processing
        - Health monitoring
        """
        logger.info("ControllerManager process started")

        last_discovery = time.time()
        discovery_interval = 1.0  # Check for new controllers every second

        try:
            while self.running:
                # Handle IPC commands (non-blocking)
                self.process_commands()

                # Periodic controller discovery
                if time.time() - last_discovery > discovery_interval:
                    self.check_for_new_controllers()
                    last_discovery = time.time()

                # Monitor controller health
                self.monitor_controller_health()

                # Brief sleep to avoid busy loop
                time.sleep(0.01)

        except KeyboardInterrupt:
            logger.info("ControllerManager received interrupt")
        except Exception as e:
            logger.error(f"ControllerManager error: {e}", exc_info=True)
        finally:
            self.shutdown()

        logger.info("ControllerManager process stopped")

    def process_commands(self):
        """
        Process commands from command queue (non-blocking).

        Commands:
        - get_controller_count: Return number of tracked controllers
        - get_ready_controllers: Return list of ready controllers
        - get_game_controllers: Return list of game controllers
        - pair_controller: Pair a new controller
        - remove_controller: Remove a controller
        - stop_all: Stop all controllers
        - shutdown: Shutdown manager
        """
        try:
            while not self.command_queue.empty():
                message = self.command_queue.get_nowait()
                command = message.get("command")
                params = message.get("params", {})
                request_id = message.get("request_id")

                logger.debug(f"Processing command: {command}")

                # Dispatch command
                if command == "get_controller_count":
                    response = self.handle_get_controller_count()
                elif command == "get_ready_controllers":
                    response = self.handle_get_ready_controllers(params)
                elif command == "get_game_controllers":
                    response = self.handle_get_game_controllers()
                elif command == "pair_controller":
                    response = self.handle_pair_controller(params)
                elif command == "remove_controller":
                    response = self.handle_remove_controller(params)
                elif command == "stop_all":
                    response = self.handle_stop_all()
                elif command == "reset_state":
                    response = self.handle_reset_state()
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

    def check_for_new_controllers(self):
        """
        Check for newly connected controllers and pair them.

        This runs periodically in the main loop.
        """
        try:
            current_count = psmove.count_connected()

            # Check for new moves
            for move_num in range(current_count):
                move = psmove.PSMove(move_num)
                move_serial = move.get_serial()

                # If not already tracked, pair it
                if move_serial not in self.tracked_moves:
                    # Check if USB connected, pair if so
                    if move.connection_type == psmove.Conn_USB:
                        if move_serial not in self.paired_moves:
                            logger.info(f"Pairing USB controller: {move_serial}")
                            self.pair_usb_move(move)

                    # Spawn tracking process
                    logger.info(f"Spawning process for controller: {move_serial}")
                    self.spawn_controller_process(move, move_num)

        except Exception as e:
            logger.error(f"Error checking for new controllers: {e}", exc_info=True)

    def pair_usb_move(self, move):
        """
        Pair a USB-connected controller via Bluetooth.

        Args:
            move: PSMove controller object
        """
        try:
            move_serial = move.get_serial()

            # Pair via Bluetooth
            self.pair.pair_move(move_serial)
            self.paired_moves.append(move_serial)

            logger.info(f"Paired controller {move_serial} via Bluetooth")

        except Exception as e:
            logger.error(f"Error pairing controller: {e}", exc_info=True)

    def spawn_controller_process(self, move, move_num):
        """
        Spawn a tracking process for a controller.

        Args:
            move: PSMove controller object
            move_num: Controller index
        """
        try:
            move_serial = move.get_serial()

            # Create shared memory for this controller
            menu_opts = Array("i", [0] * 8)
            game_opts = Array("i", [0] * 10)
            color = Array("i", [0, 0, 0])
            team = Value("i", 0)
            team_color_enum = Array("i", [0, 0, 0])
            dead_move = Value("i", 0)
            invincible_move = Value("i", 0)
            kill_proc = Value("b", False)
            sensitivity = Value("i", 0)
            sensitivity.value = self.ns.settings.get("sensitivity", 2)

            # Initialize menu options
            menu_opts[Opts.STATUS.value] = Status.ALIVE.value

            # Create controller state if using state-based tracking
            if self.use_state_based_tracking:
                controller_state = ControllerState()
                self.controller_states[move_serial] = controller_state

                # Spawn state-based process
                proc = Process(
                    target=controller_process.state_based_track_move,
                    args=(
                        controller_state,
                        move_serial,
                        move_num,
                        self.menu,
                        self.restart,
                        menu_opts,
                        game_opts,
                        color,
                        self.show_battery,
                        self.dead_count,
                        self.controller_game_mode,
                        team,
                        team_color_enum,
                        sensitivity,
                        dead_move,
                        invincible_move,
                        self.music_speed,
                        self.show_team_colors,
                        self.red_on_kill,
                        self.revive,
                        kill_proc,
                    ),
                    name=f"Controller-{move_serial}",
                )
            else:
                # Spawn legacy process
                proc = Process(
                    target=controller_process.main_track_move,
                    args=(
                        self.menu,
                        self.restart,
                        move_serial,
                        move_num,
                        menu_opts,
                        game_opts,
                        color,
                        self.show_battery,
                        self.dead_count,
                        self.controller_game_mode,
                        team,
                        team_color_enum,
                        sensitivity,
                        dead_move,
                        invincible_move,
                        self.music_speed,
                        self.show_team_colors,
                        self.red_on_kill,
                        self.revive,
                        kill_proc,
                    ),
                    name=f"Controller-{move_serial}",
                )

            proc.start()

            # Track all state
            self.tracked_moves[move_serial] = proc
            self.menu_opts[move_serial] = menu_opts
            self.game_opts[move_serial] = game_opts
            self.force_color[move_serial] = color
            self.controller_teams[move_serial] = team
            self.controller_colors[move_serial] = team_color_enum
            self.controller_sensitivity[move_serial] = sensitivity
            self.dead_moves[move_serial] = dead_move
            self.invincible_moves[move_serial] = invincible_move
            self.kill_controller_proc[move_serial] = kill_proc
            self.out_moves[move_serial] = Status.ALIVE.value

            logger.info(f"Spawned controller process for {move_serial}")

        except Exception as e:
            logger.error(f"Error spawning controller process: {e}", exc_info=True)

    def remove_controller(self, move_serial: str):
        """
        Stop and cleanup a controller process.

        Args:
            move_serial: Controller serial number
        """
        try:
            if move_serial not in self.kill_controller_proc:
                logger.warning(f"Controller {move_serial} not found")
                return

            logger.info(f"Removing controller: {move_serial}")

            # Signal process to stop
            self.kill_controller_proc[move_serial].value = True

            # Wait for process to finish
            proc = self.tracked_moves[move_serial]
            proc.join(timeout=2.0)
            if proc.is_alive():
                logger.warning(f"Controller process {move_serial} didn't stop, terminating")
                proc.terminate()

            # Cleanup state
            del self.tracked_moves[move_serial]
            del self.force_color[move_serial]
            del self.controller_teams[move_serial]
            del self.controller_colors[move_serial]
            del self.controller_sensitivity[move_serial]
            del self.dead_moves[move_serial]
            del self.invincible_moves[move_serial]
            del self.menu_opts[move_serial]
            del self.game_opts[move_serial]
            del self.kill_controller_proc[move_serial]
            del self.out_moves[move_serial]

            # Cleanup controller state if using state-based
            if self.use_state_based_tracking and move_serial in self.controller_states:
                del self.controller_states[move_serial]

            logger.info(f"Removed controller {move_serial}")

        except Exception as e:
            logger.error(f"Error removing controller: {e}", exc_info=True)

    def monitor_controller_health(self):
        """
        Monitor controller processes and remove disconnected ones.

        Checks:
        - Process still alive
        - Controller still connected
        """
        try:
            # Get currently connected controller serials
            current_count = psmove.count_connected()
            found_serials = set()

            for move_num in range(current_count):
                move = psmove.PSMove(move_num)
                found_serials.add(move.get_serial())

            # Find controllers that are tracked but no longer connected
            for move_serial in list(self.tracked_moves.keys()):
                if move_serial not in found_serials:
                    logger.info(f"Controller {move_serial} disconnected")
                    self.remove_controller(move_serial)

        except Exception as e:
            logger.error(f"Error monitoring controller health: {e}", exc_info=True)

    def shutdown(self):
        """Shutdown all controller processes gracefully."""
        logger.info("Shutting down ControllerManager")

        # Stop all controllers
        for move_serial in list(self.tracked_moves.keys()):
            self.remove_controller(move_serial)

        logger.info("All controllers stopped")

    # IPC Command Handlers

    def handle_get_controller_count(self) -> dict:
        """Get number of tracked controllers."""
        return {"status": "success", "data": {"count": len(self.tracked_moves)}}

    def handle_get_ready_controllers(self, params: dict) -> dict:
        """
        Get list of controllers ready for game.

        Args:
            params: {'force_all': bool}
        """
        force_all = params.get("force_all", False)
        ready_serials = []

        for move_serial, menu_opts in self.menu_opts.items():
            # Check if controller is alive
            if self.out_moves[move_serial] == Status.ALIVE.value:
                # Check if charging (skip charging controllers)
                is_charging = menu_opts[Opts.CHARGING.value] if hasattr(Opts, "CHARGING") else False

                if not is_charging:
                    ready_serials.append(move_serial)

        return {
            "status": "success",
            "data": {"controllers": ready_serials, "count": len(ready_serials)},
        }

    def handle_get_game_controllers(self) -> dict:
        """Get list of all tracked controllers."""
        return {
            "status": "success",
            "data": {
                "controllers": list(self.tracked_moves.keys()),
                "count": len(self.tracked_moves),
            },
        }

    def handle_pair_controller(self, params: dict) -> dict:
        """Pair a new controller (triggered by IPC)."""
        # This will be handled by periodic discovery
        # Just acknowledge the request
        return {"status": "success", "data": {"message": "Controller discovery runs automatically"}}

    def handle_remove_controller(self, params: dict) -> dict:
        """Remove a controller."""
        move_serial = params.get("serial")
        if not move_serial:
            return {"status": "error", "error": "Missing serial parameter"}

        self.remove_controller(move_serial)
        return {"status": "success", "data": {"serial": move_serial}}

    def handle_stop_all(self) -> dict:
        """Stop all controllers."""
        for move_serial in list(self.tracked_moves.keys()):
            self.remove_controller(move_serial)

        return {"status": "success", "data": {"stopped": len(self.tracked_moves)}}

    def handle_reset_state(self) -> dict:
        """Reset all controller game state."""
        for move_serial in self.tracked_moves.keys():
            # Reset game options to 0
            for i in range(len(self.game_opts[move_serial])):
                self.game_opts[move_serial][i] = 0

            # Reset dead/invincible
            self.dead_moves[move_serial].value = 0
            self.invincible_moves[move_serial].value = 0

        return {"status": "success", "data": {"reset_count": len(self.tracked_moves)}}


def send_command(
    command_queue, response_queue, command: str, params: dict = None, timeout: float = 1.0
) -> dict:
    """
    Helper function to send command to ControllerManager and wait for response.

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
