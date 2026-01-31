import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add lib to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.feature_flags import FeatureFlagClient, get_feature_flag_client


def test_singleton():
    """Test that FeatureFlagClient is a singleton."""
    client1 = get_feature_flag_client()
    client2 = get_feature_flag_client()
    assert client1 is client2


@patch("lib.feature_flags.FlagdProvider")
@patch("lib.feature_flags.api")
def test_initialization(mock_api, mock_provider):
    """Test client initialization."""
    # Reset singleton for test
    FeatureFlagClient._instance = None
    _client = FeatureFlagClient()

    # Check if provider was set with expected defaults for in-process
    mock_api.set_provider.assert_called_once()
    from openfeature.contrib.provider.flagd.config import ResolverType
    mock_provider.assert_called_once()
    args, kwargs = mock_provider.call_args
    assert kwargs["port"] == 8015
    assert kwargs["resolver_type"] == ResolverType.IN_PROCESS

    mock_api.get_client.assert_called_with()


@patch("lib.feature_flags.api")
def test_evaluation_methods(mock_api):
    """Test evaluation helper methods."""
    # Reset singleton
    FeatureFlagClient._instance = None
    mock_client = MagicMock()
    mock_api.get_client.return_value = mock_client

    client = FeatureFlagClient()

    # Boolean
    mock_client.get_boolean_value.return_value = True
    assert client.get_boolean_value("flag", False) is True
    mock_client.get_boolean_value.assert_called_with("flag", False, None)

    # String
    mock_client.get_string_value.return_value = "variant"
    assert client.get_string_value("flag", "default") == "variant"
    mock_client.get_string_value.assert_called_with("flag", "default", None)

    # Integer
    mock_client.get_integer_value.return_value = 42
    assert client.get_integer_value("flag", 0) == 42
    mock_client.get_integer_value.assert_called_with("flag", 0, None)

    # Float
    mock_client.get_float_value.return_value = 3.14
    assert client.get_float_value("flag", 0.0) == 3.14
    mock_client.get_float_value.assert_called_with("flag", 0.0, None)

    # Object
    mock_client.get_object_value.return_value = {"key": "value"}
    assert client.get_object_value("flag", {}) == {"key": "value"}
    mock_client.get_object_value.assert_called_with("flag", {}, None)
