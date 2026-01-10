# Phase 14: Mock Hardware Testing Environment

## Overview

Create a complete mock hardware environment for testing and development without physical PS Move controllers or Bluetooth adapters. This allows:
- Testing on any machine (no Bluetooth required)
- Automated integration testing
- Trace generation for demos
- Controlled game simulations via gRPC

## Goals

1. **Mock ControllerManager** - Simulates PS Move controllers via gRPC
2. **Mock Audio Service** - Simulates audio playback (already exists, needs integration)
3. **Controller Simulation API** - Control mock controllers via gRPC calls
4. **Docker Compose Configuration** - Environment variables for controller count
5. **Game Simulation Scripts** - Automated game scenarios for testing

## Architecture

### Current (Real Hardware)

```
ControllerManager (server.py)
├── Hardware Detection (Bluetooth/USB)
├── PSMove Library (libpsmoveapi)
├── Controller State Reading (60Hz)
└── gRPC Server (StreamControllerStates)
```

### New (Mock Hardware)

```
MockControllerManager (mock_server.py)
├── Mock Controller Pool (configurable count)
├── Simulated State Generation
├── gRPC Control API (SimulateMovement, SimulateDeath)
└── gRPC Server (StreamControllerStates - same interface)
```

## Implementation Plan

### Task 1: MockControllerManager Service

**File:** `services/controller_manager/mock_server.py`

**Features:**
- Configurable number of controllers via env var: `MOCK_CONTROLLER_COUNT=4`
- Same gRPC interface as real ControllerManager
- Additional control RPCs:
  - `SimulateMovement(serial, accel_x, accel_y, accel_z)` - Set acceleration
  - `SimulateDeath(serial)` - Trigger death-level acceleration
  - `SimulateTriggerPress(serial)` - Press trigger button
  - `SetControllerColor(serial, r, g, b)` - Set LED color
  - `ResetController(serial)` - Reset to idle state

**Mock Controller State:**
```python
@dataclass
class MockController:
    serial: str
    battery: int = 100
    trigger_pressed: bool = False
    move_pressed: bool = False
    ready: bool = True
    team: int = 0
    color: RGB = (255, 255, 255)
    accel: Vector3 = (0.0, 0.0, 1.0)  # Controllable via gRPC
    gyro: Vector3 = (0.0, 0.0, 0.0)
```

### Task 2: Control Protobuf Extensions

**File:** `services/controller_manager/controller_manager_mock.proto`

```protobuf
syntax = "proto3";

package controller_manager_mock;

// Additional RPCs for mock controller control
service MockControllerService {
    // Simulate controller movement
    rpc SimulateMovement(MovementRequest) returns (MovementResponse);

    // Simulate death (high acceleration)
    rpc SimulateDeath(DeathRequest) returns (DeathResponse);

    // Simulate button press
    rpc SimulateButton(ButtonRequest) returns (ButtonResponse);

    // Set LED color
    rpc SetColor(ColorRequest) returns (ColorResponse);

    // Reset controller to idle
    rpc ResetController(ResetRequest) returns (ResetResponse);

    // Get list of mock controllers
    rpc ListMockControllers(ListRequest) returns (ListResponse);
}

message MovementRequest {
    string serial = 1;
    float accel_x = 2;
    float accel_y = 3;
    float accel_z = 4;
}

message MovementResponse {
    bool success = 1;
    string error = 2;
}

message DeathRequest {
    string serial = 1;
}

message DeathResponse {
    bool success = 1;
    float accel_magnitude = 2;  // Actual simulated magnitude
}

message ButtonRequest {
    string serial = 1;
    enum Button {
        TRIGGER = 0;
        MOVE = 1;
        SELECT = 2;
        START = 3;
    }
    Button button = 2;
    bool pressed = 3;
}

message ButtonResponse {
    bool success = 1;
    string error = 2;
}

message ColorRequest {
    string serial = 1;
    int32 r = 2;
    int32 g = 3;
    int32 b = 4;
}

message ColorResponse {
    bool success = 1;
    string error = 2;
}

message ResetRequest {
    string serial = 1;
}

message ResetResponse {
    bool success = 1;
    string error = 2;
}

message ListRequest {}

message ListResponse {
    repeated string serials = 1;
    int32 count = 2;
}
```

### Task 3: Docker Compose Configuration

**File:** `docker-compose.mock.yml`

```yaml
version: '3.8'

services:
  # Mock ControllerManager (replaces real one)
  mock-controller-manager:
    build:
      context: .
      dockerfile: services/controller_manager/Dockerfile.mock
    environment:
      - OTEL_SERVICE_NAME=controller-manager-service
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
      - MOCK_CONTROLLER_COUNT=4  # Configurable!
      - MOCK_MODE=true
    ports:
      - "50052:50052"  # Main gRPC port
      - "50062:50062"  # Mock control port
    networks:
      - joustmania
    depends_on:
      - otel-collector
    healthcheck:
      test: ["CMD", "grpc_health_probe", "-addr=:50052"]
      interval: 10s
      timeout: 5s
      retries: 3

  # Mock Audio Service (already exists, just configure)
  audio:
    build:
      context: .
      dockerfile: services/audio/Dockerfile
    environment:
      - OTEL_SERVICE_NAME=audio-service
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
      - MOCK_MODE=true  # No actual audio output
    ports:
      - "50056:50056"
    networks:
      - joustmania
    depends_on:
      - otel-collector

  # Rest of services (Settings, GameCoordinator, etc.)
  settings:
    # ... same as production docker-compose.yml

  game-coordinator:
    # ... same as production docker-compose.yml

  menu:
    # ... same as production docker-compose.yml

  webui:
    # ... same as production docker-compose.yml

  # Observability stack
  otel-collector:
    # ... same as production

  jaeger:
    # ... same as production

  redis:
    # ... same as production

networks:
  joustmania:
    driver: bridge
```

### Task 4: Mock Server Implementation

**File:** `services/controller_manager/mock_server.py`

```python
"""
Mock ControllerManager gRPC Server for testing without hardware.

Provides:
- Same gRPC interface as real ControllerManager
- Additional control RPCs for simulation
- Configurable number of controllers
- Controllable controller states via gRPC
"""

import asyncio
import logging
import os
import time
from concurrent import futures
from typing import Dict, List

import grpc
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer

from controller_manager_pb2 import (
    ControllerState, RGB, Vector3,
    GetReadyControllersResponse, ControllerStateUpdate
)
from controller_manager_mock_pb2 import (
    MovementResponse, DeathResponse, ButtonResponse,
    ColorResponse, ResetResponse, ListResponse
)
import controller_manager_pb2_grpc
import controller_manager_mock_pb2_grpc

logger = logging.getLogger(__name__)


class MockController:
    """Represents a mock PS Move controller."""

    def __init__(self, serial: str):
        self.serial = serial
        self.battery = 100
        self.trigger_pressed = False
        self.move_pressed = False
        self.ready = True
        self.team = 0
        self.color = RGB(r=255, g=255, b=255)
        self.accel = Vector3(x=0.0, y=0.0, z=1.0)  # Default idle
        self.gyro = Vector3(x=0.0, y=0.0, z=0.0)

    def to_proto(self) -> ControllerState:
        """Convert to protobuf ControllerState."""
        return ControllerState(
            serial=self.serial,
            move_num=int(self.serial.split('_')[-1]),
            battery=self.battery,
            trigger_pressed=self.trigger_pressed,
            move_pressed=self.move_pressed,
            ready=self.ready,
            team=self.team,
            color=self.color,
            accel=self.accel,
            gyro=self.gyro
        )


class MockControllerManagerService(controller_manager_pb2_grpc.ControllerManagerServiceServicer):
    """Mock ControllerManager implementing same interface as real one."""

    def __init__(self, num_controllers: int):
        self.controllers: Dict[str, MockController] = {}

        # Initialize mock controllers
        for i in range(num_controllers):
            serial = f"mock_controller_{i}"
            self.controllers[serial] = MockController(serial)

        logger.info(f"Initialized {num_controllers} mock controllers")

    def GetReadyControllers(self, request, context):
        """Return all mock controllers as ready."""
        controllers = [c.to_proto() for c in self.controllers.values()]
        return GetReadyControllersResponse(
            controllers=controllers,
            success=True,
            error=""
        )

    async def StreamControllerStates(self, request, context):
        """Stream controller states at requested frequency."""
        frequency = request.update_frequency_hz or 60
        interval = 1.0 / frequency

        logger.info(f"Starting controller state stream at {frequency}Hz")

        while context.is_active():
            # Get current states
            controllers = [c.to_proto() for c in self.controllers.values()]

            yield ControllerStateUpdate(
                controllers=controllers,
                timestamp=int(time.time() * 1000)
            )

            await asyncio.sleep(interval)


class MockControllerControlService(controller_manager_mock_pb2_grpc.MockControllerServiceServicer):
    """Additional RPCs for controlling mock controllers."""

    def __init__(self, controller_manager: MockControllerManagerService):
        self.manager = controller_manager

    def SimulateMovement(self, request, context):
        """Simulate controller movement by setting acceleration."""
        controller = self.manager.controllers.get(request.serial)

        if not controller:
            return MovementResponse(
                success=False,
                error=f"Controller {request.serial} not found"
            )

        controller.accel = Vector3(
            x=request.accel_x,
            y=request.accel_y,
            z=request.accel_z
        )

        logger.info(f"Simulated movement for {request.serial}: ({request.accel_x}, {request.accel_y}, {request.accel_z})")

        return MovementResponse(success=True, error="")

    def SimulateDeath(self, request, context):
        """Simulate death by setting high acceleration."""
        controller = self.manager.controllers.get(request.serial)

        if not controller:
            return DeathResponse(
                success=False,
                accel_magnitude=0.0
            )

        # Set death-level acceleration (>2.8 for FAST sensitivity)
        controller.accel = Vector3(x=5.0, y=3.0, z=4.0)
        accel_mag = (5.0**2 + 3.0**2 + 4.0**2) ** 0.5

        logger.info(f"Simulated death for {request.serial}: magnitude={accel_mag:.2f}")

        return DeathResponse(success=True, accel_magnitude=accel_mag)

    def SimulateButton(self, request, context):
        """Simulate button press."""
        controller = self.manager.controllers.get(request.serial)

        if not controller:
            return ButtonResponse(
                success=False,
                error=f"Controller {request.serial} not found"
            )

        if request.button == 0:  # TRIGGER
            controller.trigger_pressed = request.pressed
        elif request.button == 1:  # MOVE
            controller.move_pressed = request.pressed

        logger.info(f"Simulated button {request.button} {'press' if request.pressed else 'release'} for {request.serial}")

        return ButtonResponse(success=True, error="")

    def SetColor(self, request, context):
        """Set controller LED color."""
        controller = self.manager.controllers.get(request.serial)

        if not controller:
            return ColorResponse(
                success=False,
                error=f"Controller {request.serial} not found"
            )

        controller.color = RGB(r=request.r, g=request.g, b=request.b)

        logger.info(f"Set color for {request.serial}: ({request.r}, {request.g}, {request.b})")

        return ColorResponse(success=True, error="")

    def ResetController(self, request, context):
        """Reset controller to idle state."""
        controller = self.manager.controllers.get(request.serial)

        if not controller:
            return ResetResponse(
                success=False,
                error=f"Controller {request.serial} not found"
            )

        # Reset to idle
        controller.accel = Vector3(x=0.0, y=0.0, z=1.0)
        controller.gyro = Vector3(x=0.0, y=0.0, z=0.0)
        controller.trigger_pressed = False
        controller.move_pressed = False

        logger.info(f"Reset {request.serial} to idle state")

        return ResetResponse(success=True, error="")

    def ListMockControllers(self, request, context):
        """List all mock controllers."""
        serials = list(self.manager.controllers.keys())

        return ListResponse(
            serials=serials,
            count=len(serials)
        )


def init_telemetry():
    """Initialize OpenTelemetry."""
    resource = Resource(attributes={
        SERVICE_NAME: "controller-manager-service",
        "service.namespace": "joustmania",
        "mock.enabled": "true"
    })

    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(
        endpoint=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4317'),
        insecure=True
    )
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    GrpcInstrumentorServer().instrument()

    logger.info("OpenTelemetry initialized for mock controller manager")


def serve():
    """Start mock gRPC servers."""
    init_telemetry()

    # Get configuration
    num_controllers = int(os.getenv('MOCK_CONTROLLER_COUNT', '4'))
    main_port = int(os.getenv('GRPC_PORT', '50052'))
    control_port = int(os.getenv('MOCK_CONTROL_PORT', '50062'))

    # Create services
    controller_manager = MockControllerManagerService(num_controllers)
    control_service = MockControllerControlService(controller_manager)

    # Main server (standard ControllerManager interface)
    main_server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    controller_manager_pb2_grpc.add_ControllerManagerServiceServicer_to_server(
        controller_manager, main_server
    )
    main_server.add_insecure_port(f'[::]:{main_port}')

    # Control server (mock control interface)
    control_server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    controller_manager_mock_pb2_grpc.add_MockControllerServiceServicer_to_server(
        control_service, control_server
    )
    control_server.add_insecure_port(f'[::]:{control_port}')

    logger.info(f"Starting Mock ControllerManager:")
    logger.info(f"  - Main gRPC server on port {main_port}")
    logger.info(f"  - Control gRPC server on port {control_port}")
    logger.info(f"  - Mock controllers: {num_controllers}")

    return main_server, control_server


async def main():
    """Main entry point."""
    logging.basicConfig(level=logging.INFO)

    main_server, control_server = serve()

    await main_server.start()
    await control_server.start()

    logger.info("Mock ControllerManager servers started")

    await main_server.wait_for_termination()


if __name__ == '__main__':
    asyncio.run(main())
```

### Task 5: Game Simulation Scripts

**File:** `scripts/testing/simulate_game.py`

```python
"""
Simulate a full game using mock controllers.

Usage:
    python simulate_game.py --mode FFA --controllers 4 --duration 30
"""

import asyncio
import argparse
import grpc
import random
import time

# Import protobufs
from services.controller_manager import controller_manager_mock_pb2, controller_manager_mock_pb2_grpc
from services.game_coordinator import game_coordinator_pb2, game_coordinator_pb2_grpc


async def simulate_ffa_game(num_controllers: int, duration: int):
    """Simulate an FFA game with random deaths."""

    # Connect to services
    mock_channel = grpc.aio.insecure_channel('localhost:50062')
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(mock_channel)

    game_channel = grpc.aio.insecure_channel('localhost:50053')
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    print(f"🎮 Starting FFA game simulation with {num_controllers} controllers")

    # Start game
    game_response = await game_client.StartGame(
        game_coordinator_pb2.StartGameRequest(mode="FFA")
    )

    if not game_response.success:
        print(f"❌ Failed to start game: {game_response.error}")
        return

    print(f"✅ Game started: {game_response.game_id}")

    # Simulate game duration
    start_time = time.time()
    alive_controllers = list(range(num_controllers))

    while time.time() - start_time < duration and len(alive_controllers) > 1:
        # Random controller has movement
        if random.random() < 0.1:  # 10% chance per tick
            controller_idx = random.choice(alive_controllers)
            serial = f"mock_controller_{controller_idx}"

            # Small movement (warning)
            await mock_client.SimulateMovement(
                controller_manager_mock_pb2.MovementRequest(
                    serial=serial,
                    accel_x=random.uniform(1.0, 1.8),
                    accel_y=random.uniform(0.5, 1.0),
                    accel_z=random.uniform(0.8, 1.2)
                )
            )
            print(f"⚠️  Controller {controller_idx} moved (warning)")

        # Random death
        if random.random() < 0.05 and len(alive_controllers) > 1:  # 5% chance
            controller_idx = random.choice(alive_controllers)
            serial = f"mock_controller_{controller_idx}"

            response = await mock_client.SimulateDeath(
                controller_manager_mock_pb2.DeathRequest(serial=serial)
            )

            if response.success:
                alive_controllers.remove(controller_idx)
                print(f"💀 Controller {controller_idx} died! (accel: {response.accel_magnitude:.2f})")
                print(f"   {len(alive_controllers)} controllers remaining")

        await asyncio.sleep(0.1)

    # End game
    print(f"🏁 Game ending. Winner: Controller {alive_controllers[0] if alive_controllers else 'None'}")

    await game_client.ForceEndGame(
        game_coordinator_pb2.ForceEndGameRequest()
    )

    print(f"✅ Game simulation complete")


async def main():
    parser = argparse.ArgumentParser(description='Simulate a game with mock controllers')
    parser.add_argument('--mode', default='FFA', help='Game mode (FFA, Teams, etc.)')
    parser.add_argument('--controllers', type=int, default=4, help='Number of controllers')
    parser.add_argument('--duration', type=int, default=30, help='Game duration in seconds')

    args = parser.parse_args()

    await simulate_ffa_game(args.controllers, args.duration)


if __name__ == '__main__':
    asyncio.run(main())
```

## Testing Workflow

### 1. Start Mock Environment

```bash
# Start services with mock hardware
docker-compose -f docker-compose.mock.yml up
```

### 2. Run Game Simulation

```bash
# Simulate an FFA game
python scripts/testing/simulate_game.py --mode FFA --controllers 4 --duration 30
```

### 3. View Traces in Jaeger

```bash
# Open Jaeger UI
open http://localhost:16686

# Search for game traces
service="game-coordinator-service" AND game.mode="FFA"
```

### 4. Manual Controller Control

```bash
# List controllers
grpcurl -plaintext localhost:50062 controller_manager_mock.MockControllerService/ListMockControllers

# Simulate movement
grpcurl -plaintext -d '{"serial":"mock_controller_0","accel_x":2.0,"accel_y":1.5,"accel_z":1.2}' \
  localhost:50062 controller_manager_mock.MockControllerService/SimulateMovement

# Simulate death
grpcurl -plaintext -d '{"serial":"mock_controller_1"}' \
  localhost:50062 controller_manager_mock.MockControllerService/SimulateDeath

# Reset controller
grpcurl -plaintext -d '{"serial":"mock_controller_0"}' \
  localhost:50062 controller_manager_mock.MockControllerService/ResetController
```

## Benefits

1. **Testing Without Hardware** - Develop/test on any machine
2. **Automated Integration Tests** - Simulate full games in CI/CD
3. **Trace Generation** - Create perfect traces for demos
4. **Performance Testing** - Test with 100+ mock controllers
5. **Reproducible Scenarios** - Script specific game outcomes
6. **Error Injection** - Test error handling (controller disconnect, etc.)

## Implementation Checklist

- [ ] Create `controller_manager_mock.proto`
- [ ] Generate protobuf code
- [ ] Implement `mock_server.py`
- [ ] Create `Dockerfile.mock`
- [ ] Create `docker-compose.mock.yml`
- [ ] Write game simulation scripts
- [ ] Add integration tests using mock
- [ ] Document mock environment usage
- [ ] Update README with mock setup instructions

## Timeline

**Estimated Effort:** 2-3 days
- Day 1: Protobuf + Mock server implementation
- Day 2: Docker Compose + Scripts
- Day 3: Testing + Documentation

## Related Phases

- Phase 8: gRPC + Docker (provides base infrastructure)
- Phase 13: Game Modes (consumers of mock controllers)
- Phase 11: Documentation (needs mock environment docs)
