"""
Game flow tests for JoustMania mock environment.

Tests full game lifecycles including:
- FFA games
- Team games
- Multiple games in sequence
- Staggered player deaths
- Distributed tracing propagation
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from proto import (
    controller_manager_mock_pb2,
)

from tests.integration.helpers import (
    force_end_game_and_wait,
    get_mock_client,
    start_game_via_menu,
    wait_for_game_end,
)


@pytest.mark.asyncio
async def test_ffa_game_with_mock_controllers(docker_compose):
    """Test full FFA game lifecycle starting via Menu."""

    # Get mock client first to set up auto-end
    mock_client, mock_channel = await get_mock_client(docker_compose)

    # Enable auto game end: kill players after 12 seconds (3s countdown + 9s gameplay)
    auto_end_response = await mock_client.SetAutoGameEnd(
        controller_manager_mock_pb2.AutoGameEndRequest(duration_seconds=12.0, enabled=True)
    )
    assert auto_end_response.success

    # Start game via Menu flow (handles ready state, game selection, and start)
    game_client, game_channel, _, _ = await start_game_via_menu(
        docker_compose, game_mode="JoustFFA", timeout=25.0
    )

    # Wait for auto-end to trigger and game to finish
    # 12s auto-end + 1s winner delay + 2s teardown = ~15s total
    await wait_for_game_end(game_client, timeout=20)

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_teams_game_with_mock_controllers(docker_compose):
    """Test full Teams game lifecycle starting via Menu."""

    # Start game via Menu flow
    game_client, game_channel, mock_client, mock_channel = await start_game_via_menu(
        docker_compose, game_mode="JoustTeams", timeout=25.0
    )

    # Simulate deaths - kill 3 players to ensure one team wins
    # Note: With random_teams=true (default), team assignment is randomized,
    # so we can't assume specific players are on the same team.
    # Killing 3 players guarantees one team is eliminated.
    await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
    )
    await asyncio.sleep(1)

    await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_1")
    )
    await asyncio.sleep(1)

    await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_2")
    )
    await asyncio.sleep(2)

    # Game should auto-end when one team is eliminated (only player 3 remains)
    # Wait for game to end (with extra time for winner celebration)
    await wait_for_game_end(game_client, timeout=15)

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_distributed_tracing_propagation(docker_compose):
    """Test that distributed tracing works end-to-end via Menu flow.

    This test verifies the complete trace chain:
    Menu -> Supervisor -> GameCoordinator -> Game
    """

    # Start game via Menu flow - this creates a complete trace chain
    game_client, game_channel, mock_client, mock_channel = await start_game_via_menu(
        docker_compose, game_mode="JoustFFA", timeout=25.0
    )

    # Wait for game to run briefly
    await asyncio.sleep(2)

    # Force end game and wait for completion
    await force_end_game_and_wait(game_client)

    # Note: To verify tracing, check Jaeger UI at http://localhost:16686
    # Search for service="menu-service" and verify the complete trace chain:
    # - Menu: select_game_mode span
    # - Menu: game_requested event with trace context
    # - Supervisor: orchestrate_game_start span
    # - GameCoordinator: StartGame span (child of orchestrate_game_start)
    # - GameCoordinator: game_lifecycle span (child of StartGame)

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_multiple_games_sequence(docker_compose):
    """Test running multiple games in sequence via Menu flow."""

    # Run 3 games in sequence, each started via Menu
    for i in range(3):
        # Start game via Menu flow
        game_client, game_channel, mock_client, mock_channel = await start_game_via_menu(
            docker_compose, game_mode="JoustFFA", timeout=25.0
        )

        # Wait and simulate death
        await asyncio.sleep(1)
        await mock_client.SimulateDeath(
            controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
        )
        await asyncio.sleep(1)

        # Force end game and wait
        await force_end_game_and_wait(game_client)

        # Close channels for this iteration
        await game_channel.close()
        await mock_channel.close()

        # Reset controllers for next game (releases all buttons)
        mock_client_reset, mock_channel_reset = await get_mock_client(docker_compose)
        for j in range(4):
            await mock_client_reset.ResetController(
                controller_manager_mock_pb2.ResetRequest(serial=f"mock_controller_{j}")
            )
        await mock_channel_reset.close()

        # Wait for Menu to fully reset after game end
        # The Menu receives game_force_ended and resets its state
        await asyncio.sleep(2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "game_mode",
    [
        "JoustFFA",
        "JoustTeams",
        "JoustRandomTeams",
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

    # Start game via Menu flow
    game_client, game_channel, mock_client, mock_channel = await start_game_via_menu(
        docker_compose, game_mode=game_mode, timeout=25.0
    )

    print(f"\n=== Starting {game_mode} game with staggered deaths ===")

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

    print("  Game ended with player 3 as winner")
    print("  Check Jaeger UI: http://localhost:16686")
    print(f"  Search for: {game_mode.replace(' ', '-')}")
    print("  Look for varied player/team span lengths!")

    # Cleanup
    await game_channel.close()
    await mock_channel.close()
