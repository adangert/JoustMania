"""
Unit tests for Random Teams game mode.

Tests the core Random Teams mechanics:
- Random team assignment
- Random team color generation
- Win condition detection (last team standing)
- Team elimination detection
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

from services.game_coordinator.games.random_teams import RandomTeamsGame


class MockGameplayStream:
    """Minimal mock for gameplay stream writes."""

    async def write(self, message):
        """Accept writes silently."""
        pass


class TestRandomTeamsGameMode:
    """Test Random Teams game mechanics."""

    @pytest.fixture
    def random_teams_game(self):
        """Create a Random Teams game with 4 players."""
        mock_controller_manager = MockControllerManagerService(
            num_controllers=4,
            death_schedule={},
            max_duration=10.0,
        )
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = RandomTeamsGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_random_teams_001",
            num_teams=2,
        )

        return game, mock_controller_manager, event_collector

    @pytest.mark.asyncio
    async def test_players_assigned_to_valid_teams(self, random_teams_game):
        """Test that all players are assigned to valid teams (0 or 1)."""
        game, mock_controller_manager, _ = random_teams_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All players should be assigned to team 0 or 1
        for serial, player in game.players.items():
            assert player.team in [0, 1], f"Player {serial} has invalid team {player.team}"

    @pytest.mark.asyncio
    async def test_all_players_alive_initially(self, random_teams_game):
        """Test that all players start alive."""
        game, mock_controller_manager, _ = random_teams_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for _serial, player in game.players.items():
            assert player.alive is True

    @pytest.mark.asyncio
    async def test_random_team_colors_generated(self, random_teams_game):
        """Test that random team colors are generated."""
        game, mock_controller_manager, _ = random_teams_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Should have 2 team colors
        assert len(game.team_colors) == 2

        # Each color should have name and rgb
        for color in game.team_colors:
            assert "name" in color
            assert "rgb" in color
            assert len(color["rgb"]) == 3

    @pytest.mark.asyncio
    async def test_assign_random_teams_covers_all_players(self, random_teams_game):
        """Test that _assign_random_teams assigns all players."""
        game, mock_controller_manager, _ = random_teams_game

        serials = [c.serial for c in mock_controller_manager.controllers]
        assignments = game._assign_random_teams(serials)

        # All players should be assigned
        assert len(assignments) == len(serials)
        for serial in serials:
            assert serial in assignments

    @pytest.mark.asyncio
    async def test_assign_random_teams_distributes_evenly(self, random_teams_game):
        """Test that teams are relatively evenly distributed."""
        game, mock_controller_manager, _ = random_teams_game

        serials = [c.serial for c in mock_controller_manager.controllers]

        # Run multiple times to verify randomness produces valid distributions
        for _ in range(10):
            assignments = game._assign_random_teams(serials)

            # Count players per team
            team_counts = {0: 0, 1: 0}
            for team in assignments.values():
                team_counts[team] += 1

            # With 4 players and 2 teams, each team should have 1-3 players
            # (perfect distribution is 2-2, but randomness allows 1-3)
            assert team_counts[0] >= 1
            assert team_counts[1] >= 1
            assert team_counts[0] <= 3
            assert team_counts[1] <= 3

    @pytest.mark.asyncio
    async def test_win_condition_one_team_remaining(self, random_teams_game):
        """Test that win condition triggers when one team remains."""
        game, mock_controller_manager, _ = random_teams_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Both teams alive initially - no winner
        assert not game._check_win_condition()

        # Kill all players on team 0
        for _serial, player in game.players.items():
            if player.team == 0:
                player.alive = False

        # Now check - if any team 1 players exist, team 1 wins
        alive_teams = game._get_alive_teams()
        if len(alive_teams) == 1:
            assert game._check_win_condition()

    @pytest.mark.asyncio
    async def test_get_alive_teams(self, random_teams_game):
        """Test _get_alive_teams returns correct teams."""
        game, mock_controller_manager, _ = random_teams_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initially should have 1-2 teams (depending on random assignment)
        teams = game._get_alive_teams()
        assert len(teams) >= 1
        assert len(teams) <= 2

        # Kill all players
        for player in game.players.values():
            player.alive = False

        # No teams should be alive
        teams = game._get_alive_teams()
        assert len(teams) == 0

    @pytest.mark.asyncio
    async def test_kill_player_marks_dead(self, random_teams_game):
        """Test that _kill_player_impl marks player as dead."""
        game, mock_controller_manager, _ = random_teams_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get first player
        serial = list(game.players.keys())[0]
        player = game.players[serial]
        assert player.alive is True

        # Kill the player
        await game._kill_player_impl(serial, accel_mag=5.0)

        assert player.alive is False

    @pytest.mark.asyncio
    async def test_players_get_team_colors(self, random_teams_game):
        """Test that players are assigned their team's color."""
        game, mock_controller_manager, _ = random_teams_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Each player's color should match their team's color
        for serial, player in game.players.items():
            expected_color = game.team_colors[player.team]["rgb"]
            assert player.color == expected_color, f"Player {serial} has wrong color"
