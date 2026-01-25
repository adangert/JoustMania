"""
Unit tests for Nonstop Joust game mode.

Tests the core Nonstop mechanics:
- Player scoring (kills, deaths, score, streaks)
- Respawn mechanics
- Spawn protection
- Time-based win condition
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

from services.game_coordinator.games.nonstop_joust import (  # noqa: E402
    RESPAWN_DURATION,
    NonstopJoustGame,
    NonstopPlayer,
)


class MockGameplayStream:
    """Minimal mock for gameplay stream writes."""

    async def write(self, message):
        """Accept writes silently."""
        pass


class TestNonstopJoustGameMode:
    """Test Nonstop Joust game mechanics."""

    @pytest.fixture
    def nonstop_game(self):
        """Create a Nonstop Joust game with 4 players."""
        mock_controller_manager = MockControllerManagerService(
            num_controllers=4,
            death_schedule={},
            max_duration=10.0,
        )
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = NonstopJoustGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_nonstop_001",
        )

        return game, mock_controller_manager, event_collector

    @pytest.mark.asyncio
    async def test_player_initialization(self, nonstop_game):
        """Test that players are initialized correctly."""
        game, mock_controller_manager, _ = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All 4 players should be created
        assert len(game.players) == 4

    @pytest.mark.asyncio
    async def test_players_start_with_zero_scores(self, nonstop_game):
        """Test that all players start with zero scores."""
        game, mock_controller_manager, _ = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for _serial, player in game.players.items():
            assert player.kills == 0
            assert player.deaths == 0
            assert player.score == 0
            assert player.current_streak == 0
            assert player.best_streak == 0

    @pytest.mark.asyncio
    async def test_kill_player_increments_deaths(self, nonstop_game):
        """Test that _kill_player_impl increments death count."""
        game, mock_controller_manager, _ = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        serial = list(game.players.keys())[0]
        player = game.players[serial]

        assert player.deaths == 0

        # Kill player
        await game._kill_player_impl(serial, accel_mag=5.0)

        assert player.deaths == 1

    @pytest.mark.asyncio
    async def test_kill_player_resets_streak(self, nonstop_game):
        """Test that _kill_player_impl resets current streak."""
        game, mock_controller_manager, _ = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        serial = list(game.players.keys())[0]
        player = game.players[serial]

        # Set a streak
        player.current_streak = 5

        # Kill player - streak should reset
        await game._kill_player_impl(serial, accel_mag=5.0)

        assert player.current_streak == 0

    @pytest.mark.asyncio
    async def test_kill_player_sets_respawn_timer(self, nonstop_game):
        """Test that _kill_player_impl sets respawn timer."""
        game, mock_controller_manager, _ = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        serial = list(game.players.keys())[0]
        player = game.players[serial]

        # Kill player
        await game._kill_player_impl(serial, accel_mag=5.0)

        assert player.respawn_timer == RESPAWN_DURATION

    @pytest.mark.asyncio
    async def test_kill_player_marks_dead(self, nonstop_game):
        """Test that _kill_player_impl marks player as dead."""
        game, mock_controller_manager, _ = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        serial = list(game.players.keys())[0]
        player = game.players[serial]
        assert player.alive is True

        # Kill player
        await game._kill_player_impl(serial, accel_mag=5.0)

        assert player.alive is False

    @pytest.mark.asyncio
    async def test_kill_player_publishes_event(self, nonstop_game):
        """Test that _kill_player_impl publishes death event."""
        game, mock_controller_manager, event_collector = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        serial = list(game.players.keys())[0]

        # Kill player
        await game._kill_player_impl(serial, accel_mag=5.0)

        # Verify death event
        death_events = event_collector.get_events_of_type("player_death")
        assert len(death_events) == 1
        assert death_events[0]["serial"] == serial

    @pytest.mark.asyncio
    async def test_check_win_condition_unlimited_mode(self, nonstop_game):
        """Test that win condition is false in unlimited mode."""
        game, mock_controller_manager, _ = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Unlimited mode (time_limit = 0)
        game.time_limit = 0

        # Should never end
        assert not game._check_win_condition()

    @pytest.mark.asyncio
    async def test_check_win_condition_time_not_expired(self, nonstop_game):
        """Test that win condition is false when time hasn't expired."""
        game, mock_controller_manager, _ = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Set time limit
        game.time_limit = 60
        game.start_time = time.time()  # Just started

        # Time hasn't expired
        assert not game._check_win_condition()

    @pytest.mark.asyncio
    async def test_check_win_condition_time_expired(self, nonstop_game):
        """Test that win condition triggers when time expires."""
        game, mock_controller_manager, _ = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Set time limit and pretend it expired
        game.time_limit = 60
        game.start_time = time.time() - 70  # 70 seconds ago

        # Time expired
        assert game._check_win_condition()

    @pytest.mark.asyncio
    async def test_nonstop_player_dataclass(self, nonstop_game):
        """Test NonstopPlayer dataclass attributes."""
        game, mock_controller_manager, _ = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All players should be NonstopPlayer instances
        for _serial, player in game.players.items():
            assert isinstance(player, NonstopPlayer)
            assert hasattr(player, "kills")
            assert hasattr(player, "deaths")
            assert hasattr(player, "score")
            assert hasattr(player, "current_streak")
            assert hasattr(player, "best_streak")
            assert hasattr(player, "respawn_timer")
            assert hasattr(player, "spawn_protected")
            assert hasattr(player, "spawn_protection_end")

    @pytest.mark.asyncio
    async def test_multiple_deaths_accumulate(self, nonstop_game):
        """Test that multiple deaths accumulate."""
        game, mock_controller_manager, _ = nonstop_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        serial = list(game.players.keys())[0]
        player = game.players[serial]

        # Die multiple times
        for _ in range(3):
            player.alive = True  # Reset for respawn
            await game._kill_player_impl(serial, accel_mag=5.0)

        assert player.deaths == 3
