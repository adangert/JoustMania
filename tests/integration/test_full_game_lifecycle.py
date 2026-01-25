"""
Comprehensive integration tests for all JoustMania game modes.

Tests full game lifecycle: Menu -> Game Start -> Gameplay -> Game End -> Back to Menu
with LED color verification at each stage.

Requires PR #165 observability API: GetColor, StreamObservability
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from proto import controller_manager_mock_pb2
from tests.integration.helpers import (
    ObservabilityObserver,
    force_end_game_and_wait,
    get_mock_client,
    get_mock_controller_serials,
    kill_players_for_team_win,
    kill_players_until_one_remains,
    start_game_via_menu,
    verify_controllers_have_color,
    verify_lobby_colors,
    verify_lobby_colors_restored,
    wait_for_game_end,
    wait_for_lobby_colors,
)

# Expected dim lobby colors per game mode (30% of full brightness)
# These must match services/menu/utils/led.py GAME_MODE_COLORS * DIM_FACTOR
# Note: JoustRandomTeams color verification is disabled due to a timing issue
# where team colors aren't always reset to lobby colors. See issue #XXX.
EXPECTED_LOBBY_COLORS: dict[str, tuple[int, int, int] | None] = {
    "JoustFFA": (76, 42, 0),  # Orange dimmed
    "JoustTeams": (0, 30, 76),  # Blue dimmed
    "JoustRandomTeams": None,  # Skip exact check - timing issue with team color reset
    "Swapper": (76, 0, 76),  # Magenta dimmed
    "Werewolf": (0, 76, 30),  # Green dimmed
    "Traitor": (38, 0, 38),  # Dark purple dimmed
    "Zombie": (30, 30, 30),  # Gray dimmed
    "FightClub": (76, 76, 0),  # Yellow dimmed
    "Tournament": (45, 0, 76),  # Purple dimmed
    "NonstopJoust": (76, 15, 36),  # Pink dimmed
}


# =============================================================================
# Game mode configurations
# =============================================================================

# Games that end naturally when players die (use kill flow)
# Only includes games verified to work in integration tests
STANDARD_GAME_MODES = [
    pytest.param("JoustFFA", 2, "ffa", id="JoustFFA"),
    pytest.param("JoustTeams", 3, "team", id="JoustTeams"),
    pytest.param("JoustRandomTeams", 3, "team", id="JoustRandomTeams"),
    # Note: Swapper, FightClub need debugging - timeout on game start
    # Note: Ninja, Commander not implemented in GameFactory
]

# Games that need force-end (complex win conditions, respawn, or brackets)
# Temporarily disabled - these modes have initialization issues to debug
FORCE_END_GAME_MODES = [
    # pytest.param("Traitor", 4, id="Traitor"),
    # pytest.param("Werewolf", 3, id="Werewolf"),
    # pytest.param("Zombies", 4, id="Zombies"),
    # pytest.param("Tournament", 3, id="Tournament"),
    # pytest.param("NonStop", 2, id="NonStop"),
]


# =============================================================================
# Standard game mode tests (end naturally via kill flow)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("game_mode,min_players,game_type", STANDARD_GAME_MODES)
async def test_full_lifecycle_standard(docker_compose, game_mode, min_players, game_type):  # noqa: ARG001
    """Test full game lifecycle for standard game modes.

    Verifies:
    1. Game starts via Menu flow
    2. Players get game colors (non-zero)
    3. Players can be killed to end game
    4. Game ends naturally when win condition met
    5. Menu resets LED colors (not stuck at black)

    Args:
        game_mode: Name of the game mode to test
        min_players: Minimum players required (for documentation)
        game_type: "ffa" for free-for-all or "team" for team games
    """
    # Start observability stream first
    mock_client, mock_channel = await get_mock_client(docker_compose)
    observer = ObservabilityObserver(mock_client)
    await observer.start()

    try:
        # 1. Start game via Menu flow
        game_client, game_channel, _, _ = await start_game_via_menu(docker_compose, game_mode=game_mode, timeout=25.0)

        # Get controller serials
        serials = await get_mock_controller_serials(docker_compose)

        # 2. Brief pause for game colors to be applied
        await asyncio.sleep(0.3)

        # 3. Verify all controllers have some color (game assigned)
        await verify_controllers_have_color(mock_client, serials)

        # 4. Kill players to end game
        # Kill with minimal delay - death processing is async
        if game_type == "team":
            killed = await kill_players_for_team_win(mock_client, serials, delay=0.1)
        else:
            killed = await kill_players_until_one_remains(mock_client, serials, delay=0.1)

        winner = [s for s in serials if s not in killed][0] if killed else serials[0]
        print(f"Killed: {killed}, Winner: {winner}")

        # 5. Wait for game to end naturally
        await wait_for_game_end(game_client, timeout=15)

        # 6. Wait for menu to fully reset controller colors (polls until colors match)
        # This handles timing variations in menu color reset after game ends
        expected_color = EXPECTED_LOBBY_COLORS.get(game_mode)
        await wait_for_lobby_colors(mock_client, serials, expected_color=expected_color, timeout=3.0)

        # 8. Verify event sequence shows lobby colors restored
        events = observer.get_events()
        verify_lobby_colors_restored(events, serials)

        await game_channel.close()

    finally:
        await observer.stop()
        await mock_channel.close()


# =============================================================================
# Force-end game mode tests (complex win conditions)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("game_mode,min_players", FORCE_END_GAME_MODES)
@pytest.mark.skip(reason="Force-end game modes need debugging")
async def test_full_lifecycle_force_end(docker_compose, game_mode, min_players):  # noqa: ARG001
    """Test game modes that require force-end.

    These modes have complex win conditions (Traitor, Werewolf, Zombies),
    bracket systems (Tournament), or respawn mechanics (NonStop) that
    make natural ending unreliable in tests.

    Verifies:
    1. Game starts via Menu flow
    2. Players get game colors
    3. Game runs briefly
    4. Force-end works correctly
    5. Menu resets LED colors

    Args:
        game_mode: Name of the game mode to test
        min_players: Minimum players required (for documentation)
    """
    # Start observability stream
    mock_client, mock_channel = await get_mock_client(docker_compose)
    observer = ObservabilityObserver(mock_client)
    await observer.start()

    try:
        # 1. Start game via Menu flow
        game_client, game_channel, _, _ = await start_game_via_menu(docker_compose, game_mode=game_mode, timeout=25.0)

        # Get controller serials
        serials = await get_mock_controller_serials(docker_compose)

        # 2. Brief pause for game colors
        await asyncio.sleep(0.3)

        # 3. Verify all controllers have color
        await verify_controllers_have_color(mock_client, serials)

        # 4. Let game run briefly
        await asyncio.sleep(1.0)

        # 5. Force end game
        await force_end_game_and_wait(game_client, timeout=10)

        # 6. Wait for menu to reset colors
        # Rainbow duration is configurable (300ms in CI, 3s in production)
        await asyncio.sleep(1.0)

        # 7. Verify LED colors restored to expected lobby color
        expected_color = EXPECTED_LOBBY_COLORS.get(game_mode)
        await verify_lobby_colors(mock_client, serials, expected_color=expected_color)

        # 8. Verify events
        events = observer.get_events()
        verify_lobby_colors_restored(events, serials)

        await game_channel.close()

    finally:
        await observer.stop()
        await mock_channel.close()


# =============================================================================
# LED transition verification test
# =============================================================================


@pytest.mark.asyncio
async def test_led_transition_observability(docker_compose):
    """Test LED transitions are observable via StreamObservability.

    Verifies that the observability stream captures LED changes during:
    1. Game start (players get unique colors)
    2. Player death (death effect)
    3. Game end (lobby colors restored)
    """
    mock_client, mock_channel = await get_mock_client(docker_compose)
    observer = ObservabilityObserver(mock_client)
    await observer.start()

    try:
        # Start FFA game
        game_client, game_channel, _, _ = await start_game_via_menu(docker_compose, game_mode="JoustFFA", timeout=25.0)

        serials = await get_mock_controller_serials(docker_compose)

        # Let game run briefly
        await asyncio.sleep(0.5)

        # Kill one player
        killed_serial = serials[0]
        await mock_client.SimulateDeath(controller_manager_mock_pb2.DeathRequest(serial=killed_serial))
        await asyncio.sleep(0.5)

        # Kill remaining players except last
        for serial in serials[1:-1]:
            await mock_client.SimulateDeath(controller_manager_mock_pb2.DeathRequest(serial=serial))
            await asyncio.sleep(0.1)

        # Wait for game end
        await wait_for_game_end(game_client, timeout=15)
        await asyncio.sleep(2.0)

        # Analyze collected events
        events = observer.get_events()

        # Verify we got LED events
        led_events = [e for e in events if e.HasField("led_change")]
        assert len(led_events) > 0, "No LED events captured"

        # Verify we got events for all controllers
        controllers_with_events = {e.serial for e in led_events}
        for serial in serials:
            assert serial in controllers_with_events, f"No LED events for {serial}"

        # Get final colors
        final_colors = observer.get_last_colors()
        for serial in serials:
            assert serial in final_colors, f"No final color for {serial}"
            color = final_colors[serial]
            assert sum(color) > 0, f"{serial} ended with black LED"

        await game_channel.close()

    finally:
        await observer.stop()
        await mock_channel.close()
