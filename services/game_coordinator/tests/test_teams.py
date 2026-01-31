"""
Unit tests for Teams game mode.

Tests the core Teams mechanics:
- Round-robin team assignment
- Player death handling
- Team elimination detection
- Win condition (last team standing)
"""

import sys
from pathlib import Path

import pytest

# Setup paths for imports
test_dir = Path(__file__).parent
service_dir = test_dir.parent
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(test_dir))

from conftest import EventCollector, MockControllerManagerService, MockSettingsService

from services.game_coordinator.games.teams import SimpleTeamsGame


class MockGameplayStream:
    """Minimal mock for gameplay stream writes."""

    async def write(self, message):
        """Accept writes silently."""
        pass


class TestTeamsGameMode:
    """Test Teams game mechanics."""

    @pytest.fixture
    def teams_game(self):
        """Create a Teams game with 4 players (2 per team)."""
        mock_controller_manager = MockControllerManagerService(
            num_controllers=4,
            death_schedule={},
            max_duration=10.0,
        )
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = SimpleTeamsGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_teams_001",
            num_teams=2,
        )

        return game, mock_controller_manager, event_collector

    @pytest.mark.asyncio
    async def test_player_initialization_round_robin(self, teams_game):
        """Test that players are assigned to teams round-robin (0, 1, 0, 1)."""
        game, mock_controller_manager, _ = teams_game

        # Disable random teams for deterministic assignment
        game.random_teams = False

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Verify round-robin assignment: 0, 1, 0, 1
        assert game.players["mock_controller_0"].team == 0
        assert game.players["mock_controller_1"].team == 1
        assert game.players["mock_controller_2"].team == 0
        assert game.players["mock_controller_3"].team == 1

    @pytest.mark.asyncio
    async def test_all_players_alive_initially(self, teams_game):
        """Test that all players start alive."""
        game, mock_controller_manager, _ = teams_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for _serial, player in game.players.items():
            assert player.alive is True

    @pytest.mark.asyncio
    async def test_kill_player_marks_dead(self, teams_game):
        """Test that _kill_player_impl marks player as dead."""
        game, mock_controller_manager, _ = teams_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        player = game.players["mock_controller_0"]
        assert player.alive is True

        # Kill the player
        await game._kill_player_impl("mock_controller_0", accel_mag=5.0)

        assert player.alive is False

    @pytest.mark.asyncio
    async def test_get_alive_teams(self, teams_game):
        """Test _get_alive_teams returns correct teams."""
        game, mock_controller_manager, _ = teams_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initial: both teams have players
        teams = game._get_alive_teams()
        assert teams == {0, 1}

        # Kill all players on team 0
        game.players["mock_controller_0"].alive = False
        game.players["mock_controller_2"].alive = False

        teams = game._get_alive_teams()
        assert teams == {1}

    @pytest.mark.asyncio
    async def test_win_condition_one_team_remaining(self, teams_game):
        """Test that win condition triggers when one team remains."""
        game, mock_controller_manager, _ = teams_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Both teams alive - no winner
        assert not game._check_win_condition()

        # Kill all players on team 1
        game.players["mock_controller_1"].alive = False
        game.players["mock_controller_3"].alive = False

        # Now team 0 wins
        assert game._check_win_condition()

    @pytest.mark.asyncio
    async def test_win_condition_both_teams_alive(self, teams_game):
        """Test that win condition does NOT trigger with both teams alive."""
        game, mock_controller_manager, _ = teams_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Kill one player from each team
        game.players["mock_controller_0"].alive = False  # Team 0
        game.players["mock_controller_1"].alive = False  # Team 1

        # Still both teams alive - no winner
        assert not game._check_win_condition()

    @pytest.mark.asyncio
    async def test_team_eliminated_detection(self, teams_game):
        """Test that team elimination is detected correctly."""
        game, mock_controller_manager, _ = teams_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initially team 1 has players 1 and 3
        teams = game._get_alive_teams()
        assert 1 in teams

        # Kill player 1 (team 1 still has player 3)
        game.players["mock_controller_1"].alive = False
        teams = game._get_alive_teams()
        assert 1 in teams

        # Kill player 3 (team 1 now eliminated)
        game.players["mock_controller_3"].alive = False
        teams = game._get_alive_teams()
        assert 1 not in teams

    @pytest.mark.asyncio
    async def test_team_winner_event_published(self, teams_game):
        """Test that team_winner event is published when team wins."""
        game, mock_controller_manager, event_collector = teams_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Kill all team 1 players
        game.players["mock_controller_1"].alive = False
        game.players["mock_controller_3"].alive = False

        # Check win condition (should publish event)
        assert game._check_win_condition()

        # Verify team_winner event
        winner_events = event_collector.get_events_of_type("team_winner")
        assert len(winner_events) == 1
        assert winner_events[0]["team"] == 0

    @pytest.mark.asyncio
    async def test_count_alive_players(self, teams_game):
        """Test counting alive players per team."""
        game, mock_controller_manager, _ = teams_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Count alive players per team
        def count_alive_per_team(team_num):
            return len([p for p in game.players.values() if p.alive and p.team == team_num])

        # Initially 2 players per team
        assert count_alive_per_team(0) == 2
        assert count_alive_per_team(1) == 2

        # Kill one from team 0
        game.players["mock_controller_0"].alive = False
        assert count_alive_per_team(0) == 1
        assert count_alive_per_team(1) == 2
