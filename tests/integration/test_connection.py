"""
Connection tests for JoustMania mock environment.

Tests basic connectivity to mock controller services.
"""

import asyncio
import os
import sys

import grpc
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from proto import (
    controller_manager_mock_pb2,
    controller_manager_mock_pb2_grpc,
)


@pytest.mark.asyncio
async def test_mock_controller_manager_connection(docker_compose):
    """Test that we can connect to mock controller manager and list controllers."""
    # Get dynamically assigned port for mock control API
    host = docker_compose.get_service_host("controller-manager", 50062)
    port = docker_compose.get_service_port("controller-manager", 50062)

    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(channel)

    # List mock controllers via the mock control API
    response = await client.ListMockControllers(controller_manager_mock_pb2.ListRequest())

    assert response.count == 4  # Default MOCK_CONTROLLER_COUNT
    assert len(response.serials) == 4

    # Verify controller serials
    serials = list(response.serials)
    assert "mock_controller_0" in serials
    assert "mock_controller_1" in serials
    assert "mock_controller_2" in serials
    assert "mock_controller_3" in serials

    await channel.close()


@pytest.mark.asyncio
async def test_mock_controller_control_api(docker_compose):
    """Test that we can control mock controllers via control API."""
    # Get dynamically assigned port for mock control API
    host = docker_compose.get_service_host("controller-manager", 50062)
    port = docker_compose.get_service_port("controller-manager", 50062)

    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(channel)

    # List mock controllers
    response = await client.ListMockControllers(controller_manager_mock_pb2.ListRequest())

    assert response.count == 4
    assert len(response.serials) == 4

    # Simulate movement
    move_response = await client.SimulateMovement(
        controller_manager_mock_pb2.MovementRequest(
            serial="mock_controller_0", accel_x=2.0, accel_y=1.5, accel_z=1.2
        )
    )

    assert move_response.success

    # Simulate death
    death_response = await client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
    )

    assert death_response.success
    assert death_response.accel_magnitude > 2.8  # Death threshold for FAST sensitivity

    # Reset controller
    reset_response = await client.ResetController(
        controller_manager_mock_pb2.ResetRequest(serial="mock_controller_0")
    )

    assert reset_response.success

    await channel.close()
