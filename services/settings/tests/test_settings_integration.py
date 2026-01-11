"""
Integration tests for Settings gRPC Server.

Tests the full gRPC server with real network communication.
Phase 34: Updated for async gRPC server.
"""

import asyncio
import os
import tempfile
import threading
import time

import grpc
import pytest
import yaml

from services.settings import settings_pb2, settings_pb2_grpc
from services.settings.server import SettingsServicer


@pytest.fixture(scope="module")
def temp_settings_file():
    """Create a temporary settings file for integration tests."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)
    if os.path.exists(path + ".tmp"):
        os.remove(path + ".tmp")


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def grpc_server(temp_settings_file, event_loop):
    """Start a gRPC server for integration tests (Phase 34: async server)."""
    port = 50099  # Use different port to avoid conflicts

    async def start_server():
        # Create async server
        server = grpc.aio.server()

        # Add servicer
        servicer = SettingsServicer(settings_file=temp_settings_file)
        settings_pb2_grpc.add_SettingsServiceServicer_to_server(servicer, server)

        # Bind to port
        server.add_insecure_port(f"[::]:{port}")

        # Start server
        await server.start()

        return server, servicer

    # Run in event loop
    server, servicer = event_loop.run_until_complete(start_server())

    # Give server time to start
    time.sleep(0.5)

    yield port, servicer

    # Cleanup
    async def stop_server():
        await server.stop(grace=1)

    event_loop.run_until_complete(stop_server())


@pytest.fixture
def grpc_channel(grpc_server):
    """Create a gRPC channel to the test server."""
    port, _ = grpc_server
    channel = grpc.insecure_channel(f"localhost:{port}")

    # Wait for channel to be ready
    grpc.channel_ready_future(channel).result(timeout=5)

    yield channel

    channel.close()


@pytest.fixture
def grpc_stub(grpc_channel):
    """Create a gRPC stub for the Settings service."""
    return settings_pb2_grpc.SettingsServiceStub(grpc_channel)


class TestSettingsIntegration:
    """Integration tests for Settings gRPC service."""

    def test_get_settings(self, grpc_stub):
        """Test GetSettings RPC over network."""
        request = settings_pb2.GetSettingsRequest()
        response = grpc_stub.GetSettings(request, timeout=5.0)

        assert response.success is True
        assert len(response.settings) > 0
        assert "sensitivity" in response.settings
        assert "current_game" in response.settings

    def test_get_setting(self, grpc_stub):
        """Test GetSetting RPC over network."""
        request = settings_pb2.GetSettingRequest(key="sensitivity")
        response = grpc_stub.GetSetting(request, timeout=5.0)

        assert response.success is True
        assert response.key == "sensitivity"
        assert response.value != ""

    def test_update_setting(self, grpc_stub):
        """Test UpdateSetting RPC over network."""
        # Update setting
        update_request = settings_pb2.UpdateSettingRequest(
            key="sensitivity", value="4", source="integration_test"
        )
        update_response = grpc_stub.UpdateSetting(update_request, timeout=5.0)

        assert update_response.success is True
        assert update_response.new_value == "4"

        # Verify update
        get_request = settings_pb2.GetSettingRequest(key="sensitivity")
        get_response = grpc_stub.GetSetting(get_request, timeout=5.0)

        assert get_response.value == "4"

    def test_update_setting_validation(self, grpc_stub):
        """Test UpdateSetting validation over network."""
        request = settings_pb2.UpdateSettingRequest(
            key="sensitivity",
            value="999",  # Invalid
            source="integration_test",
        )
        response = grpc_stub.UpdateSetting(request, timeout=5.0)

        assert response.success is False
        assert "maximum" in response.error.lower()

    def test_subscribe_to_changes(self, grpc_stub, grpc_server):
        """Test SubscribeToChanges streaming RPC."""
        _, servicer = grpc_server

        # Start subscription in background
        events_received = []

        def subscribe():
            request = settings_pb2.SubscribeRequest()
            try:
                for event in grpc_stub.SubscribeToChanges(request, timeout=10.0):
                    events_received.append(event)
                    if len(events_received) >= 1:
                        break
            except grpc.RpcError:
                # Timeout or cancellation is expected
                pass

        subscription_thread = threading.Thread(target=subscribe)
        subscription_thread.start()

        # Give subscription time to connect
        time.sleep(0.5)

        # Trigger a change
        update_request = settings_pb2.UpdateSettingRequest(
            key="sensitivity", value="2", source="integration_test"
        )
        grpc_stub.UpdateSetting(update_request, timeout=5.0)

        # Wait for event
        subscription_thread.join(timeout=5.0)

        # Should have received event
        assert len(events_received) > 0
        event = events_received[0]
        assert event.key == "sensitivity"
        assert event.source == "integration_test"

    def test_concurrent_updates(self, grpc_stub):
        """Test concurrent updates from multiple clients."""

        def update_setting(value):
            request = settings_pb2.UpdateSettingRequest(
                key="random_team_size", value=str(value), source="concurrent_test"
            )
            response = grpc_stub.UpdateSetting(request, timeout=5.0)
            return response.success

        # Run multiple concurrent updates
        threads = []
        for i in range(2, 6):  # Values 2-5 (all valid)
            thread = threading.Thread(target=update_setting, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all
        for thread in threads:
            thread.join(timeout=5.0)

        # Final value should be valid
        request = settings_pb2.GetSettingRequest(key="random_team_size")
        response = grpc_stub.GetSetting(request, timeout=5.0)

        assert response.success is True
        value = int(response.value)
        assert 2 <= value <= 6

    def test_persistence(self, grpc_stub, grpc_server, temp_settings_file):
        """Test that settings persist to file."""
        port, servicer = grpc_server

        # Update setting
        request = settings_pb2.UpdateSettingRequest(
            key="current_game", value="Werewolf", source="persistence_test"
        )
        response = grpc_stub.UpdateSetting(request, timeout=5.0)
        assert response.success is True

        # Read from file directly
        with open(temp_settings_file) as f:
            saved_settings = yaml.safe_load(f)

        assert saved_settings["current_game"] == "Werewolf"

    def test_error_handling(self, grpc_stub):
        """Test error handling in RPC calls."""
        # Unknown setting
        request = settings_pb2.UpdateSettingRequest(
            key="nonexistent", value="value", source="error_test"
        )
        response = grpc_stub.UpdateSetting(request, timeout=5.0)

        # Should return error, not raise exception
        assert response.success is False
        assert response.error != ""

    def test_timeout_handling(self, grpc_channel):
        """Test timeout handling for slow operations."""
        stub = settings_pb2_grpc.SettingsServiceStub(grpc_channel)

        # Very short timeout
        request = settings_pb2.GetSettingsRequest()

        try:
            response = stub.GetSettings(request, timeout=0.001)  # 1ms timeout
            # May or may not timeout depending on system speed
        except grpc.RpcError as e:
            # Timeout is acceptable
            assert e.code() == grpc.StatusCode.DEADLINE_EXCEEDED

    def test_channel_ready(self, grpc_channel):
        """Test channel connectivity."""
        # Check channel is ready
        state = grpc_channel._channel.check_connectivity_state(try_to_connect=True)
        # State can be the enum value (int) or the enum itself
        assert state in [
            grpc.ChannelConnectivity.READY,
            grpc.ChannelConnectivity.IDLE,
            grpc.ChannelConnectivity.READY.value[0],  # Enum value
            grpc.ChannelConnectivity.IDLE.value[0],  # Enum value
        ]


class TestSettingsLoadTest:
    """Load tests for Settings service."""

    def test_many_sequential_requests(self, grpc_stub):
        """Test handling many sequential requests."""
        success_count = 0

        for i in range(100):
            request = settings_pb2.GetSettingRequest(key="sensitivity")
            try:
                response = grpc_stub.GetSetting(request, timeout=5.0)
                if response.success:
                    success_count += 1
            except grpc.RpcError:
                pass

        # Should succeed most of the time
        assert success_count >= 95

    def test_rapid_updates(self, grpc_stub):
        """Test rapid setting updates."""
        success_count = 0

        for i in range(20):
            value = i % 5  # Cycle through valid values 0-4
            request = settings_pb2.UpdateSettingRequest(
                key="sensitivity", value=str(value), source="load_test"
            )
            try:
                response = grpc_stub.UpdateSetting(request, timeout=5.0)
                if response.success:
                    success_count += 1
            except grpc.RpcError:
                pass

        # Should succeed most of the time
        assert success_count >= 18
