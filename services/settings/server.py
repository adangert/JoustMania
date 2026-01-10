"""
Settings gRPC Server for JoustMania

Manages settings as a gRPC service:
- Load/save settings from/to YAML file
- Validate setting updates against schema
- Provide gRPC interface for queries and updates
- Publish change events via streaming

This replaces the Queue-based IPC from Phase 3 with gRPC (Phase 8a).
"""

import logging
import time
import yaml
import os
import threading
import queue
from typing import Dict, Any, Tuple
from concurrent import futures
import grpc
import grpc.aio
import asyncio

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer

# Import protobuf directly (not through __init__.py to avoid psmove dependency)
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.settings import settings_pb2, settings_pb2_grpc

# We need Games enum for validation, but don't want psmove dependency
# So we'll define a minimal version here for server-only use
from enum import Enum

class Games(Enum):
    """Minimal Games enum for validation (server doesn't need psmove)."""
    JoustFFA = (0, 'Joust Free-for-All', 2)
    JoustTeams = (1, 'Joust Teams', 3)
    JoustRandomTeams = (2, 'Joust Random Teams', 3)
    Traitor = (3, 'Traitors', 4)
    Werewolf = (4, 'Werewolf', 3)
    Zombies = (5, 'Zombies', 4)
    Commander = (6, 'Commander', 4)
    Swapper = (7, 'Swapper', 3)
    FightClub = (8, 'Fight Club', 2)
    Tournament = (9, 'Tournament', 3)
    NonStop = (10, 'Non Stop Joust', 2)
    Ninja = (11, 'Ninja Bomb', 2)
    Random = (12, 'Random', 2)

    def __new__(cls, value, pretty_name, min_players):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.pretty_name = pretty_name
        obj.min_players = min_players
        return obj

class Sensitivity(Enum):
    """Sensitivity levels."""
    SLOWEST = 0
    SLOW = 1
    MID = 2
    FAST = 3
    FASTEST = 4

from sys import platform

logger = logging.getLogger(__name__)

# Initialize OpenTelemetry
def init_telemetry():
    """Initialize OpenTelemetry with OTLP exporter."""
    # Get configuration from environment
    otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4317')
    service_name = os.getenv('OTEL_SERVICE_NAME', 'settings-service')

    # Create resource with service info
    resource = Resource(attributes={
        SERVICE_NAME: service_name,
        SERVICE_VERSION: "1.0.0",
        "service.namespace": "joustmania",
    })

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Create OTLP exporter
    otlp_exporter = OTLPSpanExporter(
        endpoint=otlp_endpoint,
        insecure=True  # Use insecure for local development
    )

    # Add span processor
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    # Instrument gRPC server automatically
    GrpcInstrumentorServer().instrument()

    logger.info(f"OpenTelemetry initialized: {service_name} -> {otlp_endpoint}")
    return trace.get_tracer(__name__)

# Global tracer instance
tracer = init_telemetry()

# Settings schema with validation rules (same as process.py)
SETTINGS_SCHEMA = {
    'sensitivity': {
        'type': int,
        'min': 0,
        'max': 4,
        'default': Sensitivity.MID.value,
        'description': 'Controller sensitivity (0=ultra slow, 4=ultra fast)'
    },
    'play_instructions': {
        'type': bool,
        'default': True,
        'description': 'Play voice instructions before games'
    },
    'random_modes': {
        'type': list,
        'default': ['JoustFFA', 'JoustRandomTeams', 'Werewolf', 'Swapper'],
        'description': 'Game modes included in random selection'
    },
    'current_game': {
        'type': str,
        'default': 'JoustFFA',
        'description': 'Currently selected game mode'
    },
    'play_audio': {
        'type': bool,
        'default': True,
        'immutable': True,
        'description': 'Enable audio playback'
    },
    'menu_voice': {
        'type': str,
        'allowed_values': ['ivy', 'en', 'es', 'fr', 'de'],
        'default': 'ivy',
        'description': 'Voice pack for menu announcements'
    },
    'move_can_be_admin': {
        'type': bool,
        'default': True,
        'immutable': True,
        'description': 'Allow controllers to become admin'
    },
    'enforce_minimum': {
        'type': bool,
        'default': True,
        'immutable': True,
        'description': 'Enforce minimum player requirements'
    },
    'red_on_kill': {
        'type': bool,
        'default': True,
        'description': 'Flash red when killed'
    },
    'random_teams': {
        'type': bool,
        'default': True,
        'description': 'Randomize team assignments'
    },
    'color_lock': {
        'type': bool,
        'default': False,
        'description': 'Lock team colors'
    },
    'random_team_size': {
        'type': int,
        'min': 2,
        'max': 6,
        'default': 4,
        'description': 'Size of random teams'
    },
    'force_all_start': {
        'type': bool,
        'default': False,
        'description': 'Start game with all controllers (even not ready)'
    }
}


class SettingsServicer(settings_pb2_grpc.SettingsServiceServicer):
    """
    gRPC servicer implementation for Settings service.

    Manages settings with YAML persistence and validation.
    """

    def __init__(self, settings_file: str = 'joustsettings.yaml'):
        """
        Initialize Settings servicer.

        Args:
            settings_file: Path to YAML settings file
        """
        self.settings_file = settings_file
        self.settings: Dict[str, Any] = {}
        self.subscribers: Dict[str, queue.Queue] = {}  # {subscriber_id: event_queue}
        self.subscriber_lock = threading.Lock()

        # Load settings from file
        self.load_settings()

        logger.info(f"SettingsServicer initialized with file: {settings_file}")

    def get_default_settings(self) -> dict:
        """Get default settings from schema."""
        defaults = {}
        for key, schema in SETTINGS_SCHEMA.items():
            defaults[key] = schema['default']
        return defaults

    def load_settings(self):
        """Load settings from YAML file."""
        try:
            self.settings = self.get_default_settings()

            if os.path.exists(self.settings_file):
                logger.info(f"Loading settings from {self.settings_file}")
                with open(self.settings_file, 'r') as f:
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
                temp_file = self.settings_file + '.tmp'

                # Write to temp file
                with open(temp_file, 'w') as f:
                    yaml.dump(self.settings, f, default_flow_style=False)

                # Atomic rename
                os.replace(temp_file, self.settings_file)

                # Set permissions
                if platform == "linux" or platform == "linux2":
                    os.chmod(self.settings_file, 0o666)

                span.set_attribute("settings.file", self.settings_file)
                span.set_attribute("settings.count", len(self.settings))
                logger.debug(f"Settings saved to {self.settings_file}")

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"Error saving settings: {e}", exc_info=True)

    def validate_setting_value(self, key: str, value: Any) -> Tuple[bool, str]:
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

            if key not in SETTINGS_SCHEMA:
                span.set_attribute("validation.result", "invalid")
                span.set_attribute("validation.reason", "unknown_key")
                return False, f"Unknown setting: {key}"

            schema = SETTINGS_SCHEMA[key]

            # Check if immutable
            if schema.get('immutable', False):
                span.set_attribute("validation.result", "invalid")
                span.set_attribute("validation.reason", "immutable")
                return False, f"Setting '{key}' is immutable"

            # Check type
            expected_type = schema['type']
            if not isinstance(value, expected_type):
                span.set_attribute("validation.result", "invalid")
                span.set_attribute("validation.reason", "type_mismatch")
                return False, f"Expected {expected_type.__name__}, got {type(value).__name__}"

            # Check range (for int)
            if expected_type == int:
                if 'min' in schema and value < schema['min']:
                    span.set_attribute("validation.result", "invalid")
                    span.set_attribute("validation.reason", "below_min")
                    return False, f"Value {value} below minimum {schema['min']}"
                if 'max' in schema and value > schema['max']:
                    span.set_attribute("validation.result", "invalid")
                    span.set_attribute("validation.reason", "above_max")
                    return False, f"Value {value} above maximum {schema['max']}"

            # Check allowed values (for str)
            if expected_type == str:
                if 'allowed_values' in schema and value not in schema['allowed_values']:
                    span.set_attribute("validation.result", "invalid")
                    span.set_attribute("validation.reason", "not_allowed")
                    return False, f"Value '{value}' not in allowed values: {schema['allowed_values']}"

            # Check list items (for list)
            if expected_type == list:
                if key == 'random_modes':
                    valid_games = [g.name for g in Games if g != Games.JoustTeams and g != Games.Random]
                    for item in value:
                        if item not in valid_games:
                            span.set_attribute("validation.result", "invalid")
                            span.set_attribute("validation.reason", "invalid_list_item")
                            return False, f"Invalid game mode: {item}"

            span.set_attribute("validation.result", "valid")
            return True, ""

    def publish_change(self, key: str, old_value: Any, new_value: Any, source: str):
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
                timestamp=int(time.time() * 1000)  # milliseconds
            )

            with self.subscriber_lock:
                dead_subscribers = []
                subscriber_count = len(self.subscribers)
                span.set_attribute("subscribers.count", subscriber_count)

                for sub_id, event_queue in self.subscribers.items():
                    try:
                        event_queue.put_nowait(event)
                        logger.debug(f"Published change to subscriber {sub_id}")
                    except queue.Full:
                        logger.warning(f"Subscriber {sub_id} queue full, skipping")
                    except Exception as e:
                        logger.error(f"Error publishing to subscriber {sub_id}: {e}")
                        dead_subscribers.append(sub_id)

            # Clean up dead subscribers
            for sub_id in dead_subscribers:
                del self.subscribers[sub_id]
                logger.info(f"Removed dead subscriber {sub_id}")

    # gRPC Service Methods

    def GetSettings(self, request, context):
        """Get all settings."""
        logger.debug("GetSettings called")

        try:
            # Convert settings to string map
            settings_map = {k: str(v) for k, v in self.settings.items()}

            return settings_pb2.GetSettingsResponse(
                settings=settings_map,
                success=True,
                error=""
            )

        except Exception as e:
            logger.error(f"GetSettings error: {e}", exc_info=True)
            return settings_pb2.GetSettingsResponse(
                settings={},
                success=False,
                error=str(e)
            )

    def GetSetting(self, request, context):
        """Get a specific setting."""
        logger.debug(f"GetSetting called: key={request.key}")

        try:
            key = request.key

            if key not in self.settings:
                return settings_pb2.GetSettingResponse(
                    key=key,
                    value="",
                    success=False,
                    error=f"Setting '{key}' not found"
                )

            value = self.settings[key]

            return settings_pb2.GetSettingResponse(
                key=key,
                value=str(value),
                success=True,
                error=""
            )

        except Exception as e:
            logger.error(f"GetSetting error: {e}", exc_info=True)
            return settings_pb2.GetSettingResponse(
                key=request.key,
                value="",
                success=False,
                error=str(e)
            )

    def UpdateSetting(self, request, context):
        """Update a setting."""
        logger.info(f"UpdateSetting called: key={request.key}, value={request.value}, source={request.source}")

        try:
            key = request.key
            value_str = request.value
            source = request.source or "unknown"

            # Check if setting exists
            if key not in SETTINGS_SCHEMA:
                return settings_pb2.UpdateSettingResponse(
                    success=False,
                    error=f"Unknown setting: {key}",
                    old_value="",
                    new_value=""
                )

            # Parse value based on schema type
            schema = SETTINGS_SCHEMA[key]
            expected_type = schema['type']

            try:
                if expected_type == bool:
                    value = value_str.lower() in ('true', '1', 'yes')
                elif expected_type == int:
                    value = int(value_str)
                elif expected_type == list:
                    import ast
                    value = ast.literal_eval(value_str)
                else:  # str
                    value = value_str
            except Exception as e:
                return settings_pb2.UpdateSettingResponse(
                    success=False,
                    error=f"Invalid value format: {e}",
                    old_value="",
                    new_value=""
                )

            # Validate
            valid, error = self.validate_setting_value(key, value)
            if not valid:
                return settings_pb2.UpdateSettingResponse(
                    success=False,
                    error=error,
                    old_value="",
                    new_value=""
                )

            # Update
            old_value = self.settings[key]
            self.settings[key] = value

            # Save to file
            self.save_settings()

            # Publish change event
            self.publish_change(key, old_value, value, source)

            logger.info(f"Setting '{key}' updated: {old_value} -> {value}")

            return settings_pb2.UpdateSettingResponse(
                success=True,
                error="",
                old_value=str(old_value),
                new_value=str(value)
            )

        except Exception as e:
            logger.error(f"UpdateSetting error: {e}", exc_info=True)
            return settings_pb2.UpdateSettingResponse(
                success=False,
                error=str(e),
                old_value="",
                new_value=""
            )

    def SubscribeToChanges(self, request, context):
        """
        Subscribe to setting change events (server-side streaming).

        Yields SettingChangeEvent messages as settings change.
        """
        import uuid
        subscriber_id = str(uuid.uuid4())
        event_queue = queue.Queue(maxsize=100)

        logger.info(f"New subscriber: {subscriber_id}")

        # Register subscriber
        with self.subscriber_lock:
            self.subscribers[subscriber_id] = event_queue

        try:
            # Stream events to client
            while context.is_active():
                try:
                    # Wait for event with timeout
                    event = event_queue.get(timeout=1.0)
                    yield event
                except queue.Empty:
                    # No event, continue (keeps connection alive)
                    continue

        finally:
            # Unregister subscriber
            with self.subscriber_lock:
                if subscriber_id in self.subscribers:
                    del self.subscribers[subscriber_id]
                    logger.info(f"Subscriber disconnected: {subscriber_id}")


def serve(port: int = 50051):
    """
    Start the Settings gRPC server.

    Args:
        port: Port to listen on (default: 50051)
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create server
    server = grpc.aio.server()

    # Add servicer
    settings_servicer = SettingsServicer()
    settings_pb2_grpc.add_SettingsServiceServicer_to_server(settings_servicer, server)

    # Bind to port
    server.add_insecure_port(f'[::]:{port}')

    # Start server
    logger.info(f"Starting Settings gRPC server on port {port}")
    await server.start()

    try:
        # Keep server running
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Settings server...")
        await server.stop(grace=5)


if __name__ == '__main__':
    asyncio.run(serve())
