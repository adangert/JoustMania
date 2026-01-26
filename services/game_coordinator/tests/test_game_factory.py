"""
Unit tests for GameFactory.

Tests game instance creation:
- Name resolution via Games enum
- Game class instantiation
- Team game handling
- Error cases for unknown modes

Issue #209: Improve test coverage for critical game flow
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

from lib.types import Games  # noqa: E402
from services.game_coordinator.game_factory import GameFactory  # noqa: E402


class MockControllerManagerClient:
    """Mock controller manager client."""

    pass


class MockSettingsClient:
    """Mock settings client."""

    pass


class MockAudioClient:
    """Mock audio client."""

    pass


class TestGameFactoryCreateGame:
    """Tests for GameFactory.create_game method."""

    def test_create_ffa_game(self):
        """create_game should create FFA game."""
        game = GameFactory.create_game(
            game_name="FFA",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_001",
            initial_players=[],
        )

        assert game.get_game_name() == "FFA"

    def test_create_tournament_game(self):
        """create_game should create Tournament game."""
        game = GameFactory.create_game(
            game_name="Tournament",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_002",
            initial_players=[],
        )

        assert game.get_game_name() == "Tournament"

    def test_create_zombie_game(self):
        """create_game should create Zombie game."""
        game = GameFactory.create_game(
            game_name="Zombies",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_003",
            initial_players=[],
        )

        assert game.get_game_name() == "Zombie"

    def test_create_swapper_game(self):
        """create_game should create Swapper game."""
        game = GameFactory.create_game(
            game_name="Swapper",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_004",
            initial_players=[],
        )

        assert game.get_game_name() == "Swapper"

    def test_create_fight_club_game(self):
        """create_game should create Fight Club game."""
        game = GameFactory.create_game(
            game_name="FightClub",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_005",
            initial_players=[],
        )

        assert game.get_game_name() == "Fight Club"

    def test_create_traitor_game(self):
        """create_game should create Traitor game."""
        game = GameFactory.create_game(
            game_name="Traitor",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_006",
            initial_players=[],
        )

        assert game.get_game_name() == "Traitor"

    def test_create_werewolf_game(self):
        """create_game should create Werewolf game."""
        game = GameFactory.create_game(
            game_name="Werewolf",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_007",
            initial_players=[],
        )

        assert game.get_game_name() == "Werewolf"

    def test_nonstop_is_valid_mode(self):
        """NonStop should be a valid mode (skipping creation - see #TBD)."""
        # Note: NonstopJoustGame doesn't accept initial_players parameter
        # This tests that the mode is valid without instantiation
        assert GameFactory.is_valid_mode("NonStop") is True


class TestGameFactoryTeamGames:
    """Tests for team game creation."""

    def test_create_teams_game_default_teams(self):
        """create_game should create Teams game with default 2 teams."""
        game = GameFactory.create_game(
            game_name="JoustTeams",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_teams_001",
            initial_players=[],
        )

        assert game.num_teams == 2

    def test_create_teams_game_custom_teams(self):
        """create_game should create Teams game with custom team count."""
        game = GameFactory.create_game(
            game_name="JoustTeams",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_teams_002",
            initial_players=[],
            game_settings={"num_teams": "4"},
        )

        assert game.num_teams == 4

    def test_create_random_teams_game(self):
        """create_game should create Random Teams game."""
        game = GameFactory.create_game(
            game_name="JoustRandomTeams",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_random_teams",
            initial_players=[],
            game_settings={"num_teams": "3"},
        )

        assert game.num_teams == 3


class TestGameFactoryCaseInsensitive:
    """Tests for case-insensitive name resolution."""

    def test_lowercase_name(self):
        """create_game should accept lowercase names."""
        game = GameFactory.create_game(
            game_name="ffa",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_lower",
            initial_players=[],
        )

        assert game.get_game_name() == "FFA"

    def test_uppercase_name(self):
        """create_game should accept uppercase names."""
        game = GameFactory.create_game(
            game_name="TOURNAMENT",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_upper",
            initial_players=[],
        )

        assert game.get_game_name() == "Tournament"

    def test_mixed_case_name(self):
        """create_game should accept mixed case names."""
        game = GameFactory.create_game(
            game_name="ZoMbIeS",
            controller_manager_client=MockControllerManagerClient(),
            settings_client=MockSettingsClient(),
            event_publisher=lambda *_args: None,
            audio_client=MockAudioClient(),
            game_id="test_mixed",
            initial_players=[],
        )

        assert game.get_game_name() == "Zombie"


class TestGameFactoryErrors:
    """Tests for error handling."""

    def test_unknown_mode_raises_value_error(self):
        """create_game should raise ValueError for unknown mode."""
        with pytest.raises(ValueError, match="Unknown game mode"):
            GameFactory.create_game(
                game_name="NonexistentMode",
                controller_manager_client=MockControllerManagerClient(),
                settings_client=MockSettingsClient(),
                event_publisher=lambda *_args: None,
                audio_client=MockAudioClient(),
                game_id="test_error",
                initial_players=[],
            )

    def test_empty_name_raises_value_error(self):
        """create_game should raise ValueError for empty name."""
        with pytest.raises(ValueError, match="Unknown game mode"):
            GameFactory.create_game(
                game_name="",
                controller_manager_client=MockControllerManagerClient(),
                settings_client=MockSettingsClient(),
                event_publisher=lambda *_args: None,
                audio_client=MockAudioClient(),
                game_id="test_empty",
                initial_players=[],
            )


class TestGameFactoryGetSupportedModes:
    """Tests for get_supported_modes method."""

    def test_returns_list(self):
        """get_supported_modes should return a list."""
        modes = GameFactory.get_supported_modes()

        assert isinstance(modes, list)

    def test_includes_ffa(self):
        """get_supported_modes should include JoustFFA."""
        modes = GameFactory.get_supported_modes()

        assert "JoustFFA" in modes

    def test_includes_tournament(self):
        """get_supported_modes should include Tournament."""
        modes = GameFactory.get_supported_modes()

        assert "Tournament" in modes

    def test_includes_all_implemented(self):
        """get_supported_modes should include all implemented modes."""
        modes = GameFactory.get_supported_modes()

        expected = [
            "JoustFFA",
            "JoustTeams",
            "JoustRandomTeams",
            "Traitor",
            "Werewolf",
            "Zombies",
            "Swapper",
            "FightClub",
            "Tournament",
            "NonStop",
        ]

        for mode in expected:
            assert mode in modes


class TestGameFactoryIsValidMode:
    """Tests for is_valid_mode method."""

    def test_valid_mode_returns_true(self):
        """is_valid_mode should return True for valid mode."""
        assert GameFactory.is_valid_mode("FFA") is True
        assert GameFactory.is_valid_mode("Tournament") is True
        assert GameFactory.is_valid_mode("Zombies") is True

    def test_invalid_mode_returns_false(self):
        """is_valid_mode should return False for invalid mode."""
        assert GameFactory.is_valid_mode("NonexistentMode") is False
        assert GameFactory.is_valid_mode("") is False

    def test_case_insensitive(self):
        """is_valid_mode should be case insensitive."""
        assert GameFactory.is_valid_mode("ffa") is True
        assert GameFactory.is_valid_mode("FFA") is True
        assert GameFactory.is_valid_mode("Ffa") is True


class TestGameFactoryGetGameMode:
    """Tests for get_game_mode method."""

    def test_returns_enum_for_valid(self):
        """get_game_mode should return Games enum for valid name."""
        result = GameFactory.get_game_mode("FFA")

        assert result == Games.JoustFFA

    def test_returns_none_for_invalid(self):
        """get_game_mode should return None for invalid name."""
        result = GameFactory.get_game_mode("NonexistentMode")

        assert result is None

    def test_case_insensitive(self):
        """get_game_mode should be case insensitive."""
        result1 = GameFactory.get_game_mode("ffa")
        result2 = GameFactory.get_game_mode("FFA")
        result3 = GameFactory.get_game_mode("Ffa")

        assert result1 == result2 == result3 == Games.JoustFFA


class TestGameFactoryAliases:
    """Tests for game name aliases via Games enum."""

    def test_joust_ffa_alias(self):
        """JoustFFA should be recognized."""
        assert GameFactory.is_valid_mode("JoustFFA") is True

    def test_fight_club_alias(self):
        """FightClub should be recognized."""
        assert GameFactory.is_valid_mode("FightClub") is True

    def test_non_stop_alias(self):
        """NonStop should be recognized."""
        assert GameFactory.is_valid_mode("NonStop") is True
