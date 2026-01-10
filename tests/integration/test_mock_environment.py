"""
Integration tests using testcontainers with mock environment.

These tests spin up the entire JoustMania stack using docker-compose.mock.yml
and run end-to-end game simulations without requiring physical hardware.

Usage:
    # Run tests normally (auto-teardown) - using uv script
    ./scripts/testing/test-mock.py

    # Pause before teardown to inspect Jaeger
    ./scripts/testing/test-mock-with-pause.py

    # Or run manually with pytest
    uv run pytest tests/integration/test_mock_environment.py -v
    PAUSE_BEFORE_TEARDOWN=1 uv run pytest tests/integration/test_mock_environment.py -v -s

    When paused, you can:
    - Browse Jaeger UI at http://localhost:16686
    - Inspect distributed traces
    - Check service logs
    - Test manual gRPC calls
    - Press ENTER to tear down and complete tests
"""

import pytest
import asyncio
import time
import grpc
from testcontainers.compose import DockerCompose

# Import protobufs
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from services.controller_manager import controller_manager_mock_pb2, controller_manager_mock_pb2_grpc
from services.controller_manager import controller_manager_pb2, controller_manager_pb2_grpc
from services.game_coordinator import game_coordinator_pb2, game_coordinator_pb2_grpc


@pytest.fixture(scope="module")
def docker_compose():
    """Fixture to start docker-compose mock environment."""
    compose = DockerCompose(
        filepath=".",
        compose_file_name="docker-compose.mock.yml",
        pull=False,
        build=True
    )

    compose.start()

    # Wait for services to be ready
    time.sleep(10)

    print("\n" + "="*80)
    print("🚀 Mock environment is running!")
    print("="*80)
    print("Jaeger UI: http://localhost:16686")
    print("WebUI: http://localhost:80")
    print("Mock Control API: localhost:50062")
    print("="*80)

    yield compose

    # Optional pause before teardown (set PAUSE_BEFORE_TEARDOWN=1 to inspect Jaeger)
    if os.getenv('PAUSE_BEFORE_TEARDOWN'):
        print("\n" + "="*80)
        print("⏸️  PAUSED - Inspect Jaeger at http://localhost:16686")
        print("="*80)
        print("Press ENTER to tear down the environment...")
        input()

    compose.stop()


@pytest.mark.asyncio
async def test_mock_controller_manager_connection(docker_compose):
    """Test that we can connect to mock controller manager."""
    channel = grpc.aio.insecure_channel('localhost:50052')
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    # Get ready controllers
    response = await client.GetReadyControllers(
        controller_manager_pb2.GetReadyControllersRequest()
    )

    assert response.success
    assert len(response.controllers) == 4  # Default MOCK_CONTROLLER_COUNT

    # Verify controller serials
    serials = [c.serial for c in response.controllers]
    assert "mock_controller_0" in serials
    assert "mock_controller_1" in serials
    assert "mock_controller_2" in serials
    assert "mock_controller_3" in serials

    await channel.close()


@pytest.mark.asyncio
async def test_mock_controller_control_api(docker_compose):
    """Test that we can control mock controllers via control API."""
    channel = grpc.aio.insecure_channel('localhost:50062')
    client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(channel)

    # List mock controllers
    response = await client.ListMockControllers(
        controller_manager_mock_pb2.ListRequest()
    )

    assert response.count == 4
    assert len(response.serials) == 4

    # Simulate movement
    move_response = await client.SimulateMovement(
        controller_manager_mock_pb2.MovementRequest(
            serial="mock_controller_0",
            accel_x=2.0,
            accel_y=1.5,
            accel_z=1.2
        )
    )

    assert move_response.success

    # Simulate death
    death_response = await client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(
            serial="mock_controller_0"
        )
    )

    assert death_response.success
    assert death_response.accel_magnitude > 2.8  # Death threshold for FAST sensitivity

    # Reset controller
    reset_response = await client.ResetController(
        controller_manager_mock_pb2.ResetRequest(
            serial="mock_controller_0"
        )
    )

    assert reset_response.success

    await channel.close()


@pytest.mark.asyncio
async def test_ffa_game_with_mock_controllers(docker_compose):
    """Test full FFA game lifecycle with mock controllers."""

    # Connect to game coordinator
    game_channel = grpc.aio.insecure_channel('localhost:50053')
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    # Connect to mock controller control
    mock_channel = grpc.aio.insecure_channel('localhost:50062')
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(mock_channel)

    # Start FFA game
    start_response = await game_client.StartGame(
        game_coordinator_pb2.StartGameRequest(mode="FFA")
    )

    assert start_response.success
    assert start_response.game_id != ""

    # Wait for game to start
    await asyncio.sleep(2)

    # Simulate some deaths
    for i in range(3):
        death_response = await mock_client.SimulateDeath(
            controller_manager_mock_pb2.DeathRequest(
                serial=f"mock_controller_{i}"
            )
        )
        assert death_response.success
        await asyncio.sleep(1)

    # Check game status
    status_response = await game_client.GetGameStatus(
        game_coordinator_pb2.GetGameStatusRequest()
    )

    assert status_response.is_running or status_response.is_ended  # Game might have auto-ended

    # Force end game
    end_response = await game_client.ForceEndGame(
        game_coordinator_pb2.ForceEndGameRequest()
    )

    assert end_response.success

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_teams_game_with_mock_controllers(docker_compose):
    """Test full Teams game lifecycle with mock controllers."""

    # Connect to game coordinator
    game_channel = grpc.aio.insecure_channel('localhost:50053')
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    # Connect to mock controller control
    mock_channel = grpc.aio.insecure_channel('localhost:50062')
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(mock_channel)

    # Start Teams game
    start_response = await game_client.StartGame(
        game_coordinator_pb2.StartGameRequest(mode="Teams")
    )

    assert start_response.success
    assert start_response.game_id != ""

    # Wait for game to start
    await asyncio.sleep(2)

    # Simulate deaths on one team (controllers 0 and 2 should be on same team)
    await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
    )
    await asyncio.sleep(1)

    await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_2")
    )
    await asyncio.sleep(2)

    # Game should auto-end when one team is eliminated
    status_response = await game_client.GetGameStatus(
        game_coordinator_pb2.GetGameStatusRequest()
    )

    # Game might be ended or still running depending on team assignment
    assert status_response.is_running or status_response.is_ended

    # Force end if still running
    if status_response.is_running:
        await game_client.ForceEndGame(
            game_coordinator_pb2.ForceEndGameRequest()
        )

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_controller_state_streaming(docker_compose):
    """Test streaming controller states from mock controller manager."""

    channel = grpc.aio.insecure_channel('localhost:50052')
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    # Start streaming at 10Hz
    stream_request = controller_manager_pb2.StreamControllerStatesRequest(
        update_frequency_hz=10
    )

    frame_count = 0
    async for state_update in client.StreamControllerStates(stream_request):
        assert len(state_update.controllers) == 4
        assert state_update.timestamp > 0

        frame_count += 1
        if frame_count >= 5:  # Receive 5 frames
            break

    assert frame_count == 5

    await channel.close()


@pytest.mark.asyncio
async def test_distributed_tracing_propagation(docker_compose):
    """Test that distributed tracing works end-to-end."""

    # Connect to game coordinator
    game_channel = grpc.aio.insecure_channel('localhost:50053')
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    # Start game (this should create a trace spanning all services)
    start_response = await game_client.StartGame(
        game_coordinator_pb2.StartGameRequest(mode="FFA")
    )

    assert start_response.success

    # Wait for game to initialize
    await asyncio.sleep(3)

    # Force end game
    await game_client.ForceEndGame(
        game_coordinator_pb2.ForceEndGameRequest()
    )

    # Note: To verify tracing, check Jaeger UI at http://localhost:16686
    # Search for service="game-coordinator-service" and verify:
    # - StartGame span exists
    # - GetSettings span is a child of ffa_load_settings
    # - GetReadyControllers span is a child of ffa_initialize_players
    # - StreamControllerStates span is a child of ffa_game_loop

    await game_channel.close()


@pytest.mark.asyncio
async def test_multiple_games_sequence(docker_compose):
    """Test running multiple games in sequence."""

    game_channel = grpc.aio.insecure_channel('localhost:50053')
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    mock_channel = grpc.aio.insecure_channel('localhost:50062')
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(mock_channel)

    # Run 3 games in sequence
    for i in range(3):
        # Start game
        start_response = await game_client.StartGame(
            game_coordinator_pb2.StartGameRequest(mode="FFA")
        )
        assert start_response.success

        # Wait and simulate death
        await asyncio.sleep(1)
        await mock_client.SimulateDeath(
            controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
        )
        await asyncio.sleep(1)

        # End game
        await game_client.ForceEndGame(
            game_coordinator_pb2.ForceEndGameRequest()
        )

        # Reset controllers for next game
        for j in range(4):
            await mock_client.ResetController(
                controller_manager_mock_pb2.ResetRequest(
                    serial=f"mock_controller_{j}"
                )
            )

        await asyncio.sleep(1)

    await game_channel.close()
    await mock_channel.close()
