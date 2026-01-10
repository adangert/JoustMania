"""
JoustMania Main Orchestrator (gRPC Cloud-Native Version)

Cloud-native architecture using gRPC for all microservice communication.
Designed for Kubernetes deployment across multiple Raspberry Pis.

This is a refactored version of piparty.py using:
- gRPC clients for all service communication
- No Queue-based IPC (network-ready)
- Clean separation of concerns
- Container and Kubernetes ready

Part of Phase 8a (gRPC Conversion) - Cloud-Native PoC
"""

import logging
import threading
import time
from multiprocessing import Manager, Value
from typing import Any

from grpc_clients import ServiceManager

from services.settings import settings_pb2

logger = logging.getLogger(__name__)


class JoustManiaOrchestrator:
    """
    Main orchestrator for JoustMania using gRPC microservices.

    Coordinates all microservices via gRPC:
    - Settings service (port 50051)
    - ControllerManager service (port 50052) - TODO
    - GameCoordinator service (port 50053) - TODO
    - Menu service (port 50054) - TODO
    - Supervisor service (port 50055) - TODO
    """

    def __init__(self, services_host: str = "localhost"):
        """
        Initialize JoustMania orchestrator.

        Args:
            services_host: Hostname where microservices are running
                          'localhost' for development
                          Service names for Kubernetes (e.g., 'settings-service')
        """
        logger.info("Initializing JoustMania Orchestrator (gRPC Cloud-Native)")

        # Shared state manager (for backward compatibility with web UI)
        self.manager = Manager()
        self.ns = self.manager.Namespace()
        self.ns.settings = {}
        self.ns.status = {}
        self.ns.battery_status = {}

        # Shared values (multiprocessing)
        self.menu = Value("i", 1)  # 1 = Menu, 0 = Game
        self.controller_game_mode = Value("i", 1)
        self.restart = Value("i", 0)
        self.dead_count = Value("i", 0)

        # gRPC service clients
        self.services = ServiceManager(host=services_host)

        # Settings change subscription thread
        self.settings_subscription_thread = None
        self.running = False

        logger.info(f"Orchestrator initialized for services at: {services_host}")

    def start(self):
        """Start orchestrator and connect to all services."""
        logger.info("Starting JoustMania Orchestrator...")

        try:
            # Connect to all gRPC services
            self.services.connect_all()

            # Load initial settings
            self._load_initial_settings()

            # Subscribe to settings changes
            self._subscribe_to_settings()

            logger.info("Orchestrator started successfully")

        except Exception as e:
            logger.error(f"Failed to start orchestrator: {e}", exc_info=True)
            raise

    def stop(self):
        """Stop orchestrator and close all connections."""
        logger.info("Stopping JoustMania Orchestrator...")

        self.running = False

        # Wait for subscription thread to finish
        if self.settings_subscription_thread and self.settings_subscription_thread.is_alive():
            self.settings_subscription_thread.join(timeout=5.0)

        # Close all service connections
        self.services.close_all()

        logger.info("Orchestrator stopped")

    def _load_initial_settings(self):
        """Load initial settings from Settings service."""
        logger.info("Loading initial settings from Settings service...")

        try:
            settings = self.services.settings.get_settings(timeout=10.0)
            self.ns.settings = settings
            logger.info(f"Loaded {len(settings)} settings from Settings service")
            logger.debug(f"Settings: {settings}")

        except Exception as e:
            logger.error(f"Failed to load settings: {e}", exc_info=True)
            # Use defaults
            self.ns.settings = self._get_default_settings()
            logger.warning("Using default settings due to load failure")

    def _get_default_settings(self) -> dict[str, Any]:
        """Get default settings (fallback)."""
        return {
            "sensitivity": 2,
            "play_instructions": True,
            "current_game": "JoustFFA",
            "random_modes": ["JoustFFA", "JoustRandomTeams", "Werewolf", "Swapper"],
            "play_audio": True,
            "menu_voice": "ivy",
            "move_can_be_admin": True,
            "enforce_minimum": True,
            "red_on_kill": True,
            "random_teams": True,
            "color_lock": False,
            "random_team_size": 4,
            "force_all_start": False,
        }

    def _subscribe_to_settings(self):
        """Subscribe to settings changes via gRPC streaming."""
        logger.info("Subscribing to settings changes...")

        self.running = True

        def subscription_handler(event: settings_pb2.SettingChangeEvent):
            """Handle setting change events."""
            logger.info(
                f"Setting changed: {event.key} = {event.new_value} (source: {event.source})"
            )

            # Update local cache
            key = event.key
            new_value = event.new_value

            # Parse value type
            if new_value.lower() in ("true", "false"):
                parsed_value = new_value.lower() == "true"
            else:
                try:
                    parsed_value = int(new_value)
                except ValueError:
                    if new_value.startswith("[") and new_value.endswith("]"):
                        import ast

                        parsed_value = ast.literal_eval(new_value)
                    else:
                        parsed_value = new_value

            # Update namespace
            self.ns.settings[key] = parsed_value
            logger.debug(f"Updated ns.settings['{key}'] = {parsed_value}")

        def subscribe_loop():
            """Run subscription in background thread."""
            try:
                logger.info("Starting settings subscription loop...")
                self.services.settings.subscribe_to_changes(subscription_handler)
            except Exception as e:
                logger.error(f"Settings subscription error: {e}", exc_info=True)

        # Start subscription in background thread
        self.settings_subscription_thread = threading.Thread(
            target=subscribe_loop, name="SettingsSubscription", daemon=True
        )
        self.settings_subscription_thread.start()
        logger.info("Settings subscription started in background thread")

    def update_setting(self, key: str, value: Any, source: str = "orchestrator"):
        """
        Update a setting via Settings service.

        Args:
            key: Setting key
            value: New value
            source: Source of the change

        Returns:
            True if update succeeded
        """
        try:
            success = self.services.settings.update_setting(key, value, source=source)
            if success:
                logger.info(f"Updated setting '{key}' = {value}")
            return success
        except Exception as e:
            logger.error(f"Failed to update setting '{key}': {e}")
            return False

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value.

        Args:
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value or default
        """
        return self.ns.settings.get(key, default)

    def run(self):
        """
        Main run loop (placeholder for now).

        In full implementation, this would:
        - Handle web UI commands
        - Coordinate game flow
        - Manage controller states
        - etc.
        """
        logger.info("JoustMania orchestrator running...")
        logger.info("Press Ctrl+C to stop")

        try:
            while self.running:
                time.sleep(1.0)

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.stop()


def main():
    """Main entry point for JoustMania orchestrator."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create and start orchestrator
    orchestrator = JoustManiaOrchestrator(services_host="localhost")

    try:
        orchestrator.start()
        orchestrator.run()
    except Exception as e:
        logger.error(f"Orchestrator failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
