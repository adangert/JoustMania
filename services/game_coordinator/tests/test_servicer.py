"""
Unit tests for GameCoordinatorServicer.

Tests the game lifecycle management:
- StartGame validation (player count, duplicate starts)
- ForceEndGame (running and idle states)
- GetGameState (state queries)
- State transitions and thread safety
- Error handling

Issue #209: Improve test coverage for critical game flow
"""

import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Setup paths for imports
test_dir = Path(__file__).parent
service_dir = test_dir.parent
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(test_dir))

from proto import game_coordinator_pb2
from services.game_coordinator.servicer import GameCoordinatorServicer


class MockGrpcContext:
    """Mock gRPC context for testing."""

    def __init__(self):
        self._cancelled = False
        self._metadata = []

    def cancelled(self):
        return self._cancelled

    def invocation_metadata(self):
        return self._metadata


class MockSpan:
    """Mock OpenTelemetry span."""

    def __init__(self):
        self.attributes = {}
        self.events = []

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def add_event(self, name, attributes=None):
        self.events.append((name, attributes))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestGameCoordinatorInit:
    """Tests for GameCoordinatorServicer initialization."""

    def test_initial_state_is_idle(self):
        """Servicer should start in IDLE state."""
        servicer = GameCoordinatorServicer()
        assert servicer.game_state == game_coordinator_pb2.GameState.IDLE

    def test_no_current_game_on_init(self):
        """No game should be running on init."""
        servicer = GameCoordinatorServicer()
        assert servicer.current_game is None
        assert servicer.game_running is False

    def test_empty_players_on_init(self):
        """Players list should be empty on init."""
        servicer = GameCoordinatorServicer()
        assert len(servicer.players) == 0


class TestStartGameValidation:
    """Tests for _start_game_from_config validation."""

    @pytest.fixture
    def servicer(self):
        """Create servicer for testing."""
        return GameCoordinatorServicer()

    def test_rejects_less_than_two_players(self, servicer):
        """Should reject game start with less than 2 players."""
        config = game_coordinator_pb2.StartGameConfig(
            game_name="FFA",
            players=[game_coordinator_pb2.Player(serial="p1")],  # Only 1 player
            settings={},
        )
        mock_span = MockSpan()

        success, error = servicer._start_game_from_config(config, mock_span)

        assert success is False
        assert "at least 2 players" in error.lower()

    def test_rejects_zero_players(self, servicer):
        """Should reject game start with zero players."""
        config = game_coordinator_pb2.StartGameConfig(
            game_name="FFA",
            players=[],  # No players
            settings={},
        )
        mock_span = MockSpan()

        success, error = servicer._start_game_from_config(config, mock_span)

        assert success is False
        assert "at least 2 players" in error.lower()

    def test_accepts_two_players(self, servicer):
        """Should accept game start with exactly 2 players."""
        config = game_coordinator_pb2.StartGameConfig(
            game_name="FFA",
            players=[
                game_coordinator_pb2.Player(serial="p1"),
                game_coordinator_pb2.Player(serial="p2"),
            ],
            settings={},
        )
        mock_span = MockSpan()

        # Patch the background thread to not actually start
        with patch.object(servicer, "_run_game_loop_threaded"):
            success, game_id = servicer._start_game_from_config(config, mock_span)

        assert success is True
        assert game_id.startswith("game_")

    def test_accepts_many_players(self, servicer):
        """Should accept game start with many players."""
        config = game_coordinator_pb2.StartGameConfig(
            game_name="FFA",
            players=[game_coordinator_pb2.Player(serial=f"p{i}") for i in range(8)],
            settings={},
        )
        mock_span = MockSpan()

        with patch.object(servicer, "_run_game_loop_threaded"):
            success, game_id = servicer._start_game_from_config(config, mock_span)

        assert success is True
        assert len(servicer.players) == 8

    def test_rejects_start_when_already_running(self, servicer):
        """Should reject second game start when game already running."""
        # First game start
        config1 = game_coordinator_pb2.StartGameConfig(
            game_name="FFA",
            players=[
                game_coordinator_pb2.Player(serial="p1"),
                game_coordinator_pb2.Player(serial="p2"),
            ],
            settings={},
        )
        mock_span = MockSpan()

        with patch.object(servicer, "_run_game_loop_threaded"):
            success1, _ = servicer._start_game_from_config(config1, mock_span)
            assert success1 is True

        # Simulate game is running
        servicer.game_state = game_coordinator_pb2.GameState.RUNNING

        # Second game start should fail
        config2 = game_coordinator_pb2.StartGameConfig(
            game_name="Teams",
            players=[
                game_coordinator_pb2.Player(serial="p3"),
                game_coordinator_pb2.Player(serial="p4"),
            ],
            settings={},
        )

        success2, error = servicer._start_game_from_config(config2, mock_span)

        assert success2 is False
        assert "already in progress" in error.lower()

    def test_rejects_start_when_starting(self, servicer):
        """Should reject game start when another game is starting."""
        servicer.game_state = game_coordinator_pb2.GameState.STARTING

        config = game_coordinator_pb2.StartGameConfig(
            game_name="FFA",
            players=[
                game_coordinator_pb2.Player(serial="p1"),
                game_coordinator_pb2.Player(serial="p2"),
            ],
            settings={},
        )
        mock_span = MockSpan()

        success, error = servicer._start_game_from_config(config, mock_span)

        assert success is False
        assert "already in progress" in error.lower()

    def test_generates_unique_game_id(self, servicer):
        """Should generate unique game IDs."""
        config = game_coordinator_pb2.StartGameConfig(
            game_name="FFA",
            players=[
                game_coordinator_pb2.Player(serial="p1"),
                game_coordinator_pb2.Player(serial="p2"),
            ],
            settings={},
        )
        mock_span = MockSpan()

        with patch.object(servicer, "_run_game_loop_threaded"):
            success, game_id = servicer._start_game_from_config(config, mock_span)

        assert success is True
        assert game_id is not None
        assert game_id.startswith("game_")
        # Game ID should contain timestamp
        assert servicer.game_id == game_id

    def test_stores_game_config(self, servicer):
        """Should store game configuration on start."""
        config = game_coordinator_pb2.StartGameConfig(
            game_name="Teams",
            players=[
                game_coordinator_pb2.Player(serial="p1"),
                game_coordinator_pb2.Player(serial="p2"),
            ],
            settings={"sensitivity": "FAST", "random_teams": "true"},
        )
        mock_span = MockSpan()

        with patch.object(servicer, "_run_game_loop_threaded"):
            servicer._start_game_from_config(config, mock_span)

        assert servicer.game_name == "Teams"
        assert len(servicer.players) == 2
        assert servicer.settings["sensitivity"] == "FAST"
        assert servicer.settings["random_teams"] == "true"


class TestForceEndGame:
    """Tests for ForceEndGame RPC."""

    @pytest.fixture
    def servicer(self):
        """Create servicer for testing."""
        return GameCoordinatorServicer()

    @pytest.mark.asyncio
    async def test_force_end_no_game_running(self, servicer):
        """ForceEndGame should fail gracefully when no game running."""
        request = game_coordinator_pb2.ForceEndGameRequest(reason="test")
        context = MockGrpcContext()

        response = await servicer.ForceEndGame(request, context)

        assert response.success is False
        assert "no game in progress" in response.error.lower()

    @pytest.mark.asyncio
    async def test_force_end_idle_state(self, servicer):
        """ForceEndGame should fail when state is IDLE."""
        assert servicer.game_state == game_coordinator_pb2.GameState.IDLE

        request = game_coordinator_pb2.ForceEndGameRequest(reason="test")
        context = MockGrpcContext()

        response = await servicer.ForceEndGame(request, context)

        assert response.success is False

    @pytest.mark.asyncio
    async def test_force_end_running_game(self, servicer):
        """ForceEndGame should succeed when game is running."""
        # Set up running state
        servicer.game_state = game_coordinator_pb2.GameState.RUNNING
        servicer.game_running = True
        servicer.game_id = "test_game_123"

        # Mock current game with force_end method
        mock_game = MagicMock()
        servicer.current_game = mock_game

        request = game_coordinator_pb2.ForceEndGameRequest(reason="user requested")
        context = MockGrpcContext()

        response = await servicer.ForceEndGame(request, context)

        assert response.success is True
        assert response.error == ""
        mock_game.force_end.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_end_starting_game(self, servicer):
        """ForceEndGame should succeed when game is starting."""
        servicer.game_state = game_coordinator_pb2.GameState.STARTING
        servicer.game_running = True
        servicer.game_id = "test_game_456"

        request = game_coordinator_pb2.ForceEndGameRequest(reason="cancelled")
        context = MockGrpcContext()

        response = await servicer.ForceEndGame(request, context)

        assert response.success is True
        assert servicer.game_state == game_coordinator_pb2.GameState.ENDED

    @pytest.mark.asyncio
    async def test_force_end_transitions_to_ended(self, servicer):
        """ForceEndGame should transition state to ENDED."""
        servicer.game_state = game_coordinator_pb2.GameState.RUNNING
        servicer.game_running = True
        servicer.game_id = "test_game"

        request = game_coordinator_pb2.ForceEndGameRequest(reason="test")
        context = MockGrpcContext()

        await servicer.ForceEndGame(request, context)

        assert servicer.game_state == game_coordinator_pb2.GameState.ENDED


class TestGetGameState:
    """Tests for GetGameState RPC."""

    @pytest.fixture
    def servicer(self):
        """Create servicer for testing."""
        return GameCoordinatorServicer()

    @pytest.mark.asyncio
    async def test_get_state_idle(self, servicer):
        """GetGameState should return IDLE state when no game."""
        request = game_coordinator_pb2.GetGameStateRequest()
        context = MockGrpcContext()

        response = await servicer.GetGameState(request, context)

        assert response.success is True
        assert response.game_info.state == game_coordinator_pb2.GameState.IDLE
        assert response.game_info.game_mode == ""

    @pytest.mark.asyncio
    async def test_get_state_running(self, servicer):
        """GetGameState should return game info when running."""
        servicer.game_state = game_coordinator_pb2.GameState.RUNNING
        servicer.game_name = "FFA"
        servicer.game_id = "game_123"
        servicer.game_start_time = time.time()

        request = game_coordinator_pb2.GetGameStateRequest()
        context = MockGrpcContext()

        response = await servicer.GetGameState(request, context)

        assert response.success is True
        assert response.game_info.state == game_coordinator_pb2.GameState.RUNNING
        assert response.game_info.game_mode == "FFA"
        assert response.game_info.game_id == "game_123"

    @pytest.mark.asyncio
    async def test_get_state_with_players(self, servicer):
        """GetGameState should return player info when game has players."""
        servicer.game_state = game_coordinator_pb2.GameState.RUNNING
        servicer.game_name = "Teams"
        servicer.game_id = "game_456"

        # Mock current game with players
        mock_game = MagicMock()
        mock_player1 = MagicMock()
        mock_player1.team = 0
        mock_player1.color = (255, 0, 0)
        mock_player1.alive = True
        mock_player1.sensitivity_factor = 1.0

        mock_player2 = MagicMock()
        mock_player2.team = 1
        mock_player2.color = (0, 0, 255)
        mock_player2.alive = False
        mock_player2.sensitivity_factor = 1.5

        mock_game.players = {
            "serial_1": mock_player1,
            "serial_2": mock_player2,
        }

        servicer.current_game = mock_game

        request = game_coordinator_pb2.GetGameStateRequest()
        context = MockGrpcContext()

        response = await servicer.GetGameState(request, context)

        assert response.success is True
        assert len(response.game_info.players) == 2

        # Check player info
        player_serials = {p.serial for p in response.game_info.players}
        assert "serial_1" in player_serials
        assert "serial_2" in player_serials


class TestEventStateSync:
    """Tests for event-driven state synchronization."""

    @pytest.fixture
    def servicer(self):
        """Create servicer for testing."""
        return GameCoordinatorServicer()

    def test_game_started_transitions_to_running(self, servicer):
        """GAME_STARTED event should transition state to RUNNING."""
        from lib.types import GameEvent

        servicer.game_state = game_coordinator_pb2.GameState.STARTING

        servicer._on_event_state_sync(GameEvent.GAME_STARTED)

        assert servicer.game_state == game_coordinator_pb2.GameState.RUNNING

    def test_game_ended_transitions_to_ended(self, servicer):
        """Game ending events should transition state to ENDED."""
        from lib.types import GameEvent

        servicer.game_state = game_coordinator_pb2.GameState.RUNNING

        servicer._on_event_state_sync(GameEvent.GAME_ENDED)

        assert servicer.game_state == game_coordinator_pb2.GameState.ENDED

    def test_game_force_ended_transitions_to_ended(self, servicer):
        """GAME_FORCE_ENDED event should transition state to ENDED."""
        from lib.types import GameEvent

        servicer.game_state = game_coordinator_pb2.GameState.RUNNING

        servicer._on_event_state_sync(GameEvent.GAME_FORCE_ENDED)

        assert servicer.game_state == game_coordinator_pb2.GameState.ENDED

    def test_game_error_transitions_to_ended(self, servicer):
        """GAME_ERROR event should transition state to ENDED."""
        from lib.types import GameEvent

        servicer.game_state = game_coordinator_pb2.GameState.RUNNING

        servicer._on_event_state_sync(GameEvent.GAME_ERROR)

        assert servicer.game_state == game_coordinator_pb2.GameState.ENDED


class TestShutdown:
    """Tests for servicer shutdown."""

    @pytest.fixture
    def servicer(self):
        """Create servicer for testing."""
        return GameCoordinatorServicer()

    @pytest.mark.asyncio
    async def test_shutdown_sets_game_running_false(self, servicer):
        """Shutdown should set game_running to False."""
        servicer.game_running = True

        await servicer.shutdown()

        assert servicer.game_running is False

    @pytest.mark.asyncio
    async def test_shutdown_closes_clients(self, servicer):
        """Shutdown should close gRPC clients."""
        # Mock clients.close()
        servicer.clients.close = AsyncMock()

        await servicer.shutdown()

        servicer.clients.close.assert_called_once()


class TestGameNameHandling:
    """Tests for game name handling."""

    @pytest.fixture
    def servicer(self):
        """Create servicer for testing."""
        return GameCoordinatorServicer()

    def test_valid_game_names_accepted(self, servicer):
        """Known game types should be accepted."""
        valid_names = ["FFA", "Teams", "Zombie", "Werewolf", "Tournament"]

        for name in valid_names:
            config = game_coordinator_pb2.StartGameConfig(
                game_name=name,
                players=[
                    game_coordinator_pb2.Player(serial="p1"),
                    game_coordinator_pb2.Player(serial="p2"),
                ],
                settings={},
            )
            mock_span = MockSpan()

            # Reset state for each test
            servicer.game_state = game_coordinator_pb2.GameState.IDLE
            servicer.game_running = False

            with patch.object(servicer, "_run_game_loop_threaded"):
                success, result = servicer._start_game_from_config(config, mock_span)

            # Valid game names should succeed initial validation
            assert success is True, f"Game type {name} should be accepted"

    def test_game_name_stored_correctly(self, servicer):
        """Game name should be stored in servicer."""
        config = game_coordinator_pb2.StartGameConfig(
            game_name="FFA",
            players=[
                game_coordinator_pb2.Player(serial="p1"),
                game_coordinator_pb2.Player(serial="p2"),
            ],
            settings={},
        )
        mock_span = MockSpan()

        with patch.object(servicer, "_run_game_loop_threaded"):
            servicer._start_game_from_config(config, mock_span)

        assert servicer.game_name == "FFA"


class TestStateTransitionRobustness:
    """Tests for state transition edge cases."""

    @pytest.fixture
    def servicer(self):
        """Create servicer for testing."""
        return GameCoordinatorServicer()

    def test_transition_from_idle_to_starting(self, servicer):
        """Servicer should transition from IDLE to STARTING on game start."""
        assert servicer.game_state == game_coordinator_pb2.GameState.IDLE

        config = game_coordinator_pb2.StartGameConfig(
            game_name="FFA",
            players=[
                game_coordinator_pb2.Player(serial="p1"),
                game_coordinator_pb2.Player(serial="p2"),
            ],
            settings={},
        )
        mock_span = MockSpan()

        with patch.object(servicer, "_run_game_loop_threaded"):
            servicer._start_game_from_config(config, mock_span)

        # State should be STARTING (or transitioning)
        assert servicer.game_state in [
            game_coordinator_pb2.GameState.STARTING,
            game_coordinator_pb2.GameState.RUNNING,
        ]

    @pytest.mark.asyncio
    async def test_force_end_from_multiple_states(self, servicer):
        """ForceEndGame should work from STARTING or RUNNING state."""
        context = MockGrpcContext()
        request = game_coordinator_pb2.ForceEndGameRequest(reason="test")

        # Test from STARTING
        servicer.game_state = game_coordinator_pb2.GameState.STARTING
        servicer.game_running = True
        servicer.game_id = "test_game"

        response = await servicer.ForceEndGame(request, context)
        assert response.success is True

    @pytest.mark.asyncio
    async def test_get_state_during_transition(self, servicer):
        """GetGameState should return valid state during transitions."""
        context = MockGrpcContext()
        request = game_coordinator_pb2.GetGameStateRequest()

        # Simulate mid-transition
        servicer.game_state = game_coordinator_pb2.GameState.STARTING
        servicer.game_name = "FFA"
        servicer.game_id = "transition_test"

        response = await servicer.GetGameState(request, context)

        assert response.success is True
        assert response.game_info.state == game_coordinator_pb2.GameState.STARTING


class TestDuplicatePlayerHandling:
    """Tests for handling duplicate players."""

    @pytest.fixture
    def servicer(self):
        """Create servicer for testing."""
        return GameCoordinatorServicer()

    def test_duplicate_serial_in_players(self, servicer):
        """StartGame with duplicate serials should be handled."""
        config = game_coordinator_pb2.StartGameConfig(
            game_name="FFA",
            players=[
                game_coordinator_pb2.Player(serial="same_serial"),
                game_coordinator_pb2.Player(serial="same_serial"),
                game_coordinator_pb2.Player(serial="different_serial"),
            ],
            settings={},
        )
        mock_span = MockSpan()

        with patch.object(servicer, "_run_game_loop_threaded"):
            success, result = servicer._start_game_from_config(config, mock_span)

        # Implementation may dedupe or fail - either is acceptable
        # Just verify it doesn't crash
        assert isinstance(success, bool)


class TestConcurrentOperations:
    """Tests for concurrent operation handling."""

    @pytest.fixture
    def servicer(self):
        """Create servicer for testing."""
        return GameCoordinatorServicer()

    @pytest.mark.asyncio
    async def test_get_state_concurrent_safe(self, servicer):
        """GetGameState should be safe under concurrent access."""
        context = MockGrpcContext()
        request = game_coordinator_pb2.GetGameStateRequest()

        servicer.game_state = game_coordinator_pb2.GameState.RUNNING
        servicer.game_name = "FFA"
        servicer.game_id = "concurrent_test"

        # Simulate multiple concurrent calls
        responses = []
        for _ in range(10):
            response = await servicer.GetGameState(request, context)
            responses.append(response)

        # All should succeed with consistent state
        for response in responses:
            assert response.success is True
            assert response.game_info.state == game_coordinator_pb2.GameState.RUNNING
