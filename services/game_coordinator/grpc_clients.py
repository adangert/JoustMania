"""
gRPC Client Manager - Manages connections to dependent services.

Centralizes gRPC client lifecycle:
- Environment-based configuration
- Async channel creation
- Graceful cleanup

Usage:
    from services.game_coordinator.grpc_clients import GrpcClientManager

    # Create manager
    clients = GrpcClientManager()

    # Initialize connections (call in async context)
    await clients.connect()

    # Access clients
    clients.controller_manager  # ControllerManagerServiceStub
    clients.settings           # SettingsServiceStub
    clients.audio              # AudioServiceStub

    # Cleanup
    await clients.close()
"""

import logging
import os

logger = logging.getLogger(__name__)


class GrpcClientManager:
    """
    Manages gRPC client connections to dependent services.

    Handles:
    - ControllerManager service (controller state, effects)
    - Settings service (game configuration)
    - Audio service (sound playback)
    """

    def __init__(self):
        """Initialize client manager with environment configuration."""
        # Service addresses from environment
        self._controller_manager_host = os.getenv("CONTROLLER_MANAGER_HOST", "controller-manager")
        self._controller_manager_port = os.getenv("CONTROLLER_MANAGER_PORT", "50052")
        self._settings_host = os.getenv("SETTINGS_HOST", "settings")
        self._settings_port = os.getenv("SETTINGS_PORT", "50051")
        self._audio_host = os.getenv("AUDIO_HOST", "audio")
        self._audio_port = os.getenv("AUDIO_PORT", "50056")

        # Channels and stubs (initialized on connect)
        self._controller_manager_channel = None
        self._controller_manager_stub = None
        self._settings_channel = None
        self._settings_stub = None
        self._audio_channel = None
        self._audio_stub = None

    @property
    def controller_manager(self):
        """Get ControllerManager service stub."""
        return self._controller_manager_stub

    @property
    def settings(self):
        """Get Settings service stub."""
        return self._settings_stub

    @property
    def audio(self):
        """Get Audio service stub."""
        return self._audio_stub

    @property
    def is_connected(self) -> bool:
        """Check if essential clients are connected."""
        return self._controller_manager_stub is not None and self._settings_stub is not None

    async def connect(self):
        """
        Initialize async gRPC client connections.

        Creates channels and stubs for all dependent services.
        On failure, clients are set to None for graceful degradation.
        """
        from lib.grpc_utils import create_channel
        from proto import audio_pb2_grpc, controller_manager_pb2_grpc, settings_pb2_grpc

        try:
            # ControllerManager client
            cm_address = f"{self._controller_manager_host}:{self._controller_manager_port}"
            self._controller_manager_channel = create_channel(cm_address)
            self._controller_manager_stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(
                self._controller_manager_channel
            )
            logger.info(f"Connected to ControllerManager at {cm_address}")

            # Settings client
            settings_address = f"{self._settings_host}:{self._settings_port}"
            self._settings_channel = create_channel(settings_address)
            self._settings_stub = settings_pb2_grpc.SettingsServiceStub(self._settings_channel)
            logger.info(f"Connected to Settings at {settings_address}")

            # Audio client
            audio_address = f"{self._audio_host}:{self._audio_port}"
            self._audio_channel = create_channel(audio_address)
            self._audio_stub = audio_pb2_grpc.AudioServiceStub(self._audio_channel)
            logger.info(f"Connected to Audio at {audio_address}")

        except Exception as e:
            logger.error(f"Failed to initialize gRPC clients: {e}")
            # Set to None for graceful degradation
            self._controller_manager_stub = None
            self._settings_stub = None
            self._audio_stub = None

    async def close(self):
        """
        Close all gRPC channels gracefully.

        Safe to call multiple times.
        """
        if self._controller_manager_channel:
            try:
                await self._controller_manager_channel.close()
            except Exception as e:
                logger.warning(f"Error closing controller_manager channel: {e}")
            self._controller_manager_channel = None
            self._controller_manager_stub = None

        if self._settings_channel:
            try:
                await self._settings_channel.close()
            except Exception as e:
                logger.warning(f"Error closing settings channel: {e}")
            self._settings_channel = None
            self._settings_stub = None

        if self._audio_channel:
            try:
                await self._audio_channel.close()
            except Exception as e:
                logger.warning(f"Error closing audio channel: {e}")
            self._audio_channel = None
            self._audio_stub = None

        logger.info("Closed all gRPC channels")
