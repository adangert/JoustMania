"""
Unit tests for Swapper game mode.

Tests the core swapper mechanics:
- Team swapping on death
- Grace period after swap
- Win condition detection (all players on same team)
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

from conftest import EventCollector, MockControllerManagerService, MockSettingsService

from services.game_coordinator.games.swapper import SwapperGame


class TestSwapperTeamSwapping:
    """Test Swapper's team swapping mechanics."""

    @pytest.fixture
    def swapper_game(self):
        """Create a Swapper game with 4 players (2 per team)."""
        mock_controller_manager = MockControllerManagerService(
            num_controllers=4,
            death_schedule={},  # No auto-deaths, we'll trigger manually
            max_duration=10.0,
        )
        mock_settings = MockSettingsService()
        event_collector = EventCollector()

        game = SwapperGame(
            controller_manager_client=mock_controller_manager,
            settings_client=mock_settings,
            event_publisher=event_collector.publish,
            audio_client=None,
            game_id="test_swapper_001",
        )

        return game, mock_controller_manager, event_collector

    @pytest.mark.asyncio
    async def test_initial_team_assignment(self, swapper_game):
        """Test that players are assigned to teams round-robin (0, 1, 0, 1)."""
        game, mock_controller_manager, _ = swapper_game

        # Manually initialize players (normally done by game loop)
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Verify round-robin assignment: 0, 1, 0, 1
        assert game.players["mock_controller_0"].team == 0
        assert game.players["mock_controller_1"].team == 1
        assert game.players["mock_controller_2"].team == 0
        assert game.players["mock_controller_3"].team == 1

    @pytest.mark.asyncio
    async def test_kill_player_impl_swaps_team(self, swapper_game):
        """Test that _kill_player_impl swaps player to the other team."""
        game, mock_controller_manager, event_collector = swapper_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Get initial team for player 0
        player = game.players["mock_controller_0"]
        initial_team = player.team
        assert initial_team == 0

        # Mock the gameplay stream (needed for color updates in _kill_player_impl)
        game.gameplay_stream = MockGameplayStream()

        # Assign team colors (needed for swap)
        await game._assign_team_colors()

        # Call _kill_player_impl directly
        await game._kill_player_impl("mock_controller_0", accel_mag=5.0)

        # Verify team swapped
        assert player.team == 1, f"Expected team 1, got {player.team}"
        assert player.team != initial_team

        # Verify swap event was published
        swap_events = event_collector.get_events_of_type("player_swapped")
        assert len(swap_events) == 1
        assert swap_events[0]["serial"] == "mock_controller_0"
        assert swap_events[0]["old_team"] == 0
        assert swap_events[0]["new_team"] == 1

    @pytest.mark.asyncio
    async def test_double_swap_returns_to_original_team(self, swapper_game):
        """Test that killing a player twice swaps them back to original team."""
        game, mock_controller_manager, event_collector = swapper_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        player = game.players["mock_controller_0"]
        initial_team = player.team
        assert initial_team == 0

        # Mock the gameplay stream
        game.gameplay_stream = MockGameplayStream()
        await game._assign_team_colors()

        # First swap: 0 -> 1
        await game._kill_player_impl("mock_controller_0", accel_mag=5.0)
        assert player.team == 1

        # Clear grace period for immediate second swap
        player.grace_until = 0

        # Second swap: 1 -> 0
        await game._kill_player_impl("mock_controller_0", accel_mag=5.0)
        assert player.team == 0, f"Expected team 0 after double swap, got {player.team}"

        # Verify two swap events
        swap_events = event_collector.get_events_of_type("player_swapped")
        assert len(swap_events) == 2

    @pytest.mark.asyncio
    async def test_grace_period_set_after_swap(self, swapper_game):
        """Test that player gets grace period after swapping."""
        game, mock_controller_manager, _ = swapper_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        player = game.players["mock_controller_0"]

        # Mock the gameplay stream
        game.gameplay_stream = MockGameplayStream()
        await game._assign_team_colors()

        # Record time before swap
        time_before = time.time()

        # Swap player
        await game._kill_player_impl("mock_controller_0", accel_mag=5.0)

        # Verify grace period is ~2 seconds in the future
        assert player.grace_until > time_before + 1.5
        assert player.grace_until < time_before + 3.0

    @pytest.mark.asyncio
    async def test_win_condition_all_on_same_team(self, swapper_game):
        """Test that win condition triggers when all players on same team."""
        game, mock_controller_manager, _ = swapper_game

        # Initialize players (2 per team initially)
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initial state: team 0 has [0, 2], team 1 has [1, 3]
        assert not game._check_win_condition()

        # Move all players to team 1
        for serial in game.players:
            game.players[serial].team = 1

        # Now should trigger win condition
        assert game._check_win_condition()

    @pytest.mark.asyncio
    async def test_get_alive_teams(self, swapper_game):
        """Test _get_alive_teams returns teams with players."""
        game, mock_controller_manager, _ = swapper_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Initial: both teams have players
        teams = game._get_alive_teams()
        assert teams == {0, 1}

        # Move all to team 0
        for serial in game.players:
            game.players[serial].team = 0

        teams = game._get_alive_teams()
        assert teams == {0}

    @pytest.mark.asyncio
    async def test_last_death_serial_tracked(self, swapper_game):
        """Test that last_death_serial tracks the last player to swap."""
        game, mock_controller_manager, _ = swapper_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        # Mock the gameplay stream
        game.gameplay_stream = MockGameplayStream()
        await game._assign_team_colors()

        # Initially no last death
        assert game.last_death_serial is None

        # Swap player 0
        await game._kill_player_impl("mock_controller_0", accel_mag=5.0)
        assert game.last_death_serial == "mock_controller_0"

        # Swap player 1 (clear grace first)
        game.players["mock_controller_1"].grace_until = 0
        await game._kill_player_impl("mock_controller_1", accel_mag=5.0)
        assert game.last_death_serial == "mock_controller_1"

    @pytest.mark.asyncio
    async def test_swap_count_tracked(self, swapper_game):
        """Test that swap_count is tracked per player."""
        game, mock_controller_manager, _ = swapper_game

        # Initialize players
        await game._initialize_players_impl(mock_controller_manager.controllers)

        player = game.players["mock_controller_0"]

        # Mock the gameplay stream
        game.gameplay_stream = MockGameplayStream()
        await game._assign_team_colors()

        # Initially no swaps
        assert getattr(player, "swap_count", 0) == 0

        # First swap
        await game._kill_player_impl("mock_controller_0", accel_mag=5.0)
        assert player.swap_count == 1

        # Clear grace and swap again
        player.grace_until = 0
        await game._kill_player_impl("mock_controller_0", accel_mag=5.0)
        assert player.swap_count == 2


class MockGameplayStream:
    """Minimal mock for gameplay stream writes."""

    async def write(self, message):
        """Accept writes silently."""
        pass
