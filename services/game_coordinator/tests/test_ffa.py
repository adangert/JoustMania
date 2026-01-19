"""
Integration tests for FFA game mode with mock gRPC services.

Tests the full FFA game flow using mocked ControllerManager and Settings services,
verifying game logic, event publishing, and win conditions without real hardware.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from .conftest import MockControllerManagerService

# Import FFA game module
service_dir = Path(__file__).parent.parent
games_dir = service_dir / "games"

spec = importlib.util.spec_from_file_location("ffa", games_dir / "ffa.py")
ffa = importlib.util.module_from_spec(spec)
sys.modules["ffa"] = ffa
spec.loader.exec_module(ffa)

# Import game_coordinator_pb2 for Player message
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))
from proto import game_coordinator_pb2  # noqa: E402


@pytest.mark.asyncio
async def test_ffa_game_full_lifecycle(mock_controller_manager, mock_settings, event_collector):
    """
    Test full FFA game lifecycle:
    - Game starts
    - Players initialized
    - Countdown runs
    - Game loop processes controller states
    - Players die when accelerating too much
    - Winner determined
    - Game ends
    """
    initial_players = [
        game_coordinator_pb2.Player(serial=c.serial, team=0, alive=True, score=0)
        for c in mock_controller_manager.controllers
    ]

    game = ffa.FFAGame(
        controller_manager_client=mock_controller_manager,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_1",
        initial_players=initial_players,
    )

    await game.run()

    assert game.state == ffa.GameState.ENDED
    assert event_collector.count_events_of_type("game_starting") == 1
    assert event_collector.count_events_of_type("players_initialized") == 1
    assert event_collector.count_events_of_type("countdown_start") == 1
    assert event_collector.count_events_of_type("countdown_end") == 1
    assert event_collector.count_events_of_type("game_started") == 1

    players_init_events = event_collector.get_events_of_type("players_initialized")
    assert len(players_init_events) == 1
    assert players_init_events[0]["player_count"] == 3

    death_events = event_collector.get_events_of_type("player_death")
    assert len(death_events) == 2, f"Expected 2 deaths, got {len(death_events)}"

    winner_events = event_collector.get_events_of_type("game_winner")
    assert len(winner_events) == 1, f"Expected 1 winner, got {len(winner_events)}"
    assert winner_events[0]["serial"] == "mock_controller_0"

    assert event_collector.count_events_of_type("game_ended") == 1


@pytest.mark.asyncio
async def test_ffa_game_with_two_players(mock_settings, event_collector):
    """Test FFA game with minimum 2 players."""
    mock_cm = MockControllerManagerService(
        num_controllers=2,
        death_schedule={0.1: 1},  # Controller 1 dies quickly
    )

    game = ffa.FFAGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_2",
    )

    await game.run()

    assert game.state == ffa.GameState.ENDED

    death_events = event_collector.get_events_of_type("player_death")
    assert len(death_events) == 1

    winner_events = event_collector.get_events_of_type("game_winner")
    assert len(winner_events) == 1
    assert winner_events[0]["serial"] == "mock_controller_0"


@pytest.mark.asyncio
async def test_ffa_game_settings_loaded(mock_controller_manager, mock_settings, event_collector):
    """Test that game loads settings from Settings service."""
    mock_settings.settings["sensitivity"] = "FAST"
    mock_settings.settings["play_audio"] = "true"

    game = ffa.FFAGame(
        controller_manager_client=mock_controller_manager,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_3",
    )

    await game._load_settings()

    assert game.sensitivity == ffa.Sensitivity.FAST
    assert game.play_audio is True


@pytest.mark.asyncio
async def test_ffa_game_force_end(mock_settings, event_collector):
    """Test that force_end() stops the game."""
    mock_cm = MockControllerManagerService(
        num_controllers=3,
        death_schedule={},
        infinite=True,
    )

    game = ffa.FFAGame(
        controller_manager_client=mock_cm,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_4",
    )

    game_task = asyncio.create_task(game.run())

    await asyncio.sleep(0.5)
    game.force_end()

    try:
        await asyncio.wait_for(game_task, timeout=2.0)
    except TimeoutError:
        pytest.fail("Game did not end after force_end() was called")

    assert game.running is False
