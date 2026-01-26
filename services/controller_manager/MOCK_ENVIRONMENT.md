# Mock Hardware Environment

## Overview

The mock hardware environment allows you to develop, test, and demo JoustMania **without physical PS Move controllers or Bluetooth hardware**. This is achieved by replacing the real ControllerManager with a MockControllerManager that simulates PS Move controllers via gRPC.

## Benefits

1. **No Hardware Required** - Test on any machine (no Bluetooth adapter needed)
2. **Automated Testing** - Run integration tests in CI/CD pipelines
3. **Controllable Scenarios** - Script specific game outcomes via gRPC
4. **Fast Development** - No need to physically move controllers during development
5. **Trace Generation** - Create perfect distributed traces for demos
6. **Performance Testing** - Simulate 100+ controllers without hardware limits

## Architecture

### Real Hardware (Production)

```
ControllerManager (server.py)
├── Bluetooth/USB Hardware Detection
├── PSMove Library (libpsmoveapi)
├── Real Controller State Reading (60Hz)
└── gRPC Server (StreamGameplayData)
```

### Mock Hardware (Testing/Development)

```
ControllerManager (server.py with MockBackend)
├── Mock Controller Pool (configurable count)
├── Simulated State Generation (mock_backend.py)
├── gRPC Control API (mock_control_service.py)
└── gRPC Server (same interface as real)
```

## Quick Start

### 1. Start Mock Environment

Mock mode is enabled automatically when `docker-compose.override.yml` is present (default for development).

```bash
# Start all services with mock hardware (uses override file automatically)
docker compose up

# Or in detached mode
docker compose up -d

# For production mode without mock (skip override file)
docker compose -f docker-compose.yml up
```

### 2. Run a Game Simulation

```bash
# Simulate an FFA game with 4 controllers for 30 seconds
python scripts/testing/simulate_game.py --mode FFA --controllers 4 --duration 30

# Simulate a Teams game
python scripts/testing/simulate_game.py --mode Teams --teams 2 --controllers 4 --duration 30
```

### 3. View Traces in Jaeger

Open Jaeger UI: http://localhost:16686

Search for traces:
```
service="game-coordinator-service" AND game.mode="FFA"
```

You should see complete end-to-end traces showing:
- StartGame → Settings → ControllerManager → Game Loop
- Per-player lifecycle spans
- Per-team spans (for team games)
- All service interactions

## Configuration

### Mock Controller Count

Set the number of mock controllers via environment variable:

```yaml
# docker-compose.override.yml
controller-manager:
  environment:
    - MOCK_CONTROLLER_COUNT=8  # Change from default 4 to 8 controllers
```

Or via command line:

```bash
MOCK_CONTROLLER_COUNT=8 docker compose up
```

### Mock Controller Properties

Each mock controller has:
- **Serial**: `mock_controller_0`, `mock_controller_1`, etc.
- **Battery**: 100% (fixed)
- **Ready**: Always true
- **Acceleration**: Controllable via gRPC (default: idle at 0,0,1)
- **Gyroscope**: Controllable via gRPC (default: 0,0,0)
- **Buttons**: Controllable via gRPC (trigger, move, select, start)
- **Color**: Controllable via gRPC (default: white)

## Control API

The MockControllerManager exposes a control API on port **50062** for programmatically controlling mock controllers.

### List Controllers

```bash
grpcurl -plaintext localhost:50062 \
  controller_manager_mock.MockControllerService/ListMockControllers
```

Response:
```json
{
  "serials": ["mock_controller_0", "mock_controller_1", "mock_controller_2", "mock_controller_3"],
  "count": 4
}
```

### Simulate Movement

Set acceleration (for warning-level movement):

```bash
grpcurl -plaintext -d '{
  "serial": "mock_controller_0",
  "accel_x": 2.0,
  "accel_y": 1.5,
  "accel_z": 1.2
}' localhost:50062 \
  controller_manager_mock.MockControllerService/SimulateMovement
```

### Simulate Death

Trigger death-level acceleration (>2.8 for FAST sensitivity):

```bash
grpcurl -plaintext -d '{
  "serial": "mock_controller_0"
}' localhost:50062 \
  controller_manager_mock.MockControllerService/SimulateDeath
```

Response:
```json
{
  "success": true,
  "accel_magnitude": 7.07  # Actual magnitude simulated
}
```

### Simulate Button Press

```bash
grpcurl -plaintext -d '{
  "serial": "mock_controller_0",
  "button": 0,
  "pressed": true
}' localhost:50062 \
  controller_manager_mock.MockControllerService/SimulateButton
```

Button codes:
- `0` = TRIGGER
- `1` = MOVE
- `2` = SELECT
- `3` = START

### Set LED Color

```bash
grpcurl -plaintext -d '{
  "serial": "mock_controller_0",
  "r": 255,
  "g": 0,
  "b": 0
}' localhost:50062 \
  controller_manager_mock.MockControllerService/SetColor
```

### Reset Controller

Reset to idle state (accel=0,0,1, buttons unpressed):

```bash
grpcurl -plaintext -d '{
  "serial": "mock_controller_0"
}' localhost:50062 \
  controller_manager_mock.MockControllerService/ResetController
```

## Automated Testing

### Integration Tests with Testcontainers

Run full integration tests that spin up the entire stack:

```bash
# Install all workspace members including integration tests
uv sync --all-packages

# Run integration tests (auto-teardown) - using uv script
./scripts/testing/test-mock.py

# Run with pause to inspect Jaeger before teardown
./scripts/testing/test-mock-with-pause.py

# Or run manually with pytest
uv run --package joustmania-integration-tests pytest tests/integration/ -v
PAUSE_BEFORE_TEARDOWN=1 uv run --package joustmania-integration-tests pytest tests/integration/ -v -s
```

**Note:** Integration tests are maintained as a separate workspace member (`tests/integration`)
with their own dependencies. See [tests/integration/README.md](../../tests/integration/README.md).

When using `PAUSE_BEFORE_TEARDOWN=1`:
- Tests run normally
- Environment stays up after tests complete
- You can browse Jaeger UI at http://localhost:16686
- Inspect distributed traces from test runs
- Press ENTER when done to tear down

These tests:
- Start docker-compose.yml with override file using testcontainers
- Connect to all services via gRPC
- Run full game simulations
- Verify controller control API
- Test distributed tracing propagation
- Clean up automatically (or on ENTER if paused)

### Test Coverage

Integration tests cover:
- ✅ Mock controller manager connection
- ✅ Controller control API (movement, death, buttons, color, reset)
- ✅ Full FFA game lifecycle
- ✅ Full Teams game lifecycle
- ✅ Controller state streaming at 60Hz
- ✅ Distributed tracing propagation across services
- ✅ Multiple games in sequence

## Game Simulation Scripts

### FFA Game Simulation

```bash
python scripts/testing/simulate_game.py \
  --mode FFA \
  --controllers 4 \
  --duration 30
```

Output:
```
🎮 Starting FFA game simulation with 4 controllers
✅ Game started: game_abc123
⚠️  Controller 1 moved (warning)
💀 Controller 2 died! (accel: 7.07)
   3 controllers remaining
⚠️  Controller 0 moved (warning)
💀 Controller 3 died! (accel: 7.07)
   2 controllers remaining
🏁 Game ending. Winner: Controller 0
✅ Game simulation complete
```

### Teams Game Simulation

```bash
python scripts/testing/simulate_game.py \
  --mode Teams \
  --controllers 6 \
  --teams 3 \
  --duration 45
```

### Custom Simulation Script

```python
import asyncio
import grpc
from services.controller_manager import controller_manager_mock_pb2_grpc
from services.game_coordinator import game_coordinator_pb2_grpc

async def my_scenario():
    # Connect to services
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(
        grpc.aio.insecure_channel('localhost:50062')
    )
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(
        grpc.aio.insecure_channel('localhost:50053')
    )

    # Start game
    await game_client.StartGame(
        game_coordinator_pb2.StartGameRequest(mode="FFA")
    )

    # Simulate specific scenario
    await asyncio.sleep(2)
    await mock_client.SimulateDeath(
        controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
    )

    # End game
    await game_client.ForceEndGame(
        game_coordinator_pb2.ForceEndGameRequest()
    )

asyncio.run(my_scenario())
```

## Distributed Tracing

The mock environment includes full distributed tracing support via OpenTelemetry and Jaeger.

### Viewing Traces

1. **Open Jaeger UI**: http://localhost:16686

2. **Search for game traces**:
   - Service: `game-coordinator-service`
   - Operation: `StartGame`
   - Tags: `game.mode="FFA"`, `player.serial="mock_controller_0"`

3. **Explore the trace hierarchy**:
   ```
   StartGame
   └── ffa_run
       ├── ffa_load_settings
       │   └── GetSettings → settings-service
       ├── ffa_initialize_players
       │   └── GetReadyControllers → controller-manager-service
       ├── ffa_game_loop
       │   ├── StreamGameplayData → controller-manager-service
       │   ├── player_mock_controller_0_lifecycle
       │   │   ├── player_warning (event)
       │   │   └── player_death (event)
       │   ├── player_mock_controller_1_lifecycle
       │   │   └── player_survived (event)
       │   └── ...
       └── ffa_end_game
   ```

### Trace Attributes

Mock controllers include special attributes:
- `mock.enabled: true` - Indicates mock environment
- `player.serial: mock_controller_X` - Mock controller serial
- `game.mode: FFA/Teams/RandomTeams` - Game mode

## Comparison: Real vs Mock

| Aspect | Real Hardware | Mock Hardware |
|--------|---------------|---------------|
| **Bluetooth Required** | ✅ Yes | ❌ No |
| **Physical Controllers** | ✅ Yes (PS Move) | ❌ No |
| **Privileged Docker** | ✅ Yes | ❌ No |
| **USB Devices** | ✅ /dev/bus/usb | ❌ None |
| **DBus Access** | ✅ Yes | ❌ No |
| **Controller Count** | Limited by hardware | Unlimited (configurable) |
| **Controllability** | Physical movement | gRPC API |
| **CI/CD Compatible** | ❌ No | ✅ Yes |
| **Trace Quality** | Real-world | Perfect (controllable) |
| **Cost** | ~$30/controller | Free |

## Troubleshooting

### Services Not Starting

**Check container logs:**
```bash
docker compose logs controller-manager
```

**Check health:**
```bash
docker compose ps
```

### Controller Count Mismatch

**Verify environment variable:**
```bash
docker compose config | grep MOCK_CONTROLLER_COUNT
```

**Check via control API:**
```bash
grpcurl -plaintext localhost:50062 \
  controller_manager_mock.MockControllerService/ListMockControllers
```

### Traces Not Appearing in Jaeger

**Check OTLP collector:**
```bash
docker compose logs otel-collector
```

**Verify controller manager telemetry:**
```bash
docker compose logs controller-manager | grep "OpenTelemetry"
```

Should see:
```
OpenTelemetry initialized for mock controller manager
```

### Game Simulation Fails

**Verify services are ready:**
```bash
# Wait for all services to be healthy
docker compose ps

# Test game coordinator connection
grpcurl -plaintext localhost:50053 \
  game_coordinator.GameCoordinatorService/GetGameStatus
```

**Check game coordinator logs:**
```bash
docker compose logs game-coordinator
```

## Performance

### Mock vs Real Overhead

| Metric | Real Hardware | Mock Hardware | Difference |
|--------|---------------|---------------|------------|
| **Startup Time** | ~5-10s (Bluetooth) | ~2-3s | 50-70% faster |
| **Memory Usage** | ~100MB | ~50MB | 50% less |
| **CPU Usage** | ~10% (USB polling) | ~2% | 80% less |
| **State Update Latency** | ~16ms (60Hz) | ~16ms (60Hz) | Same |
| **gRPC Call Latency** | ~1-2ms | ~1-2ms | Same |

### Scaling Tests

Mock environment can simulate large player counts:

```bash
# 16 players
MOCK_CONTROLLER_COUNT=16 docker compose up

# 100 players (stress test)
MOCK_CONTROLLER_COUNT=100 docker compose up
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync

      - name: Run integration tests
        run: |
          pytest tests/integration/test_mock_environment.py -v
```

## Future Enhancements

### Planned Features

1. **Network Latency Simulation** - Add artificial latency to gRPC calls
2. **Controller Disconnect Simulation** - Test error handling
3. **Battery Drain Simulation** - Test low-battery scenarios
4. **Button State History** - Record button press sequences
5. **Motion Replay** - Record and replay real controller movement
6. **WebUI Control Panel** - Browser-based controller control
7. **Load Testing** - Automated performance benchmarks

### Mock Audio Service

Currently, the audio service runs in mock mode (MOCK_MODE=true) but still requires the audio assets directory. Future enhancement: provide silent audio playback or optional audio synthesis.

## Related Documentation

- **[DISTRIBUTED_TRACING.md](../game_coordinator/DISTRIBUTED_TRACING.md)** - Distributed tracing architecture
- **[PER_PLAYER_TRACING.md](../game_coordinator/PER_PLAYER_TRACING.md)** - Per-player span tracking
- **[Phase 14 Plan](../../planning/PHASE_14_MOCK_HARDWARE.md)** - Implementation plan
- **[Game Modes README](../game_coordinator/README.md)** - Game modes architecture

## Summary

The mock hardware environment provides a **complete testing and development solution** without requiring physical PS Move controllers. It maintains the same gRPC interface as the real ControllerManager while adding programmable control via a secondary gRPC API.

Key features:
- ✅ Zero hardware dependencies
- ✅ Fully controllable via gRPC
- ✅ Complete distributed tracing
- ✅ Integration test support with testcontainers
- ✅ CI/CD compatible
- ✅ Scalable to 100+ mock controllers

**Perfect for:**
- Development on machines without Bluetooth
- Automated testing in CI/CD pipelines
- Demo trace generation
- Performance testing
- Integration testing without hardware setup
