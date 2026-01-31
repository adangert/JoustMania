"""
Unit tests for Traitor game mode.

Tests the core Traitor mechanics:
- Traitor assignment based on player count
- Visible team vs secret team tracking
- Win condition based on secret teams
- Player death handling
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

from services.game_coordinator.games.traitor import TraitorGame, TraitorPlayer


class MockGameplayStream:
    """Minimal mock for gameplay stream writes."""

    async def write(self, message):
        """Accept writes silently."""
        pass


class TestTraitorGameMode:
    """Test Traitor game mechanics."""

    @pytest.fixture
    def traitor_game(self):
        """Create a Traitor game with 4 players."""
        mock_controller_manager = MockControllerManagerService(
            num_controllers=4,
            death_schedule={},
            max_duration=10.0,
        )
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = TraitorGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_traitor_001",
        )

        return game, mock_controller_manager, event_collector

    def test_get_traitor_count(self, traitor_game):
        """Test traitor count calculation based on player count."""
        game, _, _ = traitor_game

        # 4-5 players: 1 traitor
        assert game._get_traitor_count(4) == 1
        assert game._get_traitor_count(5) == 1

        # 6-8 players: 2 traitors
        assert game._get_traitor_count(6) == 2
        assert game._get_traitor_count(8) == 2

        # 9-11 players: 3 traitors
        assert game._get_traitor_count(9) == 3
        assert game._get_traitor_count(11) == 3

        # 12+ players: num_players // 3
        assert game._get_traitor_count(12) == 4
        assert game._get_traitor_count(15) == 5

    @pytest.mark.asyncio
    async def test_player_initialization(self, traitor_game):
        """Test that players are initialized correctly."""
        game, mock_controller_manager, _ = traitor_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All 4 players should be created
        assert len(game.players) == 4

        # Should have 1 traitor for 4 players
        assert len(game.traitor_serials) == 1

    @pytest.mark.asyncio
    async def test_traitor_has_different_secret_team(self, traitor_game):
        """Test that traitors have different secret team than visible team."""
        game, mock_controller_manager, _ = traitor_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for serial in game.traitor_serials:
            player = game.players[serial]
            assert player.is_traitor is True
            # Secret team should be different from visible team
            assert player.secret_team != player.team

    @pytest.mark.asyncio
    async def test_non_traitors_have_matching_teams(self, traitor_game):
        """Test that non-traitors have matching visible and secret teams."""
        game, mock_controller_manager, _ = traitor_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for serial, player in game.players.items():
            if serial not in game.traitor_serials:
                assert player.is_traitor is False
                assert player.secret_team == player.team

    @pytest.mark.asyncio
    async def test_get_alive_teams_uses_secret_team(self, traitor_game):
        """Test that _get_alive_teams returns secret teams, not visible teams."""
        game, mock_controller_manager, _ = traitor_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get alive teams (should be based on secret_team)
        alive_teams = game._get_alive_teams()

        # Should have both teams (0 and 1) alive
        assert 0 in alive_teams
        assert 1 in alive_teams

    @pytest.mark.asyncio
    async def test_win_condition_based_on_secret_teams(self, traitor_game):
        """Test that win condition uses secret teams."""
        game, mock_controller_manager, event_collector = traitor_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initially no win
        assert not game._check_win_condition()

        # Kill all players with secret_team == 1
        for _serial, player in game.players.items():
            if player.secret_team == 1:
                player.alive = False

        # Team 0 should win
        assert game._check_win_condition()

        # Verify winner event
        winner_events = event_collector.get_events_of_type("traitor_winner")
        assert len(winner_events) == 1
        assert winner_events[0]["team"] == 0

    @pytest.mark.asyncio
    async def test_traitor_wins_with_secret_team(self, traitor_game):
        """Test that traitors are counted with their secret team for win condition."""
        game, mock_controller_manager, event_collector = traitor_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get the traitor
        traitor_serial = game.traitor_serials[0]
        traitor = game.players[traitor_serial]
        traitor_secret_team = traitor.secret_team

        # Kill all players EXCEPT those with the traitor's secret team
        for _serial, player in game.players.items():
            if player.secret_team != traitor_secret_team:
                player.alive = False

        # Traitor's secret team wins
        assert game._check_win_condition()

        winner_events = event_collector.get_events_of_type("traitor_winner")
        assert len(winner_events) == 1
        assert winner_events[0]["team"] == traitor_secret_team

    @pytest.mark.asyncio
    async def test_kill_player_marks_dead(self, traitor_game):
        """Test that _kill_player_impl marks player as dead."""
        game, mock_controller_manager, _ = traitor_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get first player
        serial = list(game.players.keys())[0]
        player = game.players[serial]
        assert player.alive is True

        # Kill the player
        await game._kill_player_impl(serial, accel_mag=5.0)

        assert player.alive is False

    @pytest.mark.asyncio
    async def test_traitor_player_dataclass(self, traitor_game):
        """Test TraitorPlayer dataclass attributes."""
        game, mock_controller_manager, _ = traitor_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All players should be TraitorPlayer instances
        for _serial, player in game.players.items():
            assert isinstance(player, TraitorPlayer)
            assert hasattr(player, "is_traitor")
            assert hasattr(player, "secret_team")

    @pytest.mark.asyncio
    async def test_no_win_with_both_secret_teams_alive(self, traitor_game):
        """Test that game continues with both secret teams having alive players."""
        game, mock_controller_manager, _ = traitor_game
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All alive - no win
        assert not game._check_win_condition()

        # Kill one player, but keep both secret teams alive
        # Find players from each secret team
        team0_players = [s for s, p in game.players.items() if p.secret_team == 0]

        # Only kill if we have multiple players on each team
        if len(team0_players) > 1:
            game.players[team0_players[0]].alive = False

        # Still both teams alive - no win
        assert not game._check_win_condition()

    @pytest.mark.asyncio
    async def test_get_game_name(self, traitor_game):
        """Test get_game_name returns 'Traitor'."""
        game, _, _ = traitor_game
        assert game.get_game_name() == "Traitor"


class TestTraitorCount:
    """Tests for traitor count calculation."""

    @pytest.fixture
    def traitor_game(self):
        """Create a Traitor game."""
        mock_controller_manager = MockControllerManagerService(num_controllers=4)
        mock_settings = MockSettingsService()

        game = TraitorGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_traitor_count",
        )

        return game, mock_controller_manager

    def test_traitor_count_2_players(self, traitor_game):
        """Test traitor count for 2 players."""
        game, _ = traitor_game
        # 2-3 players: 1 traitor
        assert game._get_traitor_count(2) == 1
        assert game._get_traitor_count(3) == 1

    def test_traitor_count_scales_with_players(self, traitor_game):
        """Test traitor count scales appropriately."""
        game, _ = traitor_game

        # Verify count increases with players
        counts = [game._get_traitor_count(n) for n in range(4, 17)]

        # Each count should be >= previous count
        for i in range(1, len(counts)):
            assert counts[i] >= counts[i - 1]


class TestTraitorLargeGame:
    """Tests for larger player count games."""

    @pytest.mark.asyncio
    async def test_8_players_has_2_traitors(self):
        """Test 8 players has 2 traitors."""
        mock_controller_manager = MockControllerManagerService(num_controllers=8)
        mock_settings = MockSettingsService()

        game = TraitorGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_traitor_8",
        )
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        assert len(game.traitor_serials) == 2

    @pytest.mark.asyncio
    async def test_10_players_has_3_traitors(self):
        """Test 10 players has 3 traitors."""
        mock_controller_manager = MockControllerManagerService(num_controllers=10)
        mock_settings = MockSettingsService()

        game = TraitorGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_traitor_10",
        )
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        assert len(game.traitor_serials) == 3


class TestTraitorEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_all_dead_triggers_win_condition(self):
        """Test that all players dead triggers win condition."""
        mock_controller_manager = MockControllerManagerService(num_controllers=4)
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = TraitorGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_traitor_draw",
        )
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Kill all players
        for player in game.players.values():
            player.alive = False

        # Should trigger win (draw scenario - all dead)
        # Note: Traitor checks alive teams, if none alive, might return True
        result = game._check_win_condition()
        assert result is True  # Game ends when no alive teams

    @pytest.mark.asyncio
    async def test_traitors_distributed_across_visible_teams(self):
        """Test traitors can be on different visible teams."""
        mock_controller_manager = MockControllerManagerService(num_controllers=6)
        mock_settings = MockSettingsService()

        game = TraitorGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_traitor_dist",
        )
        game.random_teams = False

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # 6 players = 2 traitors
        assert len(game.traitor_serials) == 2

        # Get visible teams of traitors
        traitor_visible_teams = {game.players[s].team for s in game.traitor_serials}

        # Traitors exist and have visible teams assigned
        assert len(traitor_visible_teams) >= 1
