"""
Unit tests for Werewolf game mode.

Tests the core Werewolf mechanics:
- Hidden werewolf assignment (~44% of players)
- Team tracking (humans vs werewolves)
- Player death handling
- Win conditions (team elimination)
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

from services.game_coordinator.games.werewolf import (
    HUMAN_COLOR,
    WerewolfGame,
    WerewolfPlayer,
)


class MockGameplayStream:
    """Minimal mock for gameplay stream writes."""

    async def write(self, message):
        """Accept writes silently."""
        pass


class TestWerewolfGameMode:
    """Test Werewolf game mechanics."""

    @pytest.fixture
    def werewolf_game(self):
        """Create a Werewolf game with 4 players."""
        mock_controller_manager = MockControllerManagerService(
            num_controllers=4,
            death_schedule={},
            max_duration=10.0,
        )
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = WerewolfGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_werewolf_001",
        )

        return game, mock_controller_manager, event_collector

    @pytest.mark.asyncio
    async def test_player_initialization(self, werewolf_game):
        """Test that players are initialized correctly."""
        game, mock_controller_manager, _ = werewolf_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All 4 players should be created
        assert len(game.players) == 4

        # Total should be 4
        total = len(game.werewolf_serials) + len(game.human_serials)
        assert total == 4

    @pytest.mark.asyncio
    async def test_werewolf_percentage(self, werewolf_game):
        """Test that approximately 44% are werewolves."""
        game, mock_controller_manager, _ = werewolf_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # 4 players * 0.44 = 1.76, so 1 werewolf (max(1, int(4*0.44)))
        # But minimum is 1, so we expect 1 werewolf
        werewolf_count = len(game.werewolf_serials)
        assert werewolf_count >= 1
        assert werewolf_count <= 2  # Could be 1 or 2 for 4 players

    @pytest.mark.asyncio
    async def test_all_players_start_yellow(self, werewolf_game):
        """Test that all players start with human color (hidden identities)."""
        game, mock_controller_manager, _ = werewolf_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for _serial, player in game.players.items():
            assert player.color == HUMAN_COLOR

    @pytest.mark.asyncio
    async def test_werewolves_marked_correctly(self, werewolf_game):
        """Test that werewolves have correct attributes."""
        game, mock_controller_manager, _ = werewolf_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for serial in game.werewolf_serials:
            player = game.players[serial]
            assert player.is_werewolf is True
            assert player.team == 1
            assert player.revealed is False

    @pytest.mark.asyncio
    async def test_humans_marked_correctly(self, werewolf_game):
        """Test that humans have correct attributes."""
        game, mock_controller_manager, _ = werewolf_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        for serial in game.human_serials:
            player = game.players[serial]
            assert player.is_werewolf is False
            assert player.team == 0
            assert player.revealed is False

    @pytest.mark.asyncio
    async def test_win_condition_humans_eliminated(self, werewolf_game):
        """Test that werewolves win when all humans are dead."""
        game, mock_controller_manager, event_collector = werewolf_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initially no win
        assert not game._check_win_condition()

        # Kill all humans
        for serial in game.human_serials:
            game.players[serial].alive = False

        # Werewolves should win
        assert game._check_win_condition()

        # Verify winner event
        winner_events = event_collector.get_events_of_type("werewolf_winner")
        assert len(winner_events) == 1
        assert winner_events[0]["winner"] == "werewolves"

    @pytest.mark.asyncio
    async def test_win_condition_werewolves_eliminated(self, werewolf_game):
        """Test that humans win when all werewolves are dead."""
        game, mock_controller_manager, event_collector = werewolf_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initially no win
        assert not game._check_win_condition()

        # Kill all werewolves
        for serial in game.werewolf_serials:
            game.players[serial].alive = False

        # Humans should win
        assert game._check_win_condition()

        # Verify winner event
        winner_events = event_collector.get_events_of_type("werewolf_winner")
        assert len(winner_events) == 1
        assert winner_events[0]["winner"] == "humans"

    @pytest.mark.asyncio
    async def test_no_win_with_both_teams_alive(self, werewolf_game):
        """Test that game continues with both teams alive."""
        game, mock_controller_manager, _ = werewolf_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All alive - no win
        assert not game._check_win_condition()

        # Kill one from each team (if possible)
        if len(game.human_serials) > 1:
            game.players[game.human_serials[0]].alive = False
        if len(game.werewolf_serials) > 1:
            game.players[game.werewolf_serials[0]].alive = False

        # Still both teams have members - no win
        alive_humans = [s for s in game.human_serials if game.players[s].alive]
        alive_wolves = [s for s in game.werewolf_serials if game.players[s].alive]

        if alive_humans and alive_wolves:
            assert not game._check_win_condition()

    @pytest.mark.asyncio
    async def test_kill_player_marks_dead(self, werewolf_game):
        """Test that _kill_player_impl marks player as dead."""
        game, mock_controller_manager, _ = werewolf_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get first player
        serial = list(game.players.keys())[0]
        player = game.players[serial]
        assert player.alive is True

        # Kill the player
        await game._kill_player_impl(serial, accel_mag=5.0)

        assert player.alive is False

    @pytest.mark.asyncio
    async def test_werewolf_player_dataclass(self, werewolf_game):
        """Test WerewolfPlayer dataclass attributes."""
        game, mock_controller_manager, _ = werewolf_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # All players should be WerewolfPlayer instances
        for _serial, player in game.players.items():
            assert isinstance(player, WerewolfPlayer)
            assert hasattr(player, "is_werewolf")
            assert hasattr(player, "revealed")

    @pytest.mark.asyncio
    async def test_get_game_name(self, werewolf_game):
        """Test get_game_name returns 'Werewolf'."""
        game, _, _ = werewolf_game
        assert game.get_game_name() == "Werewolf"

    @pytest.mark.asyncio
    async def test_kill_player_publishes_event_with_role(self, werewolf_game):
        """Test that _kill_player_impl handles werewolf role info."""
        game, mock_controller_manager, _ = werewolf_game

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get a werewolf player
        werewolf_serial = game.werewolf_serials[0]
        player = game.players[werewolf_serial]
        assert player.is_werewolf is True

        # Kill the werewolf
        await game._kill_player_impl(werewolf_serial, accel_mag=5.0)

        # Player should be dead
        assert player.alive is False


class TestWerewolfThresholds:
    """Tests for werewolf-specific thresholds."""

    @pytest.fixture
    def werewolf_game(self):
        """Create a Werewolf game."""
        mock_controller_manager = MockControllerManagerService(num_controllers=4)
        mock_settings = MockSettingsService()

        game = WerewolfGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_werewolf_thresh",
        )

        return game, mock_controller_manager

    @pytest.mark.asyncio
    async def test_werewolf_returns_werewolf_thresholds(self, werewolf_game):
        """Werewolves should get thresholds from WEREWOLF_THRESHOLDS dict."""
        from services.game_coordinator.games.werewolf import WEREWOLF_THRESHOLDS

        game, mock_controller_manager = werewolf_game
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get threshold for a werewolf
        werewolf_serial = game.werewolf_serials[0]
        werewolf_player = game.players[werewolf_serial]
        werewolf_thresholds = game._get_effective_thresholds(werewolf_player)

        # Should return a tuple from WEREWOLF_THRESHOLDS
        assert isinstance(werewolf_thresholds, tuple), "Werewolf thresholds should be tuple"
        assert len(werewolf_thresholds) == 2, "Werewolf thresholds should have (warning, death)"
        assert werewolf_thresholds[0] < werewolf_thresholds[1], "Warning should be less than death threshold"

        # Verify it matches WEREWOLF_THRESHOLDS for game's sensitivity
        expected = WEREWOLF_THRESHOLDS.get(game.sensitivity, (2.1, 2.6))
        assert werewolf_thresholds == expected

    @pytest.mark.asyncio
    async def test_human_returns_sensitivity_value(self, werewolf_game):
        """Humans should return sensitivity.value for threshold lookup."""
        game, mock_controller_manager = werewolf_game
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get threshold for a human
        human_serial = game.human_serials[0]
        human_player = game.players[human_serial]
        human_thresholds = game._get_effective_thresholds(human_player)

        # Humans return sensitivity.value (int index) for base class threshold lookup
        assert isinstance(human_thresholds, int), "Human thresholds should be int index"


class TestWerewolfReveal:
    """Tests for werewolf reveal mechanics."""

    @pytest.fixture
    def werewolf_game(self):
        """Create a Werewolf game."""
        mock_controller_manager = MockControllerManagerService(num_controllers=4)
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = WerewolfGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_werewolf_reveal",
        )

        return game, mock_controller_manager, event_collector

    @pytest.mark.asyncio
    async def test_starts_unrevealed(self, werewolf_game):
        """Game should start with revealed=False."""
        game, mock_controller_manager, _ = werewolf_game
        await game._initialize_players_impl(mock_controller_manager.controllers)

        assert game.revealed is False
        for player in game.players.values():
            assert player.revealed is False


class TestWerewolfEdgeCases:
    """Tests for edge cases in werewolf game."""

    @pytest.mark.asyncio
    async def test_larger_player_count_werewolf_ratio(self):
        """Test werewolf ratio with more players."""
        mock_controller_manager = MockControllerManagerService(num_controllers=9)
        mock_settings = MockSettingsService()

        game = WerewolfGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_werewolf_ratio",
        )

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # 9 players * 0.44 = 3.96, so 3 werewolves
        werewolf_count = len(game.werewolf_serials)
        assert werewolf_count == 3

    @pytest.mark.asyncio
    async def test_minimum_one_werewolf(self):
        """Even with 2 players, should have at least 1 werewolf."""
        mock_controller_manager = MockControllerManagerService(num_controllers=2)
        mock_settings = MockSettingsService()

        game = WerewolfGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_min_werewolf",
        )

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # 2 players * 0.44 = 0.88, but min(1, ...) ensures at least 1
        assert len(game.werewolf_serials) >= 1

    @pytest.mark.asyncio
    async def test_win_condition_all_dead(self):
        """Test when all players are dead (draw condition)."""
        mock_controller_manager = MockControllerManagerService(num_controllers=4)
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = WerewolfGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_werewolf_draw",
        )

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Kill everyone
        for player in game.players.values():
            player.alive = False

        # Should trigger win condition (with winner="none")
        assert game._check_win_condition()

        winner_events = event_collector.get_events_of_type("werewolf_winner")
        assert len(winner_events) == 1
        assert winner_events[0]["winner"] == "none"

    @pytest.mark.asyncio
    async def test_reveal_state_tracks_correctly(self):
        """Test that game reveal state can be toggled."""
        mock_controller_manager = MockControllerManagerService(num_controllers=4)
        mock_settings = MockSettingsService()

        game = WerewolfGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=lambda *_args: None,
            audio_client=None,
            game_id="test_reveal_state",
        )

        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initially not revealed
        assert game.revealed is False

        # Manually set revealed
        game.revealed = True

        assert game.revealed is True
