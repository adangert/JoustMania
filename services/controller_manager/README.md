# Controller Manager Service

**Part of JoustMania Microservices Architecture**

## Overview

The Controller Manager service is the central component for managing PS Move controllers in JoustMania. It provides a gRPC API for controller discovery, state streaming, LED control, vibration feedback, and visual effects.

## Key Features

- **Controller Discovery**: Automatic detection and pairing of PS Move controllers
- **Real-time State Streaming**: 60 Hz controller state updates via gRPC streaming
- **LED Control**: Set individual or global controller LED colors
- **Vibration Feedback**: Rumble with configurable intensity and duration
- **Visual Effects**: Flash, pulse, rainbow, fade animations
- **Button Events**: Stream button press/release events
- **Battery Monitoring**: Low battery warnings with visual feedback

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Controller Manager Service                  │
├─────────────────────────────────────────────────────────────┤
│                      gRPC API Layer                          │
│  - StreamButtonEvents (bidirectional - buttons + LED ctrl)   │
│  - StreamGameplayData (bidirectional - motion + feedback)    │
│  - PlayControllerEffect                                      │
├─────────────────────────────────────────────────────────────┤
│                    Backend Abstraction                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ Bluetooth   │  │  Windows    │  │    Mock     │          │
│  │  Backend    │  │  Backend    │  │   Backend   │          │
│  │ (Linux/Pi)  │  │ (psmoveapi) │  │  (Testing)  │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTROLLER_BACKEND` | auto | Force backend: `bluetooth`, `windows`, `mock` |
| `MOCK_CONTROLLERS` | `false` | Enable mock backend for testing |
| `MOCK_CONTROLLER_COUNT` | `4` | Number of mock controllers |
| `GRPC_PORT` | `50052` | gRPC server port |
| `PROMETHEUS_PORT` | `8001` | Prometheus metrics port |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OpenTelemetry endpoint |

### Backend Selection

The backend is selected automatically based on platform:
- **Linux**: BluetoothBackend (BlueZ/psmove)
- **Windows**: WindowsBackend (psmoveapi)
- **Testing**: MockBackend (simulated controllers)

Override with `CONTROLLER_BACKEND` environment variable or `MOCK_CONTROLLERS=true`.

## gRPC API

### Port
- **50052** (see docker-compose.yml)

### Proto Definition
See `proto/controller_manager.proto` for complete API specification.

### Key RPCs

```protobuf
// Real-time streaming (bidirectional)
rpc StreamButtonEvents(stream ButtonEventStreamControl) returns (stream ButtonEvent);
rpc StreamGameplayData(stream GameplayStreamControl) returns (stream GameplayDataUpdate);

// Feedback
rpc PlayControllerEffect(PlayControllerEffectRequest) returns (PlayControllerEffectResponse);
```

### Testing with grpcurl

```bash
# List available services
grpcurl -plaintext localhost:50052 list

# Play effect on controller
grpcurl -plaintext -d '{"serial": "CTRL001", "effect": 2, "color": {"r": 255, "g": 0, "b": 0}, "duration_ms": 500}' \
  localhost:50052 joustmania.ControllerManagerService/PlayControllerEffect
```

## Metrics

Prometheus metrics available on port 8001:

| Metric | Type | Description |
|--------|------|-------------|
| `controller_manager_active_controllers` | Gauge | Number of active controllers |
| `controller_manager_controller_battery_level` | Gauge | Battery level per controller (0-5) |
| `controller_manager_button_events_total` | Counter | Button press/release events |
| `controller_manager_discovery_checks_total` | Counter | Discovery loop iterations |

## Backend Interface

All backends implement `ControllerBackend` abstract class:

```python
class ControllerBackend(ABC):
    async def initialize(self) -> bool
    async def scan_controllers(self) -> List[Dict]
    async def connect_controller(self, address: str) -> bool
    async def disconnect_controller(self, serial: str) -> bool
    async def get_controller_state(self, serial: str) -> Optional[Dict]
    async def set_led_color(self, serial: str, r: int, g: int, b: int) -> bool
    async def set_rumble(self, serial: str, intensity: int) -> bool
    def get_connected_controllers(self) -> List[str]
    async def shutdown()
```

## Performance Optimizations

### Adaptive Polling Frequency

Controllers are polled at different rates based on activity to reduce CPU usage when controllers are idle:

| State | Polling Rate | Interval | Condition |
|-------|--------------|----------|-----------|
| **Active** | 60Hz | 16ms | Button pressed OR accelerometer movement in last 5 seconds |
| **Idle** | 10Hz | 100ms | No activity for >5 seconds |

**How it works:**
1. Each poll cycle checks for activity: any button pressed, or accelerometer change above threshold (0.05)
2. Activity resets the idle timer to 0
3. After 5 seconds of no activity, the controller switches to idle polling rate
4. Any button press or movement immediately switches back to active polling

**Example savings (8 controllers, 3 actively playing):**
- Before: 8 controllers × 60Hz = 480 polls/second
- After: 3 active × 60Hz + 5 idle × 10Hz = 230 polls/second (**52% reduction**)

**Metrics to monitor:**
- `controller_adaptive_polling_active` - Controllers at 60Hz
- `controller_adaptive_polling_idle` - Controllers at 10Hz
- `controller_adaptive_polling_skipped_total` - Poll cycles skipped

### uvloop Event Loop

On Linux, the service uses [uvloop](https://github.com/MagicStack/uvloop) for 2-4x faster asyncio performance. This reduces input latency by 10-20%.

### LED Batch Updates (Phase 72)

LED updates are separated from controller polling and batched at 20Hz (every 50ms) instead of 60Hz. This reduces Bluetooth traffic while maintaining smooth visual feedback.

**Metrics:**
- `controller_led_batch_updates_total` - LED update cycles
- `controller_led_controllers_updated_per_batch` - Controllers updated per cycle

## Thread Safety

The service uses a `threading.RLock` (`state_lock`) to protect shared state accessed by both the discovery thread and gRPC handlers:
- `tracked_controllers`
- `controller_states`
- `button_states`

## Development

### Running Locally

```bash
# With real controllers (Linux)
uv run python -m services.controller_manager.server

# With mock controllers
MOCK_CONTROLLERS=true uv run python -m services.controller_manager.server
```

### Running Tests

```bash
# Run unit tests
uv run pytest services/controller_manager/tests/ -v

# Run with coverage
uv run pytest services/controller_manager/tests/ --cov=services.controller_manager
```

## Files

```
services/controller_manager/
├── server.py           # Main gRPC service implementation
├── backend.py          # Abstract backend interface
├── backend_factory.py  # Backend selection logic
├── bluetooth_backend.py # Linux/BlueZ implementation
├── mock_backend.py     # Mock backend for testing
├── effects_base.py     # Visual effect animations
├── metrics.py          # Prometheus metrics
├── pairing.py          # Controller pairing logic
├── bluetooth.py        # BlueZ helpers
├── process.py          # Controller process management
├── Dockerfile          # Container build
├── pyproject.toml      # Dependencies
└── tests/
    └── test_effects_base.py  # Effect unit tests
```

## See Also

- [Main Project Documentation](../../README.md)
- [Architecture Overview](../../docs/ARCHITECTURE.md)
- [Proto Definitions](../../proto/controller_manager.proto)
