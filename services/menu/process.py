"""
Menu Process for JoustMania

Manages menu UI and game selection as a separate process:
- Run menu loop
- Display controller colors
- Handle game mode selection
- Detect game start triggers
- Send events to orchestrator

This is part of the microservices refactoring (Phase 5).
"""

import logging
import queue
import time
import uuid
from multiprocessing import Process

logger = logging.getLogger(__name__)


class MenuProcess(Process):
    """
    Menu UI process.

    Responsibilities:
    - Run menu display loop
    - Update controller colors based on game mode
    - Detect game start triggers
    - Handle game mode selection
    - Send events to orchestrator

    IPC Protocol:
    - Command Queue: Receives commands
    - Response Queue: Sends responses back
    - Event Queue: Sends events to orchestrator
    """

    def __init__(
        self,
        command_queue,
        response_queue,
        event_queue,
        controller_cmd_queue,
        controller_resp_queue,
        settings_cmd_queue,
        settings_resp_queue,
        menu_flag,
        ns,
    ):
        """
        Initialize Menu process.

        Args:
            command_queue: Queue for receiving commands
            response_queue: Queue for sending responses
            event_queue: Queue for sending events to orchestrator
            controller_cmd_queue: Queue for ControllerManager commands
            controller_resp_queue: Queue for ControllerManager responses
            settings_cmd_queue: Queue for Settings commands
            settings_resp_queue: Queue for Settings responses
            menu_flag: Shared flag (1 = menu, 0 = game)
            ns: Shared namespace with settings
        """
        super().__init__(name="Menu")

        # IPC
        self.command_queue = command_queue
        self.response_queue = response_queue
        self.event_queue = event_queue

        # Service IPC queues
        self.controller_cmd_queue = controller_cmd_queue
        self.controller_resp_queue = controller_resp_queue
        self.settings_cmd_queue = settings_cmd_queue
        self.settings_resp_queue = settings_resp_queue

        # Shared state
        self.menu_flag = menu_flag
        self.ns = ns

        # Menu state
        self.menu_running = False
        self.game_mode = None  # Will load from settings
        self.running = True

        logger.info("Menu process initialized")

    def run(self):
        """
        Main process loop.

        Handles:
        - Menu loop startup/shutdown
        - IPC command processing
        """
        logger.info("Menu process started")

        try:
            while self.running:
                # Process IPC commands (non-blocking)
                self.process_commands()

                # Run menu loop if active
                if self.menu_running:
                    self.menu_loop_iteration()

                # Brief sleep to avoid busy loop
                time.sleep(0.01)

        except KeyboardInterrupt:
            logger.info("Menu process received interrupt")
        except Exception as e:
            logger.error(f"Menu process error: {e}", exc_info=True)
        finally:
            self.shutdown()

        logger.info("Menu process stopped")

    def process_commands(self):
        """
        Process commands from command queue (non-blocking).

        Commands:
        - start_menu: Start menu loop
        - stop_menu: Stop menu loop
        - get_menu_status: Return menu state
        - shutdown: Shutdown process
        """
        try:
            while not self.command_queue.empty():
                message = self.command_queue.get_nowait()
                command = message.get("command")
                params = message.get("params", {})
                request_id = message.get("request_id")

                logger.debug(f"Processing command: {command}")

                # Dispatch command
                if command == "start_menu":
                    response = self.handle_start_menu(params)
                elif command == "stop_menu":
                    response = self.handle_stop_menu(params)
                elif command == "get_menu_status":
                    response = self.handle_get_menu_status()
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

    def handle_start_menu(self, _params: dict) -> dict:
        """Handle start_menu command."""
        if self.menu_running:
            return {"status": "error", "error": "Menu already running"}

        logger.info("Starting menu")

        # Load settings
        self.load_initial_state()

        # Set menu flag
        self.menu_flag.value = 1

        # Start menu
        self.menu_running = True

        # Send menu_started event
        self.send_event("menu_started", {})

        return {"status": "success", "data": {"menu_running": True}}

    def handle_stop_menu(self, _params: dict) -> dict:
        """Handle stop_menu command."""
        if not self.menu_running:
            return {"status": "error", "error": "Menu not running"}

        logger.info("Stopping menu")

        self.menu_running = False

        # Send menu_stopped event
        self.send_event("menu_stopped", {})

        return {"status": "success", "data": {"menu_running": False}}

    def handle_get_menu_status(self) -> dict:
        """Handle get_menu_status command."""
        return {
            "status": "success",
            "data": {
                "menu_running": self.menu_running,
                "game_mode": self.game_mode.name if self.game_mode else None,
            },
        }

    def load_initial_state(self):
        """Load initial state from settings."""
        # Get current game mode from settings
        current_game = self.ns.settings.get("current_game", "JoustFFA")

        # Import Games enum (avoid circular import)
        from common import Games

        self.game_mode = Games[current_game]

        logger.info(f"Loaded game mode: {self.game_mode.name}")

    def menu_loop_iteration(self):
        """
        Single iteration of menu loop.

        This is a simplified version demonstrating the pattern.
        Full implementation would include:
        - Controller color updates
        - Game mode selection handling
        - Admin controls
        - Music playback
        """
        # Check if game should start
        if self.check_game_start():
            self.request_game_start()

        # TODO: Update controller display
        # TODO: Handle game mode changes
        # TODO: Handle admin controls

    def check_game_start(self) -> bool:
        """
        Check if game should start.

        Returns True if all controllers are ready or admin force start.

        NOTE: This is a simplified check. Full implementation would:
        - Query ControllerManager for ready controllers
        - Check if all alive controllers are ready
        - Check for admin force start trigger
        """
        # For now, return False (menu never auto-starts game)
        # This will be implemented when integrating with ControllerManager
        return False

    def request_game_start(self):
        """Request game start from orchestrator."""
        logger.info("Requesting game start")

        # Stop menu
        self.menu_running = False

        # Import Games enum to check for Random mode
        from common import Games

        # Detect if Random mode is selected
        is_random_mode = self.game_mode == Games.Random if self.game_mode else False

        # Send game_requested event
        # Note: force_all_start is handled in admin.py when determining controller list
        self.send_event(
            "game_requested",
            {
                "game_mode": self.game_mode.name if self.game_mode else "JoustFFA",
                "random_mode": is_random_mode,
            },
        )

    def send_event(self, event_type: str, data: dict):
        """
        Send event to orchestrator.

        Args:
            event_type: Event type (menu_started, game_requested, etc.)
            data: Event data
        """
        event = {"event": event_type, "data": data, "timestamp": time.time()}

        try:
            self.event_queue.put_nowait(event)
            logger.debug(f"Sent event: {event_type}")
        except Exception as e:
            logger.error(f"Failed to send event {event_type}: {e}")

    def shutdown(self):
        """Shutdown Menu process gracefully."""
        logger.info("Shutting down Menu process")

        # Stop menu if running
        if self.menu_running:
            self.menu_running = False

        logger.info("Menu process shutdown complete")


def send_command(command_queue, response_queue, command: str, params: dict = None, timeout: float = 1.0) -> dict:
    """
    Helper function to send command to Menu process and wait for response.

    Args:
        command_queue: Queue to send commands
        response_queue: Queue to receive responses
        command: Command name
        params: Command parameters
        timeout: Response timeout in seconds

    Returns:
        Response dict with status and data
    """
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
        except queue.Empty:
            continue

    # Timeout
    return {"status": "error", "error": "Request timeout"}
