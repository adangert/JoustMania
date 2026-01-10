"""
gRPC Client Wrappers for JoustMania Microservices

Provides simple client interfaces for all gRPC services.
Handles connection management, retries, and error handling.

Part of Phase 8a (gRPC conversion).
"""

import logging
from contextlib import contextmanager
from typing import Any

import grpc

from services.settings import settings_pb2, settings_pb2_grpc

logger = logging.getLogger(__name__)


class SettingsClient:
    """
    gRPC client for Settings service.

    Provides simple methods to interact with Settings service over gRPC.
    """

    def __init__(self, host: str = "localhost", port: int = 50051):
        """
        Initialize Settings gRPC client.

        Args:
            host: gRPC server host
            port: gRPC server port
        """
        self.address = f"{host}:{port}"
        self.channel: grpc.Channel | None = None
        self.stub: settings_pb2_grpc.SettingsServiceStub | None = None

    def connect(self):
        """Establish connection to Settings service."""
        if self.channel is None:
            logger.info(f"Connecting to Settings service at {self.address}")
            self.channel = grpc.insecure_channel(self.address)
            self.stub = settings_pb2_grpc.SettingsServiceStub(self.channel)

            # Wait for channel to be ready
            try:
                grpc.channel_ready_future(self.channel).result(timeout=5.0)
                logger.info("Connected to Settings service")
            except grpc.FutureTimeoutError:
                logger.error("Timeout connecting to Settings service")
                raise

    def close(self):
        """Close connection to Settings service."""
        if self.channel:
            logger.info("Closing Settings service connection")
            self.channel.close()
            self.channel = None
            self.stub = None

    @contextmanager
    def ensure_connected(self):
        """Context manager to ensure connection is active."""
        if self.channel is None:
            self.connect()
        yield

    def get_settings(self, timeout: float = 5.0) -> dict[str, Any]:
        """
        Get all settings.

        Args:
            timeout: RPC timeout in seconds

        Returns:
            Dictionary of all settings

        Raises:
            grpc.RpcError: If RPC fails
        """
        with self.ensure_connected():
            request = settings_pb2.GetSettingsRequest()

            try:
                response = self.stub.GetSettings(request, timeout=timeout)

                if not response.success:
                    logger.error(f"GetSettings failed: {response.error}")
                    raise RuntimeError(response.error)

                # Convert string map back to proper types
                settings = {}
                for key, value_str in response.settings.items():
                    # Try to parse as bool/int, fallback to string
                    if value_str.lower() in ("true", "false"):
                        settings[key] = value_str.lower() == "true"
                    else:
                        try:
                            settings[key] = int(value_str)
                        except ValueError:
                            # Check if it's a list
                            if value_str.startswith("[") and value_str.endswith("]"):
                                import ast

                                settings[key] = ast.literal_eval(value_str)
                            else:
                                settings[key] = value_str

                return settings

            except grpc.RpcError as e:
                logger.error(f"GetSettings RPC failed: {e}")
                raise

    def get_setting(self, key: str, timeout: float = 5.0) -> Any:
        """
        Get a specific setting.

        Args:
            key: Setting key
            timeout: RPC timeout in seconds

        Returns:
            Setting value

        Raises:
            KeyError: If setting not found
            grpc.RpcError: If RPC fails
        """
        with self.ensure_connected():
            request = settings_pb2.GetSettingRequest(key=key)

            try:
                response = self.stub.GetSetting(request, timeout=timeout)

                if not response.success:
                    raise KeyError(f"Setting '{key}' not found: {response.error}")

                # Parse value
                value_str = response.value
                if value_str.lower() in ("true", "false"):
                    return value_str.lower() == "true"
                try:
                    return int(value_str)
                except ValueError:
                    if value_str.startswith("[") and value_str.endswith("]"):
                        import ast

                        return ast.literal_eval(value_str)
                    return value_str

            except grpc.RpcError as e:
                logger.error(f"GetSetting RPC failed: {e}")
                raise

    def update_setting(
        self, key: str, value: Any, source: str = "piparty", timeout: float = 5.0
    ) -> bool:
        """
        Update a setting.

        Args:
            key: Setting key
            value: New value
            source: Source of the change
            timeout: RPC timeout in seconds

        Returns:
            True if update succeeded

        Raises:
            ValueError: If validation fails
            grpc.RpcError: If RPC fails
        """
        with self.ensure_connected():
            # Convert value to string
            if isinstance(value, bool):
                value_str = "true" if value else "false"
            elif isinstance(value, list):
                value_str = str(value)
            else:
                value_str = str(value)

            request = settings_pb2.UpdateSettingRequest(key=key, value=value_str, source=source)

            try:
                response = self.stub.UpdateSetting(request, timeout=timeout)

                if not response.success:
                    raise ValueError(f"Update failed: {response.error}")

                logger.info(
                    f"Updated setting '{key}': {response.old_value} -> {response.new_value}"
                )
                return True

            except grpc.RpcError as e:
                logger.error(f"UpdateSetting RPC failed: {e}")
                raise

    def subscribe_to_changes(self, callback, keys: list | None = None):
        """
        Subscribe to setting change events.

        Args:
            callback: Function to call with each SettingChangeEvent
            keys: Optional list of keys to filter (None = all changes)

        Yields:
            SettingChangeEvent messages
        """
        with self.ensure_connected():
            request = settings_pb2.SubscribeRequest(keys=keys or [])

            try:
                for event in self.stub.SubscribeToChanges(request):
                    callback(event)

            except grpc.RpcError as e:
                logger.error(f"SubscribeToChanges RPC failed: {e}")
                raise


class ServiceManager:
    """
    Manager for all gRPC service clients.

    Provides centralized access to all microservice clients.
    """

    def __init__(self, host: str = "localhost"):
        """
        Initialize service manager.

        Args:
            host: gRPC services host
        """
        self.host = host

        # Create clients for all services
        self.settings = SettingsClient(host=host, port=50051)
        # Future: ControllerManager on port 50052
        # Future: GameCoordinator on port 50053
        # Future: Menu on port 50054
        # Future: Supervisor on port 50055

        logger.info(f"ServiceManager initialized for host: {host}")

    def connect_all(self):
        """Connect to all services."""
        logger.info("Connecting to all services...")
        self.settings.connect()
        # Future: connect other services
        logger.info("All services connected")

    def close_all(self):
        """Close all service connections."""
        logger.info("Closing all service connections...")
        self.settings.close()
        # Future: close other services
        logger.info("All service connections closed")

    def __enter__(self):
        """Context manager entry."""
        self.connect_all()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close_all()
