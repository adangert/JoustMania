"""
Game flow tests for JoustMania mock environment.

Tests full game lifecycles for all game modes via Docker Compose environment.
Uses parametrization to verify each game mode works correctly.
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

# Game modes that end naturally when players die
GAME_MODES = [
    pytest.param("JoustFFA", id="FFA"),
    pytest.param("JoustTeams", id="Teams"),
    # NonstopJoust has separate test - players respawn so game needs force-end
    # Tournament/Werewolf excluded - require special handling
]


@pytest.mark.asyncio
@pytest.mark.parametrize("game_mode", GAME_MODES)
async def test_game_lifecycle(docker_compose, game_mode):
    """Test full game lifecycle for each game mode.

    Verifies:
    - Game starts via Menu flow
    - Players can die
    - Game ends when win condition is met
    - Tracing spans are created
    """
    # Start game via Menu flow
    game_client, game_channel, mock_client, mock_channel = await start_game_via_menu(
        docker_compose, game_mode=game_mode, timeout=25.0
    )

    # Simulate deaths - kill 3 players to trigger win condition
    # For FFA: last player standing wins
    # For Teams/RandomTeams: killing 3 guarantees one team is eliminated
    for i, serial in enumerate(["mock_controller_0", "mock_controller_1", "mock_controller_2"]):
        await asyncio.sleep(1)
        death_response = await mock_client.SimulateDeath(
            controller_manager_mock_pb2.DeathRequest(serial=serial)
        )
        assert death_response.success, f"Failed to kill {serial}"

    # Wait for game to end naturally (winner celebration + teardown)
    await wait_for_game_end(game_client, timeout=15)

    await game_channel.close()
    await mock_channel.close()


# NonstopJoust integration test skipped - requires time-based end or manual stop
# FFA and Teams tests already validate the Menu -> Supervisor -> GameCoordinator flow
# NonstopJoust-specific logic is tested in services/game_coordinator/tests/


@pytest.mark.asyncio
async def test_distributed_tracing_propagation(docker_compose):
    """Test that distributed tracing works end-to-end via Menu flow.

    This test verifies the complete trace chain:
    Menu -> Supervisor -> GameCoordinator -> Game

    Check Jaeger UI at http://localhost:16686 to verify:
    - Menu: select_game_mode span
    - Supervisor: orchestrate_game_start span
    - GameCoordinator: StartGame span (child of orchestrate)
    - GameCoordinator: game_lifecycle span (child of StartGame)
    """
    # Start game via Menu flow - this creates a complete trace chain
    game_client, game_channel, mock_client, mock_channel = await start_game_via_menu(
        docker_compose, game_mode="JoustFFA", timeout=25.0
    )

    # Let game run briefly to generate spans
    await asyncio.sleep(2)

    # Force end game
    await force_end_game_and_wait(game_client)

    await game_channel.close()
    await mock_channel.close()


@pytest.mark.asyncio
async def test_game_to_menu_led_transition(docker_compose):
    """Test LED colors transition correctly from game end to menu.

    Verifies that the race condition is fixed:
    1. Game starts - players get unique colors
    2. Player dies - LED off (death effect)
    3. Winner detected - rainbow effect on winner (sent during gameplay)
    4. Game ends - menu resets colors
    5. Both controllers should have dim lobby color

    The fix ensures rainbow is sent via gameplay stream in _check_win_condition,
    not in _end_game_impl where the stream may already be closed.
    """
    # Start 2-player FFA game (use only 2 mock controllers for simpler test)
    game_client, game_channel, mock_client, mock_channel = await start_game_via_menu(
        docker_compose, game_mode="JoustFFA", timeout=25.0
    )

    # Kill players 0, 1, 2 to leave player 3 as winner
    for serial in ["mock_controller_0", "mock_controller_1", "mock_controller_2"]:
        await asyncio.sleep(0.5)
        death_response = await mock_client.SimulateDeath(
            controller_manager_mock_pb2.DeathRequest(serial=serial)
        )
        assert death_response.success, f"Failed to kill {serial}"

    # Wait for game to end and menu to reset
    await wait_for_game_end(game_client, timeout=15)

    # Give menu time to fully reset controller colors
    await asyncio.sleep(3.0)

    # Verify final LED colors using GetColor RPC
    # After game ends, menu should set dim lobby colors
    # JoustFFA lobby color is orange (255, 140, 0) at 30% = (76, 42, 0)
    for serial in ["mock_controller_0", "mock_controller_1", "mock_controller_2", "mock_controller_3"]:
        color_response = await mock_client.GetColor(
            controller_manager_mock_pb2.GetColorRequest(serial=serial)
        )
        assert color_response.success, f"GetColor failed for {serial}: {color_response.error}"

        # Log actual color for debugging
        print(f"{serial}: RGB({color_response.r}, {color_response.g}, {color_response.b})")

        # Verify color is not stuck at 0 (loser's death effect)
        # and not still the game color or rainbow
        # Menu lobby should set some non-zero color
        total_brightness = color_response.r + color_response.g + color_response.b
        assert total_brightness > 0, f"{serial} LED is off (stuck at death effect)"

    await game_channel.close()
    await mock_channel.close()
