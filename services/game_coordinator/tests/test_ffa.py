"""
Unit tests for FFA (Free For All) game mode.

Tests the core FFA mechanics:
- Player initialization with unique colors
- Player death handling
- Win condition detection (last player standing)
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

from services.game_coordinator.games.ffa import FFAGame  # noqa: E402


class MockGameplayStream:
    """Minimal mock for gameplay stream writes."""

    async def write(self, message):
        """Accept writes silently."""
        pass


class TestFFAGameMode:
    """Test FFA game mechanics."""

    @pytest.fixture
    def ffa_game(self):
        """Create an FFA game with 4 players."""
        mock_controller_manager = MockControllerManagerService(
            num_controllers=4,
            death_schedule={},
            max_duration=10.0,
        )
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = FFAGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_ffa_001",
        )

        return game, mock_controller_manager, event_collector

    @pytest.mark.asyncio
    async def test_player_initialization(self, ffa_game):
        """Test that players are initialized correctly."""
        game, mock_controller_manager, _ = ffa_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Verify all players created
        assert len(game.players) == 4

        # Verify all players are alive
        for _serial, player in game.players.items():
            assert player.alive is True
            assert player.team == 0  # FFA: all players on team 0

    @pytest.mark.asyncio
    async def test_kill_player_marks_dead(self, ffa_game):
        """Test that _kill_player_impl marks player as dead."""
        game, mock_controller_manager, event_collector = ffa_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        player = game.players["mock_controller_0"]
        assert player.alive is True

        # Kill the player
        await game._kill_player_impl("mock_controller_0", accel_mag=5.0)

        # Verify player is dead
        assert player.alive is False

    @pytest.mark.asyncio
    async def test_win_condition_last_player(self, ffa_game):
        """Test that win condition triggers when one player remains."""
        game, mock_controller_manager, _ = ffa_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All alive - no winner
        assert not game._check_win_condition()

        # Kill 3 players, leaving 1
        for serial in ["mock_controller_0", "mock_controller_1", "mock_controller_2"]:
            game.players[serial].alive = False

        # Now should have winner
        assert game._check_win_condition()

    @pytest.mark.asyncio
    async def test_win_condition_two_alive(self, ffa_game):
        """Test that win condition does NOT trigger with 2+ players alive."""
        game, mock_controller_manager, _ = ffa_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Kill 2 players, leaving 2
        game.players["mock_controller_0"].alive = False
        game.players["mock_controller_1"].alive = False

        # Should NOT have winner yet
        assert not game._check_win_condition()

    @pytest.mark.asyncio
    async def test_get_alive_count(self, ffa_game):
        """Test counting alive players."""
        game, mock_controller_manager, _ = ffa_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All 4 alive initially
        alive = [p for p in game.players.values() if p.alive]
        assert len(alive) == 4

        # Kill one
        game.players["mock_controller_0"].alive = False
        alive = [p for p in game.players.values() if p.alive]
        assert len(alive) == 3

    @pytest.mark.asyncio
    async def test_dead_player_excluded_from_alive(self, ffa_game):
        """Test that dead players are properly excluded."""
        game, mock_controller_manager, _ = ffa_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Kill player
        await game._kill_player_impl("mock_controller_0", accel_mag=5.0)

        # Get alive serials
        alive_serials = [s for s, p in game.players.items() if p.alive]

        assert "mock_controller_0" not in alive_serials
        assert len(alive_serials) == 3
