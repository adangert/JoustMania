# Phase 67: moved2 Backend for Controller Manager

> **Status**: Future
>
> **Prerequisites**: Phase 66 (psmoveapi Rumble Contribution) complete
>
> **Blocks**: Phase 68 (Kubernetes Manifests)

## Overview

Implement a new controller backend that communicates with psmoveapi's `moved2` daemon over UDP. This enables running the controller-manager in Kubernetes without direct hardware access.

## Motivation

Current backends:
- `bluetooth` - Direct psmove library + BlueZ (requires hardware access)
- `mock` - Simulated controllers for testing
- `windows` - Windows Bluetooth stack

The `moved2` backend adds:
- **Network-based** controller access (UDP)
- **No hardware dependencies** in container
- **Edge/cloud separation** for Kubernetes

## Architecture

```
┌─────────────────────────────────┐
│ Controller Manager Container    │
│                                 │
│  ┌───────────────────────────┐ │
│  │ moved2_backend.py         │ │
│  │                           │ │
│  │ - UDP client              │ │
│  │ - Implements Backend ABC  │ │
│  │ - Polls daemon for state  │ │
│  └─────────────┬─────────────┘ │
│                │ UDP :17778    │
└────────────────┼───────────────┘
                 │
          ┌──────▼──────┐
          │   moved2    │  (on host or edge node)
          │   daemon    │
          └──────┬──────┘
                 │
          ┌──────▼──────┐
          │  Bluetooth  │
          │  Hardware   │
          └─────────────┘
```

## Implementation

### New Backend File

`services/controller_manager/moved2_backend.py`:

```python
"""
moved2 Backend for PS Move Controllers

Communicates with psmoveapi moved2 daemon over UDP for
cloud-native deployments where hardware access is on edge nodes.
"""

import asyncio
import logging
import socket
import struct
from typing import Optional

from services.controller_manager.backend import ControllerBackend

logger = logging.getLogger(__name__)

# Protocol constants (from psmove_moved_protocol.h)
MOVED_PORT = 17778
CMD_DISCOVER = 1
CMD_COUNT_CONNECTED = 2
CMD_SET_LEDS = 3
CMD_READ_INPUT = 4
CMD_GET_SERIAL = 5
CMD_SET_RUMBLE = 8  # Phase 66 addition

REQUEST_SIZE = 16
RESPONSE_SIZE = 64


class Moved2Backend(ControllerBackend):
    """
    Backend that communicates with moved2 daemon over UDP.

    Environment variables:
        MOVED2_HOST: Daemon hostname (default: localhost)
        MOVED2_PORT: Daemon port (default: 17778)
    """

    def __init__(self, host: str = "localhost", port: int = MOVED_PORT):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.sequence = 0
        self.controllers: dict[int, str] = {}  # id -> serial
        self.running = False

        logger.info(f"Moved2Backend targeting {host}:{port}")

    async def initialize(self) -> bool:
        """Connect to moved2 daemon."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(1.0)

            # Discover daemon
            count = await self._get_controller_count()
            logger.info(f"Connected to moved2 daemon, {count} controllers")

            # Get serials for all controllers
            for i in range(count):
                serial = await self._get_serial(i)
                if serial:
                    self.controllers[i] = serial
                    logger.info(f"Controller {i}: {serial}")

            self.running = True
            return True

        except Exception as e:
            logger.error(f"Failed to connect to moved2: {e}")
            return False

    def _send_request(self, command: int, controller_id: int = 0,
                      data: bytes = b"") -> bytes:
        """Send request and receive response."""
        self.sequence += 1

        # Build request packet (16 bytes)
        request = struct.pack("<IHH", self.sequence, command, controller_id)
        request += data.ljust(8, b"\x00")

        self.socket.sendto(request, (self.host, self.port))
        response, _ = self.socket.recvfrom(RESPONSE_SIZE)

        return response

    async def _get_controller_count(self) -> int:
        """Get number of connected controllers."""
        response = self._send_request(CMD_COUNT_CONNECTED)
        # Response format: sequence(4) + count(4) + ...
        _, count = struct.unpack("<II", response[:8])
        return count

    async def _get_serial(self, controller_id: int) -> Optional[str]:
        """Get serial/MAC for controller."""
        response = self._send_request(CMD_GET_SERIAL, controller_id)
        # Serial is 6 bytes starting at offset 8
        serial_bytes = response[8:14]
        return ":".join(f"{b:02X}" for b in serial_bytes)

    async def get_controller_state(self, serial: str) -> Optional[dict]:
        """Read controller state from daemon."""
        controller_id = self._get_id_for_serial(serial)
        if controller_id is None:
            return None

        try:
            response = self._send_request(CMD_READ_INPUT, controller_id)

            # Parse 49-byte input report from response
            # Format matches raw HID report from PS Move
            data = response[8:57]

            buttons = struct.unpack("<I", data[0:4])[0]
            trigger = data[4]

            # Accelerometer (3x int16)
            ax, ay, az = struct.unpack("<hhh", data[5:11])

            # Gyroscope (3x int16)
            gx, gy, gz = struct.unpack("<hhh", data[11:17])

            # Battery
            battery = data[17]

            return {
                "serial": serial,
                "battery": battery,
                "trigger": trigger,
                "move_button": bool(buttons & 0x00080000),
                "ps_button": bool(buttons & 0x00010000),
                "trigger_button": bool(buttons & 0x00100000),
                "accel": {"x": ax, "y": ay, "z": az},
                "gyro": {"x": gx, "y": gy, "z": gz},
                "connection_type": "moved2",
            }

        except Exception as e:
            logger.error(f"Error reading state for {serial}: {e}")
            return None

    async def set_led_color(self, serial: str, r: int, g: int, b: int) -> bool:
        """Set LED color via daemon."""
        controller_id = self._get_id_for_serial(serial)
        if controller_id is None:
            return False

        try:
            data = struct.pack("BBB", r, g, b)
            self._send_request(CMD_SET_LEDS, controller_id, data)
            return True
        except Exception as e:
            logger.error(f"Error setting LED for {serial}: {e}")
            return False

    async def set_rumble(self, serial: str, intensity: int) -> bool:
        """Set rumble via daemon (requires Phase 66)."""
        controller_id = self._get_id_for_serial(serial)
        if controller_id is None:
            return False

        try:
            data = struct.pack("B", intensity)
            self._send_request(CMD_SET_RUMBLE, controller_id, data)
            return True
        except Exception as e:
            logger.error(f"Error setting rumble for {serial}: {e}")
            return False

    def get_connected_controllers(self) -> list[str]:
        """Return list of controller serials."""
        return list(self.controllers.values())

    def _get_id_for_serial(self, serial: str) -> Optional[int]:
        """Map serial back to controller ID."""
        for cid, s in self.controllers.items():
            if s == serial:
                return cid
        return None

    async def scan_controllers(self) -> list[dict]:
        """Scan for controllers via daemon."""
        controllers = []
        count = await self._get_controller_count()

        for i in range(count):
            serial = await self._get_serial(i)
            if serial:
                controllers.append({
                    "address": serial,
                    "serial": serial,
                    "name": f"PS Move {serial[-5:]}",
                })

        return controllers

    async def connect_controller(self, address: str) -> bool:
        """Controllers are managed by daemon, just track locally."""
        # Refresh controller list
        count = await self._get_controller_count()
        for i in range(count):
            serial = await self._get_serial(i)
            if serial and serial not in self.controllers.values():
                self.controllers[i] = serial
        return address in self.controllers.values()

    async def disconnect_controller(self, serial: str) -> bool:
        """Remove from local tracking."""
        cid = self._get_id_for_serial(serial)
        if cid is not None:
            del self.controllers[cid]
            return True
        return False

    async def shutdown(self):
        """Cleanup."""
        logger.info("Shutting down moved2 backend")

        # Turn off all LEDs
        for serial in self.controllers.values():
            try:
                await self.set_led_color(serial, 0, 0, 0)
                await self.set_rumble(serial, 0)
            except Exception:
                pass

        if self.socket:
            self.socket.close()

        self.running = False
        logger.info("moved2 backend shutdown complete")
```

### Backend Selection Update

Update `services/controller_manager/main.py`:

```python
def get_backend(backend_type: str) -> ControllerBackend:
    if backend_type == "bluetooth":
        from services.controller_manager.bluetooth_backend import BluetoothBackend
        return BluetoothBackend()
    elif backend_type == "mock":
        from services.controller_manager.mock_backend import MockBackend
        return MockBackend()
    elif backend_type == "moved2":
        from services.controller_manager.moved2_backend import Moved2Backend
        host = os.environ.get("MOVED2_HOST", "localhost")
        port = int(os.environ.get("MOVED2_PORT", "17778"))
        return Moved2Backend(host=host, port=port)
    else:
        raise ValueError(f"Unknown backend: {backend_type}")
```

### Environment Variables

```yaml
# docker-compose or K8s
environment:
  - CONTROLLER_BACKEND=moved2
  - MOVED2_HOST=moved2-daemon.joustmania.svc
  - MOVED2_PORT=17778
```

## Tasks

- [ ] Create `moved2_backend.py` with UDP client
- [ ] Implement all ControllerBackend methods
- [ ] Add backend selection in main.py
- [ ] Parse moved2 protocol responses correctly
- [ ] Handle connection failures gracefully
- [ ] Add reconnection logic
- [ ] Write unit tests with mocked UDP
- [ ] Integration test with real moved2 daemon
- [ ] Document environment variables
- [ ] Update architecture docs

## Testing Strategy

1. **Unit tests**: Mock UDP socket, verify protocol encoding
2. **Integration tests**: Run moved2 daemon locally, test full flow
3. **Latency tests**: Measure round-trip time for operations
4. **Stress tests**: Rapid LED/rumble updates

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTROLLER_BACKEND` | `mock` | Set to `moved2` |
| `MOVED2_HOST` | `localhost` | Daemon hostname |
| `MOVED2_PORT` | `17778` | Daemon UDP port |
| `MOVED2_TIMEOUT` | `1.0` | Socket timeout (seconds) |

## Risks

| Risk | Mitigation |
|------|------------|
| UDP packet loss | Add retry logic, sequence tracking |
| Daemon unavailable | Health checks, reconnection |
| Latency spikes | Async polling, connection pooling |
| Protocol mismatch | Version check on connect |

## Next Phase

Phase 68: Kubernetes Manifests
