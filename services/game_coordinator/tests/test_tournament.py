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

    @pytest.mark.asyncio
    async def test_get_game_name(self, tournament_game):
        """Test get_game_name returns 'Tournament'."""
        game, _, _ = tournament_game
        assert game.get_game_name() == "Tournament"


class TestTournamentBracket:
    """Tests for tournament bracket generation."""

    @pytest.fixture
    def tournament_game(self):
        """Create a Tournament game."""
        mock_controller_manager = MockControllerManagerService(num_controllers=8)
        mock_settings = MockSettingsService()

        game = TournamentGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_tournament_bracket",
        )

        return game, mock_controller_manager

    def test_generate_bracket_8_players(self, tournament_game):
        """Test bracket generation for 8 players."""
        game, _ = tournament_game

        bracket = game._generate_bracket(8)

        # 8 players = 3 rounds = 7 matches (4 + 2 + 1)
        assert game.total_rounds == 3  # log2(8) = 3 rounds
        assert len(bracket) >= 4  # At least first round matches

    def test_generate_bracket_5_players_has_byes(self, tournament_game):
        """Test bracket generation for 5 players has byes."""
        game, _ = tournament_game

        bracket = game._generate_bracket(5)

        # 5 players rounds up to 8 slots (3 byes)
        # Check that there are bye matches
        bye_count = sum(1 for m in bracket if m.is_bye)
        assert bye_count == 3  # 8 - 5 = 3 byes

    def test_generate_bracket_6_players(self, tournament_game):
        """Test bracket generation for 6 players."""
        game, _ = tournament_game

        bracket = game._generate_bracket(6)

        # 6 players rounds up to 8 slots (2 byes)
        bye_count = sum(1 for m in bracket if m.is_bye)
        assert bye_count == 2  # 8 - 6 = 2 byes

    def test_generate_bracket_2_players(self, tournament_game):
        """Test bracket for minimum 2 players."""
        game, _ = tournament_game

        bracket = game._generate_bracket(2)

        # 2 players = 1 round = 1 match
        assert game.total_rounds == 1
        assert len(bracket) == 1


class TestTournamentMatch:
    """Tests for match mechanics."""

    def test_match_defaults(self):
        """Test Match default values."""
        match = Match(
            match_id=1,
            round_number=1,
            player1_serial="p1",
            player2_serial="p2",
        )

        assert match.winner_serial is None
        assert match.is_complete is False
        assert match.is_bye is False

    def test_match_with_bye(self):
        """Test Match with bye marker."""
        match = Match(
            match_id=2,
            round_number=1,
            player1_serial="p1",
            player2_serial=None,
            is_bye=True,
        )

        assert match.is_bye is True
        assert match.player2_serial is None


class TestTournamentWinCondition:
    """Tests for tournament win conditions."""

    @pytest.fixture
    def tournament_game(self):
        """Create a Tournament game."""
        mock_controller_manager = MockControllerManagerService(num_controllers=4)
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = TournamentGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_tournament_win",
        )

        return game, mock_controller_manager, event_collector

    @pytest.mark.asyncio
    async def test_no_win_all_waiting(self, tournament_game):
        """No winner when all players are in WAITING state."""
        game, mock_controller_manager, _ = tournament_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All waiting - no win
        assert not game._check_win_condition()

    @pytest.mark.asyncio
    async def test_no_win_multiple_non_eliminated(self, tournament_game):
        """No winner when multiple players are not eliminated."""
        game, mock_controller_manager, _ = tournament_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Set one to FIGHTING, one to WAITING, one to ELIMINATED
        serials = list(game.players.keys())
        game.players[serials[0]].tournament_state = TournamentState.FIGHTING
        game.players[serials[1]].tournament_state = TournamentState.WAITING
        game.players[serials[2]].tournament_state = TournamentState.ELIMINATED
        game.players[serials[3]].tournament_state = TournamentState.WAITING

        # Multiple non-eliminated - no win
        assert not game._check_win_condition()

    @pytest.mark.asyncio
    async def test_champion_receives_event(self, tournament_game):
        """Champion event includes player info."""
        game, mock_controller_manager, event_collector = tournament_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Eliminate all but one
        serials = list(game.players.keys())
        champion_serial = serials[-1]

        for serial in serials[:-1]:
            game.players[serial].tournament_state = TournamentState.ELIMINATED

        game._check_win_condition()

        champion_events = event_collector.get_events_of_type("tournament_champion")
        assert len(champion_events) == 1
        assert champion_events[0]["champion"] == champion_serial
