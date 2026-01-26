# Distributed Tracing in GameCoordinator

## Overview

GameCoordinator now has **full distributed tracing** with OpenTelemetry, tracking both incoming requests (server-side) and outgoing calls to other services (client-side).

## Architecture

### OpenTelemetry Instrumentation

**Server-Side (Incoming RPCs):**
- `GrpcInstrumentorServer()` - Automatically traces all incoming gRPC requests
- Creates spans for: `StartGame`, `GetGameStatus`, `ForceEndGame`, `StreamGameEvents`

**Client-Side (Outgoing RPCs):**
- `GrpcInstrumentorClient()` - Automatically traces all outgoing gRPC calls
- Creates spans for calls to:
  - **Settings service**: `GetSettings`
  - **ControllerManager service**: `GetReadyControllers`, `StreamGameplayData`

### Trace Hierarchy

**Phase 36 Normalized Hierarchy** - All game modes follow consistent span naming:

#### FFA (Free-For-All)
```
StartGame (incoming RPC to GameCoordinator)
├── Free-For-All (game session)
│   ├── initialization_phase
│   │   ├── GetSettings → Settings service (outgoing RPC)
│   │   │   └── settings.validate_and_get
│   │   └── GetReadyControllers → ControllerManager (outgoing RPC)
│   │       └── controller_manager.get_ready_controllers
│   ├── countdown_phase
│   ├── gameplay_phase
│   │   ├── StreamGameplayData → ControllerManager (outgoing RPC)
│   │   │   └── controller_manager.stream_controller_states
│   │   ├── player_mock_controller_0_lifecycle
│   │   │   ├── player_warning (event)
│   │   │   └── player_death (event)
│   │   ├── player_mock_controller_1_lifecycle
│   │   │   ├── player_warning (event)
│   │   │   └── player_death (event)
│   │   └── player_mock_controller_2_lifecycle
│   │       └── player_survived (event)
│   └── teardown_phase
└── game_ended (event)
```

#### Teams / Random Teams (Hierarchical Spans)
```
StartGame (incoming RPC to GameCoordinator)
├── Teams (or "Random Teams") (game session)
│   ├── initialization_phase
│   │   ├── GetSettings → Settings service
│   │   └── GetReadyControllers → ControllerManager
│   ├── team_formation_phase (Random Teams only)
│   │   └── display_team_colors (event)
│   ├── countdown_phase
│   ├── gameplay_phase
│   │   ├── StreamGameplayData → ControllerManager
│   │   ├── team_0_lifecycle
│   │   │   ├── player_mock_controller_0_lifecycle
│   │   │   │   └── player_death (event)
│   │   │   ├── player_mock_controller_2_lifecycle
│   │   │   │   └── player_death (event)
│   │   │   └── team_eliminated (event)
│   │   └── team_1_lifecycle
│   │       ├── player_mock_controller_1_lifecycle
│   │       │   └── player_death (event)
│   │       └── player_mock_controller_3_lifecycle
│   │           └── player_survived (event)
│   └── teardown_phase
│       └── team_1_wins (event)
└── game_ended (event)
```

#### Nonstop Joust (Respawning Players)
```
StartGame (incoming RPC to GameCoordinator)
├── Nonstop Joust (game session)
│   ├── initialization_phase
│   │   ├── GetSettings → Settings service
│   │   └── GetReadyControllers → ControllerManager
│   ├── countdown_phase
│   ├── gameplay_phase
│   │   ├── StreamGameplayData → ControllerManager
│   │   ├── player_mock_controller_0_lifecycle (stays open)
│   │   │   ├── player_death (event)
│   │   │   ├── player_respawn (event)
│   │   │   └── player_death (event)
│   │   ├── player_mock_controller_1_lifecycle (stays open)
│   │   │   ├── player_death (event)
│   │   │   └── player_respawn (event)
│   │   └── player_mock_controller_2_lifecycle (stays open)
│   │       └── player_death (event)
│   └── teardown_phase
│       ├── final_scores (event)
│       └── winner_determined (event)
└── game_ended (event)
```

**Key Differences:**
- **FFA**: Flat player hierarchy, players die permanently (spans end)
- **Teams**: Hierarchical (team → player), team-based win condition
- **Random Teams**: Same as Teams + `team_formation_phase` before countdown
- **Nonstop Joust**: Player spans stay open, death events only, scoring-based winner

## Context Propagation

### Automatic Propagation

`GrpcInstrumentorClient` automatically:
1. Extracts trace context from incoming request
2. Injects trace context into outgoing gRPC calls via metadata
3. Maintains parent-child span relationships across service boundaries

### Manual Propagation (Not Required)

The game mode code (ffa.py, teams.py, random_teams.py) does **not** need to manually propagate context. The gRPC instrumentation handles this automatically.

## Implementation

### services/game_coordinator/server.py

```python
from opentelemetry.instrumentation.grpc import (
    GrpcInstrumentorServer,
    GrpcInstrumentorClient  # Added for client calls
)

def init_telemetry():
    """Initialize OpenTelemetry with OTLP exporter."""
    # ... TracerProvider setup ...

    # Instrument both server and client-side gRPC calls
    GrpcInstrumentorServer().instrument()  # Incoming RPCs
    GrpcInstrumentorClient().instrument()  # Outgoing RPCs
```

### Game Mode Span Management

**Phase 36b Base Class** - Span creation is now centralized in `BaseGameMode`:

```python
# BaseGameMode.run() orchestrates all spans automatically
async def run(self, game_context=None):
    """Template method handling span hierarchy."""
    span_name = get_game_display_name(self.get_game_name())

    with tracer.start_as_current_span(span_name, context=game_context) as game_span:
        # initialization_phase span
        with tracer.start_as_current_span("initialization_phase", ...):
            await self._load_settings()  # GetSettings RPC automatically traced
            await self._initialize_players()  # GetReadyControllers RPC automatically traced
            self._create_player_spans(game_context)

        # Additional phases (e.g., team_formation_phase)
        for phase in self._get_additional_phases():
            with tracer.start_as_current_span(phase.name, ...):
                await phase.execute()

        # countdown_phase, gameplay_phase, teardown_phase...
```

**Subclasses** (FFA, Teams, Random Teams, Nonstop Joust) focus on game-specific logic:
- Inherit span orchestration from `BaseGameMode`
- Implement abstract methods (`_initialize_players_impl`, `_create_player_spans`, etc.)
- Make normal gRPC calls (automatically traced by `GrpcInstrumentorClient`)

**Benefits:**
- **Consistency**: All game modes use identical span hierarchy
- **DRY**: Span creation logic exists in one place
- **Maintainability**: Fix span bugs once in base class

## Viewing Traces in Jaeger

### 1. Start All Services

```bash
docker compose up
```

### 2. Run a Game

Via WebUI or gRPC call:
```bash
grpcurl -plaintext -d '{"mode":"FFA"}' localhost:50053 game_coordinator.GameCoordinatorService/StartGame
```

### 3. Open Jaeger UI

```
http://localhost:16686
```

### 4. Search for Traces

**By Service:**
```
service="game-coordinator-service"
```

**By Operation (Root Span):**
```
operation="StartGame"
```

**By Game Mode (Human-Readable):**
```
operation="Free-For-All"
operation="Teams"
operation="Random Teams"
operation="Nonstop Joust"
```

**By Game Phase:**
```
operation="initialization_phase"
operation="countdown_phase"
operation="gameplay_phase"
operation="teardown_phase"
operation="team_formation_phase"  # Random Teams only
```

**By Player:**
```
player.serial="mock_controller_0"
```

**By Team (Team Games):**
```
team.number=0
team.number=1
```

### 5. Explore the Trace

You should see:
- **Root span**: `StartGame` (incoming RPC to GameCoordinator)
- **Game session span**: Human-readable name (`Free-For-All`, `Teams`, `Random Teams`, `Nonstop Joust`)
- **Phase spans**: Consistent across all modes
  - `initialization_phase` (contains Settings and ControllerManager RPCs)
  - `team_formation_phase` (Random Teams only)
  - `countdown_phase`
  - `gameplay_phase` (contains player/team lifecycle spans)
  - `teardown_phase`
- **Lifecycle spans**:
  - FFA/Nonstop: `player_{serial}_lifecycle` (flat hierarchy)
  - Teams/Random Teams: `team_{number}_lifecycle` → `player_{serial}_lifecycle` (hierarchical)
- **RPC spans** (automatic from instrumentation):
  - `GetSettings` (outgoing to Settings service)
  - `GetReadyControllers` (outgoing to ControllerManager)
  - `StreamGameplayData` (streaming from ControllerManager)

## Metrics Available

### Latency Metrics

**Cross-Service Latency:**
- Time from `initialization_phase` to `GetSettings` response
- Time from `initialization_phase` to `GetReadyControllers` response
- Time from `gameplay_phase` to first `StreamGameplayData` frame

**Game Phase Latency:**
- `initialization_phase` duration (settings + player setup)
- `team_formation_phase` duration (Random Teams: ~3 seconds)
- `countdown_phase` duration (typically 3 seconds)
- `gameplay_phase` duration (entire game, varies by mode)
- `teardown_phase` duration (cleanup + winner declaration)

**Player-Level Latency:**
- Time to first warning (high acceleration detected)
- Time to death (span duration for FFA/Teams)
- Survival duration (player lifecycle span length)
- Respawn time (Nonstop Joust: 3 seconds between death and respawn events)

**Team-Level Latency (Teams/Random Teams):**
- Team lifecycle span duration (formation → elimination)
- Time to team elimination
- Player death intervals within team

### Error Tracking

**Service Errors:**
- Settings service unavailable
- ControllerManager service unavailable
- gRPC call failures

**Game Errors:**
- Player initialization failures
- Controller stream errors
- Death detection errors

## Troubleshooting

### Traces Not Appearing

**Check OTLP Endpoint:**
```bash
# In docker-compose.yml or environment
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

**Check Collector Logs:**
```bash
docker compose logs otel-collector
```

**Check Service Logs:**
```bash
docker compose logs game-coordinator
# Look for: "OpenTelemetry initialized: game-coordinator-service -> ..."
```

### Traces Are Disconnected

**Symptom:** You see multiple separate traces instead of one connected trace.

**Cause:** Missing `GrpcInstrumentorClient()` instrumentation.

**Solution:** Verify both instrumentors are called:
```python
GrpcInstrumentorServer().instrument()
GrpcInstrumentorClient().instrument()  # Must be present
```

### Missing Player Spans

**Symptom:** You see `Free-For-All` (or other game mode) but no `player_{serial}_lifecycle` spans.

**Cause:** Game didn't start properly or no players detected.

**Solution:**
- Check ControllerManager is returning controllers
- Verify `GetReadyControllers` RPC succeeds in `initialization_phase`
- Look for `players_initialized` event in logs
- Check that `gameplay_phase` span exists (player spans created there)

### Missing Team Spans

**Symptom:** You see `Teams` or `Random Teams` but no `team_{number}_lifecycle` spans.

**Cause:** Team initialization failed or no teams created.

**Solution:**
- Verify at least 2 players are ready (minimum for team games)
- Check team assignment logic in initialization
- Look for `teams_created` event in logs
- Verify player → team assignment completed

## Performance Impact

### Overhead

**gRPC Instrumentation:**
- Server-side: ~0.1-0.5ms per RPC
- Client-side: ~0.1-0.5ms per RPC
- Streaming: ~0.01ms per message

**Span Creation:**
- Per-player spans: ~0.1ms to create
- Events: <0.01ms per event

**Total Overhead:**
- ~1-2ms per game for full distributed trace
- Negligible impact on 60 FPS game loop (16.67ms budget per frame)

### Optimization

**Batch Span Processor:**
```python
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
```
- Batches spans before sending to collector
- Reduces network overhead
- Default batch size: 512 spans

**Sampling (Optional):**
If overhead becomes an issue, configure sampling:
```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

provider = TracerProvider(
    sampler=TraceIdRatioBased(0.1),  # Sample 10% of traces
    resource=resource
)
```

## Service Dependencies

### GameCoordinator Makes Client Calls To:

1. **Settings Service** (localhost:50051)
   - `GetSettings` - Load game configuration
   - Called once per game in `_load_settings()`

2. **ControllerManager Service** (localhost:50052)
   - `GetReadyControllers` - Get available controllers
   - `StreamGameplayData` - Stream controller states at 60Hz
   - Called in `_initialize_players()` and `_game_loop()`

### GameCoordinator Receives Server Calls From:

1. **WebUI** (via HTTP → gRPC)
   - `StartGame` - User starts a game
   - `ForceEndGame` - User force ends a game
   - `GetGameStatus` - Poll game status

2. **Menu Service** (future)
   - `StartGame` - Menu system starts a game

3. **Supervisor Service** (future)
   - `GetGameStatus` - Health check

## Related Services

### Also Have Client Instrumentation:

**WebUI** (`services/webui/server.py`)
- Calls: Settings, ControllerManager, Menu, Supervisor, GameCoordinator
- Instrumented with: `GrpcInstrumentorClient()`

### Server-Only Instrumentation:

**Settings, ControllerManager, Menu, Supervisor, Audio**
- Only receive requests, don't make gRPC client calls
- Instrumented with: `GrpcInstrumentorServer()` only

## Completed Enhancements

### Phase 36: Span Hierarchy Normalization ✓
- **Human-readable game names**: `Free-For-All`, `Teams`, `Random Teams`, `Nonstop Joust`
- **Consistent phase spans**: `initialization_phase`, `countdown_phase`, `gameplay_phase`, `teardown_phase`
- **Standardized lifecycle spans**: `player_{serial}_lifecycle`, `team_{number}_lifecycle`
- **Hierarchical team spans**: Team spans contain player spans for Teams/Random Teams

### Phase 36b: Base Game Class Refactoring (In Progress)
- **BaseGameMode**: Template method pattern for span orchestration
- **Code reduction**: ~1,500 lines of duplicate code eliminated (56% reduction)
- **Consistent behavior**: All game modes inherit same span creation logic
- **Easier maintenance**: Fix span issues once in base class

## Future Enhancements

### 1. Menu → GameCoordinator Traces
When Menu service calls `StartGame`, trace will show:
```
ProcessInput (Menu) → StartGame (GameCoordinator) → Free-For-All → ...
```

### 2. Audio Service Integration
When GameCoordinator calls Audio service:
```
countdown_phase → PlaySound (Audio) → audio.play
```

### 3. Multi-Game Sessions
Track multiple games in sequence:
```
StartGame (game1) → Free-For-All → ... → game_ended
StartGame (game2) → Teams → ... → game_ended
StartGame (game3) → Random Teams → ... → game_ended
```

### 4. Advanced Analytics
- Player behavior across multiple games (survival rates, warning frequencies)
- Team composition impact on win rate
- Optimal sensitivity thresholds by player
- Controller hardware reliability (death patterns)
- Game duration comparisons by mode

## References

- **OpenTelemetry gRPC Instrumentation**: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/grpc/grpc.html
- **Per-Player Tracing**: See `PER_PLAYER_TRACING.md` in this directory
- **Game Modes Architecture**: See `README.md` in this directory
