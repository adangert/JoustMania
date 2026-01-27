"""
Settings gRPC Servicer for JoustMania

Manages settings as a gRPC service:
- Load/save settings from/to YAML file
- Validate setting updates against schema
- Provide gRPC interface for queries and updates
- Publish change events via streaming
"""

import asyncio
import logging
import os
import sys
import time
from typing import Any

import yaml
from opentelemetry import trace

from lib.telemetry import SpanAttr, get_tracer
from lib.types import Games, Sensitivity
from proto import settings_pb2, settings_pb2_grpc

logger = logging.getLogger(__name__)

# Lazy telemetry initialization - defers OTLP setup until first span
tracer = get_tracer(__name__)

# Settings schema with validation rules
SETTINGS_SCHEMA = {
    "sensitivity": {
        "type": int,
        "min": 0,
        "max": 4,
        "default": Sensitivity.MEDIUM.value,
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
        "default": [Games.JoustFFA.name, Games.JoustRandomTeams.name, Games.Werewolf.name, Games.NonStop.name],
        "description": "Game modes included in random selection (for future Random game mode)",
    },
    "menu_voice": {
        "type": str,
        "allowed_values": ["ivy", "aaron"],
        "default": "ivy",
        "description": "Voice pack for menu announcements",
    },
    "play_audio": {
        "type": bool,
        "default": True,
        "description": "Enable/disable all audio playback",
    },
    "current_game": {
        "type": str,
        "allowed_values": Games.all_names(),
        "default": Games.JoustFFA.name,
        "description": "Currently selected game mode",
    },
    "random_teams": {
        "type": bool,
        "default": True,
        "description": "Randomize team assignments (vs sequential)",
    },
}


class SettingsServicer(settings_pb2_grpc.SettingsServiceServicer):
    """
    gRPC servicer implementation for Settings service.

    Manages settings with YAML persistence and validation.
    """

    def __init__(self, settings_file: str = "joustsettings.yaml"):
        """
        Initialize Settings servicer.

        Args:
            settings_file: Path to YAML settings file
        """
        self.settings_file = settings_file
        self.settings: dict[str, Any] = {}
        self.subscribers: dict[str, asyncio.Queue] = {}  # {subscriber_id: event_queue}
        self.subscriber_lock = asyncio.Lock()

        # Load settings from file
        self.load_settings()

        logger.info(f"SettingsServicer initialized with file: {settings_file}")

    def get_default_settings(self) -> dict:
        """Get default settings from schema."""
        defaults = {}
        for key, schema in SETTINGS_SCHEMA.items():
            defaults[key] = schema["default"]
        return defaults

    def load_settings(self):
        """Load settings from YAML file."""
        try:
            self.settings = self.get_default_settings()

            if os.path.exists(self.settings_file):
                logger.info(f"Loading settings from {self.settings_file}")
                with open(self.settings_file) as f:
                    file_settings = yaml.safe_load(f)

                if file_settings:
                    # Validate and merge with defaults
                    for key, value in file_settings.items():
                        if key in SETTINGS_SCHEMA:
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
                self.save_settings()

        except Exception as e:
            logger.error(f"Error loading settings: {e}, using defaults", exc_info=True)
            self.settings = self.get_default_settings()

    def save_settings(self):
        """
        Save settings to YAML file atomically.

        Uses temp file + rename for atomic write.
        """
        with tracer.start_as_current_span("save_settings") as span:
            try:
                temp_file = self.settings_file + ".tmp"

                # Write to temp file
                with open(temp_file, "w") as f:
                    yaml.dump(self.settings, f, default_flow_style=False)

                # Atomic rename
                os.replace(temp_file, self.settings_file)

                # Set permissions
                if sys.platform == "linux" or sys.platform == "linux2":
                    os.chmod(self.settings_file, 0o666)

                span.set_attribute("settings.file", self.settings_file)
                span.set_attribute("settings.count", len(self.settings))
                logger.debug(f"Settings saved to {self.settings_file}")

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"Error saving settings: {e}", exc_info=True)

    def _validate_int_range(self, value: int, schema: dict) -> tuple[bool, str, str]:
        """Validate integer is within schema min/max range."""
        if "min" in schema and value < schema["min"]:
            return False, f"Value {value} below minimum {schema['min']}", "below_min"
        if "max" in schema and value > schema["max"]:
            return False, f"Value {value} above maximum {schema['max']}", "above_max"
        return True, "", ""

    def _validate_str_allowed(self, value: str, schema: dict) -> tuple[bool, str, str]:
        """Validate string is in allowed values list."""
        if "allowed_values" in schema and value not in schema["allowed_values"]:
            return False, f"Value '{value}' not in allowed values: {schema['allowed_values']}", "not_allowed"
        return True, "", ""

    def _validate_list_items(self, value: list, key: str) -> tuple[bool, str, str]:
        """Validate list items for specific keys like random_modes."""
        if key == "random_modes":
            valid_games = [g.name for g in Games if g != Games.JoustTeams and g != Games.Random]
            for item in value:
                if item not in valid_games:
                    return False, f"Invalid game mode: {item}", "invalid_list_item"
        return True, "", ""

    def validate_setting_value(self, key: str, value: Any) -> tuple[bool, str]:
        """
        Validate a setting value against schema.

        Args:
            key: Setting key
            value: Setting value

        Returns:
            (valid, error_message)
        """
        with tracer.start_as_current_span("validate_setting_value") as span:
            span.set_attribute("setting.key", key)
            span.set_attribute("setting.value_type", type(value).__name__)

            # Check key exists
            if key not in SETTINGS_SCHEMA:
                span.set_attribute(SpanAttr.VALIDATION_RESULT, "invalid")
                span.set_attribute(SpanAttr.VALIDATION_REASON, "unknown_key")
                return False, f"Unknown setting: {key}"

            schema = SETTINGS_SCHEMA[key]

            # Check if immutable
            if schema.get("immutable", False):
                span.set_attribute(SpanAttr.VALIDATION_RESULT, "invalid")
                span.set_attribute(SpanAttr.VALIDATION_REASON, "immutable")
                return False, f"Setting '{key}' is immutable"

            # Check type
            expected_type = schema["type"]
            if not isinstance(value, expected_type):
                span.set_attribute(SpanAttr.VALIDATION_RESULT, "invalid")
                span.set_attribute(SpanAttr.VALIDATION_REASON, "type_mismatch")
                return False, f"Expected {expected_type.__name__}, got {type(value).__name__}"

            # Type-specific validation
            valid, error, reason = True, "", ""
            if expected_type is int:
                valid, error, reason = self._validate_int_range(value, schema)
            elif expected_type is str:
                valid, error, reason = self._validate_str_allowed(value, schema)
            elif expected_type is list:
                valid, error, reason = self._validate_list_items(value, key)

            if not valid:
                span.set_attribute(SpanAttr.VALIDATION_RESULT, "invalid")
                span.set_attribute(SpanAttr.VALIDATION_REASON, reason)
                return False, error

            span.set_attribute(SpanAttr.VALIDATION_RESULT, "valid")
            return True, ""

    async def publish_change(self, key: str, old_value: Any, new_value: Any, source: str):
        """
        Publish setting change event to all subscribers.

        Args:
            key: Setting key that changed
            old_value: Previous value
            new_value: New value
            source: Source of the change
        """
        with tracer.start_as_current_span("publish_change") as span:
            span.set_attribute("setting.key", key)
            span.set_attribute("setting.old_value", str(old_value))
            span.set_attribute("setting.new_value", str(new_value))
            span.set_attribute("change.source", source)

            event = settings_pb2.SettingChangeEvent(
                key=key,
                old_value=str(old_value),
                new_value=str(new_value),
                source=source,
                timestamp=int(time.time() * 1000),  # milliseconds
            )

            async with self.subscriber_lock:
                dead_subscribers = []
                subscriber_count = len(self.subscribers)
                span.set_attribute("subscribers.count", subscriber_count)

                for sub_id, event_queue in self.subscribers.items():
                    try:
                        event_queue.put_nowait(event)
                        logger.debug(f"Published change to subscriber {sub_id}")
                    except asyncio.QueueFull:
                        logger.warning(f"Subscriber {sub_id} queue full, skipping")
                    except Exception as e:
                        logger.error(f"Error publishing to subscriber {sub_id}: {e}")
                        dead_subscribers.append(sub_id)

            # Clean up dead subscribers (outside lock)
            async with self.subscriber_lock:
                for sub_id in dead_subscribers:
                    if sub_id in self.subscribers:
                        del self.subscribers[sub_id]
                        logger.info(f"Removed dead subscriber {sub_id}")

    # gRPC Service Methods

    def _value_to_string(self, value: Any) -> str:
        """
        Convert a setting value to string for gRPC response.

        Ensures booleans are lowercase ('true'/'false') for consistent
        comparison by consumers.
        """
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def GetSettings(self, request, context):  # noqa: N802, ARG002
        """Get all settings."""
        logger.debug("GetSettings called")

        try:
            # Convert settings to string map (booleans as lowercase)
            settings_map = {k: self._value_to_string(v) for k, v in self.settings.items()}

            return settings_pb2.GetSettingsResponse(settings=settings_map, success=True, error="")

        except Exception as e:
            logger.error(f"GetSettings error: {e}", exc_info=True)
            return settings_pb2.GetSettingsResponse(settings={}, success=False, error=str(e))

    def GetSetting(self, request, context):  # noqa: N802, ARG002
        """Get a specific setting."""
        logger.debug(f"GetSetting called: key={request.key}")

        try:
            key = request.key

            if key not in self.settings:
                return settings_pb2.GetSettingResponse(
                    key=key, value="", success=False, error=f"Setting '{key}' not found"
                )

            value = self.settings[key]

            return settings_pb2.GetSettingResponse(key=key, value=self._value_to_string(value), success=True, error="")

        except Exception as e:
            logger.error(f"GetSetting error: {e}", exc_info=True)
            return settings_pb2.GetSettingResponse(key=request.key, value="", success=False, error=str(e))

    async def UpdateSetting(self, request, context):  # noqa: N802, ARG002
        """Update a setting."""
        logger.info(f"UpdateSetting called: key={request.key}, value={request.value}, source={request.source}")

        try:
            key = request.key
            value_str = request.value
            source = request.source or "unknown"

            # Check if setting exists
            if key not in SETTINGS_SCHEMA:
                return settings_pb2.UpdateSettingResponse(
                    success=False, error=f"Unknown setting: {key}", old_value="", new_value=""
                )

            # Parse value based on schema type
            schema = SETTINGS_SCHEMA[key]
            expected_type = schema["type"]

            try:
                if expected_type is bool:
                    value = value_str.lower() in ("true", "1", "yes")
                elif expected_type is int:
                    value = int(value_str)
                elif expected_type is list:
                    import ast

                    value = ast.literal_eval(value_str)
                else:  # str
                    value = value_str
            except Exception as e:
                return settings_pb2.UpdateSettingResponse(
                    success=False, error=f"Invalid value format: {e}", old_value="", new_value=""
                )

            # Validate
            valid, error = self.validate_setting_value(key, value)
            if not valid:
                return settings_pb2.UpdateSettingResponse(success=False, error=error, old_value="", new_value="")

            # Update
            old_value = self.settings[key]
            self.settings[key] = value

            # Save to file (run in executor to avoid blocking event loop)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.save_settings)

            # Publish change event
            await self.publish_change(key, old_value, value, source)

            logger.info(f"Setting '{key}' updated: {old_value} -> {value}")

            return settings_pb2.UpdateSettingResponse(
                success=True, error="", old_value=str(old_value), new_value=str(value)
            )

        except Exception as e:
            logger.error(f"UpdateSetting error: {e}", exc_info=True)
            return settings_pb2.UpdateSettingResponse(success=False, error=str(e), old_value="", new_value="")

    async def SubscribeToChanges(self, request, context):  # noqa: N802, ARG002
        """Subscribe to setting change events (server-side streaming)."""
        import uuid

        subscriber_id = str(uuid.uuid4())
        event_queue = asyncio.Queue(maxsize=100)

        logger.info(f"New subscriber: {subscriber_id}")

        # Register subscriber
        async with self.subscriber_lock:
            self.subscribers[subscriber_id] = event_queue

        try:
            # Stream events to client
            while not context.cancelled():
                try:
                    # Wait for event with timeout
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    yield event
                except TimeoutError:
                    # No event, continue (keeps connection alive)
                    continue

        finally:
            # Unregister subscriber
            async with self.subscriber_lock:
                if subscriber_id in self.subscribers:
                    del self.subscribers[subscriber_id]
                    logger.info(f"Subscriber disconnected: {subscriber_id}")
