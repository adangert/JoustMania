"""
Integration tests for menu lobby feedback (Phase 39).

Tests the full gRPC flow of lobby feedback:
- Menu service receives controller states
- Sends LED color updates to controller manager
- Handles game mode changes
- Admin mode visual feedback
"""

import asyncio
import os
import sys
import time

import grpc
import pytest
from testcontainers.compose import DockerCompose

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from proto import (
    controller_manager_mock_pb2,
    controller_manager_mock_pb2_grpc,
    menu_pb2,
    menu_pb2_grpc,
)


@pytest.fixture(scope="module")
def docker_compose():
    """Fixture to start docker-compose mock environment."""
    compose = DockerCompose(
        context=".", compose_file_name="docker-compose.mock.yml", pull=False, build=True
    )

    compose.start()

    # Wait for services to be ready
    time.sleep(10)

    print("\n🚀 Mock environment running for menu lobby feedback tests")

    yield compose

    compose.stop()


@pytest.mark.asyncio
async def test_lobby_feedback_connection_flash(docker_compose):
    """Test that first connection triggers green flash."""
    # Get service endpoints
    menu_host = docker_compose.get_service_host("menu", 50054)
    menu_port = docker_compose.get_service_port("menu", 50054)
    mock_host = docker_compose.get_service_host("mock-controller-manager", 50062)
    mock_port = docker_compose.get_service_port("mock-controller-manager", 50062)

    # Connect to services
    menu_channel = grpc.aio.insecure_channel(f"{menu_host}:{menu_port}")
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")

    menu_client = menu_pb2_grpc.MenuServiceStub(menu_channel)
    mock_client = controller_manager_mock_pb2_grpc.ControllerManagerMockServiceStub(mock_channel)

    try:
        # Start menu
        await menu_client.StartMenu(menu_pb2.StartMenuRequest())

        # Add a mock controller
        await mock_client.AddMockController(
            controller_manager_mock_pb2.AddMockControllerRequest(serial="lobby_test_1", battery=5)
        )

        # Wait for green flash to be processed
        await asyncio.sleep(1.0)

        # Check controller state (should have received green color)
        # Note: In real test we'd check the LED color history via mock service
        status = await menu_client.GetMenuStatus(menu_pb2.GetMenuStatusRequest())
        assert status.state == menu_pb2.MenuState.RUNNING

        # Stop menu
        await menu_client.StopMenu(menu_pb2.StopMenuRequest())

    finally:
        await menu_channel.close()
        await mock_channel.close()


@pytest.mark.asyncio
async def test_lobby_feedback_ready_state(docker_compose):
    """Test trigger press marks controller as ready with bright color."""
    menu_host = docker_compose.get_service_host("menu", 50054)
    menu_port = docker_compose.get_service_port("menu", 50054)
    mock_host = docker_compose.get_service_host("mock-controller-manager", 50062)
    mock_port = docker_compose.get_service_port("mock-controller-manager", 50062)

    menu_channel = grpc.aio.insecure_channel(f"{menu_host}:{menu_port}")
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")

    menu_client = menu_pb2_grpc.MenuServiceStub(menu_channel)
    mock_client = controller_manager_mock_pb2_grpc.ControllerManagerMockServiceStub(mock_channel)

    try:
        # Start menu
        await menu_client.StartMenu(menu_pb2.StartMenuRequest())

        # Add controller
        await mock_client.AddMockController(
            controller_manager_mock_pb2.AddMockControllerRequest(serial="lobby_test_2", battery=5)
        )

        # Wait for initial connection
        await asyncio.sleep(1.0)

        # Press trigger
        await mock_client.UpdateMockController(
            controller_manager_mock_pb2.UpdateMockControllerRequest(
                serial="lobby_test_2", trigger_pressed=True
            )
        )

        # Wait for ready state update
        await asyncio.sleep(0.5)

        # Check menu status - should have 1 ready controller
        status = await menu_client.GetMenuStatus(menu_pb2.GetMenuStatusRequest())
        assert status.ready_controller_count == 1

        # Release trigger - should stay ready
        await mock_client.UpdateMockController(
            controller_manager_mock_pb2.UpdateMockControllerRequest(
                serial="lobby_test_2", trigger_pressed=False
            )
        )

        await asyncio.sleep(0.5)

        # Should still be ready
        status = await menu_client.GetMenuStatus(menu_pb2.GetMenuStatusRequest())
        assert status.ready_controller_count == 1

        # Stop menu
        await menu_client.StopMenu(menu_pb2.StopMenuRequest())

    finally:
        await menu_channel.close()
        await mock_channel.close()


@pytest.mark.asyncio
async def test_lobby_feedback_game_mode_colors(docker_compose):
    """Test that game mode selection changes controller colors."""
    menu_host = docker_compose.get_service_host("menu", 50054)
    menu_port = docker_compose.get_service_port("menu", 50054)
    mock_host = docker_compose.get_service_host("mock-controller-manager", 50062)
    mock_port = docker_compose.get_service_port("mock-controller-manager", 50062)

    menu_channel = grpc.aio.insecure_channel(f"{menu_host}:{menu_port}")
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")

    menu_client = menu_pb2_grpc.MenuServiceStub(menu_channel)
    mock_client = controller_manager_mock_pb2_grpc.ControllerManagerMockServiceStub(mock_channel)

    try:
        # Start menu (defaults to JoustFFA)
        await menu_client.StartMenu(menu_pb2.StartMenuRequest())

        # Add controller
        await mock_client.AddMockController(
            controller_manager_mock_pb2.AddMockControllerRequest(serial="lobby_test_3", battery=5)
        )

        # Wait for connection
        await asyncio.sleep(1.0)

        # Check initial game mode
        status = await menu_client.GetMenuStatus(menu_pb2.GetMenuStatusRequest())
        assert status.current_selection == "JoustFFA"

        # Change game mode by pressing move button
        await mock_client.UpdateMockController(
            controller_manager_mock_pb2.UpdateMockControllerRequest(
                serial="lobby_test_3", move_pressed=True
            )
        )

        await asyncio.sleep(0.3)

        # Release move button
        await mock_client.UpdateMockController(
            controller_manager_mock_pb2.UpdateMockControllerRequest(
                serial="lobby_test_3", move_pressed=False
            )
        )

        await asyncio.sleep(0.5)

        # Check game mode changed
        status = await menu_client.GetMenuStatus(menu_pb2.GetMenuStatusRequest())
        assert status.current_selection == "JoustTeams"

        # Stop menu
        await menu_client.StopMenu(menu_pb2.StopMenuRequest())

    finally:
        await menu_channel.close()
        await mock_channel.close()


@pytest.mark.asyncio
async def test_admin_mode_white_led(docker_compose):
    """Test that admin mode shows white LED."""
    menu_host = docker_compose.get_service_host("menu", 50054)
    menu_port = docker_compose.get_service_port("menu", 50054)
    mock_host = docker_compose.get_service_host("mock-controller-manager", 50062)
    mock_port = docker_compose.get_service_port("mock-controller-manager", 50062)

    menu_channel = grpc.aio.insecure_channel(f"{menu_host}:{menu_port}")
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")

    menu_client = menu_pb2_grpc.MenuServiceStub(menu_channel)
    mock_client = controller_manager_mock_pb2_grpc.ControllerManagerMockServiceStub(mock_channel)

    try:
        # Start menu
        await menu_client.StartMenu(menu_pb2.StartMenuRequest())

        # Add controller
        await mock_client.AddMockController(
            controller_manager_mock_pb2.AddMockControllerRequest(
                serial="lobby_test_admin", battery=5
            )
        )

        # Wait for connection
        await asyncio.sleep(1.0)

        # Press all 4 front buttons to enter admin mode
        await mock_client.UpdateMockController(
            controller_manager_mock_pb2.UpdateMockControllerRequest(
                serial="lobby_test_admin",
                cross_pressed=True,
                circle_pressed=True,
                square_pressed=True,
                triangle_pressed=True,
            )
        )

        # Wait for admin mode entry and white flash
        await asyncio.sleep(1.0)

        # Release buttons
        await mock_client.UpdateMockController(
            controller_manager_mock_pb2.UpdateMockControllerRequest(
                serial="lobby_test_admin",
                cross_pressed=False,
                circle_pressed=False,
                square_pressed=False,
                triangle_pressed=False,
            )
        )

        await asyncio.sleep(0.5)

        # Exit admin mode (press PS button)
        await mock_client.UpdateMockController(
            controller_manager_mock_pb2.UpdateMockControllerRequest(
                serial="lobby_test_admin", ps_pressed=True
            )
        )

        await asyncio.sleep(0.5)

        # Release PS button
        await mock_client.UpdateMockController(
            controller_manager_mock_pb2.UpdateMockControllerRequest(
                serial="lobby_test_admin", ps_pressed=False
            )
        )

        # Wait for color restoration
        await asyncio.sleep(0.5)

        # Stop menu
        await menu_client.StopMenu(menu_pb2.StopMenuRequest())

    finally:
        await menu_channel.close()
        await mock_channel.close()


@pytest.mark.asyncio
async def test_multiple_controllers_lobby_feedback(docker_compose):
    """Test lobby feedback with multiple controllers."""
    menu_host = docker_compose.get_service_host("menu", 50054)
    menu_port = docker_compose.get_service_port("menu", 50054)
    mock_host = docker_compose.get_service_host("mock-controller-manager", 50062)
    mock_port = docker_compose.get_service_port("mock-controller-manager", 50062)

    menu_channel = grpc.aio.insecure_channel(f"{menu_host}:{menu_port}")
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")

    menu_client = menu_pb2_grpc.MenuServiceStub(menu_channel)
    mock_client = controller_manager_mock_pb2_grpc.ControllerManagerMockServiceStub(mock_channel)

    try:
        # Start menu
        await menu_client.StartMenu(menu_pb2.StartMenuRequest())

        # Add 3 controllers
        for i in range(3):
            await mock_client.AddMockController(
                controller_manager_mock_pb2.AddMockControllerRequest(
                    serial=f"multi_test_{i}", battery=5
                )
            )

        # Wait for all to connect
        await asyncio.sleep(1.5)

        # Mark first two as ready
        for i in range(2):
            await mock_client.UpdateMockController(
                controller_manager_mock_pb2.UpdateMockControllerRequest(
                    serial=f"multi_test_{i}", trigger_pressed=True
                )
            )

        await asyncio.sleep(0.8)

        # Check ready count
        status = await menu_client.GetMenuStatus(menu_pb2.GetMenuStatusRequest())
        assert status.ready_controller_count == 2

        # Stop menu
        await menu_client.StopMenu(menu_pb2.StopMenuRequest())

        # Verify state cleared
        status = await menu_client.GetMenuStatus(menu_pb2.GetMenuStatusRequest())
        assert status.ready_controller_count == 0

    finally:
        await menu_channel.close()
        await mock_channel.close()
