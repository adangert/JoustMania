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


class TestZombieKillMechanics:
    """Tests for zombie kill and conversion mechanics."""

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
            game_id="test_zombie_kill",
        )

        return game, mock_controller_manager, event_collector

    @pytest.mark.asyncio
    async def test_human_killed_becomes_zombie(self, zombie_game):
        """When a human is killed, they should become a zombie."""
        game, mock_controller_manager, event_collector = zombie_game
        game.gameplay_stream = MockGameplayStream()
        game.running = True

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get a human serial
        human_serial = game.human_serials[0]
        player = game.players[human_serial]

        assert player.is_zombie is False
        assert player.team == 0

        # Kill the human
        await game._kill_player_impl(human_serial, accel_mag=3.0)

        # Player should now be a zombie
        assert player.is_zombie is True
        assert player.team == 1
        assert player.color == ZOMBIE_COLOR
        assert player.alive is True  # Zombies stay alive after conversion

    @pytest.mark.asyncio
    async def test_human_conversion_publishes_event(self, zombie_game):
        """Human conversion should publish human_converted event."""
        game, mock_controller_manager, event_collector = zombie_game
        game.gameplay_stream = MockGameplayStream()
        game.running = True

        await game._initialize_players_impl(mock_controller_manager.controllers)

        human_serial = game.human_serials[0]
        initial_human_count = len(game.human_serials)

        await game._kill_player_impl(human_serial, accel_mag=3.0)

        # Check event was published
        conversion_events = event_collector.get_events_of_type("human_converted")
        assert len(conversion_events) == 1
        assert conversion_events[0]["serial"] == human_serial
        assert conversion_events[0]["remaining_humans"] == initial_human_count - 1

    @pytest.mark.asyncio
    async def test_zombie_killed_sets_respawn(self, zombie_game):
        """When a zombie is killed, they should be set to respawn."""
        game, mock_controller_manager, _ = zombie_game
        game.gameplay_stream = MockGameplayStream()
        game.running = True

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get a zombie serial
        zombie_serial = game.zombie_serials[0]
        player = game.players[zombie_serial]

        assert player.is_zombie is True
        assert player.alive is True

        # Kill the zombie
        await game._kill_player_impl(zombie_serial, accel_mag=3.0)

        # Zombie should be dead with respawn timer set
        assert player.alive is False
        assert player.respawn_until > 0

    @pytest.mark.asyncio
    async def test_converted_human_removed_from_human_list(self, zombie_game):
        """Converted human should be removed from human_serials."""
        game, mock_controller_manager, _ = zombie_game
        game.gameplay_stream = MockGameplayStream()
        game.running = True

        await game._initialize_players_impl(mock_controller_manager.controllers)

        human_serial = game.human_serials[0]
        assert human_serial in game.human_serials
        assert human_serial not in game.zombie_serials

        await game._kill_player_impl(human_serial, accel_mag=3.0)

        assert human_serial not in game.human_serials
        assert human_serial in game.zombie_serials


class TestZombieThresholds:
    """Tests for zombie-specific thresholds."""

    @pytest.fixture
    def zombie_game(self):
        """Create a Zombie game."""
        mock_controller_manager = MockControllerManagerService(num_controllers=4)
        mock_settings = MockSettingsService()

        game = ZombieGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_zombie_thresh",
        )

        return game, mock_controller_manager

    @pytest.mark.asyncio
    async def test_zombie_returns_zombie_thresholds(self, zombie_game):
        """Zombies should get thresholds from ZOMBIE_THRESHOLDS dict."""

        game, mock_controller_manager = zombie_game
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get threshold for a zombie
        zombie_serial = game.zombie_serials[0]
        zombie_player = game.players[zombie_serial]
        zombie_thresholds = game._get_effective_thresholds(zombie_player)

        # Should return a tuple from ZOMBIE_THRESHOLDS
        assert isinstance(zombie_thresholds, tuple), "Zombie thresholds should be tuple"
        assert len(zombie_thresholds) == 2, "Zombie thresholds should have (warning, death)"
        assert zombie_thresholds[0] < zombie_thresholds[1], "Warning should be less than death threshold"

    @pytest.mark.asyncio
    async def test_human_returns_sensitivity_value(self, zombie_game):
        """Humans should return sensitivity.value for threshold lookup."""
        game, mock_controller_manager = zombie_game
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get threshold for a human
        human_serial = game.human_serials[0]
        human_player = game.players[human_serial]
        human_thresholds = game._get_effective_thresholds(human_player)

        # Humans return sensitivity.value (int index) for base class threshold lookup
        # This is intentional - base class uses this to index into SLOW_MAX/FAST_MAX arrays
        assert isinstance(human_thresholds, int), "Human thresholds should be int index"


class TestZombieEdgeCases:
    """Tests for edge cases in zombie game."""

    def test_calculate_duration_two_players(self):
        """Game duration with minimum players."""
        # 2 players: (2 * 3 / 16) * 60 = 22.5 seconds
        duration = calculate_game_duration(2)
        assert duration == 22.5

    def test_calculate_duration_sixteen_players(self):
        """Game duration with 16 players."""
        # 16 players: (16 * 3 / 16) * 60 = 180 seconds (3 minutes)
        duration = calculate_game_duration(16)
        assert duration == 180.0

    @pytest.mark.asyncio
    async def test_minimum_one_human(self):
        """Even with many players, should have at least 1 human."""
        mock_controller_manager = MockControllerManagerService(num_controllers=3)
        mock_settings = MockSettingsService()

        game = ZombieGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_min_human",
        )

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # With 3 players and INITIAL_ZOMBIES=2, should have 2 zombies and 1 human
        assert len(game.human_serials) >= 1
        assert len(game.zombie_serials) == min(INITIAL_ZOMBIES, 2)

    @pytest.mark.asyncio
    async def test_get_game_name(self):
        """get_game_name should return 'Zombie'."""
        mock_controller_manager = MockControllerManagerService(num_controllers=2)
        mock_settings = MockSettingsService()

        game = ZombieGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_name",
        )

        assert game.get_game_name() == "Zombie"
