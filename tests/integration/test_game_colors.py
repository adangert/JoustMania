"""
Integration tests for game color assignment (Phase 39 - Task 3).

Tests the full flow of LED color assignment during game phases
with the mock controller environment.
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
    game_coordinator_pb2,
    game_coordinator_pb2_grpc,
)


@pytest.fixture(scope="module")
def docker_compose():
    """Fixture to start docker-compose mock environment.

    Uses docker-compose.yml with docker-compose.override.yml which enables
    mock mode (no hardware required).
    """
    compose = DockerCompose(
        context=".",
        compose_file_name=["docker-compose.yml", "docker-compose.override.yml"],
        pull=False,
        build=True,
    )

    compose.start()

    # Wait for services to be ready
    time.sleep(10)

    print("\n🎨 Mock environment running for game color tests")

    yield compose

    compose.stop()


@pytest.mark.asyncio
async def test_ffa_unique_player_colors(docker_compose):
    """Test FFA assigns unique colors to each player."""
    # Get service endpoints
    gc_host = docker_compose.get_service_host("game-coordinator", 50053)
    gc_port = docker_compose.get_service_port("game-coordinator", 50053)
    mock_host = docker_compose.get_service_host("controller-manager", 50062)
    mock_port = docker_compose.get_service_port("controller-manager", 50062)

    gc_channel = grpc.aio.insecure_channel(f"{gc_host}:{gc_port}")
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")

    gc_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(gc_channel)
    mock_client = controller_manager_mock_pb2_grpc.ControllerManagerMockServiceStub(mock_channel)

    try:
        # Add 3 mock controllers
        for i in range(3):
            await mock_client.AddMockController(
                controller_manager_mock_pb2.AddMockControllerRequest(
                    serial=f"ffa_player_{i}", battery=5
                )
            )
            # Mark as ready
            await mock_client.UpdateMockController(
                controller_manager_mock_pb2.UpdateMockControllerRequest(
                    serial=f"ffa_player_{i}", ready=True
                )
            )

        await asyncio.sleep(0.5)

        # Start FFA game
        start_response = await gc_client.StartGame(
            game_coordinator_pb2.StartGameRequest(
                game_mode="FFA",
                force_start=True,
            )
        )
        assert start_response.success

        # Wait for game to start and colors to be assigned
        await asyncio.sleep(6)  # Countdown + color phase

        # Get controller states to check colors
        colors_assigned = []
        for i in range(3):
            state = await mock_client.GetMockControllerState(
                controller_manager_mock_pb2.GetMockControllerStateRequest(serial=f"ffa_player_{i}")
            )
            color = (state.color.r, state.color.g, state.color.b)
            colors_assigned.append(color)

        # All colors should be unique
        assert len(set(colors_assigned)) == 3, f"Colors not unique: {colors_assigned}"

        # All should be vibrant (max channel = 255)
        for color in colors_assigned:
            assert max(color) == 255, f"Color not vibrant: {color}"

        # Stop game
        await gc_client.StopGame(game_coordinator_pb2.StopGameRequest())

    finally:
        await gc_channel.close()
        await mock_channel.close()


@pytest.mark.asyncio
async def test_teams_team_colors(docker_compose):
    """Test Teams mode assigns team colors correctly."""
    gc_host = docker_compose.get_service_host("game-coordinator", 50053)
    gc_port = docker_compose.get_service_port("game-coordinator", 50053)
    mock_host = docker_compose.get_service_host("controller-manager", 50062)
    mock_port = docker_compose.get_service_port("controller-manager", 50062)

    gc_channel = grpc.aio.insecure_channel(f"{gc_host}:{gc_port}")
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")

    gc_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(gc_channel)
    mock_client = controller_manager_mock_pb2_grpc.ControllerManagerMockServiceStub(mock_channel)

    try:
        # Add 4 mock controllers (2 teams of 2)
        for i in range(4):
            await mock_client.AddMockController(
                controller_manager_mock_pb2.AddMockControllerRequest(
                    serial=f"team_player_{i}", battery=5
                )
            )
            await mock_client.UpdateMockController(
                controller_manager_mock_pb2.UpdateMockControllerRequest(
                    serial=f"team_player_{i}", ready=True
                )
            )

        await asyncio.sleep(0.5)

        # Start Teams game
        start_response = await gc_client.StartGame(
            game_coordinator_pb2.StartGameRequest(
                game_mode="Teams",
                force_start=True,
            )
        )
        assert start_response.success

        # Wait for team color assignment
        await asyncio.sleep(6)  # Countdown + team color phase

        # Get controller colors
        colors = {}
        for i in range(4):
            state = await mock_client.GetMockControllerState(
                controller_manager_mock_pb2.GetMockControllerStateRequest(serial=f"team_player_{i}")
            )
            colors[f"team_player_{i}"] = (state.color.r, state.color.g, state.color.b)

        # Players 0 and 2 should be same team (team 0)
        # Players 1 and 3 should be same team (team 1)
        assert colors["team_player_0"] == colors["team_player_2"], "Team 0 colors don't match"
        assert colors["team_player_1"] == colors["team_player_3"], "Team 1 colors don't match"

        # Teams should have different colors
        assert colors["team_player_0"] != colors["team_player_1"], "Teams have same color"

        # Stop game
        await gc_client.StopGame(game_coordinator_pb2.StopGameRequest())

    finally:
        await gc_channel.close()
        await mock_channel.close()


@pytest.mark.asyncio
async def test_nonstop_unique_colors(docker_compose):
    """Test Nonstop Joust assigns unique colors."""
    gc_host = docker_compose.get_service_host("game-coordinator", 50053)
    gc_port = docker_compose.get_service_port("game-coordinator", 50053)
    mock_host = docker_compose.get_service_host("controller-manager", 50062)
    mock_port = docker_compose.get_service_port("controller-manager", 50062)

    gc_channel = grpc.aio.insecure_channel(f"{gc_host}:{gc_port}")
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")

    gc_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(gc_channel)
    mock_client = controller_manager_mock_pb2_grpc.ControllerManagerMockServiceStub(mock_channel)

    try:
        # Add 2 mock controllers
        for i in range(2):
            await mock_client.AddMockController(
                controller_manager_mock_pb2.AddMockControllerRequest(
                    serial=f"nonstop_player_{i}", battery=5
                )
            )
            await mock_client.UpdateMockController(
                controller_manager_mock_pb2.UpdateMockControllerRequest(
                    serial=f"nonstop_player_{i}", ready=True
                )
            )

        await asyncio.sleep(0.5)

        # Start Nonstop game
        start_response = await gc_client.StartGame(
            game_coordinator_pb2.StartGameRequest(
                game_mode="NonstopJoust",
                force_start=True,
            )
        )
        assert start_response.success

        # Wait for color assignment
        await asyncio.sleep(6)

        # Get colors
        color1_state = await mock_client.GetMockControllerState(
            controller_manager_mock_pb2.GetMockControllerStateRequest(serial="nonstop_player_0")
        )
        color2_state = await mock_client.GetMockControllerState(
            controller_manager_mock_pb2.GetMockControllerStateRequest(serial="nonstop_player_1")
        )

        color1 = (color1_state.color.r, color1_state.color.g, color1_state.color.b)
        color2 = (color2_state.color.r, color2_state.color.g, color2_state.color.b)

        # Colors should be different
        assert color1 != color2, f"Nonstop colors not unique: {color1} vs {color2}"

        # Stop game
        await gc_client.StopGame(game_coordinator_pb2.StopGameRequest())

    finally:
        await gc_channel.close()
        await mock_channel.close()


@pytest.mark.asyncio
async def test_random_teams_color_pulse(docker_compose):
    """Test Random Teams shows pulsing team colors during formation."""
    gc_host = docker_compose.get_service_host("game-coordinator", 50053)
    gc_port = docker_compose.get_service_port("game-coordinator", 50053)
    mock_host = docker_compose.get_service_host("controller-manager", 50062)
    mock_port = docker_compose.get_service_port("controller-manager", 50062)

    gc_channel = grpc.aio.insecure_channel(f"{gc_host}:{gc_port}")
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")

    gc_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(gc_channel)
    mock_client = controller_manager_mock_pb2_grpc.ControllerManagerMockServiceStub(mock_channel)

    try:
        # Add 4 controllers
        for i in range(4):
            await mock_client.AddMockController(
                controller_manager_mock_pb2.AddMockControllerRequest(
                    serial=f"random_player_{i}", battery=5
                )
            )
            await mock_client.UpdateMockController(
                controller_manager_mock_pb2.UpdateMockControllerRequest(
                    serial=f"random_player_{i}", ready=True
                )
            )

        await asyncio.sleep(0.5)

        # Start Random Teams game
        start_response = await gc_client.StartGame(
            game_coordinator_pb2.StartGameRequest(
                game_mode="RandomTeams",
                force_start=True,
            )
        )
        assert start_response.success

        # Wait for team formation (5 seconds) + countdown
        await asyncio.sleep(9)

        # Get final colors - should be team colors
        colors = []
        for i in range(4):
            state = await mock_client.GetMockControllerState(
                controller_manager_mock_pb2.GetMockControllerStateRequest(
                    serial=f"random_player_{i}"
                )
            )
            color = (state.color.r, state.color.g, state.color.b)
            colors.append(color)

        # Should have 2 distinct team colors (2 teams)
        unique_colors = set(colors)
        assert len(unique_colors) == 2, f"Expected 2 team colors, got {len(unique_colors)}"

        # Stop game
        await gc_client.StopGame(game_coordinator_pb2.StopGameRequest())

    finally:
        await gc_channel.close()
        await mock_channel.close()


@pytest.mark.asyncio
async def test_color_persistence_during_game(docker_compose):
    """Test colors persist throughout game phase."""
    gc_host = docker_compose.get_service_host("game-coordinator", 50053)
    gc_port = docker_compose.get_service_port("game-coordinator", 50053)
    mock_host = docker_compose.get_service_host("controller-manager", 50062)
    mock_port = docker_compose.get_service_port("controller-manager", 50062)

    gc_channel = grpc.aio.insecure_channel(f"{gc_host}:{gc_port}")
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")

    gc_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(gc_channel)
    mock_client = controller_manager_mock_pb2_grpc.ControllerManagerMockServiceStub(mock_channel)

    try:
        # Add 2 controllers
        for i in range(2):
            await mock_client.AddMockController(
                controller_manager_mock_pb2.AddMockControllerRequest(
                    serial=f"persist_player_{i}", battery=5
                )
            )
            await mock_client.UpdateMockController(
                controller_manager_mock_pb2.UpdateMockControllerRequest(
                    serial=f"persist_player_{i}", ready=True
                )
            )

        await asyncio.sleep(0.5)

        # Start FFA game
        await gc_client.StartGame(
            game_coordinator_pb2.StartGameRequest(
                game_mode="FFA",
                force_start=True,
            )
        )

        # Wait for color assignment
        await asyncio.sleep(6)

        # Capture initial colors
        state1 = await mock_client.GetMockControllerState(
            controller_manager_mock_pb2.GetMockControllerStateRequest(serial="persist_player_0")
        )
        initial_color = (state1.color.r, state1.color.g, state1.color.b)

        # Wait a bit
        await asyncio.sleep(2)

        # Check color again - should be same (persistent)
        state2 = await mock_client.GetMockControllerState(
            controller_manager_mock_pb2.GetMockControllerStateRequest(serial="persist_player_0")
        )
        current_color = (state2.color.r, state2.color.g, state2.color.b)

        assert initial_color == current_color, "Color did not persist during game"

        # Stop game
        await gc_client.StopGame(game_coordinator_pb2.StopGameRequest())

    finally:
        await gc_channel.close()
        await mock_channel.close()
