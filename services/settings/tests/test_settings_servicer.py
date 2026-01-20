"""
Unit tests for Settings gRPC Servicer.

Tests the core SettingsServicer functionality without full gRPC server.
"""

import asyncio
import os
import tempfile
from unittest.mock import Mock

import pytest
import yaml

from proto import settings_pb2
from services.settings.servicer import SETTINGS_SCHEMA, SettingsServicer


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
        assert defaults["sensitivity"] == 2  # Sensitivity.MEDIUM
        assert defaults["instructions"] is True
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
        test_settings = {"sensitivity": 3, "instructions": False, "current_game": "Werewolf"}
        with open(temp_settings_file, "w") as f:
            yaml.dump(test_settings, f)

        servicer = SettingsServicer(settings_file=temp_settings_file)

        # Should load from file
        assert servicer.settings["sensitivity"] == 3
        assert servicer.settings["instructions"] is False
        assert servicer.settings["current_game"] == "Werewolf"

    def test_load_settings_invalid_values(self, temp_settings_file):
        """Test loading with invalid values uses defaults."""
        # Write invalid settings
        invalid_settings = {
            "sensitivity": 999,  # Out of range
            "menu_voice": "invalid",  # Not in allowed values
            "current_game": "JoustFFA",  # Valid value
        }
        with open(temp_settings_file, "w") as f:
            yaml.dump(invalid_settings, f)

        servicer = SettingsServicer(settings_file=temp_settings_file)

        # Invalid values should use defaults
        assert servicer.settings["sensitivity"] == 2  # Default
        assert servicer.settings["menu_voice"] == "ivy"  # Default
        # Valid value should be preserved
        assert servicer.settings["current_game"] == "JoustFFA"

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
        servicer.settings["sensitivity"] = 3
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
        valid, error = servicer.validate_setting_value("instructions", True)
        assert valid is True

        valid, error = servicer.validate_setting_value("instructions", False)
        assert valid is True

        # Wrong type
        valid, error = servicer.validate_setting_value("instructions", "true")
        assert valid is False

    def test_validate_setting_value_str_allowed(self, servicer):
        """Test validation for string with allowed values."""
        # Valid
        valid, error = servicer.validate_setting_value("menu_voice", "ivy")
        assert valid is True

        valid, error = servicer.validate_setting_value("menu_voice", "aaron")
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

    def test_clear_one_controller_preserves_others(self):
        """Test clearing one controller doesn't affect others."""
        # This test doesn't apply to settings - removed


@pytest.mark.asyncio
class TestSettingsServicerAsync:
    """Async tests for SettingsServicer."""

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

    async def test_publish_change(self, servicer):
        """Test publishing changes to subscribers."""
        # Create mock subscriber
        sub_queue = asyncio.Queue(maxsize=10)
        servicer.subscribers["test_sub"] = sub_queue

        # Publish change
        await servicer.publish_change("sensitivity", 2, 3, "test")

        # Check event received
        assert not sub_queue.empty()
        event = await sub_queue.get()
        assert event.key == "sensitivity"
        assert event.old_value == "2"
        assert event.new_value == "3"
        assert event.source == "test"

    async def test_publish_change_full_queue(self, servicer):
        """Test publishing when subscriber queue is full."""
        # Create full queue
        sub_queue = asyncio.Queue(maxsize=1)
        await sub_queue.put("dummy")
        servicer.subscribers["test_sub"] = sub_queue

        # Publish should not raise exception
        await servicer.publish_change("sensitivity", 2, 3, "test")

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
        context.cancelled = Mock(return_value=False)
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


@pytest.mark.asyncio
class TestSettingsServicerRPCsAsync:
    """Async tests for gRPC service methods."""

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
        context.cancelled = Mock(return_value=False)
        return context

    async def test_update_setting_valid(self, servicer, mock_context):
        """Test UpdateSetting RPC with valid value."""
        request = settings_pb2.UpdateSettingRequest(key="sensitivity", value="3", source="test")
        response = await servicer.UpdateSetting(request, mock_context)

        assert response.success is True
        assert response.error == ""
        assert response.old_value == "2"
        assert response.new_value == "3"

        # Verify setting actually changed
        assert servicer.settings["sensitivity"] == 3

    async def test_update_setting_invalid_value(self, servicer, mock_context):
        """Test UpdateSetting RPC with invalid value."""
        request = settings_pb2.UpdateSettingRequest(
            key="sensitivity",
            value="999",  # Out of range
            source="test",
        )
        response = await servicer.UpdateSetting(request, mock_context)

        assert response.success is False
        assert "above maximum" in response.error.lower()

        # Setting should not change
        assert servicer.settings["sensitivity"] == 2

    async def test_update_setting_unknown_key(self, servicer, mock_context):
        """Test UpdateSetting RPC with unknown key."""
        request = settings_pb2.UpdateSettingRequest(key="nonexistent", value="value", source="test")
        response = await servicer.UpdateSetting(request, mock_context)

        assert response.success is False
        assert "unknown setting" in response.error.lower()

    async def test_update_setting_bool_parsing(self, servicer, mock_context):
        """Test UpdateSetting RPC parses boolean strings correctly."""
        # Test 'true'
        request = settings_pb2.UpdateSettingRequest(key="instructions", value="true", source="test")
        response = await servicer.UpdateSetting(request, mock_context)
        assert response.success is True
        assert servicer.settings["instructions"] is True

        # Test 'false'
        request = settings_pb2.UpdateSettingRequest(key="instructions", value="false", source="test")
        response = await servicer.UpdateSetting(request, mock_context)
        assert response.success is True
        assert servicer.settings["instructions"] is False

    async def test_update_setting_publishes_event(self, servicer, mock_context):
        """Test UpdateSetting publishes change event."""
        # Add subscriber
        sub_queue = asyncio.Queue()
        servicer.subscribers["test"] = sub_queue

        # Update setting
        request = settings_pb2.UpdateSettingRequest(key="sensitivity", value="4", source="test")
        await servicer.UpdateSetting(request, mock_context)

        # Check event published
        assert not sub_queue.empty()
        event = await sub_queue.get()
        assert event.key == "sensitivity"
        assert event.new_value == "4"
