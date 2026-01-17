# Controller Backend Architecture (Phase 57)

## Overview

The controller manager now uses a unified backend system that supports multiple platforms and testing modes through a single interface.

**Before Phase 57:**
- Separate `Dockerfile.mock` for testing
- `MOCK_MODE=true` flag
- Tightly coupled to psmove + dbus-python
- Difficult to develop on Windows

**After Phase 57:**
- Single `Dockerfile` for all modes
- `CONTROLLER_BACKEND` environment variable selects implementation
- Clean abstraction via `ControllerBackend` interface
- Easy development on Windows/Linux/Mock

## Architecture

```
┌──────────────────────────────────────────┐
│     ControllerManagerServicer (gRPC)     │
│                                          │
│  - Stream controller states              │
│  - Handle LED/rumble commands            │
│  - Manage controller lifecycle           │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│       ControllerBackend (Interface)       │
│                                          │
│  - initialize()                          │
│  - get_controller_state(serial)          │
│  - set_led_color(serial, rgb)            │
│  - set_rumble(serial, intensity)         │
│  - scan_controllers()                    │
│  - connect_controller(address)           │
└────────────────┬─────────────────────────┘
                 │
       ┌─────────┴─────────┬─────────────┐
       ▼                   ▼             ▼
┌─────────────┐    ┌──────────────┐ ┌──────────┐
│  Bluetooth  │    │   Windows    │ │   Mock   │
│   Backend   │    │   Backend    │ │  Backend │
│             │    │              │ │          │
│ Linux/BlueZ │    │  psmoveapi   │ │ Testing  │
│ + psmove    │    │  (Windows)   │ │ (No HW)  │
└─────────────┘    └──────────────┘ └──────────┘
```

## Backends

### 1. BluetoothBackend (Production - Raspberry Pi)

**File**: `services/controller_manager/bluetooth_backend.py`

**Platform**: Linux (Raspberry Pi)

**Dependencies**:
- `psmove` - PS Move controller I/O
- `dbus-python` - BlueZ D-Bus communication
- `controller_state` - State tracking
- `pair` - Controller pairing

**Usage**:
```yaml
# docker-compose.yml (production)
controller-manager:
  environment:
    - CONTROLLER_BACKEND=bluetooth  # Auto-detected on Linux
```

**Features**:
- Full Bluetooth pairing support
- RSSI (signal strength) monitoring
- Battery level tracking
- Motion sensors (accel/gyro)
- LED + rumble control

### 2. WindowsBackend (Development)

**File**: `services/controller_manager/windows_backend.py`

**Platform**: Windows 10/11

**Dependencies**:
- `psmoveapi` only (no dbus required)

**Usage**:
```powershell
# Windows - Run natively (not in Docker)
$env:CONTROLLER_BACKEND = "windows"
python -m services.controller_manager.server --host 0.0.0.0 --port 50051
```

```yaml
# docker-compose.override.yml (WSL services)
game-coordinator:
  environment:
    - CONTROLLER_MANAGER_HOST=host.docker.internal:50051
```

**Features**:
- Pair via Windows Bluetooth settings
- Full LED + rumble support
- Motion sensors
- Battery monitoring
- **No RSSI** (Windows API limitation)

**Use Case**: Develop/debug with real controllers on Windows without deploying to Pi

### 3. MockBackend (Testing/CI)

**File**: `services/controller_manager/mock_backend.py`

**Platform**: Any (pure Python)

**Dependencies**: None

**Usage**:
```yaml
# docker-compose.mock.yml
controller-manager:
  environment:
    - CONTROLLER_BACKEND=mock
    - MOCK_CONTROLLER_COUNT=4
```

**Features**:
- Simulates 1-N controllers
- Random button presses
- Realistic motion sensor noise
- Battery drain simulation
- LED/rumble state tracking (no output)
- **No hardware required**

**Use Cases**:
- CI/CD pipelines
- Integration tests
- Development without controllers
- Automated testing

## Backend Selection

### Auto-Detection

The system auto-detects platform if `CONTROLLER_BACKEND` not set:

```python
# services/controller_manager/backend_factory.py
def create_backend():
    system = platform.system()

    if system == "Windows":
        return WindowsBackend()
    elif system == "Linux":
        return BluetoothBackend()
    else:
        raise RuntimeError("Unsupported platform")
```

### Manual Override

Force a specific backend with `CONTROLLER_BACKEND`:

```bash
export CONTROLLER_BACKEND=mock      # Use mock (any platform)
export CONTROLLER_BACKEND=bluetooth  # Force BlueZ (Linux only)
export CONTROLLER_BACKEND=windows    # Force Windows (Windows only)
```

## Docker Compose Integration

### Production (docker-compose.yml)

```yaml
controller-manager:
  dockerfile: services/controller_manager/Dockerfile
  privileged: true  # Bluetooth access
  devices:
    - /dev/bus/usb  # USB pairing
  environment:
    # CONTROLLER_BACKEND auto-detected (Linux → Bluetooth)
```

### Testing (docker-compose.mock.yml)

```yaml
mock-controller-manager:
  dockerfile: services/controller_manager/Dockerfile  # Same Dockerfile!
  environment:
    - CONTROLLER_BACKEND=mock  # No privileged mode, no devices needed
    - MOCK_CONTROLLER_COUNT=4
  # No 'privileged', no 'devices' - runs anywhere
```

### Development (docker-compose.override.yml)

```yaml
# Run controller_manager on Windows (native)
# WSL services connect via host.docker.internal

game-coordinator:
  environment:
    - CONTROLLER_MANAGER_HOST=host.docker.internal:50051

menu:
  environment:
    - CONTROLLER_MANAGER_HOST=host.docker.internal:50051
```

## Migration Guide

### Before Phase 57 (Old Approach)

```python
# server.py - Tightly coupled to psmove
import psmove
move = psmove.PSMove(0)
trigger = move.get_trigger()
move.set_leds(255, 0, 0)
```

```yaml
# Separate mock Dockerfile
services:
  mock-controller-manager:
    dockerfile: Dockerfile.mock  # Special mock image
    environment:
      - MOCK_MODE=true
```

### After Phase 57 (New Approach)

```python
# server.py - Uses backend abstraction
from backend_factory import create_backend

backend = create_backend()  # Auto-detects platform
await backend.initialize()
state = await backend.get_controller_state(serial)
await backend.set_led_color(serial, 255, 0, 0)
```

```yaml
# Single Dockerfile, backend selected via env var
services:
  mock-controller-manager:
    dockerfile: Dockerfile  # Same for all modes!
    environment:
      - CONTROLLER_BACKEND=mock
```

## Benefits

### 1. **Single Dockerfile**
- No more `Dockerfile.mock`
- Backend selected at runtime via environment variable
- Reduces maintenance burden

### 2. **Windows Development**
- Develop with real controllers on Windows/WSL
- No Pi deployment required for testing
- Full debugging in IDE

### 3. **Clean Testing**
- Mock backend has zero hardware dependencies
- Runs in CI without special setup
- Consistent behavior across environments

### 4. **Platform Independence**
- Same service code works on all platforms
- Backend handles platform-specific details
- Easy to add new backends (macOS, virtual controllers, etc.)

### 5. **No Code Changes for Mock**
- Set `CONTROLLER_BACKEND=mock` → instant mock mode
- No conditional code in service logic
- Clean separation of concerns

## Environment Variables

| Variable | Values | Default | Description |
|----------|---------|---------|-------------|
| `CONTROLLER_BACKEND` | `bluetooth`, `windows`, `mock` | Auto-detect | Force specific backend |
| `MOCK_CONTROLLER_COUNT` | 1-10 | 4 | Number of mock controllers |

## See Also

- [ControllerBackend Interface](../../services/controller_manager/backend.py)
