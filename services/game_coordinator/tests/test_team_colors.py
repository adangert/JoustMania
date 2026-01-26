"""
Unit tests for team color assignment (Phase 39 - Task 3).

Tests team color functionality in TeamsGameBase and subclasses.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.game_coordinator.games.base import Player  # noqa: E402
from services.game_coordinator.games.teams_base import TEAM_COLORS, TeamsGameBase  # noqa: E402


class MockTeamsGame(TeamsGameBase):
    """Mock implementation of TeamsGameBase for testing."""

    def get_game_name(self):
        return "Mock Teams"

    async def _initialize_players_impl(self, controllers):
        for idx, controller in enumerate(controllers):
            team_num = idx % self.num_teams
            self.players[controller.serial] = Player(
                serial=controller.serial,
                team=team_num,
                alive=True,
                color=self.team_colors[team_num]["rgb"],
            )

    def _get_additional_phases(self):
        return []

    async def _kill_player_impl(self, serial, accel_mag):
        pass

    async def _end_game_impl(self):
        pass


@pytest.fixture
def mock_controller_client():
    """Create mock controller manager client."""
    return AsyncMock()


@pytest.fixture
def mock_settings_client():
    """Create mock settings client."""
    return AsyncMock()


@pytest.fixture
def mock_event_publisher():
    """Create mock event publisher."""
    return MagicMock()


@pytest.fixture
def teams_game(mock_controller_client, mock_settings_client, mock_event_publisher):
    """Create MockTeamsGame instance."""
    return MockTeamsGame(
        controller_manager_client=mock_controller_client,
        settings_client=mock_settings_client,
        event_publisher=mock_event_publisher,
        num_teams=2,
    )


class TestTeamColorPalette:
    """Test team color palette definition."""

    def test_team_colors_count(self):
        """Team colors should have 8 distinct colors."""
        assert len(TEAM_COLORS) == 8

    def test_team_colors_structure(self):
        """Each team color should have name and rgb."""
        for color in TEAM_COLORS:
            assert "name" in color
            assert "rgb" in color
            assert len(color["rgb"]) == 3
            assert all(0 <= c <= 255 for c in color["rgb"])

    def test_team_colors_unique(self):
        """All team colors should be distinct."""
        rgb_values = [color["rgb"] for color in TEAM_COLORS]
        assert len(rgb_values) == len(set(rgb_values))

    def test_team_color_names(self):
        """Team colors should have expected names."""
        expected_names = [
            "Pink",
            "Magenta",
            "Orange",
            "Yellow",
            "Green",
            "Turquoise",
            "Blue",
            "Purple",
        ]
        actual_names = [color["name"] for color in TEAM_COLORS]
        assert actual_names == expected_names


class TestTeamsGameBaseInit:
    """Test TeamsGameBase initialization."""

    def test_team_initialization(self, teams_game):
        """Teams should be initialized with correct colors."""
        assert len(teams_game.teams) == 2
        assert teams_game.teams[0].name == "Pink"
        assert teams_game.teams[0].color == (255, 108, 108)
        assert teams_game.teams[1].name == "Magenta"
        assert teams_game.teams[1].color == (255, 0, 192)

    def test_team_colors_subset(self, teams_game):
        """team_colors should be first N colors from TEAM_COLORS."""
        assert len(teams_game.team_colors) == 2
        assert teams_game.team_colors == TEAM_COLORS[:2]

    def test_multiple_teams(self, mock_controller_client, mock_settings_client, mock_event_publisher):
        """Should support up to 8 teams."""
        for num_teams in range(2, 9):
            game = MockTeamsGame(
                controller_manager_client=mock_controller_client,
                settings_client=mock_settings_client,
                event_publisher=mock_event_publisher,
                num_teams=num_teams,
            )
            assert len(game.teams) == num_teams
            assert len(game.team_colors) == num_teams


class TestSetTeamColors:
    """Test _set_team_colors method."""

    @pytest.mark.asyncio
    async def test_set_team_colors_multiple_teams(
        self, mock_controller_client, mock_settings_client, mock_event_publisher
    ):
        """Should handle multiple teams correctly via stream."""
        game = MockTeamsGame(
            controller_manager_client=mock_controller_client,
            settings_client=mock_settings_client,
            event_publisher=mock_event_publisher,
            num_teams=4,
        )

        # Mock the gameplay stream
        mock_stream = AsyncMock()
        game.gameplay_stream = mock_stream

        # Add players across 4 teams
        game.players = {
            "p1": Player(serial="p1", team=0, alive=True, color=TEAM_COLORS[0]["rgb"]),
            "p2": Player(serial="p2", team=1, alive=True, color=TEAM_COLORS[1]["rgb"]),
            "p3": Player(serial="p3", team=2, alive=True, color=TEAM_COLORS[2]["rgb"]),
            "p4": Player(serial="p4", team=3, alive=True, color=TEAM_COLORS[3]["rgb"]),
        }

        await game._set_team_colors(pulse_effect=False, duration_ms=0)

        # Should write base_color for all 4 players via stream
        assert mock_stream.write.call_count == 4

        # Verify each team got correct color via stream
        calls = mock_stream.write.call_args_list
        for idx, call in enumerate(calls):
            msg = call[0][0]
            expected_color = TEAM_COLORS[idx]["rgb"]
            assert msg.base_color.color.r == expected_color[0]
            assert msg.base_color.color.g == expected_color[1]
            assert msg.base_color.color.b == expected_color[2]


class TestGetAliveTeams:
    """Test _get_alive_teams method."""

    def test_get_alive_teams_all_alive(self, teams_game):
        """Should return all teams when all players alive."""
        teams_game.players = {
            "p1": Player(serial="p1", team=0, alive=True),
            "p2": Player(serial="p2", team=1, alive=True),
            "p3": Player(serial="p3", team=0, alive=True),
        }

        alive_teams = teams_game._get_alive_teams()
        assert alive_teams == {0, 1}

    def test_get_alive_teams_one_eliminated(self, teams_game):
        """Should not include teams with all dead players."""
        teams_game.players = {
            "p1": Player(serial="p1", team=0, alive=True),
            "p2": Player(serial="p2", team=1, alive=False),
            "p3": Player(serial="p3", team=0, alive=True),
        }

        alive_teams = teams_game._get_alive_teams()
        assert alive_teams == {0}

    def test_get_alive_teams_empty(self, teams_game):
        """Should return empty set when all dead."""
        teams_game.players = {
            "p1": Player(serial="p1", team=0, alive=False),
            "p2": Player(serial="p2", team=1, alive=False),
        }

        alive_teams = teams_game._get_alive_teams()
        assert alive_teams == set()

    def test_get_alive_teams_partial_team(self, teams_game):
        """Team should be alive if any member is alive."""
        teams_game.players = {
            "p1": Player(serial="p1", team=0, alive=True),
            "p2": Player(serial="p2", team=0, alive=False),
            "p3": Player(serial="p3", team=0, alive=False),
        }

        alive_teams = teams_game._get_alive_teams()
        assert alive_teams == {0}


class TestTeamColorAssignment:
    """Test team color assignment to players."""

    @pytest.mark.asyncio
    async def test_players_get_team_colors(self, teams_game):
        """Players should be assigned their team's color."""

        class MockController:
            def __init__(self, serial):
                self.serial = serial

        controllers = [MockController("p1"), MockController("p2"), MockController("p3")]
        await teams_game._initialize_players_impl(controllers)

        # p1 and p3 should be team 0 (Pink), p2 should be team 1 (Magenta)
        assert teams_game.players["p1"].team == 0
        assert teams_game.players["p1"].color == (255, 108, 108)

        assert teams_game.players["p2"].team == 1
        assert teams_game.players["p2"].color == (255, 0, 192)

        assert teams_game.players["p3"].team == 0
        assert teams_game.players["p3"].color == (255, 108, 108)
