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
- **Signal Strength**: RSSI monitoring for Bluetooth controllers (Linux only)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Controller Manager Service                  │
├─────────────────────────────────────────────────────────────┤
│                      gRPC API Layer                          │
│  - GetControllerCount, GetControllers, GetReadyControllers   │
│  - StreamControllerStates, StreamButtonEvents                │
│  - SetControllerColor, SetControllerVibration                │
│  - PlayControllerEffect, PairController, RemoveController    │
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
// Query controllers
rpc GetControllerCount(Empty) returns (GetControllerCountResponse);
rpc GetControllers(Empty) returns (GetControllersResponse);
rpc GetReadyControllers(Empty) returns (GetReadyControllersResponse);

// Real-time streaming
rpc StreamControllerStates(StreamRequest) returns (stream ControllerStateUpdate);
rpc StreamButtonEvents(StreamRequest) returns (stream ButtonEvent);

// Controller management
rpc PairController(PairControllerRequest) returns (PairControllerResponse);
rpc RemoveController(RemoveControllerRequest) returns (RemoveControllerResponse);

// Feedback
rpc SetControllerColor(SetControllerColorRequest) returns (SetControllerColorResponse);
rpc SetControllerVibration(SetControllerVibrationRequest) returns (SetControllerVibrationResponse);
rpc PlayControllerEffect(PlayControllerEffectRequest) returns (PlayControllerEffectResponse);
```

### Testing with grpcurl

```bash
# List available services
grpcurl -plaintext localhost:50052 list

# Get controller count
grpcurl -plaintext localhost:50052 joustmania.ControllerManagerService/GetControllerCount

# Get all controllers
grpcurl -plaintext localhost:50052 joustmania.ControllerManagerService/GetControllers

# Set LED color (all controllers to red)
grpcurl -plaintext -d '{"color": {"r": 255, "g": 0, "b": 0}}' \
  localhost:50052 joustmania.ControllerManagerService/SetControllerColor

# Set vibration with duration
grpcurl -plaintext -d '{"serial": "CTRL001", "intensity": 200, "duration_ms": 500}' \
  localhost:50052 joustmania.ControllerManagerService/SetControllerVibration
```

## Metrics

Prometheus metrics available on port 8001:

| Metric | Type | Description |
|--------|------|-------------|
| `controller_manager_active_controllers` | Gauge | Number of active controllers |
| `controller_manager_controller_battery_level` | Gauge | Battery level per controller (0-5) |
| `controller_manager_controller_rssi_dbm` | Gauge | Signal strength in dBm |
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
    async def get_rssi(self, serial: str) -> Optional[int]  # Optional
    async def shutdown()
```

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

# Windows development (see docs/development/windows-setup.md)
uv run --package joustmania-controller-manager python -m services.controller_manager.server
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
- [Windows Development Setup](../../docs/development/windows-setup.md)
- [Proto Definitions](../../proto/controller_manager.proto)
