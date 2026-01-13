"""
Unit tests for unique color assignment in FFA and Nonstop Joust (Phase 39 - Task 3).

Tests unique color generation and assignment for non-team game modes.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.game_coordinator.games.base import Player
from services.game_coordinator.games.ffa import FFAGame
from services.game_coordinator.games.nonstop_joust import NonstopJoustGame, NonstopPlayer


@pytest.fixture
def mock_controller_client():
    """Create mock controller manager client."""
    client = AsyncMock()
    client.SetControllerColor = AsyncMock()
    client.PlayControllerEffect = AsyncMock()
    client.GetReadyControllers = AsyncMock()
    return client


@pytest.fixture
def mock_settings_client():
    """Create mock settings client."""
    return AsyncMock()


@pytest.fixture
def mock_event_publisher():
    """Create mock event publisher."""
    return MagicMock()


@pytest.fixture
def ffa_game(mock_controller_client, mock_settings_client, mock_event_publisher):
    """Create FFAGame instance."""
    return FFAGame(
        controller_manager_client=mock_controller_client,
        settings_client=mock_settings_client,
        event_publisher=mock_event_publisher,
    )


@pytest.fixture
def nonstop_game(mock_controller_client, mock_settings_client, mock_event_publisher):
    """Create NonstopJoustGame instance."""
    return NonstopJoustGame(
        controller_manager_client=mock_controller_client,
        settings_client=mock_settings_client,
        event_publisher=mock_event_publisher,
    )


class TestFFAUniqueColors:
    """Test FFA unique color assignment."""

    @pytest.mark.asyncio
    async def test_ffa_assigns_unique_colors(self, ffa_game):
        """FFA should assign unique colors to each player."""
        # Add players
        ffa_game.players = {
            "p1": Player(serial="p1", team=0, alive=True, color=(255, 255, 255)),
            "p2": Player(serial="p2", team=0, alive=True, color=(255, 255, 255)),
            "p3": Player(serial="p3", team=0, alive=True, color=(255, 255, 255)),
        }

        await ffa_game._set_ffa_colors()

        # Should call SetControllerColor for each player
        assert ffa_game.controller_manager_client.SetControllerColor.call_count == 3

        # Collect assigned colors
        assigned_colors = []
        for call in ffa_game.controller_manager_client.SetControllerColor.call_args_list:
            request = call[0][0]
            color = (request.color.r, request.color.g, request.color.b)
            assigned_colors.append(color)

        # All colors should be unique
        assert len(assigned_colors) == len(set(assigned_colors))

        # Colors should be vibrant (at least one channel at max)
        for color in assigned_colors:
            assert max(color) == 255

    @pytest.mark.asyncio
    async def test_ffa_updates_player_color_attribute(self, ffa_game):
        """FFA should update player.color attribute."""
        ffa_game.players = {
            "p1": Player(serial="p1", team=0, alive=True, color=(255, 255, 255)),
            "p2": Player(serial="p2", team=0, alive=True, color=(255, 255, 255)),
        }

        await ffa_game._set_ffa_colors()

        # Players should have their colors updated
        p1_color = ffa_game.players["p1"].color
        p2_color = ffa_game.players["p2"].color

        # Colors should be different
        assert p1_color != p2_color

        # Colors should match what was sent to controller
        call1 = ffa_game.controller_manager_client.SetControllerColor.call_args_list[0]
        request1 = call1[0][0]
        assert request1.color.r == p1_color[0]
        assert request1.color.g == p1_color[1]
        assert request1.color.b == p1_color[2]

    @pytest.mark.asyncio
    async def test_ffa_colors_persistent(self, ffa_game):
        """FFA colors should be persistent (duration_ms=0)."""
        ffa_game.players = {
            "p1": Player(serial="p1", team=0, alive=True, color=(255, 255, 255)),
        }

        await ffa_game._set_ffa_colors()

        call = ffa_game.controller_manager_client.SetControllerColor.call_args_list[0]
        request = call[0][0]
        assert request.duration_ms == 0  # Persistent

    @pytest.mark.asyncio
    async def test_ffa_many_players(self, ffa_game):
        """Should handle many players with distinct colors."""
        # Create 8 players
        ffa_game.players = {
            f"p{i}": Player(serial=f"p{i}", team=0, alive=True, color=(255, 255, 255)) for i in range(8)
        }

        await ffa_game._set_ffa_colors()

        # Collect all colors
        assigned_colors = []
        for call in ffa_game.controller_manager_client.SetControllerColor.call_args_list:
            request = call[0][0]
            color = (request.color.r, request.color.g, request.color.b)
            assigned_colors.append(color)

        # All 8 colors should be unique
        assert len(set(assigned_colors)) == 8

    @pytest.mark.asyncio
    async def test_ffa_publishes_event(self, ffa_game):
        """Should publish ffa_colors_display event."""
        ffa_game.players = {
            "p1": Player(serial="p1", team=0, alive=True, color=(255, 255, 255)),
        }

        await ffa_game._set_ffa_colors()

        # Should publish event
        ffa_game.event_publisher.assert_called()
        call_args = ffa_game.event_publisher.call_args_list[0]
        assert call_args[0][0] == "ffa_colors_display"
        assert call_args[0][1]["player_count"] == 1


class TestNonstopUniqueColors:
    """Test Nonstop Joust unique color assignment."""

    @pytest.mark.asyncio
    async def test_nonstop_assigns_unique_colors(self, nonstop_game):
        """Nonstop should assign unique colors to each player."""
        nonstop_game.players = {
            "p1": NonstopPlayer(serial="p1", team=0, alive=True, color=(255, 255, 255)),
            "p2": NonstopPlayer(serial="p2", team=0, alive=True, color=(255, 255, 255)),
            "p3": NonstopPlayer(serial="p3", team=0, alive=True, color=(255, 255, 255)),
        }

        await nonstop_game._set_unique_colors()

        # Should call SetControllerColor for each player
        assert nonstop_game.controller_manager_client.SetControllerColor.call_count == 3

        # Collect assigned colors
        assigned_colors = []
        for call in nonstop_game.controller_manager_client.SetControllerColor.call_args_list:
            request = call[0][0]
            color = (request.color.r, request.color.g, request.color.b)
            assigned_colors.append(color)

        # All colors should be unique
        assert len(assigned_colors) == len(set(assigned_colors))

    @pytest.mark.asyncio
    async def test_nonstop_updates_player_color(self, nonstop_game):
        """Nonstop should update player.color attribute."""
        nonstop_game.players = {
            "p1": NonstopPlayer(serial="p1", team=0, alive=True, color=(255, 255, 255)),
            "p2": NonstopPlayer(serial="p2", team=0, alive=True, color=(255, 255, 255)),
        }

        await nonstop_game._set_unique_colors()

        # Players should have different colors
        p1_color = nonstop_game.players["p1"].color
        p2_color = nonstop_game.players["p2"].color
        assert p1_color != p2_color

    @pytest.mark.asyncio
    async def test_nonstop_publishes_event(self, nonstop_game):
        """Should publish nonstop_colors_display event."""
        nonstop_game.players = {
            "p1": NonstopPlayer(serial="p1", team=0, alive=True, color=(255, 255, 255)),
        }

        await nonstop_game._set_unique_colors()

        # Should publish event
        nonstop_game.event_publisher.assert_called()
        call_args = nonstop_game.event_publisher.call_args_list[0]
        assert call_args[0][0] == "nonstop_colors_display"
        assert call_args[0][1]["player_count"] == 1


class TestColorGeneration:
    """Test color generation algorithm."""

    @pytest.mark.asyncio
    async def test_color_distribution(self, ffa_game):
        """Colors should be evenly distributed in HSV space."""
        from lib.colors import generate_colors

        # Generate colors for 6 players
        colors = generate_colors(6)

        # Should have 6 colors
        assert len(colors) == 6

        # All should be unique
        assert len(set(colors)) == 6

        # All should be vibrant (full saturation/value)
        for color in colors:
            assert max(color) == 255

    @pytest.mark.asyncio
    async def test_color_ordering_consistent(self, ffa_game):
        """Color generation should be deterministic."""
        from lib.colors import generate_colors

        colors1 = generate_colors(4)
        colors2 = generate_colors(4)

        # Should generate same colors in same order
        assert colors1 == colors2

    @pytest.mark.asyncio
    async def test_color_hue_separation(self, ffa_game):
        """Colors should have maximum hue separation."""
        import colorsys

        from lib.colors import generate_colors

        colors = generate_colors(4)

        # Convert to HSV and check hue distribution
        hues = []
        for r, g, b in colors:
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            hues.append(h)

        # Hues should be roughly evenly spaced
        # For 4 colors: 0, 0.25, 0.5, 0.75
        expected_spacing = 1.0 / 4
        for i in range(len(hues) - 1):
            actual_spacing = hues[i + 1] - hues[i]
            # Allow some tolerance
            assert abs(actual_spacing - expected_spacing) < 0.1


class TestGetAdditionalPhases:
    """Test additional phases for color assignment."""

    def test_ffa_has_color_phase(self, ffa_game):
        """FFA should have ffa_colors_phase."""
        phases = ffa_game._get_additional_phases()

        assert len(phases) == 1
        assert phases[0].name == "ffa_colors_phase"

    def test_nonstop_has_color_phase(self, nonstop_game):
        """Nonstop should have nonstop_colors_phase."""
        phases = nonstop_game._get_additional_phases()

        assert len(phases) == 1
        assert phases[0].name == "nonstop_colors_phase"

    @pytest.mark.asyncio
    async def test_color_phase_executes(self, ffa_game):
        """Color phase should execute the color assignment."""
        ffa_game.players = {
            "p1": Player(serial="p1", team=0, alive=True, color=(255, 255, 255)),
        }
        ffa_game.running = True

        phases = ffa_game._get_additional_phases()

        # Execute the phase
        await phases[0].execute()

        # Color should have been assigned
        assert ffa_game.controller_manager_client.SetControllerColor.called
