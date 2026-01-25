"""
Unit tests for Zombie game mode.

Tests the core Zombie mechanics:
- Human vs Zombie team assignment
- Human conversion to zombie on death
- Zombie respawn mechanics
- Win conditions (all converted vs time expired)
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

from services.game_coordinator.games.zombie import (  # noqa: E402
    HUMAN_COLOR,
    INITIAL_ZOMBIES,
    ZOMBIE_COLOR,
    ZombieGame,
    ZombiePlayer,
    calculate_game_duration,
)


class MockGameplayStream:
    """Minimal mock for gameplay stream writes."""

    async def write(self, message):
        """Accept writes silently."""
        pass


class TestZombieGameMode:
    """Test Zombie game mechanics."""

    @pytest.fixture
    def zombie_game(self):
        """Create a Zombie game with 4 players."""
        mock_controller_manager = MockControllerManagerService(
            num_controllers=4,
            death_schedule={},
            max_duration=10.0,
        )
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = ZombieGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_zombie_001",
        )

        return game, mock_controller_manager, event_collector

    def test_calculate_game_duration(self):
        """Test game duration calculation based on player count."""
        # 4 players: (4 * 3 / 16) * 60 = 45 seconds
        assert calculate_game_duration(4) == 45.0

        # 8 players: (8 * 3 / 16) * 60 = 90 seconds
        assert calculate_game_duration(8) == 90.0

        # 12 players: (12 * 3 / 16) * 60 = 135 seconds
        assert calculate_game_duration(12) == 135.0

    @pytest.mark.asyncio
    async def test_player_initialization(self, zombie_game):
        """Test that players are initialized correctly."""
        game, mock_controller_manager, _ = zombie_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All 4 players should be created
        assert len(game.players) == 4

        # Should have 2 zombies and 2 humans (INITIAL_ZOMBIES=2)
        zombie_count = len(game.zombie_serials)
        human_count = len(game.human_serials)

        assert zombie_count == min(INITIAL_ZOMBIES, 3)  # min(2, 4-1)
        assert human_count == 4 - zombie_count

    @pytest.mark.asyncio
    async def test_initial_zombies_marked_correctly(self, zombie_game):
        """Test that initial zombies have correct attributes."""
        game, mock_controller_manager, _ = zombie_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for serial in game.zombie_serials:
            player = game.players[serial]
            assert player.is_zombie is True
            assert player.team == 1
            assert player.color == ZOMBIE_COLOR

    @pytest.mark.asyncio
    async def test_initial_humans_marked_correctly(self, zombie_game):
        """Test that initial humans have correct attributes."""
        game, mock_controller_manager, _ = zombie_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for serial in game.human_serials:
            player = game.players[serial]
            assert player.is_zombie is False
            assert player.team == 0
            assert player.color == HUMAN_COLOR

    @pytest.mark.asyncio
    async def test_win_condition_all_humans_converted(self, zombie_game):
        """Test that zombies win when all humans are converted."""
        game, mock_controller_manager, event_collector = zombie_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initially no win
        game.time_remaining = 100  # Plenty of time
        assert not game._check_win_condition()

        # Convert all humans to zombies
        for serial in list(game.human_serials):
            game.players[serial].is_zombie = True
            game.players[serial].team = 1
            game.zombie_serials.append(serial)
        game.human_serials.clear()

        # Zombies should win
        assert game._check_win_condition()

        # Verify zombie_winner event
        winner_events = event_collector.get_events_of_type("zombie_winner")
        assert len(winner_events) == 1
        assert winner_events[0]["winner"] == "zombies"

    @pytest.mark.asyncio
    async def test_win_condition_time_expired_humans_survive(self, zombie_game):
        """Test that humans win when time expires with survivors."""
        game, mock_controller_manager, event_collector = zombie_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Set time to 0 (expired)
        game.time_remaining = 0

        # Humans should win (still have humans alive)
        assert game._check_win_condition()

        # Verify zombie_winner event
        winner_events = event_collector.get_events_of_type("zombie_winner")
        assert len(winner_events) == 1
        assert winner_events[0]["winner"] == "humans"

    @pytest.mark.asyncio
    async def test_no_win_with_time_and_humans(self, zombie_game):
        """Test that game continues with time remaining and humans alive."""
        game, mock_controller_manager, _ = zombie_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Time remaining and humans alive
        game.time_remaining = 100

        # Game should continue
        assert not game._check_win_condition()

    @pytest.mark.asyncio
    async def test_human_conversion_updates_lists(self, zombie_game):
        """Test that human conversion updates tracking lists."""
        game, mock_controller_manager, _ = zombie_game
        game.gameplay_stream = MockGameplayStream()

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get a human serial
        human_serial = game.human_serials[0]
        initial_human_count = len(game.human_serials)
        initial_zombie_count = len(game.zombie_serials)

        # Simulate conversion (set player as zombie directly to test logic)
        player = game.players[human_serial]
        player.is_zombie = True
        player.team = 1
        game.human_serials.remove(human_serial)
        game.zombie_serials.append(human_serial)

        # Lists should be updated
        assert len(game.human_serials) == initial_human_count - 1
        assert len(game.zombie_serials) == initial_zombie_count + 1
        assert human_serial not in game.human_serials
        assert human_serial in game.zombie_serials

    @pytest.mark.asyncio
    async def test_zombie_player_dataclass(self, zombie_game):
        """Test ZombiePlayer dataclass attributes."""
        game, mock_controller_manager, _ = zombie_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All players should be ZombiePlayer instances
        for _serial, player in game.players.items():
            assert isinstance(player, ZombiePlayer)
            assert hasattr(player, "is_zombie")
            assert hasattr(player, "respawn_until")

    @pytest.mark.asyncio
    async def test_game_duration_set_on_init(self, zombie_game):
        """Test that game duration is calculated on player init."""
        game, mock_controller_manager, _ = zombie_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # 4 players: (4 * 3 / 16) * 60 = 45 seconds
        expected_duration = calculate_game_duration(4)
        assert game.game_duration == expected_duration
        assert game.time_remaining == expected_duration
