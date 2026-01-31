"""Unit tests for menu utility classes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.menu.utils.audio import GAME_MODE_VOICE, AudioHelper
from services.menu.utils.led import DEFAULT_COLOR, GAME_MODE_COLORS, LedController
from services.menu.utils.settings import GAME_MODES, SettingsHelper


class TestAudioHelper:
    """Tests for AudioHelper."""

    @pytest.fixture
    def audio(self):
        """Create AudioHelper instance."""
        return AudioHelper(MagicMock())

    def test_initialization(self, audio):
        """AudioHelper should initialize correctly."""
        assert audio.lobby_music_track_id is None

    @pytest.mark.asyncio
    async def test_play_sound_string(self, audio):
        """play_sound should handle string sound paths."""
        with patch("proto.audio_pb2_grpc.AudioServiceStub") as mock_stub_class:
            mock_stub = MagicMock()
            mock_stub.PlaySound = AsyncMock()
            mock_stub_class.return_value = mock_stub

            await audio.play_sound("test/sound.wav", volume=0.5)

            mock_stub.PlaySound.assert_called_once()

    @pytest.mark.asyncio
    async def test_play_game_mode_voice(self, audio):
        """play_game_mode_voice should play correct voice for game mode."""
        audio.play_voice = AsyncMock()

        await audio.play_game_mode_voice("JoustFFA")

        audio.play_voice.assert_called_once()
        assert audio.play_voice.call_args[0][0] == GAME_MODE_VOICE["JoustFFA"]

    @pytest.mark.asyncio
    async def test_play_game_mode_voice_unknown(self, audio):
        """play_game_mode_voice should handle unknown game modes."""
        audio.play_voice = AsyncMock()

        await audio.play_game_mode_voice("UnknownGame")

        audio.play_voice.assert_not_called()


class TestLedController:
    """Tests for LedController."""

    @pytest.fixture
    def led(self):
        """Create LedController instance."""
        return LedController(MagicMock())

    def test_get_game_color_known(self, led):
        """get_game_color should return correct color for known game."""
        color = led.get_game_color("JoustFFA")
        assert color == GAME_MODE_COLORS["JoustFFA"]

    def test_get_game_color_unknown(self, led):
        """get_game_color should return default for unknown game."""
        color = led.get_game_color("UnknownGame")
        assert color == DEFAULT_COLOR

    def test_dim_color(self, led):
        """dim_color should reduce brightness."""
        color = (100, 200, 255)
        dimmed = led.dim_color(color, 0.5)
        assert dimmed == (50, 100, 127)

    def test_set_stream(self, led):
        """set_stream should store queue reference."""
        queue = asyncio.Queue()
        led.set_stream(queue)
        assert led._stream_queue is queue

    @pytest.mark.asyncio
    async def test_send_base_color_no_stream(self, led):
        """send_base_color should return False when no stream."""
        result = await led.send_base_color("serial1", (255, 0, 0))
        assert result is False

    @pytest.mark.asyncio
    async def test_send_base_color_with_stream(self, led):
        """send_base_color should send message to stream queue."""
        queue = asyncio.Queue()
        led.set_stream(queue)

        result = await led.send_base_color("serial1", (255, 0, 0))

        assert result is True
        assert not queue.empty()

    @pytest.mark.asyncio
    async def test_set_connected_color(self, led):
        """set_connected_color should set dimmed game mode color."""
        led.set_color = AsyncMock(return_value=True)

        await led.set_connected_color("serial1", "JoustFFA")

        led.set_color.assert_called_once()
        call_color = led.set_color.call_args[0][1]
        expected = led.dim_color(GAME_MODE_COLORS["JoustFFA"])
        assert call_color == expected

    @pytest.mark.asyncio
    async def test_set_ready_color(self, led):
        """set_ready_color should set bright game mode color."""
        led.set_color = AsyncMock(return_value=True)

        await led.set_ready_color("serial1", "JoustFFA")

        led.set_color.assert_called_once_with("serial1", GAME_MODE_COLORS["JoustFFA"])


class TestSettingsHelper:
    """Tests for SettingsHelper."""

    @pytest.fixture
    def settings(self):
        """Create SettingsHelper instance."""
        return SettingsHelper(MagicMock())

    @pytest.mark.asyncio
    async def test_get_setting(self, settings):
        """get_setting should return setting value."""
        with patch("proto.settings_pb2_grpc.SettingsServiceStub") as mock_stub_class:
            mock_stub = MagicMock()
            mock_response = MagicMock()
            mock_response.value = "test_value"
            mock_stub.GetSetting = AsyncMock(return_value=mock_response)
            mock_stub_class.return_value = mock_stub

            result = await settings.get_setting("test_key")

            assert result == "test_value"

    @pytest.mark.asyncio
    async def test_load_voice_actor_valid(self, settings):
        """load_voice_actor should return valid voice actor."""
        settings.get_setting = AsyncMock(return_value="aaron")

        result = await settings.load_voice_actor()

        assert result == "aaron"

    @pytest.mark.asyncio
    async def test_load_voice_actor_default(self, settings):
        """load_voice_actor should return default when missing."""
        settings.get_setting = AsyncMock(return_value=None)

        result = await settings.load_voice_actor()

        assert result == "ivy"

    def test_get_next_game_mode_forward(self, settings):
        """get_next_game_mode should cycle forward."""
        from lib.types import Games

        current_idx = GAME_MODES.index("JoustFFA")
        expected_name = GAME_MODES[(current_idx + 1) % len(GAME_MODES)]

        result = settings.get_next_game_mode(Games.JoustFFA, forward=True)

        assert result.name == expected_name

    def test_get_next_game_mode_backward(self, settings):
        """get_next_game_mode should cycle backward."""
        from lib.types import Games

        current_idx = GAME_MODES.index("JoustFFA")
        expected_name = GAME_MODES[(current_idx - 1) % len(GAME_MODES)]

        result = settings.get_next_game_mode(Games.JoustFFA, forward=False)

        assert result.name == expected_name

    def test_is_valid_game_mode(self, settings):
        """is_valid_game_mode should validate game modes."""
        from lib.types import Games

        assert settings.is_valid_game_mode(Games.JoustFFA) is True
        assert settings.is_valid_game_mode(Games.Werewolf) is True


class TestGameModesConstant:
    """Test GAME_MODES constant."""

    def test_game_modes_not_empty(self):
        """GAME_MODES should not be empty."""
        assert len(GAME_MODES) > 0

    def test_game_modes_are_unique(self):
        """All game modes should be unique."""
        assert len(GAME_MODES) == len(set(GAME_MODES))

    def test_random_not_in_game_modes(self):
        """Random should not be in GAME_MODES (it's meta)."""
        assert "Random" not in GAME_MODES
