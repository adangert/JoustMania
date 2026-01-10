# Game Modes

Modern gRPC-based game mode implementations for JoustMania microservices architecture.

## Overview

This directory contains game modes built with:
- **gRPC** for all service communication (no multiprocessing Queues)
- **Async/await** patterns for non-blocking execution
- **State machines** for clear game lifecycle management
- **Event publishing** for real-time game updates
- **OpenTelemetry** for comprehensive distributed tracing

Legacy implementations have been archived to `legacy_archived/`.

## Implemented Game Modes

### ✅ FFA (Free-For-All) - `ffa.py`
**Status:** Complete (Phase 13.2)

Players try to keep their controllers still. Last player standing wins.

**Features:**
- Streams controller states at 60Hz from ControllerManager
- Fetches settings (sensitivity, audio) from Settings service
- Detects deaths based on acceleration thresholds
- Publishes real-time events (deaths, winner, game end)
- Full OpenTelemetry instrumentation

**Events Published:**
- `game_starting` - Game initialization
- `players_initialized` - Players loaded from controllers
- `countdown_start` / `countdown_end` - Countdown phase
- `game_started` - Game loop begins
- `player_death` - Player died
- `game_winner` - Winner determined
- `game_ended` - Game finished

### ✅ Teams - `teams.py`
**Status:** Complete (Phase 13.2)

Players are divided into teams and compete against other teams. Last team standing wins.

**Features:**
- Automatic team assignment (round-robin)
- Team colors from predefined palette (Pink, Magenta, Orange, Yellow, Green, Turquoise, Blue, Purple)
- Streams controller states at 60Hz from ControllerManager
- Fetches settings (sensitivity, audio, num_teams) from Settings service
- Detects deaths based on acceleration thresholds
- Publishes real-time events with team information
- Full OpenTelemetry instrumentation

**Events Published:**
- `game_starting` - Game initialization (includes num_teams)
- `players_initialized` - Players loaded and assigned to teams
- `countdown_start` / `countdown_end` - Countdown phase
- `game_started` - Game loop begins
- `player_death` - Player died (includes team, alive_teams_count)
- `team_winner` - Winning team determined (includes team name, color, winning players)
- `game_ended` - Game finished

**Configuration:**
- `num_teams` - Number of teams (default: 2, supports 2-8 teams)

### ✅ Random Teams - `random_teams.py`
**Status:** Complete (Phase 13.2)

Players are randomly assigned to teams and compete against other teams. Team colors are shown before the game starts so players can identify their teammates. Last team standing wins.

**Features:**
- **Random team assignment** (shuffled, not round-robin)
- **Random team colors** (shuffled from predefined palette)
- **Team formation phase** (5 seconds showing team colors before game starts)
- Streams controller states at 60Hz from ControllerManager
- Fetches settings (sensitivity, audio, random_team_size) from Settings service
- Detects deaths based on acceleration thresholds
- Publishes real-time events with team information
- Full OpenTelemetry instrumentation

**Events Published:**
- `game_starting` - Game initialization (includes num_teams)
- `players_initialized` - Players loaded and randomly assigned to teams (includes team_colors)
- `team_formation_start` - Team formation phase begins (shows team colors)
- `team_formation_end` - Team formation phase ends
- `countdown_start` / `countdown_end` - Countdown phase
- `game_started` - Game loop begins
- `player_death` - Player died (includes team, team_name, alive_teams_count)
- `team_winner` - Winning team determined (includes team name, color, winning players)
- `game_ended` - Game finished

**Configuration:**
- `random_team_size` - Number of teams (default: 2, supports 2-8 teams)

**Differences from Teams:**
- Random assignment instead of round-robin or pre-selected teams
- Random team color selection (shuffled each game)
- Team formation phase to show players their team assignments

## Architecture

### Game Base Pattern

```python
class GameMode:
    def __init__(
        self,
        controller_manager_client,  # gRPC stub
        settings_client,            # gRPC stub
        event_publisher: Callable,  # Event callback
        game_id: str
    ):
        # Initialize with gRPC clients
        # No direct hardware access
        # No multiprocessing primitives

    async def run(self):
        """Main game entry point (async)."""
        # IDLE → STARTING
        await self._load_settings()
        await self._initialize_players()
        await self._countdown()

        # STARTING → RUNNING
        await self._game_loop()

        # RUNNING → ENDING → ENDED
        await self._end_game()
```

### State Machine

All games follow the same lifecycle:

```
IDLE → STARTING → RUNNING → ENDING → ENDED
        ↑          ↓ (force_end)
        └──────────┘
```

### Communication Flow

```
GameCoordinator
    ↓ (creates game instance with gRPC clients)
GameMode
    ↓ (streams controller states)
ControllerManager → Real/Mock PS Move controllers
    ↓ (fetches settings)
Settings Service → joustsettings.yaml
```

## Testing

### Integration Tests

Each game mode has integration tests with mock gRPC services.

**Run FFA tests:**
```bash
cd services/game_coordinator
pytest test_ffa_integration.py -v -s
```

**Test structure:**
- `MockControllerManagerService` - Simulates controller states
- `MockSettingsService` - Provides mock settings
- `EventCollector` - Captures published events

**What tests verify:**
- ✅ Full game lifecycle (start → deaths → winner → end)
- ✅ Event publishing (all expected events published)
- ✅ Win conditions (correct winner determined)
- ✅ Settings loading (sensitivity, audio, etc.)
- ✅ Force end (graceful shutdown)

### Example Test

```python
@pytest.mark.asyncio
async def test_ffa_game_full_lifecycle(mock_controller_manager, mock_settings, event_collector):
    game = ffa_grpc.FFAGame(
        controller_manager_client=mock_controller_manager,
        settings_client=mock_settings,
        event_publisher=event_collector.publish,
        game_id="test_game_1"
    )

    await game.run()

    # Verify game completed
    assert game.state == ffa_grpc.GameState.ENDED

    # Verify events
    assert event_collector.count_events_of_type("player_death") == 2
    assert event_collector.count_events_of_type("game_winner") == 1
```

## Development Guide

### Adding a New Game Mode

1. **Create game file:** `new_game_grpc.py`
2. **Implement async run() method**
3. **Use gRPC clients (no direct hardware access)**
4. **Publish events via callback**
5. **Add OpenTelemetry spans**
6. **Create integration tests**
7. **Register in GameCoordinator server.py**

### Game Mode Checklist

- [ ] Async `run()` method
- [ ] State machine (IDLE → STARTING → RUNNING → ENDING → ENDED)
- [ ] `_load_settings()` from Settings service
- [ ] `_initialize_players()` from ControllerManager
- [ ] `_game_loop()` with StreamControllerStates
- [ ] Event publishing for all game events
- [ ] OpenTelemetry spans
- [ ] `force_end()` method
- [ ] Integration tests with mocks
- [ ] Documentation

## Migration from Legacy

### Old Pattern (games/)
```python
# Direct hardware access ❌
self.moves = moves  # Direct PSMove objects

# Queue-based IPC ❌
self.command_queue = command_queue

# Shared namespace ❌
self.ns.settings['play_audio']

# Blocking execution ❌
self.game_loop()  # Blocks
```

### New Pattern (services/game_coordinator/games/)
```python
# gRPC communication ✅
controller_states = await self.controller_client.StreamControllerStates()

# Settings via gRPC ✅
settings = await self.settings_client.GetSettings()

# Event publishing ✅
self.event_publisher("player_death", {...})

# Async execution ✅
await self._game_loop()  # Non-blocking
```

## Performance

- **Game tick rate:** 60 FPS (configurable)
- **Controller stream:** 60 Hz (matches game tick rate)
- **Latency target:** < 10ms p95 (controller state → death detection)
- **OpenTelemetry overhead:** < 1ms per span

## Dependencies

### gRPC Services (Required)
- **ControllerManager** (localhost:50052) - Controller states
- **Settings** (localhost:50051) - Game settings

### Python Packages
- `grpcio` - gRPC client
- `opentelemetry-*` - Distributed tracing
- `pytest` - Testing framework
- `pytest-asyncio` - Async test support

## Observability

All games are fully instrumented with OpenTelemetry.

**View traces:**
```bash
# Start Jaeger UI
docker-compose up jaeger

# Open browser
http://localhost:16686

# Search for: game.id="ffa_*"
```

**Trace spans:**
- `ffa_run` - Full game execution
- `ffa_load_settings` - Settings fetch
- `ffa_initialize_players` - Player setup
- `ffa_countdown` - Countdown phase
- `ffa_game_loop` - Main game loop
- `ffa_kill_player` - Death event
- `ffa_end_game` - Game cleanup

## Legacy Files

Legacy game implementations (using multiprocessing Queues and direct hardware access) have been moved to `legacy_archived/`:
- `base.py` - Legacy base game class
- `ffa.py` - Legacy FFA implementation
- `joust_teams.py` - Legacy Teams implementation
- `joust_random_teams.py` - Legacy Random Teams implementation
- `player.py` - Legacy player tracking
- `pacemanager.py` - Legacy pace management

These files are kept for reference but are no longer used in the modern gRPC-based architecture.

## Support

- **Issues:** Report in project issue tracker
- **Phase:** Phase 13 (Game Modes Refactoring)
- **Status:** Complete (FFA, Teams, Random Teams implemented and tested)
