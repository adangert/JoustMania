"""Tests for lib/types.py"""

import sys
from pathlib import Path

# Add lib to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.types import (
    GameEvent,
    Games,
    Opts,
    Sensitivity,
    Status,
    get_game_display_name,
)


class TestGames:
    """Tests for Games enum."""

    def test_all_games_have_value(self):
        """All games should have an integer value."""
        for game in Games:
            assert isinstance(game.value, int)

    def test_all_games_have_pretty_name(self):
        """All games should have a pretty name."""
        for game in Games:
            assert hasattr(game, "pretty_name")
            assert isinstance(game.pretty_name, str)
            assert len(game.pretty_name) > 0

    def test_all_games_have_minimum_players(self):
        """All games should have minimum_players >= 2."""
        for game in Games:
            assert hasattr(game, "minimum_players")
            assert game.minimum_players >= 2

    def test_from_name_exact_match(self):
        """from_name should match exact enum names."""
        assert Games.from_name("JoustFFA") == Games.JoustFFA
        assert Games.from_name("NonStop") == Games.NonStop
        assert Games.from_name("FightClub") == Games.FightClub

    def test_from_name_case_insensitive(self):
        """from_name should be case insensitive."""
        assert Games.from_name("joustffa") == Games.JoustFFA
        assert Games.from_name("JOUSTFFA") == Games.JoustFFA
        assert Games.from_name("JoUsTfFa") == Games.JoustFFA

    def test_from_name_aliases(self):
        """from_name should resolve common aliases."""
        assert Games.from_name("FFA") == Games.JoustFFA
        assert Games.from_name("ffa") == Games.JoustFFA
        assert Games.from_name("Teams") == Games.JoustTeams
        assert Games.from_name("nonstop") == Games.NonStop

    def test_from_name_pretty_name(self):
        """from_name should match pretty names."""
        assert Games.from_name("Joust Free-for-All") == Games.JoustFFA
        assert Games.from_name("Non Stop Joust") == Games.NonStop

    def test_from_name_returns_none_for_invalid(self):
        """from_name should return None for invalid names."""
        assert Games.from_name("InvalidGame") is None
        assert Games.from_name("") is None
        assert Games.from_name("not a game") is None

    def test_is_valid(self):
        """is_valid should return True for valid names."""
        assert Games.is_valid("FFA") is True
        assert Games.is_valid("JoustFFA") is True
        assert Games.is_valid("invalid") is False

    def test_all_names(self):
        """all_names should return list of enum names."""
        names = Games.all_names()
        assert "JoustFFA" in names
        assert "NonStop" in names
        assert len(names) == len(Games)


class TestStatus:
    """Tests for Status enum."""

    def test_status_values(self):
        """Status should have expected values."""
        assert Status.ALIVE.value == 0
        assert Status.DIED.value == 1
        assert Status.DEAD.value == 2
        assert Status.REVIVED.value == 3


class TestOpts:
    """Tests for Opts enum."""

    def test_battery_levels_dict(self):
        """battery_levels_dict should return valid levels."""
        levels = Opts.battery_levels_dict()
        assert isinstance(levels, dict)
        assert 0 in levels
        assert levels[0] == "Low"
        assert levels[5] == "100%"
        assert levels[6] == "Charging"


class TestSensitivity:
    """Tests for Sensitivity enum."""

    def test_sensitivity_order(self):
        """Sensitivity values should be ordered 0-4."""
        assert Sensitivity.ULTRA_SLOW.value == 0
        assert Sensitivity.SLOW.value == 1
        assert Sensitivity.MEDIUM.value == 2
        assert Sensitivity.FAST.value == 3
        assert Sensitivity.ULTRA_FAST.value == 4

    def test_can_use_as_index(self):
        """Sensitivity values should work as array indices."""
        thresholds = [1.0, 1.5, 2.0, 2.5, 3.0]
        assert thresholds[Sensitivity.ULTRA_SLOW.value] == 1.0
        assert thresholds[Sensitivity.MEDIUM.value] == 2.0


class TestGameEvent:
    """Tests for GameEvent enum."""

    def test_is_game_starting(self):
        """is_game_starting should identify start events."""
        assert GameEvent.is_game_starting(GameEvent.GAME_START) is True
        assert GameEvent.is_game_starting(GameEvent.GAME_STARTING) is True
        assert GameEvent.is_game_starting(GameEvent.GAME_STARTED) is True
        assert GameEvent.is_game_starting(GameEvent.GAME_ENDED) is False
        assert GameEvent.is_game_starting(GameEvent.PLAYER_DEATH) is False

    def test_is_game_ending(self):
        """is_game_ending should identify end events."""
        assert GameEvent.is_game_ending(GameEvent.GAME_ENDED) is True
        assert GameEvent.is_game_ending(GameEvent.GAME_FORCE_ENDED) is True
        assert GameEvent.is_game_ending(GameEvent.GAME_ERROR) is True
        assert GameEvent.is_game_ending(GameEvent.GAME_STARTED) is False


class TestGetGameDisplayName:
    """Tests for get_game_display_name function."""

    def test_returns_pretty_name(self):
        """Should return pretty name for valid games."""
        assert get_game_display_name("FFA") == "Joust Free-for-All"
        assert get_game_display_name("JoustTeams") == "Joust Teams"

    def test_returns_original_for_invalid(self):
        """Should return original name if game not found."""
        assert get_game_display_name("UnknownGame") == "UnknownGame"
