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
    uv run --package joustmania-integration-tests pytest tests/integration/ -v
    PAUSE_BEFORE_TEARDOWN=1 uv run --package joustmania-integration-tests pytest tests/integration/ -v -s

    When paused, you can:
    - Browse Jaeger UI at http://localhost:16686
    - Inspect distributed traces
    - Check service logs
    - Test manual gRPC calls
    - Press ENTER to tear down and complete tests
"""

import asyncio
import os

# Import protobufs
import sys
import time

import grpc
import pytest
from testcontainers.compose import DockerCompose

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from proto import (
    controller_manager_pb2,
    controller_manager_pb2_grpc,
    controller_manager_mock_pb2,
    controller_manager_mock_pb2_grpc,
    game_coordinator_pb2,
    game_coordinator_pb2_grpc,
)


async def get_ready_players(docker_compose):
    """Helper function to get ready controllers and convert them to players."""
    host = docker_compose.get_service_host("mock-controller-manager", 50052)
    port = docker_compose.get_service_port("mock-controller-manager", 50052)
    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    response = await client.GetReadyControllers(controller_manager_pb2.GetReadyControllersRequest())
    await channel.close()

    # Convert controllers to players
    players = []
    for i, controller in enumerate(response.controllers):
        players.append(
            game_coordinator_pb2.Player(serial=controller.serial, team=i % 2, alive=True, score=0)
        )
    return players


async def wait_for_game_end(game_client, timeout=10):
    """Wait for game to reach ENDED state."""
    for _ in range(timeout * 10):  # Check every 0.1 seconds
        status = await game_client.GetGameStatus(game_coordinator_pb2.GetGameStatusRequest())
        if status.state == game_coordinator_pb2.GameState.ENDED:
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(f"Game did not end within {timeout} seconds")


@pytest.fixture(scope="module")
def docker_compose():
    """Fixture to start docker-compose mock environment."""
    compose = DockerCompose(
        context=".", compose_file_name="docker-compose.mock.yml", pull=False, build=True
    )

    compose.start()

    # Wait for services to be ready
    time.sleep(10)

    print("\n" + "=" * 80)
    print("🚀 Mock environment is running!")
    print("=" * 80)
    print("Jaeger UI: http://localhost:16686")
    print("WebUI: http://localhost:80")
    print("Mock Control API: localhost:50062")
    print("=" * 80)

    yield compose

    # Optional pause before teardown (set PAUSE_BEFORE_TEARDOWN=1 to inspect Jaeger)
    if os.getenv("PAUSE_BEFORE_TEARDOWN"):
        print("\n" + "=" * 80)
        print("⏸️  PAUSED - Inspect Jaeger at http://localhost:16686")
        print("=" * 80)
        print("Press ENTER to tear down the environment...")
        input()

    compose.stop()


@pytest.mark.asyncio
async def test_mock_controller_manager_connection(docker_compose):
    """Test that we can connect to mock controller manager."""
    # Get dynamically assigned port for controller manager
    host = docker_compose.get_service_host("mock-controller-manager", 50052)
    port = docker_compose.get_service_port("mock-controller-manager", 50052)

    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    # Get ready controllers
    response = await client.GetReadyControllers(controller_manager_pb2.GetReadyControllersRequest())

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
    # Get dynamically assigned port for mock control API
    host = docker_compose.get_service_host("mock-controller-manager", 50062)
    port = docker_compose.get_service_port("mock-controller-manager", 50062)

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


@pytest.mark.asyncio
async def test_ffa_game_with_mock_controllers(docker_compose):
    """Test full FFA game lifecycle with mock controllers."""

    # Connect to game coordinator
    game_host = docker_compose.get_service_host("game-coordinator", 50053)
    game_port = docker_compose.get_service_port("game-coordinator", 50053)
    game_channel = grpc.aio.insecure_channel(f"{game_host}:{game_port}")
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    # Connect to mock controller control
    mock_host = docker_compose.get_service_host("mock-controller-manager", 50062)
    mock_port = docker_compose.get_service_port("mock-controller-manager", 50062)
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(mock_channel)

    # Get ready players
    players = await get_ready_players(docker_compose)

    # Start FFA game
    start_response = await game_client.StartGame(
        game_coordinator_pb2.StartGameRequest(game_name="FFA", players=players)
    )

    assert start_response.success
    assert start_response.game_id != ""

    # Wait for game to start
    await asyncio.sleep(2)

    # Simulate some deaths
    for i in range(3):
        death_response = await mock_client.SimulateDeath(
            controller_manager_mock_pb2.DeathRequest(serial=f"mock_controller_{i}")
        )
        assert death_response.success
        await asyncio.sleep(1)

    # Wait for game to end (with extra time for 1-second winner delay)
    await wait_for_game_end(game_client, timeout=15)

    # Check game status
    status_response = await game_client.GetGameStatus(game_coordinator_pb2.GetGameStatusRequest())
    assert status_response.state == game_coordinator_pb2.GameState.ENDED

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_teams_game_with_mock_controllers(docker_compose):
    """Test full Teams game lifecycle with mock controllers."""

    # Connect to game coordinator
    game_host = docker_compose.get_service_host("game-coordinator", 50053)
    game_port = docker_compose.get_service_port("game-coordinator", 50053)
    game_channel = grpc.aio.insecure_channel(f"{game_host}:{game_port}")
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    # Connect to mock controller control
    mock_host = docker_compose.get_service_host("mock-controller-manager", 50062)
    mock_port = docker_compose.get_service_port("mock-controller-manager", 50062)
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(mock_channel)

    # Get ready players
    players = await get_ready_players(docker_compose)

    # Start Teams game
    start_response = await game_client.StartGame(
        game_coordinator_pb2.StartGameRequest(game_name="Teams", players=players)
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
    # Wait for game to end (with extra time for 1-second winner delay)
    await wait_for_game_end(game_client, timeout=15)

    status_response = await game_client.GetGameStatus(game_coordinator_pb2.GetGameStatusRequest())
    assert status_response.state == game_coordinator_pb2.GameState.ENDED

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_controller_state_streaming(docker_compose):
    """Test streaming controller states from mock controller manager."""

    # Get dynamically assigned port for controller manager
    host = docker_compose.get_service_host("mock-controller-manager", 50052)
    port = docker_compose.get_service_port("mock-controller-manager", 50052)

    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    # Start streaming at 10Hz
    stream_request = controller_manager_pb2.StreamRequest(update_frequency_hz=10)

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
    game_host = docker_compose.get_service_host("game-coordinator", 50053)
    game_port = docker_compose.get_service_port("game-coordinator", 50053)
    game_channel = grpc.aio.insecure_channel(f"{game_host}:{game_port}")
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    # Get ready players
    players = await get_ready_players(docker_compose)

    # Start game (this should create a trace spanning all services)
    start_response = await game_client.StartGame(
        game_coordinator_pb2.StartGameRequest(game_name="FFA", players=players)
    )

    assert start_response.success

    # Wait for game to initialize
    await asyncio.sleep(3)

    # Force end game
    await game_client.ForceEndGame(game_coordinator_pb2.ForceEndGameRequest())

    # Wait for game to fully end
    await wait_for_game_end(game_client, timeout=10)

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

    # Connect to game coordinator
    game_host = docker_compose.get_service_host("game-coordinator", 50053)
    game_port = docker_compose.get_service_port("game-coordinator", 50053)
    game_channel = grpc.aio.insecure_channel(f"{game_host}:{game_port}")
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    # Connect to mock controller control
    mock_host = docker_compose.get_service_host("mock-controller-manager", 50062)
    mock_port = docker_compose.get_service_port("mock-controller-manager", 50062)
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(mock_channel)

    # Get ready players once
    players = await get_ready_players(docker_compose)

    # Run 3 games in sequence
    for i in range(3):
        # Start game
        start_response = await game_client.StartGame(
            game_coordinator_pb2.StartGameRequest(game_name="FFA", players=players)
        )
        assert start_response.success

        # Wait and simulate death
        await asyncio.sleep(1)
        await mock_client.SimulateDeath(
            controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
        )
        await asyncio.sleep(1)

        # End game
        await game_client.ForceEndGame(game_coordinator_pb2.ForceEndGameRequest())

        # Wait for game to fully end before starting next game
        await wait_for_game_end(game_client, timeout=10)

        # Reset controllers for next game
        for j in range(4):
            await mock_client.ResetController(
                controller_manager_mock_pb2.ResetRequest(serial=f"mock_controller_{j}")
            )

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_controller_effects(docker_compose):
    """Test controller visual effects (FLASH, PULSE, RAINBOW, FADE) - Phase 31."""

    # Get dynamically assigned port for controller manager
    host = docker_compose.get_service_host("mock-controller-manager", 50052)
    port = docker_compose.get_service_port("mock-controller-manager", 50052)

    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    # Test 1: FLASH effect on single controller
    flash_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_FLASH,
            color=controller_manager_pb2.RGB(r=255, g=0, b=0),  # Red
            duration_ms=500,
            speed=5,
        )
    )
    assert flash_response.success
    await asyncio.sleep(0.6)  # Wait for effect to complete

    # Test 2: PULSE effect on single controller
    pulse_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_1",
            effect=controller_manager_pb2.EFFECT_PULSE,
            color=controller_manager_pb2.RGB(r=0, g=255, b=0),  # Green
            duration_ms=500,
            speed=3,
        )
    )
    assert pulse_response.success
    await asyncio.sleep(0.6)

    # Test 3: RAINBOW effect on single controller
    rainbow_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_2",
            effect=controller_manager_pb2.EFFECT_RAINBOW,
            duration_ms=500,
            speed=5,
        )
    )
    assert rainbow_response.success
    await asyncio.sleep(0.6)

    # Test 4: FADE_OUT effect
    fade_out_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_3",
            effect=controller_manager_pb2.EFFECT_FADE_OUT,
            color=controller_manager_pb2.RGB(r=0, g=0, b=255),  # Blue
            duration_ms=300,
        )
    )
    assert fade_out_response.success
    await asyncio.sleep(0.4)

    # Test 5: FADE_IN effect
    fade_in_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_3",
            effect=controller_manager_pb2.EFFECT_FADE_IN,
            color=controller_manager_pb2.RGB(r=255, g=255, b=0),  # Yellow
            duration_ms=300,
        )
    )
    assert fade_in_response.success
    await asyncio.sleep(0.4)

    # Test 6: EFFECT_NONE (solid color)
    none_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_NONE,
            color=controller_manager_pb2.RGB(r=255, g=0, b=255),  # Magenta
            duration_ms=0,
        )
    )
    assert none_response.success

    # Test 7: Effect on all controllers (empty serial)
    all_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="",  # All controllers
            effect=controller_manager_pb2.EFFECT_FLASH,
            color=controller_manager_pb2.RGB(r=255, g=255, b=255),  # White
            duration_ms=500,
            speed=10,  # Fast flash
        )
    )
    assert all_response.success
    await asyncio.sleep(0.6)

    # Test 8: Effect cancellation (start new effect before previous completes)
    # Start long-running effect
    await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_PULSE,
            color=controller_manager_pb2.RGB(r=255, g=0, b=0),
            duration_ms=2000,  # 2 seconds
            speed=1,
        )
    )
    await asyncio.sleep(0.2)  # Let it start

    # Cancel by starting new effect
    cancel_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_FLASH,
            color=controller_manager_pb2.RGB(r=0, g=255, b=0),
            duration_ms=300,
            speed=5,
        )
    )
    assert cancel_response.success
    await asyncio.sleep(0.4)

    await channel.close()

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "game_mode",
    [
        "FFA",
        "Teams",
        "Random Teams",
        # Note: Nonstop Joust not included - players respawn so spans don't end on death
    ],
)
async def test_staggered_player_deaths(docker_compose, game_mode):
    """Test game with staggered player deaths to show varied span lengths in Jaeger.

    This test demonstrates realistic gameplay where players die at different times,
    creating varied player lifecycle span lengths in distributed traces.

    For FFA: Players die one by one until winner remains
    For Teams/Random Teams: Players from different teams die, last team wins

    Note: Nonstop Joust is excluded because players respawn - deaths don't end spans.
    """

    # Connect to game coordinator
    game_host = docker_compose.get_service_host("game-coordinator", 50053)
    game_port = docker_compose.get_service_port("game-coordinator", 50053)
    game_channel = grpc.aio.insecure_channel(f"{game_host}:{game_port}")
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    # Connect to mock controller control
    mock_host = docker_compose.get_service_host("mock-controller-manager", 50062)
    mock_port = docker_compose.get_service_port("mock-controller-manager", 50062)
    mock_channel = grpc.aio.insecure_channel(f"{mock_host}:{mock_port}")
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(mock_channel)

    # Get ready players
    players = await get_ready_players(docker_compose)
    assert len(players) == 4

    # Start game
    start_response = await game_client.StartGame(
        game_coordinator_pb2.StartGameRequest(game_name=game_mode, players=players)
    )
    assert start_response.success
    game_id = start_response.game_id

    print(f"\n=== Starting {game_mode} game with staggered deaths ===")

    # Wait for game to fully start (initialization + color phases + countdown)
    # FFA: 1s colors + 3s countdown = 4s
    # Teams: 2s colors + 3s countdown = 5s
    # Random Teams: 5s team formation + 3s countdown = 8s
    # Wait 9 seconds to be safe for all modes (covers Random Teams + buffer)
    await asyncio.sleep(9)

    # Simulate deaths at different times to create varied span lengths
    # For team games, kill players from different teams to avoid early game end

    # Player 0 dies first (shortest span)
    await asyncio.sleep(1)
    death_0 = await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
    )
    assert death_0.success
    print(f"  Player 0 died at ~3s (accel: {death_0.accel_magnitude:.2f})")

    # Player 2 dies second (different team for team modes)
    await asyncio.sleep(2)
    death_2 = await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_2")
    )
    assert death_2.success
    print(f"  Player 2 died at ~5s (accel: {death_2.accel_magnitude:.2f})")

    # Player 1 dies third
    await asyncio.sleep(2)
    death_1 = await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_1")
    )
    assert death_1.success
    print(f"  Player 1 died at ~7s (accel: {death_1.accel_magnitude:.2f})")

    # Player 3 wins (longest span) - wait for game to end naturally
    # Game will: detect win → sleep 1 second (showing winner) → teardown
    await wait_for_game_end(game_client, timeout=15)

    # Check game status
    status_response = await game_client.GetGameStatus(
        game_coordinator_pb2.GetGameStatusRequest()
    )
    # Game should have ended automatically
    # FFA: when only 1 player remains
    # Teams/Random Teams: when only 1 team remains
    assert status_response.state == game_coordinator_pb2.GameState.ENDED

    print(f"  Game ended with player 3 as winner")
    print(f"  Check Jaeger UI: http://localhost:16686")
    print(f"  Search for: {game_mode.replace(' ', '-')}")
    print(f"  Look for varied player/team span lengths!")

    # Cleanup
    await game_channel.close()
    await mock_channel.close()
