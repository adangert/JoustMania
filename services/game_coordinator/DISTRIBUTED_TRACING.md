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
  - **ControllerManager service**: `GetReadyControllers`, `StreamControllerStates`

### Trace Hierarchy

```
StartGame (incoming RPC to GameCoordinator)
├── ffa_run (game execution)
│   ├── ffa_load_settings
│   │   └── GetSettings → Settings service (outgoing RPC)
│   │       └── settings.validate_and_get
│   ├── ffa_initialize_players
│   │   └── GetReadyControllers → ControllerManager (outgoing RPC)
│   │       └── controller_manager.get_ready_controllers
│   ├── ffa_countdown
│   ├── ffa_game_loop
│   │   ├── StreamControllerStates → ControllerManager (outgoing RPC)
│   │   │   └── controller_manager.stream_controller_states
│   │   ├── player_controller_0_lifecycle
│   │   │   ├── player_warning (event)
│   │   │   └── player_survived (event)
│   │   ├── player_controller_1_lifecycle
│   │   │   ├── player_warning (event)
│   │   │   └── player_death (event)
│   │   └── player_controller_2_lifecycle
│   │       └── player_death (event)
│   └── ffa_end_game
└── game_ended (event)
```

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

### No Changes Needed in Game Modes

Game modes (ffa.py, teams.py, random_teams.py) continue to make normal gRPC calls:

```python
# Automatically traced by GrpcInstrumentorClient
response = self.settings_client.GetSettings(settings_pb2.GetSettingsRequest())

# Automatically traced by GrpcInstrumentorClient
response = self.controller_client.GetReadyControllers(
    controller_manager_pb2.GetReadyControllersRequest()
)

# Automatically traced by GrpcInstrumentorClient (streaming)
async for state_update in self.controller_client.StreamControllerStates(stream_request):
    # Process states...
```

## Viewing Traces in Jaeger

### 1. Start All Services

```bash
docker-compose up
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

**By Operation:**
```
operation="StartGame"
```

**By Game Mode:**
```
game.mode="FFA"
```

**By Player:**
```
player.serial="controller_abc123"
```

### 5. Explore the Trace

You should see:
- **Root span**: `StartGame` (incoming RPC to GameCoordinator)
- **Child spans**:
  - `ffa_run` (game execution)
  - `GetSettings` (outgoing RPC to Settings)
  - `GetReadyControllers` (outgoing RPC to ControllerManager)
  - `StreamControllerStates` (streaming RPC to ControllerManager)
  - Per-player lifecycle spans
  - Team lifecycle spans (for team games)

## Metrics Available

### Latency Metrics

**Cross-Service Latency:**
- Time from `ffa_load_settings` to `GetSettings` response
- Time from `ffa_initialize_players` to `GetReadyControllers` response
- Time from `ffa_game_loop` to first `StreamControllerStates` frame

**Game Phase Latency:**
- Settings load time
- Player initialization time
- Countdown duration
- Game loop duration (per frame at 60 FPS)
- End game duration

**Player-Level Latency:**
- Time to first warning
- Time to death
- Survival duration

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
docker-compose logs otel-collector
```

**Check Service Logs:**
```bash
docker-compose logs game-coordinator
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

**Symptom:** You see `ffa_run` but no `player_controller_X_lifecycle` spans.

**Cause:** Game didn't start properly or no players detected.

**Solution:**
- Check ControllerManager is returning controllers
- Verify `GetReadyControllers` RPC succeeds
- Look for `players_initialized` event in logs

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
   - `StreamControllerStates` - Stream controller states at 60Hz
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

## Future Enhancements

### 1. Menu → GameCoordinator Traces
When Menu service calls `StartGame`, trace will show:
```
ProcessInput (Menu) → StartGame (GameCoordinator) → ffa_run → ...
```

### 2. Audio Service Integration
When GameCoordinator calls Audio service:
```
ffa_countdown → PlaySound (Audio) → audio.play
```

### 3. Multi-Game Sessions
Track multiple games in sequence:
```
StartGame (game1) → ... → game_ended
StartGame (game2) → ... → game_ended
StartGame (game3) → ... → game_ended
```

### 4. Advanced Analytics
- Player behavior across multiple games
- Team composition impact on win rate
- Optimal sensitivity thresholds
- Controller hardware reliability

## References

- **OpenTelemetry gRPC Instrumentation**: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/grpc/grpc.html
- **Per-Player Tracing**: See `PER_PLAYER_TRACING.md` in this directory
- **Game Modes Architecture**: See `README.md` in this directory
