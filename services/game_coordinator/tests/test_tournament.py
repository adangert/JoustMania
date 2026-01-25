"""
Unit tests for Tournament game mode.

Tests the core Tournament mechanics:
- Bracket generation
- Player states (WAITING, FIGHTING, ELIMINATED, CHAMPION)
- Match handling
- Win condition (last player standing)
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

from conftest import EventCollector, MockControllerManagerService, MockSettingsService  # noqa: E402

from services.game_coordinator.games.tournament import (  # noqa: E402
    Match,
    TournamentGame,
    TournamentPlayer,
    TournamentState,
)


class MockGameplayStream:
    """Minimal mock for gameplay stream writes."""

    async def write(self, message):
        """Accept writes silently."""
        pass


class TestTournamentGameMode:
    """Test Tournament game mechanics."""

    @pytest.fixture
    def tournament_game(self):
        """Create a Tournament game with 4 players."""
        mock_controller_manager = MockControllerManagerService(
            num_controllers=4,
            death_schedule={},
            max_duration=10.0,
        )
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = TournamentGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_tournament_001",
        )

        return game, mock_controller_manager, event_collector

    @pytest.mark.asyncio
    async def test_player_initialization(self, tournament_game):
        """Test that players are initialized correctly."""
        game, mock_controller_manager, _ = tournament_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All 4 players should be created
        assert len(game.players) == 4

    @pytest.mark.asyncio
    async def test_players_start_waiting(self, tournament_game):
        """Test that all players start in WAITING state."""
        game, mock_controller_manager, _ = tournament_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for _serial, player in game.players.items():
            assert player.tournament_state == TournamentState.WAITING
            assert player.wins == 0

    def test_generate_bracket_4_players(self, tournament_game):
        """Test bracket generation for 4 players (power of 2)."""
        game, _, _ = tournament_game

        bracket = game._generate_bracket(4)

        # 4 players = 2 rounds = 3 matches (2 first round + 1 final)
        # First round: 2 matches
        # Final: 1 match
        assert len(bracket) >= 2  # At least first round matches
        assert game.total_rounds == 2  # log2(4) = 2 rounds

    def test_generate_bracket_3_players(self, tournament_game):
        """Test bracket generation for 3 players (needs bye)."""
        game, _, _ = tournament_game

        bracket = game._generate_bracket(3)

        # 3 players rounds up to 4 slots
        # One player gets a bye
        has_bye = any(m.is_bye for m in bracket)
        assert has_bye or game.total_rounds == 2

    def test_generate_bracket_empty(self, tournament_game):
        """Test bracket generation with no players."""
        game, _, _ = tournament_game

        bracket = game._generate_bracket(0)
        assert bracket == []

        bracket = game._generate_bracket(1)
        assert bracket == []

    @pytest.mark.asyncio
    async def test_check_win_condition_all_active(self, tournament_game):
        """Test that win condition is false when multiple players active."""
        game, mock_controller_manager, _ = tournament_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All players active - no win
        assert not game._check_win_condition()

    @pytest.mark.asyncio
    async def test_check_win_condition_one_remaining(self, tournament_game):
        """Test that win condition triggers when one player remains."""
        game, mock_controller_manager, event_collector = tournament_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Eliminate 3 players
        serials = list(game.players.keys())
        for serial in serials[:-1]:  # All but last
            game.players[serial].tournament_state = TournamentState.ELIMINATED

        # Should have winner
        assert game._check_win_condition()

        # Last player should be champion
        last_serial = serials[-1]
        assert game.players[last_serial].tournament_state == TournamentState.CHAMPION

        # Verify event
        champion_events = event_collector.get_events_of_type("tournament_champion")
        assert len(champion_events) == 1

    @pytest.mark.asyncio
    async def test_tournament_player_dataclass(self, tournament_game):
        """Test TournamentPlayer dataclass attributes."""
        game, mock_controller_manager, _ = tournament_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All players should be TournamentPlayer instances
        for _serial, player in game.players.items():
            assert isinstance(player, TournamentPlayer)
            assert hasattr(player, "tournament_state")
            assert hasattr(player, "bracket_position")
            assert hasattr(player, "round_number")
            assert hasattr(player, "wins")
            assert hasattr(player, "invincible_until")

    def test_match_dataclass(self, tournament_game):
        """Test Match dataclass attributes."""
        match = Match(
            match_id=1,
            round_number=1,
            player1_serial="player1",
            player2_serial="player2",
        )

        assert match.match_id == 1
        assert match.round_number == 1
        assert match.player1_serial == "player1"
        assert match.player2_serial == "player2"
        assert match.winner_serial is None
        assert match.is_complete is False
        assert match.is_bye is False

    @pytest.mark.asyncio
    async def test_kill_player_not_in_match_ignored(self, tournament_game):
        """Test that kills are ignored if player not in FIGHTING state."""
        game, mock_controller_manager, _ = tournament_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        serial = list(game.players.keys())[0]
        player = game.players[serial]

        # Player is in WAITING state
        assert player.tournament_state == TournamentState.WAITING

        # Kill should be ignored
        await game._kill_player_impl(serial, accel_mag=5.0)

        # Player state should be unchanged
        assert player.tournament_state == TournamentState.WAITING
