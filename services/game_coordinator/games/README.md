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

All games are fully instrumented with OpenTelemetry distributed tracing.

### Viewing Traces

**Start Jaeger UI:**
```bash
docker-compose up jaeger

# Open browser
open http://localhost:16686

# Search for traces:
# - Service: game-coordinator-service
# - Operation: Free-For-All, Teams, Random Teams
```

### Expected Span Structure by Game Mode

All game modes follow a consistent span hierarchy. The root span is created in `server.py` with a FOLLOWS_FROM link to the `StartGame` RPC span.

#### FFA (Free-For-All) - Flat Hierarchy

```
Free-For-All (game span)
├── initialization_phase
│   ├── load_settings
│   └── initialize_players
├── ffa_colors_phase (player colors shown)
├── countdown_phase
├── gameplay_phase
│   ├── player_lifecycle [player.serial=<serial1>]
│   │   ├── death_warning (event)
│   │   └── player_death (event) → span ends
│   ├── player_lifecycle [player.serial=<serial2>]
│   │   └── victory (event) → span ends (winner)
│   └── player_lifecycle [player.serial=<serial3>]
│       └── player_death (event) → span ends
└── teardown_phase
    └── end_game_impl
```

**Key Characteristics:**
- **Flat player hierarchy**: Player spans are direct children of `gameplay_phase`
- **Consistent span naming**: All player spans use the same name `player_lifecycle`, differentiated by `player.serial` attribute
- **Player span duration**: Spans start when game begins, end when player dies or game ends
- **Death events**: Each player span includes `death_warning` events (if applicable) and `player_death` or `victory` events

#### Teams - 2-Level Hierarchy

```
Teams (game span)
├── initialization_phase
│   ├── load_settings
│   └── initialize_players (with team assignment)
├── countdown_phase
├── gameplay_phase
│   ├── team_lifecycle [team.number=0, team.name=Pink]
│   │   ├── player_lifecycle [player.serial=<serial1>]
│   │   │   ├── death_warning (event)
│   │   │   └── player_death (event) → span ends
│   │   ├── player_lifecycle [player.serial=<serial2>]
│   │   │   └── player_death (event) → span ends
│   │   └── team_eliminated (event) → team span ends
│   ├── team_lifecycle [team.number=1, team.name=Magenta]
│   │   ├── player_lifecycle [player.serial=<serial3>]
│   │   │   └── player_survived (event) → span ends
│   │   └── player_lifecycle [player.serial=<serial4>]
│   │       └── player_survived (event) → span ends
│   └── team_victory (event) → team span ends
└── teardown_phase
    └── end_game_impl
```

**Key Characteristics:**
- **Hierarchical structure**: `gameplay_phase` → `team_lifecycle` → `player_lifecycle`
- **Consistent span naming**: All team spans use `team_lifecycle`, all player spans use `player_lifecycle`
- **Span attributes**: Teams differentiated by `team.number` and `team.name`, players by `player.serial`
- **Team spans**: One span per team, ends when team is eliminated or game ends
- **Player spans**: Nested under their team span, end when player dies or game ends
- **Team events**: `team_eliminated` when last player dies, `team_victory` for winning team

#### Random Teams - 2-Level Hierarchy with Team Formation

```
Random Teams (game span)
├── initialization_phase
│   ├── load_settings
│   └── initialize_players (with random team assignment)
├── team_formation_phase (5 seconds showing team colors)
├── countdown_phase
├── gameplay_phase
│   ├── team_lifecycle [team.number=0, team.name=<RandomColor1>]
│   │   ├── player_lifecycle [player.serial=<serial1>]
│   │   │   └── player_death (event) → span ends
│   │   └── player_lifecycle [player.serial=<serial2>]
│   │       └── player_death (event) → span ends
│   │   └── team_eliminated (event) → team span ends
│   └── team_lifecycle [team.number=1, team.name=<RandomColor2>]
│       ├── player_lifecycle [player.serial=<serial3>]
│       │   └── player_survived (event) → span ends
│       └── player_lifecycle [player.serial=<serial4>]
│           └── player_survived (event) → span ends
│       └── team_victory (event) → team span ends
└── teardown_phase
    └── end_game_impl
```

**Key Characteristics:**
- **Additional phase**: `team_formation_phase` (unique to Random Teams)
- **Random colors**: Team colors are shuffled each game (reflected in `team.name` attribute)
- **Same hierarchy as Teams**: 2-level hierarchy (team → player)
- **Consistent span naming**: Same as Teams - `team_lifecycle` and `player_lifecycle` with attributes

### Span Naming Conventions (OpenTelemetry Best Practices)

JoustMania follows OpenTelemetry best practices for span naming to ensure:
- **Low-cardinality span names** for efficient aggregation and analysis
- **High-cardinality data in attributes** for filtering and detailed inspection
- **Consistent naming** across game modes where operations are similar

#### Naming Strategy

**✅ Use consistent names for similar operations:**
- All player lifecycle spans use `"player_lifecycle"` (not `"player_<serial>_lifecycle"`)
- All team lifecycle spans use `"team_lifecycle"` (not `"team_0_Pink_lifecycle"`)
- Differentiation happens via attributes (e.g., `player.serial`, `team.number`, `team.name`)

**✅ Use different names for fundamentally different operations:**
- Game mode spans differ by operation: `"Free-For-All"`, `"Teams"`, `"Random Teams"`
- Phase spans differ by purpose: `"initialization_phase"`, `"gameplay_phase"`, `"teardown_phase"`

**Why this matters:**
- **Cardinality**: Span names create unique operation types in tracing backends. High-cardinality names (e.g., one per player serial) can overwhelm the system and make queries difficult.
- **Aggregation**: Consistent names allow you to query "all player lifecycles" and filter by serial, team, or game mode via attributes.
- **Performance**: Low-cardinality span names reduce index size and improve query performance in Jaeger/Tempo.

**Example queries enabled by this approach:**
```
# Find all player lifecycle spans across all games
operation=player_lifecycle

# Filter to specific player
operation=player_lifecycle player.serial="00:06:F7:AB:CD:EF"

# Find all team lifecycle spans in Teams games
operation=team_lifecycle game.mode="Teams"

# Compare player lifecycle duration across game modes
operation=player_lifecycle | group by game.mode
```

### Span Attributes

**Game Span Attributes:**
- `game.name` - Game mode name (e.g., "Free-For-All", "Teams")
- `game.id` - Unique game instance ID
- `player.count` - Number of players

**Phase Span Attributes:**
- `game.id` - Links to game span
- `game.mode` - Game mode name
- `player_count` - Number of players (initialization phase)

**Team Span Attributes (Teams/Random Teams only):**
- `team.number` - Team number (0-7)
- `team.name` - Team color name (e.g., "Pink", "Magenta")
- `team.color` - RGB tuple (e.g., "(255, 108, 108)")
- `game.mode` - Game mode name

**Player Span Attributes:**
- `player.serial` - Controller serial number
- `player.team` - Team number (0 for FFA)
- `player.team_name` - Team color name (Teams/Random Teams)
- `player.color` - Player LED color RGB tuple
- `game.mode` - Game mode name

**Player Span Events:**
- `death_warning` - Acceleration exceeded warning threshold
  - Attributes: `accel_magnitude`, `threshold`
- `player_death` - Player died
  - Attributes: `accel_magnitude`, `threshold`, `alive_count`, `team_eliminated` (Teams only)
- `victory` / `player_survived` - Player survived until game end
  - Attributes: `game_duration`, `winner`

### Implementation Notes

**Span Registration with OpenTelemetry SDK:**

For Teams and Random Teams, team and player spans are created using `trace.use_span()` to properly register them with the OpenTelemetry SDK for export:

```python
# Create team span and register with SDK
team_span = tracer.start_span("team_lifecycle", context=gameplay_context,
                                attributes={"team.number": 0, "team.name": "Pink", ...})

# Register with SDK using trace.use_span()
with trace.use_span(team_span, end_on_exit=False):
    team.span = team_span  # Store for manual .end() later

    # Create player spans while team is current
    for player in team_players:
        player_span = tracer.start_span("player_lifecycle",
                                        context=otel_context.get_current(),
                                        attributes={"player.serial": serial, ...})
```

This ensures:
- Team spans are properly tracked by the SDK export pipeline
- Player spans are created as children of team spans
- All spans appear in Jaeger traces with correct hierarchy

**Why `trace.use_span()` is necessary:**
- `tracer.start_span()` creates a span but doesn't make it "current"
- `trace.set_span_in_context()` creates a NEW context that isn't registered with the SDK
- `trace.use_span()` makes the span current AND registers it with the SDK for export

### Troubleshooting Missing Spans

If spans don't appear in Jaeger:

1. **Check OTLP Collector logs:**
   ```bash
   docker-compose logs otel-collector | grep error
   ```

2. **Check Jaeger import:**
   ```bash
   docker-compose logs jaeger | grep error
   ```

3. **Verify span creation in game-coordinator logs:**
   ```bash
   docker-compose logs game-coordinator | grep span
   ```

4. **Query Jaeger API:**
   ```bash
   curl "http://localhost:16686/api/traces?service=game-coordinator-service&operation=Teams&lookback=5m&limit=1"
   ```

5. **Check that `trace.use_span()` is used for hierarchical spans** (Teams/Random Teams)

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
