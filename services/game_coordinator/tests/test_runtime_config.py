import logging
from unittest.mock import ANY, MagicMock, patch

import pytest

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


@patch("openfeature.api.add_handler")
@patch("lib.feature_flags.get_feature_flag_client")
def test_runtime_config_flag_updates(mock_get_client, mock_add_handler):
    """Test that config updates when flags are evaluated."""
    # Setup mock client
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # Configure mock evaluations
    # get_integer_value(flag_key, default_value, context)
    mock_client.get_integer_value.return_value = 30
    # get_string_value(flag_key, default_value, context)
    mock_client.get_string_value.return_value = "HIGH"

    manager = RuntimeConfigManager()
    config = manager.get_config()

    # Verify event handler was registered
    mock_add_handler.assert_called_once()

    # Verify mock was called with correct keys and EvaluationContext
    mock_client.get_integer_value.assert_any_call("update_frequency_hz", 60, ANY)
    mock_client.get_string_value.assert_any_call("sensitivity_mode", "MEDIUM", ANY)

    # Verify values were updated
    assert config.update_frequency_hz == 30
    assert config.sensitivity_mode == "HIGH"


@patch("openfeature.api.add_handler")
def test_runtime_config_flag_error_fallback(_mock_add_handler, caplog):
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


@patch("openfeature.api.add_handler")
@patch("lib.feature_flags.get_feature_flag_client")
def test_on_flags_changed_event(mock_get_client, _mock_add_handler, caplog):
    """Test that _on_flags_changed updates config when event fires."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # Initial values
    mock_client.get_integer_value.return_value = 60
    mock_client.get_string_value.return_value = "MEDIUM"

    manager = RuntimeConfigManager()
    config = manager.get_config()
    assert config.update_frequency_hz == 60

    # Simulate flag change
    mock_client.get_integer_value.return_value = 30
    mock_client.get_string_value.return_value = "HIGH"

    # Trigger event handler
    mock_event = MagicMock()
    mock_event.flags_changed = ["update_frequency_hz", "sensitivity_mode"]

    with caplog.at_level(logging.INFO):
        manager._on_flags_changed(mock_event)

    # Verify config was updated
    config = manager.get_config()
    assert config.update_frequency_hz == 30
    assert config.sensitivity_mode == "HIGH"
    assert "Feature flags changed" in caplog.text


@patch("openfeature.api.add_handler")
@patch("lib.feature_flags.get_feature_flag_client")
def test_on_flags_changed_no_flag_list(mock_get_client, _mock_add_handler, caplog):
    """Test that _on_flags_changed works when flags_changed is empty."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.get_integer_value.return_value = 45
    mock_client.get_string_value.return_value = "LOW"

    manager = RuntimeConfigManager()

    # Trigger event handler without flags_changed attribute
    mock_event = MagicMock()
    mock_event.flags_changed = []

    with caplog.at_level(logging.INFO):
        manager._on_flags_changed(mock_event)

    assert "unspecified flags" in caplog.text


@pytest.mark.asyncio
async def test_get_update_interval():
    """Test get_update_interval returns correct interval."""
    manager = RuntimeConfigManager()
    manager.config.update_frequency_hz = 60

    interval = await manager.get_update_interval()
    assert interval == 1.0 / 60


@pytest.mark.asyncio
async def test_get_update_interval_custom_hz():
    """Test get_update_interval with custom frequency."""
    manager = RuntimeConfigManager()
    manager.config.update_frequency_hz = 30

    interval = await manager.get_update_interval()
    assert interval == 1.0 / 30


def test_export_config():
    """Test export_config returns dict copy."""
    manager = RuntimeConfigManager()
    manager.config.update_frequency_hz = 45
    manager.config.sensitivity_mode = "HIGH"

    exported = manager.export_config()

    assert isinstance(exported, dict)
    assert exported["update_frequency_hz"] == 45
    assert exported["sensitivity_mode"] == "HIGH"


def test_get_config_manager_singleton():
    """Test get_config_manager returns singleton."""
    from services.game_coordinator.runtime_config import get_config_manager

    manager1 = get_config_manager()
    manager2 = get_config_manager()

    assert manager1 is manager2


def test_get_current_config():
    """Test get_current_config convenience function."""
    from services.game_coordinator.runtime_config import get_current_config

    config = get_current_config()
    assert isinstance(config, GamePerformanceConfig)


def test_env_override_invalid_countdown(caplog):
    """Test that invalid countdown env var is handled gracefully."""
    with patch.dict("os.environ", {"COUNTDOWN_DURATION_SECONDS": "invalid"}):
        with caplog.at_level(logging.WARNING):
            manager = RuntimeConfigManager()

        assert "Invalid COUNTDOWN_DURATION_SECONDS" in caplog.text
        assert manager.config.countdown_duration_seconds == 3  # Default


def test_env_override_invalid_rainbow(caplog):
    """Test that invalid rainbow duration env var is handled gracefully."""
    with patch.dict("os.environ", {"WINNER_RAINBOW_DURATION_MS": "not_a_number"}):
        with caplog.at_level(logging.WARNING):
            manager = RuntimeConfigManager()

        assert "Invalid WINNER_RAINBOW_DURATION_MS" in caplog.text
        assert manager.config.winner_rainbow_duration_ms == 3000  # Default


def test_setup_feature_flags_import_error(caplog):
    """Test that ImportError in _setup_feature_flags is handled."""
    with patch("lib.feature_flags.get_feature_flag_client", side_effect=ImportError("no module")):
        with caplog.at_level(logging.WARNING):
            manager = RuntimeConfigManager()

        assert manager.flag_client is None
        assert "Could not import FeatureFlagClient" in caplog.text


@patch("openfeature.api.add_handler")
def test_setup_feature_flags_generic_error(_mock_add_handler, caplog):
    """Test that generic exceptions in _setup_feature_flags are handled."""
    with patch("lib.feature_flags.get_feature_flag_client", side_effect=RuntimeError("startup failed")):
        with caplog.at_level(logging.ERROR):
            manager = RuntimeConfigManager()

        assert manager.flag_client is None
        assert "Failed to initialize feature flags" in caplog.text


@patch("openfeature.api.add_handler")
@patch("lib.feature_flags.get_feature_flag_client")
def test_refresh_from_flags_with_metrics(mock_get_client, _mock_add_handler):
    """Test that _refresh_from_flags tracks metrics on changes."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # First call returns 60, second call returns 45 (change)
    mock_client.get_integer_value.side_effect = [60, 45]
    mock_client.get_string_value.side_effect = ["MEDIUM", "HIGH"]

    with patch("services.game_coordinator.metrics.config_changes_total") as mock_changes, patch(
        "services.game_coordinator.metrics.flag_evaluations_total"
    ) as mock_evaluations, patch("services.game_coordinator.metrics.current_update_frequency_hz") as mock_gauge:
        manager = RuntimeConfigManager()

        # Verify initial setup called metrics
        assert mock_evaluations.labels.called
        assert mock_gauge.set.called

        # Trigger another refresh with different values
        manager._refresh_from_flags()

        # Should track config changes
        mock_changes.labels.assert_any_call(parameter="update_frequency_hz")
        mock_changes.labels.assert_any_call(parameter="sensitivity_mode")


@patch("openfeature.api.add_handler")
@patch("lib.feature_flags.get_feature_flag_client")
def test_on_flags_changed_with_metrics(mock_get_client, _mock_add_handler):
    """Test that _on_flags_changed increments metrics."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.get_integer_value.return_value = 60
    mock_client.get_string_value.return_value = "MEDIUM"

    with patch("services.game_coordinator.metrics.flag_configuration_changes_total") as mock_counter:
        manager = RuntimeConfigManager()

        # Trigger event
        mock_event = MagicMock()
        mock_event.flags_changed = ["some_flag"]
        manager._on_flags_changed(mock_event)

        # Should increment counter
        mock_counter.inc.assert_called()


def test_refresh_from_flags_no_client():
    """Test that _refresh_from_flags does nothing when flag_client is None."""
    manager = RuntimeConfigManager()
    manager.flag_client = None

    # Should not raise exception
    manager._refresh_from_flags()
