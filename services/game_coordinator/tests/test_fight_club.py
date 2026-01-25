"""
Unit tests for Fight Club game mode.

Tests the core Fight Club mechanics:
- Queue-based 1v1 matches
- Player state management (IN_LINE, DEFENDER, FIGHTER)
- Scoring system
- Invincibility period
- Win condition (highest score after minimum rounds)
"""

import sys
import time
from pathlib import Path

import pytest

# Setup paths for imports
test_dir = Path(__file__).parent
service_dir = test_dir.parent
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(test_dir))

from conftest import EventCollector, MockControllerManagerService, MockSettingsService  # noqa: E402

from services.game_coordinator.games.fight_club import (  # noqa: E402
    DEFENDER_COLOR,
    FIGHTER_COLOR,
    INVINCIBILITY_DURATION,
    MIN_ROUNDS,
    WAITING_COLOR,
    FightClubGame,
    FightState,
)


class MockGameplayStream:
    """Minimal mock for gameplay stream writes."""

    async def write(self, message):
        """Accept writes silently."""
        pass


class TestFightClubGameMode:
    """Test Fight Club game mechanics."""

    @pytest.fixture
    def fight_club_game(self):
        """Create a Fight Club game with 4 players."""
        mock_controller_manager = MockControllerManagerService(
            num_controllers=4,
            death_schedule={},
            max_duration=10.0,
        )
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = FightClubGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_fight_club_001",
        )

        return game, mock_controller_manager, event_collector

    @pytest.mark.asyncio
    async def test_player_initialization(self, fight_club_game):
        """Test that players are initialized in queue."""
        game, mock_controller_manager, _ = fight_club_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All 4 players should be created
        assert len(game.players) == 4

        # All players should be in queue
        assert len(game.queue) == 4

    @pytest.mark.asyncio
    async def test_players_start_in_line(self, fight_club_game):
        """Test that all players start in IN_LINE state."""
        game, mock_controller_manager, _ = fight_club_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for _serial, player in game.players.items():
            assert player.state == FightState.IN_LINE
            assert player.color == WAITING_COLOR
            assert player.score == 0

    @pytest.mark.asyncio
    async def test_start_round_sets_defender_and_fighter(self, fight_club_game):
        """Test that _start_round sets defender and fighter from queue."""
        game, mock_controller_manager, _ = fight_club_game
        # Don't set gameplay_stream to avoid proto bug with ColorUpdate
        game.gameplay_stream = None

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Start first round
        await game._start_round()

        # First player becomes defender, second becomes fighter
        assert game.current_defender == "mock_controller_0"
        assert game.current_fighter == "mock_controller_1"

        # They should have correct states
        defender = game.players[game.current_defender]
        fighter = game.players[game.current_fighter]

        assert defender.state == FightState.DEFENDER
        assert defender.color == DEFENDER_COLOR

        assert fighter.state == FightState.FIGHTER
        assert fighter.color == FIGHTER_COLOR

    @pytest.mark.asyncio
    async def test_queue_decreases_after_round_start(self, fight_club_game):
        """Test that queue shrinks as players enter fights."""
        game, mock_controller_manager, _ = fight_club_game
        # Don't set gameplay_stream to avoid proto bug with ColorUpdate
        game.gameplay_stream = None

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initially 4 in queue
        assert len(game.queue) == 4

        # Start round - 2 leave queue
        await game._start_round()

        assert len(game.queue) == 2

    @pytest.mark.asyncio
    async def test_invincibility_set_on_round_start(self, fight_club_game):
        """Test that players get invincibility when round starts."""
        game, mock_controller_manager, _ = fight_club_game
        # Don't set gameplay_stream to avoid proto bug with ColorUpdate
        game.gameplay_stream = None

        await game._initialize_players_impl(mock_controller_manager.controllers)

        time_before = time.time()
        await game._start_round()

        defender = game.players[game.current_defender]
        fighter = game.players[game.current_fighter]

        # Both should have invincibility for ~4 seconds
        assert defender.invincible_until > time_before + INVINCIBILITY_DURATION - 0.5
        assert fighter.invincible_until > time_before + INVINCIBILITY_DURATION - 0.5

    @pytest.mark.asyncio
    async def test_kill_player_during_invincibility_ignored(self, fight_club_game):
        """Test that kills during invincibility are ignored."""
        game, mock_controller_manager, _ = fight_club_game
        # Don't set gameplay_stream to avoid proto bug with ColorUpdate
        game.gameplay_stream = None

        await game._initialize_players_impl(mock_controller_manager.controllers)
        await game._start_round()

        defender = game.players[game.current_defender]
        initial_score = defender.score

        # Try to kill defender during invincibility (should be ignored)
        await game._kill_player_impl(game.current_defender, accel_mag=5.0)

        # Defender should still be in fight, not moved to queue
        assert game.current_defender is not None
        assert defender.state == FightState.DEFENDER
        assert defender.score == initial_score

    @pytest.mark.asyncio
    async def test_kill_player_after_invincibility(self, fight_club_game):
        """Test that kills after invincibility are processed."""
        game, mock_controller_manager, event_collector = fight_club_game
        # Don't set gameplay_stream to avoid proto bug with ColorUpdate
        game.gameplay_stream = None

        await game._initialize_players_impl(mock_controller_manager.controllers)
        await game._start_round()

        defender_serial = game.current_defender
        fighter_serial = game.current_fighter

        # Clear invincibility
        game.players[defender_serial].invincible_until = 0
        game.players[fighter_serial].invincible_until = 0

        # Kill defender - fighter wins
        await game._kill_player_impl(defender_serial, accel_mag=5.0)

        # Fighter becomes new defender with 1 point
        assert game.current_defender == fighter_serial
        assert game.players[fighter_serial].score == 1
        assert game.players[fighter_serial].state == FightState.DEFENDER

        # Old defender goes to back of queue
        assert defender_serial in game.queue
        assert game.players[defender_serial].state == FightState.IN_LINE

    @pytest.mark.asyncio
    async def test_defender_wins_stays_defender(self, fight_club_game):
        """Test that when defender wins, they stay as defender."""
        game, mock_controller_manager, _ = fight_club_game
        # Don't set gameplay_stream to avoid proto bug with ColorUpdate
        game.gameplay_stream = None

        await game._initialize_players_impl(mock_controller_manager.controllers)
        await game._start_round()

        defender_serial = game.current_defender
        fighter_serial = game.current_fighter

        # Clear invincibility
        game.players[defender_serial].invincible_until = 0
        game.players[fighter_serial].invincible_until = 0

        # Kill fighter - defender wins
        await game._kill_player_impl(fighter_serial, accel_mag=5.0)

        # Defender stays with 1 point
        assert game.current_defender == defender_serial
        assert game.players[defender_serial].score == 1

        # Fighter goes to back of queue
        assert fighter_serial in game.queue

    @pytest.mark.asyncio
    async def test_should_end_game_before_min_rounds(self, fight_club_game):
        """Test that game doesn't end before minimum rounds."""
        game, mock_controller_manager, _ = fight_club_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Even with clear leader, shouldn't end before MIN_ROUNDS
        game.round_number = MIN_ROUNDS - 1
        game.players["mock_controller_0"].score = 5
        game.players["mock_controller_1"].score = 0

        assert game._should_end_game() is False

    @pytest.mark.asyncio
    async def test_should_end_game_after_min_rounds_with_leader(self, fight_club_game):
        """Test that game ends after minimum rounds with clear leader."""
        game, mock_controller_manager, _ = fight_club_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Past MIN_ROUNDS with clear leader
        game.round_number = MIN_ROUNDS + 1
        game.players["mock_controller_0"].score = 5
        game.players["mock_controller_1"].score = 3

        assert game._should_end_game() is True

    @pytest.mark.asyncio
    async def test_should_not_end_game_when_tied(self, fight_club_game):
        """Test that game continues with tied scores (enables face-off)."""
        game, mock_controller_manager, _ = fight_club_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Past MIN_ROUNDS but tied
        game.round_number = MIN_ROUNDS + 1
        game.players["mock_controller_0"].score = 5
        game.players["mock_controller_1"].score = 5

        # Should enable face-off mode but not end
        assert game._should_end_game() is False
        assert game.face_off_mode is True

    @pytest.mark.asyncio
    async def test_check_win_condition(self, fight_club_game):
        """Test _check_win_condition returns game_over flag."""
        game, mock_controller_manager, _ = fight_club_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initially not over
        assert game._check_win_condition() is False

        # Set game over
        game.game_over = True
        assert game._check_win_condition() is True
