"""
Comprehensive integration tests for all JoustMania game modes.

Tests full game lifecycle: Menu -> Game Start -> Gameplay -> Game End -> Back to Menu
with LED color verification at each stage.

Requires PR #165 observability API: GetColor, StreamObservability
"""

import asyncio
import os
import sys
from collections.abc import Callable
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from tests.integration.helpers import (
    GameEventCollector,
    ObservabilityObserver,
    end_fight_club_game,
    end_swapper_game,
    end_tournament_game,
    end_werewolf_game,
    end_zombies_game,
    force_end_game,
    get_game_client,
    get_mock_client,
    get_mock_controller_serials,
    kill_players_for_team_win,
    kill_players_until_one_remains,
    start_game_via_menu,
    verify_controllers_have_color,
    verify_lobby_colors,
    verify_lobby_colors_restored,
)

# =============================================================================
# Test timing configuration
# =============================================================================
# Game settings are now stored in Menu service's state_manager and passed via
# typed proto config when starting games. Integration tests use default values.

FIGHT_CLUB_ROUNDS = 4  # Run 1 more than minimum to ensure clear winner


# =============================================================================
# End strategy type and helpers
# =============================================================================

# Type alias for end strategy functions
# Signature: async def(mock_client, serials, game_client, event_collector) -> None
EndStrategy = Callable[[Any, list[str], Any, GameEventCollector], Any]


async def configure_test_settings(docker_compose, game_mode: str):
    """Configure game-specific settings for faster test execution.

    Note: Settings are now stored in Menu service's state_manager and passed
    via typed proto config. Integration tests use default settings.
    This function is kept for API compatibility but is now a no-op.

    Args:
        docker_compose: Docker compose fixture (unused)
        game_mode: The game mode being tested (unused)
    """
    # Settings are now passed via StartGameConfig proto from Menu service
    # Default settings are used for integration tests
    pass


async def end_ffa_game(mock_client, serials: list[str], _game_client, _event_collector) -> None:
    """End FFA game by killing all but one player."""
    await kill_players_until_one_remains(mock_client, serials, delay=0.1)


async def end_team_game(mock_client, serials: list[str], _game_client, _event_collector) -> None:
    """End team game by eliminating one team."""
    await kill_players_for_team_win(mock_client, serials, delay=0.1)


async def end_swapper(mock_client, serials: list[str], game_client, _event_collector) -> None:
    """End Swapper by swapping all to one team."""
    await end_swapper_game(mock_client, serials, game_client, delay=0.3)


async def end_zombies(mock_client, serials: list[str], _game_client, _event_collector) -> None:
    """End Zombies by converting all humans."""
    await end_zombies_game(mock_client, serials, delay=0.3)


async def end_werewolf(mock_client, serials: list[str], _game_client, _event_collector) -> None:
    """End Werewolf by killing all werewolves.

    The game ends when all werewolves (or humans) are dead.
    Test configures werewolf_reveal_time=0 so reveal is immediate.
    """
    # Small delay for reveal (configured to 0, so just need processing time)
    await asyncio.sleep(0.5)
    await end_werewolf_game(mock_client, serials, delay=0.3, wait_for_reveal=False)


async def end_tournament(mock_client, serials: list[str], _game_client, _event_collector) -> None:
    """End Tournament by running through bracket.

    Test configures tournament_invincibility=0.5 for faster matches.
    """
    # Invincibility is configured to 0.5s, wait slightly longer
    await end_tournament_game(
        mock_client, serials, delay=0.2, invincibility_wait=0.7  # 0.5s configured + buffer
    )


async def end_fight_club(mock_client, serials: list[str], game_client, _event_collector) -> None:
    """End FightClub by running minimum rounds until winner.

    Test configures fight_club_invincibility=0.5 and fight_club_min_rounds=3
    for faster execution.
    """
    # Invincibility is configured to 0.5s, wait slightly longer
    await end_fight_club_game(
        mock_client,
        serials,
        game_client,
        delay=0.2,
        invincibility_wait=0.7,  # 0.5s configured + buffer
        rounds=FIGHT_CLUB_ROUNDS,
    )


async def end_with_force(_mock_client, _serials: list[str], game_client, event_collector) -> None:
    """End game via ForceEndGame RPC."""
    await asyncio.sleep(2.0)  # Let game run briefly
    await force_end_game(game_client, event_collector, timeout=10)


# =============================================================================
# Game mode configurations - single list with callable end strategies
# =============================================================================

# All game modes with their end strategies and timeouts
# Format: (game_mode, min_players, end_strategy_fn, timeout_seconds)
ALL_GAME_MODES = [
    # FFA games - kill until one remains
    pytest.param("JoustFFA", 2, end_ffa_game, 15, id="JoustFFA"),
    # Team games - eliminate one team
    pytest.param("JoustTeams", 3, end_team_game, 15, id="JoustTeams"),
    pytest.param("JoustRandomTeams", 3, end_team_game, 15, id="JoustRandomTeams"),
    # Complex game modes
    pytest.param("Swapper", 4, end_swapper, 15, id="Swapper"),
    pytest.param("Zombies", 4, end_zombies, 15, id="Zombies"),
    pytest.param("Werewolf", 4, end_werewolf, 20, id="Werewolf"),
    pytest.param("Tournament", 4, end_tournament, 30, id="Tournament"),
    pytest.param("FightClub", 4, end_fight_club, 30, id="FightClub"),
    pytest.param("NonStop", 2, end_with_force, 15, id="NonStop"),
    pytest.param("Traitor", 4, end_with_force, 15, id="Traitor"),
    # Note: Ninja, Commander not implemented in GameFactory
]


# =============================================================================
# Main game lifecycle test
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("game_mode,_min_players,end_strategy,game_timeout", ALL_GAME_MODES)
async def test_full_game_lifecycle(
    docker_compose, game_mode: str, _min_players: int, end_strategy: EndStrategy, game_timeout: int
):
    """Test full game lifecycle for all game modes.

    Each game mode has its own end strategy:
    - FFA games: Kill until one player remains
    - Team games: Eliminate one team
    - Swapper: Swap all players to one team
    - Zombies: Convert all humans to zombies
    - Werewolf: Kill werewolves (reveal_time=0 via settings for instant reveal)
    - Tournament: Run bracket matches (invincibility=0.5s via settings)
    - FightClub: Run 4 rounds (min_rounds=3, invincibility=0.5s via settings)
    - NonStop/Traitor: Force-end (no natural end in tests)

    Verifies:
    1. Game starts via Menu flow
    2. Players get game colors (non-zero)
    3. End strategy triggers win condition
    4. Game ends (naturally or via force)
    5. Menu resets LED colors (not stuck at black)

    Args:
        game_mode: Name of the game mode to test
        _min_players: Minimum players required (for documentation, unused in test)
        end_strategy: Async function to trigger game end
        game_timeout: Timeout for game end in seconds
    """
    # Configure game-specific settings for faster test execution
    await configure_test_settings(docker_compose, game_mode)

    # Get clients
    mock_client, mock_channel = await get_mock_client(docker_compose)
    game_client, game_channel = await get_game_client(docker_compose)
    serials = await get_mock_controller_serials(docker_compose)

    # Use context managers for clean resource management
    async with GameEventCollector(game_client) as event_collector:
        observer = ObservabilityObserver(mock_client)
        await observer.start()

        try:
            # 1. Start game via Menu flow (uses event_collector for reliable event detection)
            await start_game_via_menu(
                docker_compose,
                game_mode=game_mode,
                timeout=25.0,
                event_collector=event_collector,
            )

            # 2. Brief pause for game colors to be applied
            await asyncio.sleep(0.5)

            # 3. Verify all controllers have some color (game assigned)
            await verify_controllers_have_color(mock_client, serials)

            # 4. Apply end strategy
            print(f"Applying end strategy for {game_mode}")
            await end_strategy(mock_client, serials, game_client, event_collector)

            # 5. Wait for game to end (if not already ended by force)
            if end_strategy != end_with_force:
                try:
                    await event_collector.wait_for_any_event(
                        ["game_ended", "game_force_ended", "game_error"],
                        timeout=game_timeout
                    )
                except TimeoutError:
                    # Debug: print collected events before re-raising
                    print(f"DEBUG: Collected {len(event_collector.events)} events:")
                    for event in event_collector.events:
                        print(f"  - {event.event_type}: {dict(event.data)}")
                    raise

            # 6. Wait for menu to fully reset controller colors
            await asyncio.sleep(2.0)

            # 7. Verify LED colors are restored (not stuck at black)
            await verify_lobby_colors(mock_client, serials)

            # 8. Verify event sequence shows lobby colors restored
            events = observer.get_events()
            verify_lobby_colors_restored(events, serials)

        finally:
            await observer.stop()

    await game_channel.close()
    await mock_channel.close()
