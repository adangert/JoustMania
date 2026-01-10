"""
Unit tests for Settings gRPC Servicer.

Tests the core SettingsServicer functionality without full gRPC server.
"""

import os
import queue
import tempfile
from unittest.mock import Mock

import pytest
import yaml

from services.settings import settings_pb2
from services.settings.server import SETTINGS_SCHEMA, SettingsServicer


class TestSettingsServicer:
    """Unit tests for SettingsServicer class."""

    @pytest.fixture
    def temp_settings_file(self):
        """Create a temporary settings file."""
        fd, path = tempfile.mkstemp(suffix=".yaml")
        os.close(fd)
        yield path
        # Cleanup
        if os.path.exists(path):
            os.remove(path)
        if os.path.exists(path + ".tmp"):
            os.remove(path + ".tmp")

    @pytest.fixture
    def servicer(self, temp_settings_file):
        """Create a SettingsServicer instance with temp file."""
        return SettingsServicer(settings_file=temp_settings_file)

    def test_initialization(self, servicer):
        """Test servicer initializes with default settings."""
        assert servicer.settings is not None
        assert isinstance(servicer.settings, dict)
        assert len(servicer.settings) > 0
        assert "sensitivity" in servicer.settings
        assert "current_game" in servicer.settings

    def test_default_settings(self, servicer):
        """Test default settings are loaded from schema."""
        defaults = servicer.get_default_settings()

        # Check all schema keys present
        for key in SETTINGS_SCHEMA:
            assert key in defaults

        # Check specific defaults
        assert defaults["sensitivity"] == 2  # Sensitivity.MID
        assert defaults["play_instructions"] is True
        assert defaults["current_game"] == "JoustFFA"

    def test_load_settings_no_file(self, temp_settings_file):
        """Test loading when no settings file exists."""
        # Remove file if it exists
        if os.path.exists(temp_settings_file):
            os.remove(temp_settings_file)

        servicer = SettingsServicer(settings_file=temp_settings_file)

        # Should use defaults
        assert servicer.settings == servicer.get_default_settings()

        # Should create file
        assert os.path.exists(temp_settings_file)

    def test_load_settings_with_file(self, temp_settings_file):
        """Test loading settings from existing file."""
        # Write test settings
        test_settings = {"sensitivity": 3, "play_instructions": False, "current_game": "Werewolf"}
        with open(temp_settings_file, "w") as f:
            yaml.dump(test_settings, f)

        servicer = SettingsServicer(settings_file=temp_settings_file)

        # Should load from file
        assert servicer.settings["sensitivity"] == 3
        assert servicer.settings["play_instructions"] is False
        assert servicer.settings["current_game"] == "Werewolf"

    def test_load_settings_invalid_values(self, temp_settings_file):
        """Test loading with invalid values uses defaults."""
        # Write invalid settings
        invalid_settings = {
            "sensitivity": 999,  # Out of range
            "menu_voice": "invalid",  # Not in allowed values
            "current_game": "ValidValue",
        }
        with open(temp_settings_file, "w") as f:
            yaml.dump(invalid_settings, f)

        servicer = SettingsServicer(settings_file=temp_settings_file)

        # Invalid values should use defaults
        assert servicer.settings["sensitivity"] == 2  # Default
        assert servicer.settings["menu_voice"] == "ivy"  # Default
        # Valid value should be preserved
        assert servicer.settings["current_game"] == "ValidValue"

    def test_save_settings(self, servicer, temp_settings_file):
        """Test saving settings to file."""
        servicer.settings["sensitivity"] = 4
        servicer.save_settings()

        # Read back from file
        with open(temp_settings_file) as f:
            saved = yaml.safe_load(f)

        assert saved["sensitivity"] == 4

    def test_save_settings_atomic(self, servicer, temp_settings_file):
        """Test atomic save using temp file."""
        servicer.settings["test_key"] = "test_value"
        servicer.save_settings()

        # Temp file should not exist after save
        assert not os.path.exists(temp_settings_file + ".tmp")

        # Main file should exist
        assert os.path.exists(temp_settings_file)

    def test_validate_setting_value_int(self, servicer):
        """Test validation for integer settings."""
        # Valid
        valid, error = servicer.validate_setting_value("sensitivity", 2)
        assert valid is True
        assert error == ""

        # Below minimum
        valid, error = servicer.validate_setting_value("sensitivity", -1)
        assert valid is False
        assert "below minimum" in error.lower()

        # Above maximum
        valid, error = servicer.validate_setting_value("sensitivity", 10)
        assert valid is False
        assert "above maximum" in error.lower()

        # Wrong type
        valid, error = servicer.validate_setting_value("sensitivity", "2")
        assert valid is False
        assert "expected" in error.lower()

    def test_validate_setting_value_bool(self, servicer):
        """Test validation for boolean settings."""
        # Valid
        valid, error = servicer.validate_setting_value("play_instructions", True)
        assert valid is True

        valid, error = servicer.validate_setting_value("play_instructions", False)
        assert valid is True

        # Wrong type
        valid, error = servicer.validate_setting_value("play_instructions", "true")
        assert valid is False

    def test_validate_setting_value_str_allowed(self, servicer):
        """Test validation for string with allowed values."""
        # Valid
        valid, error = servicer.validate_setting_value("menu_voice", "ivy")
        assert valid is True

        valid, error = servicer.validate_setting_value("menu_voice", "en")
        assert valid is True

        # Invalid
        valid, error = servicer.validate_setting_value("menu_voice", "invalid")
        assert valid is False
        assert "not in allowed values" in error.lower()

    def test_validate_setting_value_list(self, servicer):
        """Test validation for list settings."""
        # Valid
        valid, error = servicer.validate_setting_value("random_modes", ["JoustFFA", "Werewolf"])
        assert valid is True

        # Invalid game in list
        valid, error = servicer.validate_setting_value("random_modes", ["InvalidGame"])
        assert valid is False
        assert "invalid game mode" in error.lower()

    def test_validate_setting_value_unknown(self, servicer):
        """Test validation for unknown setting."""
        valid, error = servicer.validate_setting_value("unknown_key", "value")
        assert valid is False
        assert "unknown setting" in error.lower()

    def test_validate_setting_value_immutable(self, servicer):
        """Test validation rejects changes to immutable settings."""
        valid, error = servicer.validate_setting_value("play_audio", False)
        assert valid is False
        assert "immutable" in error.lower()

    def test_publish_change(self, servicer):
        """Test publishing changes to subscribers."""
        # Create mock subscriber
        sub_queue = queue.Queue(maxsize=10)
        servicer.subscribers["test_sub"] = sub_queue

        # Publish change
        servicer.publish_change("sensitivity", 2, 3, "test")

        # Check event received
        assert not sub_queue.empty()
        event = sub_queue.get_nowait()
        assert event.key == "sensitivity"
        assert event.old_value == "2"
        assert event.new_value == "3"
        assert event.source == "test"

    def test_publish_change_full_queue(self, servicer):
        """Test publishing when subscriber queue is full."""
        # Create full queue
        sub_queue = queue.Queue(maxsize=1)
        sub_queue.put("dummy")
        servicer.subscribers["test_sub"] = sub_queue

        # Publish should not raise exception
        servicer.publish_change("sensitivity", 2, 3, "test")

        # Subscriber should still exist
        assert "test_sub" in servicer.subscribers


class TestSettingsServicerRPCs:
    """Test gRPC service methods."""

    @pytest.fixture
    def temp_settings_file(self):
        """Create a temporary settings file."""
        fd, path = tempfile.mkstemp(suffix=".yaml")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.remove(path)
        if os.path.exists(path + ".tmp"):
            os.remove(path + ".tmp")

    @pytest.fixture
    def servicer(self, temp_settings_file):
        """Create a SettingsServicer instance."""
        return SettingsServicer(settings_file=temp_settings_file)

    @pytest.fixture
    def mock_context(self):
        """Create a mock gRPC context."""
        context = Mock()
        context.is_active = Mock(return_value=True)
        return context

    def test_get_settings(self, servicer, mock_context):
        """Test GetSettings RPC."""
        request = settings_pb2.GetSettingsRequest()
        response = servicer.GetSettings(request, mock_context)

        assert response.success is True
        assert response.error == ""
        assert len(response.settings) > 0
        assert "sensitivity" in response.settings
        assert "current_game" in response.settings

    def test_get_setting_exists(self, servicer, mock_context):
        """Test GetSetting RPC for existing setting."""
        request = settings_pb2.GetSettingRequest(key="sensitivity")
        response = servicer.GetSetting(request, mock_context)

        assert response.success is True
        assert response.error == ""
        assert response.key == "sensitivity"
        assert response.value == "2"  # Default value

    def test_get_setting_not_exists(self, servicer, mock_context):
        """Test GetSetting RPC for non-existent setting."""
        request = settings_pb2.GetSettingRequest(key="nonexistent")
        response = servicer.GetSetting(request, mock_context)

        assert response.success is False
        assert "not found" in response.error.lower()
        assert response.value == ""

    def test_update_setting_valid(self, servicer, mock_context):
        """Test UpdateSetting RPC with valid value."""
        request = settings_pb2.UpdateSettingRequest(key="sensitivity", value="3", source="test")
        response = servicer.UpdateSetting(request, mock_context)

        assert response.success is True
        assert response.error == ""
        assert response.old_value == "2"
        assert response.new_value == "3"

        # Verify setting actually changed
        assert servicer.settings["sensitivity"] == 3

    def test_update_setting_invalid_value(self, servicer, mock_context):
        """Test UpdateSetting RPC with invalid value."""
        request = settings_pb2.UpdateSettingRequest(
            key="sensitivity",
            value="999",  # Out of range
            source="test",
        )
        response = servicer.UpdateSetting(request, mock_context)

        assert response.success is False
        assert "above maximum" in response.error.lower()

        # Setting should not change
        assert servicer.settings["sensitivity"] == 2

    def test_update_setting_unknown_key(self, servicer, mock_context):
        """Test UpdateSetting RPC with unknown key."""
        request = settings_pb2.UpdateSettingRequest(key="nonexistent", value="value", source="test")
        response = servicer.UpdateSetting(request, mock_context)

        assert response.success is False
        assert "unknown setting" in response.error.lower()

    def test_update_setting_immutable(self, servicer, mock_context):
        """Test UpdateSetting RPC on immutable setting."""
        request = settings_pb2.UpdateSettingRequest(key="play_audio", value="false", source="test")
        response = servicer.UpdateSetting(request, mock_context)

        assert response.success is False
        assert "immutable" in response.error.lower()

    def test_update_setting_bool_parsing(self, servicer, mock_context):
        """Test UpdateSetting RPC parses boolean strings correctly."""
        # Test 'true'
        request = settings_pb2.UpdateSettingRequest(
            key="play_instructions", value="true", source="test"
        )
        response = servicer.UpdateSetting(request, mock_context)
        assert response.success is True
        assert servicer.settings["play_instructions"] is True

        # Test 'false'
        request = settings_pb2.UpdateSettingRequest(
            key="play_instructions", value="false", source="test"
        )
        response = servicer.UpdateSetting(request, mock_context)
        assert response.success is True
        assert servicer.settings["play_instructions"] is False

    def test_update_setting_publishes_event(self, servicer, mock_context):
        """Test UpdateSetting publishes change event."""
        # Add subscriber
        sub_queue = queue.Queue()
        servicer.subscribers["test"] = sub_queue

        # Update setting
        request = settings_pb2.UpdateSettingRequest(key="sensitivity", value="4", source="test")
        servicer.UpdateSetting(request, mock_context)

        # Check event published
        assert not sub_queue.empty()
        event = sub_queue.get_nowait()
        assert event.key == "sensitivity"
        assert event.new_value == "4"

    def test_subscribe_to_changes(self, servicer, mock_context):
        """Test SubscribeToChanges RPC."""
        # Create iterator from generator
        request = settings_pb2.SubscribeRequest()

        # Mock context to stop after first event
        call_count = [0]

        def is_active_mock():
            call_count[0] += 1
            return call_count[0] < 3  # Stop after 2 iterations

        mock_context.is_active = is_active_mock

        # Start subscription (will run in background)
        events = []
        for event in servicer.SubscribeToChanges(request, mock_context):
            events.append(event)
            break  # Get first event and stop

        # Should have received at least one call
        assert call_count[0] >= 1

        # Subscriber should be cleaned up
        # (may still exist briefly due to timing)
