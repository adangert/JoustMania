"""
Integration tests for Teams game mode with mock gRPC services.

Tests the full Teams game flow using mocked ControllerManager and Settings services,
verifying team assignment, game logic, event publishing, and win conditions.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from .conftest import MockControllerManagerService

# Import Teams game module
service_dir = Path(__file__).parent.parent
games_dir = service_dir / "games"

spec = importlib.util.spec_from_file_location("teams", games_dir / "teams.py")
teams = importlib.util.module_from_spec(spec)
sys.modules["teams"] = teams
spec.loader.exec_module(teams)

# Import game_coordinator_pb2 for Player message
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))
from proto import game_coordinator_pb2  # noqa: E402


@pytest.fixture
def mock_controller_manager_teams():
    """Fixture providing mock ControllerManager for teams (4 players, 2 teams)."""
    return MockControllerManagerService(
        num_controllers=4,
        death_schedule={2.0: 1, 3.0: 3},  # Team 1 dies (controllers 1, 3)
    )


@pytest.mark.asyncio
async def test_teams_game_full_lifecycle(mock_controller_manager_teams, mock_settings, event_collector):
    """
    Test full Teams game lifecycle:
    - Game starts
    - Players assigned to teams
    - Team colors set
    - Deaths tracked per team
    - Winning team determined
    """
    initial_players = [
        game_coordinator_pb2.Player(serial=c.serial, team=i % 2, alive=True, score=0)
        for i, c in enumerate(mock_controller_manager_teams.controllers)
    ]

    game = teams.TeamsGame(
        controller_manager_client=mock_controller_manager_teams,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_teams_1",
        num_teams=2,
        initial_players=initial_players,
    )

    await game.run()

    assert game.state == teams.GameState.ENDED
    assert event_collector.count_events_of_type("game_starting") == 1
    assert event_collector.count_events_of_type("teams_assigned") == 1
    assert event_collector.count_events_of_type("countdown_start") == 1
    assert event_collector.count_events_of_type("game_started") == 1

    teams_events = event_collector.get_events_of_type("teams_assigned")
    assert len(teams_events) == 1
    assert teams_events[0]["num_teams"] == 2

    death_events = event_collector.get_events_of_type("player_death")
    assert len(death_events) == 2

    winner_events = event_collector.get_events_of_type("team_winner")
    assert len(winner_events) == 1
    assert winner_events[0]["team"] == 0
    assert winner_events[0]["winner_count"] == 2

    assert event_collector.count_events_of_type("game_ended") == 1


@pytest.mark.asyncio
async def test_teams_game_with_three_teams(mock_settings, event_collector):
    """Test Teams game with 3 teams and 6 players."""
    mock_cm = MockControllerManagerService(
        num_controllers=6,
        death_schedule={1.5: 1, 2.0: 4},  # Kill controllers 1 and 4
    )

    game = teams.TeamsGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_teams_2",
        num_teams=3,
    )

    await game.run()

    assert game.state == teams.GameState.ENDED

    death_events = event_collector.get_events_of_type("player_death")
    assert len(death_events) == 2


@pytest.mark.asyncio
async def test_teams_game_settings_loaded(mock_controller_manager_teams, mock_settings, event_collector):
    """Test that game loads settings from Settings service."""
    mock_settings.settings["sensitivity"] = "FAST"
    mock_settings.settings["play_audio"] = "true"

    game = teams.TeamsGame(
        controller_manager_client=mock_controller_manager_teams,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_teams_3",
        num_teams=2,
    )

    await game._load_settings()

    assert game.sensitivity == teams.Sensitivity.FAST
    assert game.play_audio is True


@pytest.mark.asyncio
async def test_teams_game_force_end(mock_settings, event_collector):
    """Test that force_end() stops the Teams game."""
    mock_cm = MockControllerManagerService(
        num_controllers=4,
        death_schedule={},
        infinite=True,
    )

    game = teams.TeamsGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_teams_4",
        num_teams=2,
    )

    game_task = asyncio.create_task(game.run())

    await asyncio.sleep(0.5)
    game.force_end()

    try:
        await asyncio.wait_for(game_task, timeout=2.0)
    except TimeoutError:
        pytest.fail("Game did not end after force_end() was called")

    assert game.running is False
