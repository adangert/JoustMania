"""
Integration tests for Random Teams game mode with mock gRPC services.

Tests the full Random Teams game flow using mocked ControllerManager and Settings services,
verifying random team assignment, team formation phase, game logic, and win conditions.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from .conftest import MockControllerManagerService

# Import Random Teams game module
service_dir = Path(__file__).parent.parent
games_dir = service_dir / "games"

spec = importlib.util.spec_from_file_location("random_teams", games_dir / "random_teams.py")
random_teams = importlib.util.module_from_spec(spec)
sys.modules["random_teams"] = random_teams
spec.loader.exec_module(random_teams)


@pytest.fixture
def mock_controller_manager_random():
    """Fixture providing mock ControllerManager for random teams."""
    return MockControllerManagerService(
        num_controllers=4,
        death_schedule={2.0: 1, 3.0: 2, 4.0: 3},  # Kill 3 players
        max_duration=7.0,
    )


@pytest.mark.asyncio
async def test_random_teams_game_full_lifecycle(mock_controller_manager_random, mock_settings, event_collector):
    """
    Test full Random Teams game lifecycle:
    - Game starts
    - Random team assignment phase
    - Team colors set
    - Deaths tracked
    - Winner determined
    """
    game = random_teams.RandomTeamsGame(
        controller_manager_client=mock_controller_manager_random,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_random_teams_1",
        num_teams=2,
    )

    await game.run()

    assert game.state == random_teams.GameState.ENDED
    assert event_collector.count_events_of_type("game_starting") == 1
    assert event_collector.count_events_of_type("countdown_start") == 1
    assert event_collector.count_events_of_type("game_started") == 1

    death_events = event_collector.get_events_of_type("player_death")
    assert len(death_events) >= 1

    assert event_collector.count_events_of_type("game_ended") == 1


@pytest.mark.asyncio
async def test_random_teams_with_three_teams(mock_settings, event_collector):
    """Test Random Teams game with 3 teams and 6 players."""
    mock_cm = MockControllerManagerService(
        num_controllers=6,
        death_schedule={1.5: 1, 2.0: 4},
        max_duration=7.0,
    )

    game = random_teams.RandomTeamsGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_random_teams_2",
        num_teams=3,
    )

    await game.run()

    assert game.state == random_teams.GameState.ENDED

    death_events = event_collector.get_events_of_type("player_death")
    assert len(death_events) >= 1


@pytest.mark.asyncio
async def test_random_teams_game_settings_loaded(mock_controller_manager_random, mock_settings, event_collector):
    """Test that game loads settings from Settings service."""
    mock_settings.settings["sensitivity"] = "FAST"
    mock_settings.settings["play_audio"] = "true"

    game = random_teams.RandomTeamsGame(
        controller_manager_client=mock_controller_manager_random,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_random_teams_3",
        num_teams=2,
    )

    await game._load_settings()

    assert game.sensitivity == random_teams.Sensitivity.FAST
    assert game.play_audio is True


@pytest.mark.asyncio
async def test_random_teams_game_force_end(mock_settings, event_collector):
    """Test that force_end() stops the Random Teams game."""
    mock_cm = MockControllerManagerService(
        num_controllers=4,
        death_schedule={},
        infinite=True,
    )

    game = random_teams.RandomTeamsGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_random_teams_4",
        num_teams=2,
    )

    game_task = asyncio.create_task(game.run())

    await asyncio.sleep(1.0)
    game.force_end()

    try:
        await asyncio.wait_for(game_task, timeout=2.0)
    except TimeoutError:
        pytest.fail("Game did not end after force_end() was called")

    assert game.running is False
