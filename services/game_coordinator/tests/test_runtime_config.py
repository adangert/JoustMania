import logging
from unittest.mock import MagicMock, patch

from services.game_coordinator.runtime_config import GamePerformanceConfig, RuntimeConfigManager


def test_runtime_config_defaults():
    """Test that RuntimeConfigManager initializes with defaults when no flags are available."""
    manager = RuntimeConfigManager()
    config = manager.get_config()

    assert isinstance(config, GamePerformanceConfig)
    assert config.update_frequency_hz == 60
    assert config.sensitivity_mode == "MEDIUM"


def test_runtime_config_env_overrides():
    """Test that environment variables still override defaults."""
    with patch.dict("os.environ", {"COUNTDOWN_DURATION_SECONDS": "5", "WINNER_RAINBOW_DURATION_MS": "500"}):
        manager = RuntimeConfigManager()
        config = manager.get_config()

        assert config.countdown_duration_seconds == 5
        assert config.winner_rainbow_duration_ms == 500


@patch("lib.feature_flags.get_feature_flag_client")
def test_runtime_config_flag_updates(mock_get_client):
    """Test that config updates when flags are evaluated."""
    # Setup mock client
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # Configure mock evaluations
    # get_integer_value(flag_key, default_value)
    mock_client.get_integer_value.return_value = 30
    # get_string_value(flag_key, default_value)
    mock_client.get_string_value.return_value = "HIGH"

    manager = RuntimeConfigManager()
    config = manager.get_config()

    # Verify mock was called with correct keys
    mock_client.get_integer_value.assert_any_call("update_frequency_hz", 60)
    mock_client.get_string_value.assert_any_call("sensitivity_mode", "MEDIUM")

    # Verify values were updated
    assert config.update_frequency_hz == 30
    assert config.sensitivity_mode == "HIGH"


def test_runtime_config_flag_error_fallback(caplog):
    """Test that config stays at default if flag evaluation fails."""
    with patch("lib.feature_flags.get_feature_flag_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_integer_value.side_effect = Exception("flagd unreachable")

        manager = RuntimeConfigManager()
        with caplog.at_level(logging.WARNING):
            config = manager.get_config()

        assert "Failed to evaluate flags" in caplog.text
        assert config.update_frequency_hz == 60  # Stayed at default
