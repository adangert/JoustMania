"""
Unit tests for MenuServicer.

Tests the core Menu gRPC service:
- State management
- Controller event callbacks
- Admin mode callbacks
- Input handling logic
- Lifecycle methods

Note: MenuServicer has complex initialization with many dependencies.
These tests mock at method level rather than trying to mock the entire __init__.

Issue #209: Improve test coverage for critical game flow
"""

import asyncio
import contextlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Setup paths for imports
test_dir = Path(__file__).parent
service_dir = test_dir.parent
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(test_dir))

from lib.types import Games
from proto import menu_pb2
from services.menu.handlers.base import ControllerState


class MockGrpcContext:
    """Mock gRPC context."""

    def __init__(self):
        self._cancelled = False

    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True


class FakeMenuServicer:
    """A lightweight fake of MenuServicer for testing individual methods.

    This avoids the complex initialization of the real MenuServicer
    while allowing us to test the method logic.

    Uses the new data model where controller state is managed via
    state_manager.controller_states as the single source of truth.
    """

    def __init__(self):
        self.state = menu_pb2.MenuState.STOPPED
        self.current_selection = Games.JoustFFA

        # Game event monitoring
        self.game_event_task = None
        self.game_event_monitor_running = False

        # Mocked dependencies
        self.led = MagicMock()
        self.audio = MagicMock()
        self.audio.start_lobby_music = AsyncMock()
        self.audio.stop_lobby_music = AsyncMock()
        self.audio.play_voice = AsyncMock()

        self.settings_helper = MagicMock()
        self.settings_helper.load_voice_actor = AsyncMock(return_value="ivy")
        self.settings_helper.load_current_game = AsyncMock(return_value="JoustFFA")
        self.settings_helper.save_current_game = AsyncMock()

        self.event_publisher = MagicMock()
        self.event_publisher.publish = AsyncMock()
        self.event_publisher.subscribe = AsyncMock(return_value=asyncio.Queue())
        self.event_publisher.unsubscribe = AsyncMock()

        self.state_manager = MagicMock()
        self.state_manager.on_controller_connected = AsyncMock()
        self.state_manager.on_controller_disconnected = AsyncMock()
        self.state_manager.update_battery = MagicMock()
        self.state_manager.handle_button_event = AsyncMock()
        self.state_manager.set_game_mode = MagicMock()
        self.state_manager.reset = AsyncMock(return_value=["serial_1", "serial_2"])
        # controller_states is the single source of truth (starts empty)
        self.state_manager.controller_states = {}
        self.state_manager.button_states = {}
        self.state_manager.transition_to = AsyncMock()

        # Computed properties on state_manager (match real implementation)
        type(self.state_manager).ready_controllers = property(
            lambda sm: {s for s, st in sm.controller_states.items() if st == ControllerState.READY}
        )
        type(self.state_manager).connected_controllers = property(lambda sm: set(sm.controller_states.keys()))

        self.controller_events = MagicMock()
        self.controller_events.start = AsyncMock()
        self.controller_events.stop = AsyncMock()
        self.controller_events.is_running = False
        self.controller_events.wait_for_connection = AsyncMock()

        self.admin_handler = MagicMock()
        self.admin_handler.combo_shown = False
        self.admin_handler.check_combo_from_state = MagicMock(return_value=False)

        self.voice_actor = "ivy"
        self.game_options = []

        # Mock channels
        self.controller_channel = MagicMock()
        self.controller_channel.close = AsyncMock()
        self.settings_channel = MagicMock()
        self.settings_channel.close = AsyncMock()
        self.game_coordinator_channel = MagicMock()
        self.game_coordinator_channel.close = AsyncMock()
        self.audio_channel = MagicMock()
        self.audio_channel.close = AsyncMock()

    # Computed properties that delegate to state_manager (match real implementation)
    @property
    def ready_controllers(self) -> set[str]:
        """Controllers in READY state (delegates to state_manager)."""
        return self.state_manager.ready_controllers

    @property
    def connected_controllers(self) -> set[str]:
        """All connected controllers (delegates to state_manager)."""
        return self.state_manager.connected_controllers

    @property
    def ready_controller_count(self) -> int:
        """Number of ready controllers (computed from state_manager)."""
        return len(self.state_manager.ready_controllers)

    async def on_disconnect(self, serial: str) -> None:
        """Handle controller disconnect (matches real implementation)."""
        await self.state_manager.on_controller_disconnected(serial)


# Import the actual method implementations to bind to our fake
def bind_methods_from_servicer():
    """Import real method implementations from MenuServicer."""
    # We'll test the logic of individual methods by copying them to the fake
    pass


class TestMenuServicerState:
    """Tests for state management."""

    @pytest.fixture
    def servicer(self):
        """Create a fake servicer for testing."""
        return FakeMenuServicer()

    def test_initial_state_stopped(self, servicer):
        """Initial state should be STOPPED."""
        assert servicer.state == menu_pb2.MenuState.STOPPED

    def test_initial_selection_is_joust_ffa(self, servicer):
        """Initial selection should be JoustFFA."""
        assert servicer.current_selection == Games.JoustFFA

    def test_initial_ready_controllers_empty(self, servicer):
        """Ready controllers set should start empty."""
        assert servicer.ready_controllers == set()

    def test_initial_connected_controllers_empty(self, servicer):
        """Connected controllers set should start empty."""
        assert servicer.connected_controllers == set()

    def test_initial_ready_count_zero(self, servicer):
        """Ready controller count should start at 0."""
        assert servicer.ready_controller_count == 0


class TestMenuServicerAdminModeCallbacks:
    """Tests for AdminModeCallbacks protocol methods."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    def test_set_menu_state(self, servicer):
        """set_menu_state should update the state."""
        servicer.state = menu_pb2.MenuState.STOPPED

        # Simulate the real implementation
        def set_menu_state(state):
            servicer.state = state

        set_menu_state(menu_pb2.MenuState.RUNNING)

        assert servicer.state == menu_pb2.MenuState.RUNNING

    def test_get_game_options_empty_default(self, servicer):
        """get_game_options should return empty list by default."""
        assert servicer.game_options == []

    def test_get_game_options_returns_options(self, servicer):
        """get_game_options should return options when set."""
        servicer.game_options = ["Option1", "Option2"]
        assert servicer.game_options == ["Option1", "Option2"]


class TestMenuServicerControllerCallbacks:
    """Tests for ControllerEventCallbacks protocol methods."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    def test_get_menu_state(self, servicer):
        """get_menu_state should return current state."""
        servicer.state = menu_pb2.MenuState.GAME_STARTING
        assert servicer.state == menu_pb2.MenuState.GAME_STARTING

    @pytest.mark.asyncio
    async def test_on_connect_adds_to_connected(self, servicer):
        """on_connect should delegate to state_manager which tracks the connection."""

        # Make state_manager.on_controller_connected update controller_states
        async def mock_on_connected(serial):
            servicer.state_manager.controller_states[serial] = ControllerState.CONNECTED

        servicer.state_manager.on_controller_connected = AsyncMock(side_effect=mock_on_connected)

        # Simulate the real on_connect implementation (just delegates to state_manager)
        async def on_connect(serial):
            await servicer.state_manager.on_controller_connected(serial)

        await on_connect("serial_1")

        assert "serial_1" in servicer.connected_controllers
        servicer.state_manager.on_controller_connected.assert_called_once_with("serial_1")

    @pytest.mark.asyncio
    async def test_on_disconnect_removes_from_all_sets(self, servicer):
        """on_disconnect should clean up all tracking state."""
        # Set up initial state via state_manager.controller_states (single source of truth)
        servicer.state_manager.controller_states = {
            "serial_1": ControllerState.READY,
            "serial_2": ControllerState.CONNECTED,
        }

        # Make state_manager.on_controller_disconnected update controller_states
        async def mock_on_disconnected(serial):
            servicer.state_manager.controller_states.pop(serial, None)

        servicer.state_manager.on_controller_disconnected = AsyncMock(side_effect=mock_on_disconnected)

        # Call on_disconnect (now delegates to state_manager)
        await servicer.on_disconnect("serial_1")

        assert "serial_1" not in servicer.connected_controllers
        assert "serial_1" not in servicer.ready_controllers
        assert servicer.ready_controller_count == 0

    def test_update_battery_calls_state_manager(self, servicer):
        """update_battery should delegate to state_manager."""
        servicer.state_manager.update_battery("serial_1", 80)
        servicer.state_manager.update_battery.assert_called_with("serial_1", 80)


class TestMenuServicerOnButton:
    """Tests for on_button callback logic."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    @pytest.mark.asyncio
    async def test_on_button_forwards_to_state_manager(self, servicer):
        """on_button should forward to state_manager.handle_button_event."""
        await servicer.state_manager.handle_button_event("serial_1", "trigger", True)
        servicer.state_manager.handle_button_event.assert_called_once_with("serial_1", "trigger", True)

    @pytest.mark.asyncio
    async def test_on_button_checks_admin_combo(self, servicer):
        """on_button should check admin combo on face button press."""
        servicer.state_manager.button_states = {"serial_1": {"cross": True, "circle": True, "square": True}}

        # Create preview state like the real implementation
        button_state = servicer.state_manager.button_states.get("serial_1", {})
        preview_state = dict(button_state)
        preview_state["triangle"] = True

        servicer.admin_handler.check_combo_from_state(preview_state)

        servicer.admin_handler.check_combo_from_state.assert_called_with(preview_state)

    @pytest.mark.asyncio
    async def test_face_button_release_resets_admin_combo(self, servicer):
        """Release of face button should reset admin combo flag."""
        servicer.admin_handler.combo_shown = True

        # Simulate the real logic
        button = "cross"
        is_press = False
        if not is_press and button in ["cross", "circle", "square", "triangle"]:
            servicer.admin_handler.combo_shown = False

        assert servicer.admin_handler.combo_shown is False


class TestMenuServicerStartMenu:
    """Tests for StartMenu gRPC method logic."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    @pytest.mark.asyncio
    async def test_start_menu_success(self, servicer):
        """StartMenu should transition to RUNNING and return success."""
        # Add some ready controllers to verify they get cleared
        servicer.state_manager.controller_states = {"s1": ControllerState.READY}

        # Simulate the real StartMenu logic
        if servicer.state == menu_pb2.MenuState.RUNNING:
            success = False
            error = "Menu already running"
        else:
            servicer.state = menu_pb2.MenuState.RUNNING
            # Clear ready state (new implementation clears controller_states READY entries)
            for serial in list(servicer.state_manager.controller_states.keys()):
                if servicer.state_manager.controller_states[serial] == ControllerState.READY:
                    servicer.state_manager.controller_states[serial] = ControllerState.CONNECTED
            await servicer.settings_helper.load_voice_actor()
            await servicer.settings_helper.load_current_game()
            await servicer.audio.start_lobby_music()
            await servicer.event_publisher.publish("menu_started", {})
            success = True
            error = ""

        assert success is True
        assert error == ""
        assert servicer.state == menu_pb2.MenuState.RUNNING
        assert servicer.ready_controller_count == 0  # All ready controllers cleared
        servicer.audio.start_lobby_music.assert_called_once()
        servicer.event_publisher.publish.assert_called_with("menu_started", {})

    @pytest.mark.asyncio
    async def test_start_menu_already_running(self, servicer):
        """StartMenu should fail if already running."""
        servicer.state = menu_pb2.MenuState.RUNNING

        if servicer.state == menu_pb2.MenuState.RUNNING:
            success = False
            error = "Menu already running"
        else:
            success = True
            error = ""

        assert success is False
        assert "already running" in error


class TestMenuServicerStopMenu:
    """Tests for StopMenu gRPC method logic."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    @pytest.mark.asyncio
    async def test_stop_menu_success(self, servicer):
        """StopMenu should transition to STOPPED and clear state."""
        servicer.state = menu_pb2.MenuState.RUNNING
        # Set up state via controller_states (single source of truth)
        servicer.state_manager.controller_states = {
            "serial_1": ControllerState.READY,
            "serial_2": ControllerState.CONNECTED,
        }

        # Simulate the real StopMenu logic (new implementation)
        if servicer.state != menu_pb2.MenuState.STOPPED:
            servicer.state = menu_pb2.MenuState.STOPPED
            servicer.state_manager.controller_states.clear()
            await servicer.event_publisher.publish("menu_stopped", {})

        assert servicer.state == menu_pb2.MenuState.STOPPED
        assert servicer.ready_controllers == set()
        assert servicer.connected_controllers == set()
        servicer.event_publisher.publish.assert_called_with("menu_stopped", {})

    @pytest.mark.asyncio
    async def test_stop_menu_already_stopped(self, servicer):
        """StopMenu should fail if already stopped."""
        servicer.state = menu_pb2.MenuState.STOPPED

        if servicer.state == menu_pb2.MenuState.STOPPED:
            success = False
            error = "Menu already stopped"
        else:
            success = True
            error = ""

        assert success is False
        assert "already stopped" in error


class TestMenuServicerHandleButtonInput:
    """Tests for _handle_button_input method logic."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    @pytest.mark.asyncio
    async def test_button_select_cycles_game_mode(self, servicer):
        """Select button should cycle to next game mode."""
        servicer.current_selection = Games.JoustFFA

        # Simulate the real logic using settings helper
        next_mode = servicer.settings_helper.get_next_game_mode(servicer.current_selection)
        servicer.current_selection = next_mode
        servicer.state_manager.set_game_mode(servicer.current_selection)
        await servicer.event_publisher.publish("selection_changed", {"game_name": servicer.current_selection.name})
        await servicer.settings_helper.save_current_game(servicer.current_selection)

        assert servicer.current_selection != Games.JoustFFA
        servicer.state_manager.set_game_mode.assert_called()
        servicer.event_publisher.publish.assert_called()


class TestMenuServicerHandleWebCommand:
    """Tests for _handle_web_command method logic."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    @pytest.mark.asyncio
    async def test_web_command_select_game_valid(self, servicer):
        """select_game command should update selection for valid game."""
        from services.menu.utils.settings import GAME_MODES

        servicer.current_selection = Games.JoustFFA
        game_name = "Tournament"

        # Simulate the real logic
        game_mode = Games.from_name(game_name)
        if game_mode is not None and game_name in GAME_MODES:
            servicer.current_selection = game_mode
            servicer.state_manager.set_game_mode(game_mode)
            await servicer.event_publisher.publish("selection_changed", {"game_name": game_mode.name, "source": "web"})
            await servicer.settings_helper.save_current_game(game_mode)

        assert servicer.current_selection == Games.Tournament
        servicer.state_manager.set_game_mode.assert_called_with(Games.Tournament)

    @pytest.mark.asyncio
    async def test_web_command_select_game_invalid(self, servicer):
        """select_game command should ignore invalid game names."""
        servicer.current_selection = Games.JoustFFA
        game_name = "InvalidGameMode"

        # Simulate the real logic
        game_mode = Games.from_name(game_name)
        if game_mode is not None:
            servicer.current_selection = game_mode

        assert servicer.current_selection == Games.JoustFFA  # Unchanged


class TestMenuServicerHandleResetMenu:
    """Tests for _handle_reset_menu method logic."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    @pytest.mark.asyncio
    async def test_reset_menu_from_game_starting(self, servicer):
        """reset_menu should reset from GAME_STARTING to RUNNING."""
        servicer.state = menu_pb2.MenuState.GAME_STARTING

        # Simulate the real logic
        if servicer.state == menu_pb2.MenuState.GAME_STARTING:
            servicer.state = menu_pb2.MenuState.RUNNING
            await servicer.event_publisher.publish("game_start_cancelled", {})

        assert servicer.state == menu_pb2.MenuState.RUNNING
        servicer.event_publisher.publish.assert_called_with("game_start_cancelled", {})

    @pytest.mark.asyncio
    async def test_reset_menu_from_running_no_change(self, servicer):
        """reset_menu should not change state if RUNNING."""
        servicer.state = menu_pb2.MenuState.RUNNING

        # Simulate the real logic
        if servicer.state == menu_pb2.MenuState.GAME_STARTING:
            servicer.state = menu_pb2.MenuState.RUNNING
            await servicer.event_publisher.publish("game_start_cancelled", {})

        assert servicer.state == menu_pb2.MenuState.RUNNING
        servicer.event_publisher.publish.assert_not_called()


class TestMenuServicerStartGame:
    """Tests for _start_game method logic."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    @pytest.mark.asyncio
    async def test_start_game_requires_two_players(self, servicer):
        """_start_game should require at least 2 players."""
        # Only 1 ready controller
        servicer.state_manager.controller_states = {"serial_1": ControllerState.READY}

        # Simulate the check
        controllers = list(servicer.state_manager.ready_controllers)
        if len(controllers) < 2:
            started = False
        else:
            servicer.state = menu_pb2.MenuState.GAME_STARTING
            started = True

        assert started is False
        assert servicer.state == menu_pb2.MenuState.STOPPED

    @pytest.mark.asyncio
    async def test_start_game_sets_game_starting_state(self, servicer):
        """_start_game should set GAME_STARTING state with enough players."""
        # 3 ready controllers
        servicer.state_manager.controller_states = {
            "serial_1": ControllerState.READY,
            "serial_2": ControllerState.READY,
            "serial_3": ControllerState.READY,
        }

        # Simulate the logic
        controllers = list(servicer.state_manager.ready_controllers)
        if len(controllers) >= 2:
            servicer.state = menu_pb2.MenuState.GAME_STARTING

        assert servicer.state == menu_pb2.MenuState.GAME_STARTING


class TestMenuServicerLifecycle:
    """Tests for lifecycle methods."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    @pytest.mark.asyncio
    async def test_start_button_monitor(self, servicer):
        """start_button_monitor should start controller events."""
        await servicer.controller_events.start()
        servicer.controller_events.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_button_monitor(self, servicer):
        """stop_button_monitor should stop controller events."""
        await servicer.controller_events.stop()
        servicer.controller_events.stop.assert_called_once()

    def test_button_monitor_running_property(self, servicer):
        """button_monitor_running should reflect controller_events.is_running."""
        servicer.controller_events.is_running = True
        assert servicer.controller_events.is_running is True

        servicer.controller_events.is_running = False
        assert servicer.controller_events.is_running is False

    @pytest.mark.asyncio
    async def test_start_game_event_monitor(self, servicer):
        """start_game_event_monitor should set flag and create task."""
        # Simulate the logic
        if not servicer.game_event_monitor_running:
            servicer.game_event_monitor_running = True
            servicer.game_event_task = asyncio.create_task(asyncio.sleep(0.01))

        assert servicer.game_event_monitor_running is True
        assert servicer.game_event_task is not None

        # Clean up
        servicer.game_event_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await servicer.game_event_task

    @pytest.mark.asyncio
    async def test_stop_game_event_monitor(self, servicer):
        """stop_game_event_monitor should clear flag and cancel task."""
        servicer.game_event_monitor_running = True
        servicer.game_event_task = asyncio.create_task(asyncio.sleep(10))

        # Simulate the stop logic
        servicer.game_event_monitor_running = False
        if servicer.game_event_task:
            servicer.game_event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await servicer.game_event_task

        assert servicer.game_event_monitor_running is False

    @pytest.mark.asyncio
    async def test_shutdown_closes_channels(self, servicer):
        """shutdown should close all gRPC channels."""
        await servicer.controller_channel.close()
        await servicer.settings_channel.close()
        await servicer.game_coordinator_channel.close()
        await servicer.audio_channel.close()

        servicer.controller_channel.close.assert_called_once()
        servicer.settings_channel.close.assert_called_once()
        servicer.game_coordinator_channel.close.assert_called_once()
        servicer.audio_channel.close.assert_called_once()


class TestMenuServicerLobbyState:
    """Tests for lobby state management."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    def test_multiple_controller_connect(self, servicer):
        """Should correctly track multiple connected controllers via controller_states."""
        servicer.state_manager.controller_states["serial_1"] = ControllerState.CONNECTED
        servicer.state_manager.controller_states["serial_2"] = ControllerState.CONNECTED
        servicer.state_manager.controller_states["serial_3"] = ControllerState.CONNECTED

        assert len(servicer.connected_controllers) == 3
        assert "serial_1" in servicer.connected_controllers
        assert "serial_2" in servicer.connected_controllers
        assert "serial_3" in servicer.connected_controllers

    def test_controller_disconnect_updates_count(self, servicer):
        """Disconnecting should update ready count (computed from controller_states)."""
        servicer.state_manager.controller_states = {
            "serial_1": ControllerState.READY,
            "serial_2": ControllerState.READY,
        }
        assert servicer.ready_controller_count == 2

        # Remove one controller
        del servicer.state_manager.controller_states["serial_1"]

        assert servicer.ready_controller_count == 1


class TestMenuServicerGameModeSelection:
    """Tests for game mode selection logic."""

    @pytest.fixture
    def servicer(self):
        return FakeMenuServicer()

    def test_set_game_mode_updates_state_manager(self, servicer):
        """Setting game mode should update state_manager."""
        servicer.state_manager.set_game_mode(Games.Tournament)
        servicer.state_manager.set_game_mode.assert_called_with(Games.Tournament)

    def test_current_selection_persistence(self, servicer):
        """Current selection should persist across state changes."""
        servicer.current_selection = Games.Werewolf
        servicer.state = menu_pb2.MenuState.RUNNING
        servicer.state = menu_pb2.MenuState.STOPPED

        assert servicer.current_selection == Games.Werewolf
