"""
Settings Process for JoustMania

Manages settings as a separate process:
- Load/save settings from/to YAML file
- Validate setting updates against schema
- Provide query interface via IPC
- Publish change events (pub/sub)

This is part of the microservices refactoring (Phase 3).
"""

import fnmatch
import logging
import os
import time
import uuid
from multiprocessing import Process
from sys import platform
from typing import Any

import yaml

from lib.types import Games, Sensitivity

logger = logging.getLogger(__name__)


# Settings schema with validation rules (Phase 32 - cleaned up)
SETTINGS_SCHEMA = {
    "sensitivity": {
        "type": int,
        "min": 0,
        "max": 4,
        "default": Sensitivity.MID.value,
        "description": "Controller sensitivity (0=ultra slow, 4=ultra fast)",
    },
    "instructions": {
        "type": bool,
        "default": True,
        "description": "Play voice instructions before games",
    },
    "num_teams": {
        "type": int,
        "min": 2,
        "max": 6,
        "default": 2,
        "description": "Number of teams for team-based games",
    },
    "force_all_start": {
        "type": bool,
        "default": False,
        "description": "Start game with all controllers (even not ready)",
    },
    "nonstop_time_limit": {
        "type": int,
        "min": 0,
        "max": 3600,
        "default": 0,
        "description": "Time limit in seconds for Nonstop Joust (0 = no limit)",
    },
    "random_modes": {
        "type": list,
        "default": ["JoustFFA", "JoustRandomTeams", "Werewolf", "Nonstop"],
        "description": "Game modes included in random selection (for future Random game mode)",
    },
    "menu_voice": {
        "type": str,
        "allowed_values": ["ivy", "en", "es", "fr", "de"],
        "default": "ivy",
        "description": "Voice pack for menu announcements (for future multi-language support)",
    },
}


class SettingsProcess(Process):
    """
    Settings management running as separate process.

    Responsibilities:
    - Load/save settings from/to YAML file
    - Validate settings updates against schema
    - Provide query interface via IPC
    - Publish change events (pub/sub pattern)

    IPC Protocol:
    - Command Queue: Receives commands (get_settings, update_setting, subscribe, etc.)
    - Response Queue: Sends responses back
    - Subscribers publish to their own event queues
    """

    def __init__(self, command_queue, response_queue, settings_file):
        """
        Initialize Settings process.

        Args:
            command_queue: Queue for receiving commands
            response_queue: Queue for sending responses
            settings_file: Path to YAML settings file
        """
        super().__init__(name="Settings")

        # IPC
        self.command_queue = command_queue
        self.response_queue = response_queue

        # Settings file
        self.settings_file = settings_file

        # Current settings (in-memory)
        self.settings = {}

        # Subscribers: {subscription_id: {'queue': Queue, 'pattern': str}}
        self.subscribers = {}

        # Running flag
        self.running = True

        logger.info("Settings process initialized")

    def run(self):
        """
        Main process loop.

        Handles:
        - Loading settings on startup
        - IPC command processing
        - Publishing events to subscribers
        """
        logger.info("Settings process started")

        # Load settings from file
        self.load_settings()

        try:
            while self.running:
                # Process IPC commands (non-blocking)
                self.process_commands()

                # Brief sleep to avoid busy loop
                time.sleep(0.01)

        except KeyboardInterrupt:
            logger.info("Settings process received interrupt")
        except Exception as e:
            logger.error(f"Settings process error: {e}", exc_info=True)
        finally:
            self.shutdown()

        logger.info("Settings process stopped")

    def load_settings(self):
        """
        Load settings from YAML file.

        If file doesn't exist or is invalid, use defaults.
        """
        # Start with defaults
        self.settings = self.get_default_settings()

        try:
            if os.path.exists(self.settings_file):
                logger.info(f"Loading settings from {self.settings_file}")
                with open(self.settings_file) as f:
                    file_settings = yaml.safe_load(f)

                if file_settings:
                    # Validate and merge with defaults
                    for key, value in file_settings.items():
                        if key in SETTINGS_SCHEMA:
                            # Validate before accepting
                            valid, error = self.validate_setting_value(key, value)
                            if valid:
                                self.settings[key] = value
                            else:
                                logger.warning(f"Invalid setting {key}: {error}, using default")
                        else:
                            logger.warning(f"Unknown setting {key} in file, ignoring")

                logger.info("Settings loaded successfully")
            else:
                logger.info("Settings file not found, using defaults")
                # Save defaults to file
                self.save_settings()

        except Exception as e:
            logger.error(f"Error loading settings: {e}, using defaults", exc_info=True)
            self.settings = self.get_default_settings()

    def get_default_settings(self) -> dict:
        """Get default settings from schema."""
        defaults = {}
        for key, schema in SETTINGS_SCHEMA.items():
            defaults[key] = schema["default"]
        return defaults

    def save_settings(self):
        """
        Save settings to YAML file atomically.

        Uses temp file + rename for atomic write.
        """
        try:
            temp_file = self.settings_file + ".tmp"

            # Write to temp file
            with open(temp_file, "w") as f:
                yaml.dump(self.settings, f, default_flow_style=False)

            # Atomic rename
            os.replace(temp_file, self.settings_file)

            # Set permissions (make it writable)
            if platform == "linux" or platform == "linux2":
                os.chmod(self.settings_file, 0o666)

            logger.debug(f"Settings saved to {self.settings_file}")

        except Exception as e:
            logger.error(f"Error saving settings: {e}", exc_info=True)

    def validate_setting_value(self, key: str, value: Any) -> tuple[bool, str]:
        """
        Validate a setting value against schema.

        Args:
            key: Setting key
            value: Setting value

        Returns:
            (valid, error_message)
        """
        if key not in SETTINGS_SCHEMA:
            return False, f"Unknown setting: {key}"

        schema = SETTINGS_SCHEMA[key]

        # Check type
        expected_type = schema["type"]
        if not isinstance(value, expected_type):
            return False, f"Expected {expected_type.__name__}, got {type(value).__name__}"

        # Check range (for int)
        if expected_type == int:
            if "min" in schema and value < schema["min"]:
                return False, f"Value {value} below minimum {schema['min']}"
            if "max" in schema and value > schema["max"]:
                return False, f"Value {value} above maximum {schema['max']}"

        # Check allowed values (for str)
        if expected_type == str:
            if "allowed_values" in schema and value not in schema["allowed_values"]:
                return False, f"Value '{value}' not in allowed values: {schema['allowed_values']}"

        # Check list items (for list)
        if expected_type == list:
            # Validate random_modes specifically
            if key == "random_modes":
                valid_games = [g.name for g in Games if g != Games.JoustTeams and g != Games.Random]
                for item in value:
                    if item not in valid_games:
                        return False, f"Invalid game mode in random_modes: {item}"

        return True, ""

    def process_commands(self):
        """
        Process commands from command queue (non-blocking).

        Commands:
        - get_settings: Return all settings
        - get_setting: Return individual setting
        - update_setting: Update a setting
        - subscribe: Subscribe to setting changes
        - unsubscribe: Unsubscribe from changes
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
                if command == "get_settings":
                    response = self.handle_get_settings()
                elif command == "get_setting":
                    response = self.handle_get_setting(params)
                elif command == "update_setting":
                    response = self.handle_update_setting(params)
                elif command == "subscribe":
                    response = self.handle_subscribe(params)
                elif command == "unsubscribe":
                    response = self.handle_unsubscribe(params)
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

    def handle_get_settings(self) -> dict:
        """Handle get_settings command."""
        return {"status": "success", "data": {"settings": self.settings.copy()}}

    def handle_get_setting(self, params: dict) -> dict:
        """Handle get_setting command."""
        key = params.get("key")

        if not key:
            return {"status": "error", "error": "Missing key parameter"}

        if key not in self.settings:
            return {"status": "error", "error": f"Unknown setting: {key}"}

        return {"status": "success", "data": {"key": key, "value": self.settings[key]}}

    def handle_update_setting(self, params: dict) -> dict:
        """Handle update_setting command."""
        key = params.get("key")
        value = params.get("value")
        source = params.get("source", "unknown")

        if not key:
            return {"status": "error", "error": "Missing key parameter"}

        if key not in SETTINGS_SCHEMA:
            return {"status": "error", "error": f"Unknown setting: {key}"}

        # Check if immutable
        schema = SETTINGS_SCHEMA[key]
        if schema.get("immutable", False):
            return {"status": "error", "error": f"Setting {key} is immutable"}

        # Validate value
        valid, error = self.validate_setting_value(key, value)
        if not valid:
            return {"status": "error", "error": f"Validation failed: {error}"}

        # Update setting
        old_value = self.settings.get(key)
        self.settings[key] = value

        # Save to file
        self.save_settings()

        # Publish change event
        self.publish_change(key, old_value, value, source)

        logger.info(f"Setting updated: {key} = {value} (source: {source})")

        return {
            "status": "success",
            "data": {"key": key, "old_value": old_value, "new_value": value},
        }

    def handle_subscribe(self, params: dict) -> dict:
        """Handle subscribe command."""
        pattern = params.get("pattern", "*")
        event_queue = params.get("event_queue")

        if not event_queue:
            return {"status": "error", "error": "Missing event_queue parameter"}

        # Create subscription
        subscription_id = str(uuid.uuid4())
        self.subscribers[subscription_id] = {"queue": event_queue, "pattern": pattern}

        logger.info(f"New subscription: {subscription_id} (pattern: {pattern})")

        return {
            "status": "success",
            "data": {"subscription_id": subscription_id, "pattern": pattern},
        }

    def handle_unsubscribe(self, params: dict) -> dict:
        """Handle unsubscribe command."""
        subscription_id = params.get("subscription_id")

        if not subscription_id:
            return {"status": "error", "error": "Missing subscription_id parameter"}

        if subscription_id not in self.subscribers:
            return {"status": "error", "error": f"Unknown subscription: {subscription_id}"}

        del self.subscribers[subscription_id]

        logger.info(f"Unsubscribed: {subscription_id}")

        return {"status": "success", "data": {"subscription_id": subscription_id}}

    def publish_change(self, key: str, old_value: Any, new_value: Any, source: str = "unknown"):
        """
        Publish setting change to matching subscribers.

        Args:
            key: Setting key that changed
            old_value: Previous value
            new_value: New value
            source: Source of the change (webui, menu, etc.)
        """
        event = {
            "event": "setting_changed",
            "data": {"key": key, "old_value": old_value, "new_value": new_value, "source": source},
            "timestamp": time.time(),
        }

        # Send to all matching subscribers
        for sub_id, subscriber in list(self.subscribers.items()):
            pattern = subscriber["pattern"]

            # Check if pattern matches
            if pattern == "*" or pattern == key or fnmatch.fnmatch(key, pattern):
                try:
                    subscriber["queue"].put_nowait(event)
                    logger.debug(f"Published change to subscriber {sub_id}")
                except Exception as e:
                    logger.warning(f"Failed to send event to subscriber {sub_id}: {e}")

    def shutdown(self):
        """Shutdown Settings process gracefully."""
        logger.info("Shutting down Settings process")

        # Final save
        try:
            self.save_settings()
        except:
            pass

        logger.info("Settings process shutdown complete")


def send_command(
    command_queue, response_queue, command: str, params: dict = None, timeout: float = 1.0
) -> dict:
    """
    Helper function to send command to Settings process and wait for response.

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
        except:
            continue

    # Timeout
    return {"status": "error", "error": "Request timeout"}
