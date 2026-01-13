# Phase 57: Windows Controller Backend for Development

## Goal
Enable development and debugging with real PS Move controllers on Windows/WSL by creating a platform-agnostic controller backend system with Windows support.

## Current State
✅ Controller Manager uses Linux/BlueZ for Bluetooth (services/controller_manager/bluetooth.py)
✅ Mock controller support exists for testing
❌ Cannot use real controllers on Windows/WSL during development
❌ Must deploy to Raspberry Pi for controller testing
❌ Tightly coupled to Linux dbus/BlueZ implementation

## Problem
Developers using Windows/WSL cannot test with real PS Move controllers:
- BlueZ (Linux Bluetooth stack) not available on Windows
- dbus not available on Windows
- USB/IP passthrough is complex and unreliable
- Testing requires deployment to Raspberry Pi

This slows down development iteration and makes debugging difficult.

## Solution
Create a platform-agnostic backend system:
1. Abstract controller interface (`ControllerBackend`)
2. Refactor existing BlueZ code to implement interface
3. Implement Windows backend using psmoveapi
4. Auto-detect platform and load appropriate backend
5. Run controller_manager natively on Windows, other services in WSL Docker

## Architecture

### Backend Interface
```python
# services/controller_manager/backend.py
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

class ControllerBackend(ABC):
    """Abstract interface for controller backends (BlueZ, Windows, Mock)"""

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the backend (connect to Bluetooth, etc.)"""
        pass

    @abstractmethod
    async def scan_controllers(self) -> List[Dict]:
        """Scan for available controllers"""
        pass

    @abstractmethod
    async def connect_controller(self, address: str) -> bool:
        """Connect to a controller by address"""
        pass

    @abstractmethod
    async def disconnect_controller(self, serial: str) -> bool:
        """Disconnect a controller"""
        pass

    @abstractmethod
    async def get_controller_state(self, serial: str) -> Optional[Dict]:
        """Get current state of a controller (battery, buttons, motion, etc.)"""
        pass

    @abstractmethod
    async def set_led_color(self, serial: str, r: int, g: int, b: int) -> bool:
        """Set LED color on a controller"""
        pass

    @abstractmethod
    async def set_rumble(self, serial: str, intensity: int) -> bool:
        """Set rumble intensity on a controller"""
        pass

    @abstractmethod
    def get_connected_controllers(self) -> List[str]:
        """Get list of connected controller serials"""
        pass

    @abstractmethod
    async def shutdown(self):
        """Cleanup resources"""
        pass
```

### Deployment Architecture
```
┌─────────────────────────┐         ┌─────────────────────────┐
│       Windows Host      │         │          WSL            │
│                         │         │                         │
│  PS Move Controllers    │         │                         │
│         ↓ Bluetooth     │         │                         │
│  ┌───────────────────┐  │         │  Docker Compose         │
│  │ Controller Manager│  │         │  ┌──────────────────┐   │
│  │  (Native Python)  │  │         │  │ Game Coordinator │   │
│  │                   │  │  gRPC   │  │                  │   │
│  │  Windows Backend  │◄─┼─────────┼──│  Connects to:    │   │
│  │  (psmoveapi)      │  │ :50051  │  │  host.docker     │   │
│  │                   │  │         │  │  .internal:50051 │   │
│  └───────────────────┘  │         │  └──────────────────┘   │
│                         │         │  ┌──────────────────┐   │
│                         │         │  │ Menu             │   │
│                         │         │  │ Audio            │   │
│                         │         │  │ Settings         │   │
│                         │         │  └──────────────────┘   │
└─────────────────────────┘         └─────────────────────────┘
```

## Implementation Steps

### 1. Create Abstract Backend Interface
**File**: `services/controller_manager/backend.py` (NEW)

Create the abstract base class with all controller operations as shown above.

### 2. Refactor BlueZ Implementation
**File**: `services/controller_manager/bluetooth_backend.py` (RENAMED from bluetooth.py)

```python
from controller_manager.backend import ControllerBackend
import dbus
# ... existing imports

class BluetoothBackend(ControllerBackend):
    """Linux BlueZ backend for PS Move controllers"""

    def __init__(self):
        self.bus = dbus.SystemBus()
        # ... existing initialization

    async def initialize(self) -> bool:
        # Existing BT adapter setup
        ...

    async def get_controller_state(self, serial: str) -> Optional[Dict]:
        # Extract from existing code
        return {
            'serial': serial,
            'battery': self._get_battery(serial),
            'trigger': self._get_trigger(serial),
            'move_button': self._get_move_button(serial),
            'accel': self._get_accel(serial),
            'gyro': self._get_gyro(serial),
            # ... etc
        }

    # Implement all other abstract methods using existing code
```

### 3. Create Windows Backend
**File**: `services/controller_manager/windows_backend.py` (NEW)

```python
from controller_manager.backend import ControllerBackend
from typing import Dict, List, Optional
import asyncio

try:
    import psmove
    PSMOVE_AVAILABLE = True
except ImportError:
    PSMOVE_AVAILABLE = False

class WindowsBackend(ControllerBackend):
    """Windows backend using psmoveapi"""

    def __init__(self):
        if not PSMOVE_AVAILABLE:
            raise RuntimeError("psmoveapi not available. Install with: pip install psmoveapi")

        self.controllers: Dict[str, psmove.PSMove] = {}
        self.running = False

    async def initialize(self) -> bool:
        """Scan and connect to all paired PS Move controllers"""
        count = psmove.count_connected()
        logger.info(f"Found {count} PS Move controllers")

        for i in range(count):
            move = psmove.PSMove(i)
            serial = move.get_serial()

            if move.connection_type == psmove.Conn_Bluetooth:
                self.controllers[serial] = move
                logger.info(f"Connected to controller: {serial}")

        self.running = True
        return len(self.controllers) > 0

    async def scan_controllers(self) -> List[Dict]:
        """Return already connected controllers (Windows manages pairing)"""
        return [
            {
                'address': serial,
                'serial': serial,
                'name': f'Motion Controller {serial[-4:]}'
            }
            for serial in self.controllers.keys()
        ]

    async def connect_controller(self, address: str) -> bool:
        """Controllers auto-connect on Windows, just verify"""
        return address in self.controllers

    async def disconnect_controller(self, serial: str) -> bool:
        """Cannot force disconnect on Windows"""
        return False

    async def get_controller_state(self, serial: str) -> Optional[Dict]:
        """Read current controller state"""
        move = self.controllers.get(serial)
        if not move:
            return None

        # Poll for new data
        while move.poll():
            pass

        # Read all inputs
        trigger = move.get_trigger()

        # Read buttons
        buttons = move.get_buttons()
        move_button = bool(buttons & psmove.Btn_MOVE)
        trigger_button = bool(buttons & psmove.Btn_T)

        # Read accelerometer (raw values)
        ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)

        # Read gyroscope (raw values)
        gx, gy, gz = move.get_gyroscope_frame(psmove.Frame_SecondHalf)

        # Battery level (0-5)
        battery = move.get_battery()

        return {
            'serial': serial,
            'battery': battery,
            'trigger': trigger,
            'move_button': move_button,
            'trigger_button': trigger_button,
            'accel': {'x': ax, 'y': ay, 'z': az},
            'gyro': {'x': gx, 'y': gy, 'z': gz},
            'temperature': move.get_temperature(),
        }

    async def set_led_color(self, serial: str, r: int, g: int, b: int) -> bool:
        """Set LED color"""
        move = self.controllers.get(serial)
        if not move:
            return False

        move.set_leds(r, g, b)
        move.update_leds()
        return True

    async def set_rumble(self, serial: str, intensity: int) -> bool:
        """Set rumble (0-255)"""
        move = self.controllers.get(serial)
        if not move:
            return False

        move.set_rumble(intensity)
        return True

    def get_connected_controllers(self) -> List[str]:
        """Return list of connected controller serials"""
        return list(self.controllers.keys())

    async def shutdown(self):
        """Cleanup"""
        # Turn off all LEDs
        for move in self.controllers.values():
            move.set_leds(0, 0, 0)
            move.update_leds()

        self.controllers.clear()
        self.running = False
```

### 4. Create Mock Backend
**File**: `services/controller_manager/mock_backend.py` (NEW)

```python
from controller_manager.backend import ControllerBackend
from typing import Dict, List, Optional
import random

class MockBackend(ControllerBackend):
    """Mock backend for testing without hardware"""

    def __init__(self, num_controllers: int = 4):
        self.num_controllers = num_controllers
        self.controllers = {}

    async def initialize(self) -> bool:
        # Create mock controllers
        for i in range(self.num_controllers):
            serial = f"MOCK{i:04d}"
            self.controllers[serial] = {
                'battery': 5,
                'trigger': 0,
                'move_button': False,
            }
        return True

    # ... implement all methods with mock data
```

### 5. Update Server with Platform Detection
**File**: `services/controller_manager/server.py`

```python
import platform
import os
from controller_manager.backend import ControllerBackend

def create_backend() -> ControllerBackend:
    """Create appropriate backend based on platform and environment"""

    # Check for mock mode (environment variable or command line flag)
    if os.getenv('MOCK_CONTROLLERS', '').lower() == 'true':
        from controller_manager.mock_backend import MockBackend
        logger.info("Using Mock backend (MOCK_CONTROLLERS=true)")
        num_controllers = int(os.getenv('MOCK_CONTROLLER_COUNT', '4'))
        return MockBackend(num_controllers)

    # Platform detection
    system = platform.system()

    if system == "Windows":
        try:
            from controller_manager.windows_backend import WindowsBackend
            logger.info("Using Windows backend (psmoveapi)")
            return WindowsBackend()
        except ImportError as e:
            logger.error(f"Windows backend not available: {e}")
            logger.info("Install psmoveapi: pip install psmoveapi")
            raise

    elif system == "Linux":
        from controller_manager.bluetooth_backend import BluetoothBackend
        logger.info("Using Linux BlueZ backend")
        return BluetoothBackend()

    else:
        raise RuntimeError(f"Unsupported platform: {system}")

# In main server initialization
async def main():
    backend = create_backend()
    await backend.initialize()

    # Start gRPC server with backend
    server = ControllerManagerServer(backend)
    await server.serve()
```

### 6. Update ControllerManagerServer to Use Backend
**File**: `services/controller_manager/server.py`

Refactor the gRPC service implementation to delegate to the backend:

```python
class ControllerManagerServer:
    def __init__(self, backend: ControllerBackend):
        self.backend = backend

    async def GetControllers(self, request, context):
        controllers = self.backend.get_connected_controllers()
        return controller_manager_pb2.GetControllersResponse(
            success=True,
            controllers=[
                controller_manager_pb2.Controller(serial=s)
                for s in controllers
            ]
        )

    async def GetControllerState(self, request, context):
        state = await self.backend.get_controller_state(request.serial)
        if state:
            return controller_manager_pb2.GetControllerStateResponse(
                success=True,
                state=self._state_to_proto(state)
            )
        # ... error handling
```

### 7. Windows Development Setup
**File**: `docs/development/windows-setup.md` (NEW)

```markdown
# Windows Development Setup

## Prerequisites
- Windows 10/11
- WSL2 with Ubuntu
- Python 3.11+ on both Windows and WSL

## Setup Steps

### 1. Install psmoveapi on Windows
```powershell
# Windows PowerShell
pip install psmoveapi
```

### 2. Pair PS Move Controllers
Use Windows Bluetooth settings or PS Move Pair Tool to pair controllers.

### 3. Install JoustMania Dependencies
```powershell
# Windows PowerShell
cd JoustMania/services/controller_manager
pip install -r requirements-windows.txt
```

### 4. Start Controller Manager on Windows
```powershell
# Windows PowerShell
cd JoustMania
python -m services.controller_manager.server --host 0.0.0.0 --port 50051
```

### 5. Configure WSL Services
```bash
# In WSL
cd JoustMania

# Create docker-compose.override.yml
cat > docker-compose.override.yml <<EOF
services:
  game_coordinator:
    environment:
      - CONTROLLER_MANAGER_HOST=host.docker.internal:50051

  menu:
    environment:
      - CONTROLLER_MANAGER_HOST=host.docker.internal:50051
EOF

# Start services in WSL
docker-compose up
```

### 6. Test
Controllers should now work with the game running in WSL!
```

### 8. Dependencies
**File**: `services/controller_manager/requirements-windows.txt` (NEW)

```txt
# Windows-specific dependencies
psmoveapi>=4.0.12
```

**File**: `services/controller_manager/requirements.txt` (UPDATE)

```txt
# Linux dependencies (existing)
dbus-python>=1.3.2

# Shared dependencies
grpcio>=1.70.0
grpcio-tools>=1.70.0
protobuf>=5.29.0
```

### 9. Update Dockerfile (Optional Mock Support)
**File**: `services/controller_manager/Dockerfile`

```dockerfile
# Add environment variable support for mock mode
ENV MOCK_CONTROLLERS=false
ENV MOCK_CONTROLLER_COUNT=4
```

## Testing Plan

### Local Testing (Windows)
```powershell
# 1. Pair PS Move controllers via Windows Bluetooth

# 2. Test controller detection
python -m services.controller_manager.server --test

# 3. Start server
python -m services.controller_manager.server

# 4. Test from another terminal
python test_controller_connection.py
```

### Integration Testing (WSL + Windows)
```bash
# 1. Start controller_manager on Windows (separate PowerShell)

# 2. In WSL, start services
docker-compose up

# 3. Navigate to webui
curl http://localhost:5000

# 4. Verify controllers appear in lobby
```

### Mock Testing (CI/Development without hardware)
```bash
# Set environment variable
export MOCK_CONTROLLERS=true
export MOCK_CONTROLLER_COUNT=4

# Start services - will use mock backend
docker-compose up
```

## Success Metrics
- [ ] Backend interface defined with all operations
- [ ] BlueZ backend refactored to implement interface
- [ ] Windows backend implemented with psmoveapi
- [ ] Mock backend available for testing
- [ ] Platform auto-detection works correctly
- [ ] Controller manager runs natively on Windows
- [ ] WSL services connect to Windows via gRPC
- [ ] All existing functionality works (LED, rumble, input)
- [ ] Documentation complete for Windows setup
- [ ] Can develop/debug with 3-4 real controllers in WSL

## Rollback Plan
If issues occur:
- Keep existing `bluetooth.py` alongside new backends
- Add feature flag: `USE_NEW_BACKEND=false`
- Windows backend is optional - only affects Windows development

## Benefits
- **Faster Development**: Test with real controllers without deploying to Pi
- **Better Debugging**: Full IDE debugging with real hardware
- **Platform Flexibility**: Same codebase works on Linux, Windows, and Mock
- **Clean Architecture**: Backend abstraction improves testability
- **Optional**: Windows backend doesn't affect production (Pi deployment)

## Future Enhancements
- macOS backend (psmoveapi also supports macOS)
- Virtual controller backend (keyboard/gamepad mapping)
- Recording/playback backend for regression testing
- Multiple backend support (mix real + mock)

## Related Phases
- Phase 40: Controller Manager Base Class (architectural foundation)
- Phase 41: Controller Data Stream Split (gRPC protocol)
- Phase 48: Connection Strength Monitoring (state tracking)
