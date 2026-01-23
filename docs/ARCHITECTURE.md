# JoustMania Architecture

This document provides a comprehensive overview of the JoustMania microservices architecture.

## Overview

JoustMania is a party game system for PS Move controllers, built as a collection of microservices communicating via gRPC. The architecture supports:

- Real-time controller input processing (1000Hz hardware polling)
- Multiple game modes with different rules
- Web-based administration
- Distributed tracing and observability

## Service Diagram

```
                              ┌──────────────┐
                              │   Web UI     │ :80
                              │   (Flask)    │
                              └──────┬───────┘
                                     │ HTTP + gRPC
       ┌─────────────────────────────┼─────────────────────────────┐
       │                             │                             │
       ▼                             ▼                             ▼
┌──────────────┐          ┌──────────────────┐          ┌──────────────┐
│   Settings   │◄─────────│    Supervisor    │─────────►│    Menu      │
│   :50051     │          │    :50055        │          │   :50054     │
└──────────────┘          └────────┬─────────┘          └──────┬───────┘
       ▲                           │                           │
       │                           │ orchestrates              │
       │                           ▼                           │
       │                  ┌──────────────────┐                 │
       └──────────────────│ Game Coordinator │◄────────────────┘
                          │     :50053       │
                          └────────┬─────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
     ┌──────────────┐    ┌──────────────────┐   ┌──────────────┐
     │    Audio     │    │ Controller Mgr   │   │  Bluetooth   │
     │   :50056     │    │     :50052       │   │  Hardware    │
     └──────────────┘    └────────┬─────────┘   └──────────────┘
                                  │
                           USB/Bluetooth
                                  │
                         ┌────────┴────────┐
                         │  PS Move        │
                         │  Controllers    │
                         └─────────────────┘
```

## Services

### Settings Service (Port 50051)

**Purpose**: Centralized configuration management

**Responsibilities**:
- Load/save settings from YAML file
- Schema-based validation
- Publish setting changes via streaming
- Single source of truth for configuration

**Key RPCs**:
| RPC | Type | Description |
|-----|------|-------------|
| `GetSettings` | Unary | Get all settings |
| `GetSetting` | Unary | Get single setting by key |
| `UpdateSetting` | Unary | Update a setting value |
| `SubscribeToChanges` | Server Stream | Real-time setting change notifications |

**Dependencies**: None (foundational service)

---

### Controller Manager Service (Port 50052)

**Purpose**: PS Move controller hardware management

**Responsibilities**:
- Hardware discovery (USB/Bluetooth)
- Controller pairing via BlueZ
- Real-time state streaming (1000Hz polling → 60Hz stream)
- LED control and visual effects
- Vibration feedback
- Button event detection

**Key RPCs**:
| RPC | Type | Description |
|-----|------|-------------|
| `StreamButtonEvents` | Bidirectional | Button events + LED control commands |
| `StreamGameplayData` | Bidirectional | Filtered motion data + feedback commands |
| `PlayControllerEffect` | Unary | Trigger visual effect (flash, pulse, rainbow) |

**Backends**:
- `bluetooth` - Linux BlueZ (production)
- `windows` - psmoveapi (Windows)
- `mock` - Simulated controllers (testing)

**Special Features**:
- Adaptive polling: 60Hz active, 10Hz idle
- LED batch updates at 20Hz
- Effect priority system (cancellable vs non-cancellable)

**Dependencies**: Settings

---

### Game Coordinator Service (Port 50053)

**Purpose**: Game lifecycle and rules management

**Responsibilities**:
- Start/stop games
- Game state machine (IDLE → STARTING → RUNNING → ENDING → ENDED)
- Death detection based on movement thresholds
- Game event streaming
- Support for 13 game modes

**Game Modes**:
- JoustFFA, JoustTeams, JoustRandomTeams
- Werewolf, Traitor, Zombies
- Commander, Swapper
- Tournament, FightClub
- NonStop, Ninja
- Random

**Key RPCs**:
| RPC | Type | Description |
|-----|------|-------------|
| `StartGame` | Unary | Start a game with specified mode |
| `ForceEndGame` | Unary | Force end current game |
| `StreamGameEvents` | Server Stream | Game lifecycle events |

**Dependencies**: Settings, ControllerManager, Audio

---

### Menu Service (Port 50054)

**Purpose**: Menu UI and game selection

**Responsibilities**:
- Menu state management
- Process controller button inputs
- Game mode selection cycling
- Team assignment
- Admin mode controls
- LED feedback based on state
- Auto-start when all players ready

**Key RPCs**:
| RPC | Type | Description |
|-----|------|-------------|
| `StartMenu` | Unary | Start menu mode |
| `StopMenu` | Unary | Stop menu mode |
| `ProcessInput` | Unary | Process button input |
| `StreamMenuEvents` | Server Stream | Menu state change events |

**Admin Mode**: Press all 4 face buttons simultaneously
- White LED indicator
- 60 second timeout
- Configure teams, sensitivity, force_all_start

**Dependencies**: Settings, ControllerManager, GameCoordinator

---

### Supervisor Service (Port 50055)

**Purpose**: Service orchestration and health monitoring

**Type**: Pure gRPC client (orchestrator)

**Responsibilities**:
- Subscribe to Menu events
- Orchestrate game starts via GameCoordinator
- Propagate distributed tracing context
- Expose gRPC Health service for probes

**Dependencies**: All services

---

### Audio Service (Port 50056)

**Purpose**: Audio playback and mixing

**Responsibilities**:
- Play sound effects with priorities
- Play background music with tempo control
- Audio device management

**Priority Levels**:
| Priority | Value | Use Case |
|----------|-------|----------|
| LOW | 0 | Background effects |
| MEDIUM | 1 | Normal game sounds |
| HIGH | 2 | Important events |
| CRITICAL | 3 | System announcements |

**Key RPCs**:
| RPC | Type | Description |
|-----|------|-------------|
| `PlaySound` | Unary | Play sound effect |
| `PlayMusic` | Unary | Start background music |
| `StopMusic` | Unary | Stop music |
| `ChangeTempo` | Unary | Adjust music speed |
| `SetVolume` | Unary | Set volume level |

**Dependencies**: None (foundational)

---

### Web UI Service (Port 80)

**Purpose**: HTTP web interface

**Framework**: Flask

**Routes**:
| Route | Description |
|-------|-------------|
| `/` | Main dashboard |
| `/battery` | Controller battery status |
| `/settings` | Settings management |
| `/admin` | Administration panel |
| `/start_game/<mode>` | Start specific game |
| `/kill_game` | Force end game |

**Dependencies**: All services (gRPC client)

---

## Communication Patterns

### Protocol: gRPC with Protocol Buffers

JoustMania uses gRPC for all inter-service communication:
- Binary protocol (3-10x faster than REST/JSON)
- Strong typing with Protocol Buffers v3
- HTTP/2 multiplexing
- Bidirectional streaming support

### Service Discovery

Services discover each other via Docker Compose DNS:
```
settings:50051
controller-manager:50052
game-coordinator:50053
menu:50054
supervisor:50055
audio:50056
```

### Streaming Patterns

**Server Streaming** (Service → Client):
- `SubscribeToChanges` - Setting notifications
- `StreamGameplayData` - Controller motion
- `StreamGameEvents` - Game lifecycle
- `StreamMenuEvents` - Menu state

**Bidirectional Streaming** (Both directions):
- `StreamButtonEvents` - Buttons ↔ LED commands
- `StreamGameplayData` - Motion ↔ Feedback

---

## Data Flows

### Controller Connection

```
1. PS Move hardware (1000Hz) → Controller Manager
2. Controller Manager updates internal state
3. Menu/Game subscribes via StreamButtonEvents
4. Controller Manager sends button events
5. Menu/Game sends LED commands back
6. Controller Manager applies LED to hardware
```

### Game Start

```
1. Menu detects all controllers ready (≥2 players)
2. Menu publishes "game_requested" event
3. Supervisor receives via StreamMenuEvents
4. Supervisor calls GameCoordinator.StartGame
5. GameCoordinator initializes game instance
6. Game streams events back via StreamGameEvents
7. Game runs until win condition
8. Menu receives "game_ended", resets to lobby
```

### Settings Update

```
1. Web UI calls Settings.UpdateSetting
2. Settings validates against schema
3. Settings saves to YAML file
4. Settings publishes SettingChangeEvent
5. Subscribed services receive notification
6. Services update cached settings
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CONTROLLER_BACKEND` | Controller backend type | `bluetooth` |
| `MOCK_CONTROLLER_COUNT` | Simulated controllers | `4` |
| `AUDIO_MOCK_MODE` | Silent audio mode | `false` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

### Docker Compose Variants

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Full stack with observability |
| `docker-compose.lite.yml` | Minimal stack |
| `docker-compose.hardware.yml` | Hardware overrides |
| `docker-compose.ci.yml` | CI/CD testing |

### Persistence

- `joustsettings.yaml` - Settings storage (Docker volume)
- `~/.psmoveapi/` - Controller calibration (Linux)

---

## Observability

### Stack

| Component | Purpose | Port |
|-----------|---------|------|
| Jaeger | Distributed tracing | 16686 |
| Prometheus | Metrics collection | 9090 |
| Grafana | Visualization | 3000 |
| Loki | Log aggregation | 3100 |

### Tracing

- OpenTelemetry SDK with Jaeger exporter
- Automatic gRPC instrumentation
- W3C Trace Context propagation
- Manual spans for critical operations

### Metrics

Each service exposes Prometheus metrics at `/metrics`:
- Request counts and latencies
- Active stream counts
- Controller counts
- Game statistics

---

## Build & Deployment

### Build Commands

```bash
make builders   # Build base images (~15min on Pi)
make images     # Build all service images
make up         # Start full stack
make up-mock    # Start with mock controllers
make test       # Run integration tests
make lint       # Run linting
```

### Container Privileges

| Service | Privileged | Reason |
|---------|------------|--------|
| Controller Manager | Yes | Bluetooth/USB access |
| Audio | Yes | Audio device access |
| Others | No | Standard containers |

---

## Shared Libraries

Located in `/lib/`:

| Module | Purpose |
|--------|---------|
| `grpc_tracing.py` | OpenTelemetry gRPC interceptor |
| `types.py` | Shared type definitions |
| `colors.py` | Color constants |
| `controller_constants.py` | Controller constants |
| `telemetry.py` | Telemetry helpers |

---

## Proto Files

Located in `/proto/`:

| File | Service |
|------|---------|
| `settings.proto` | SettingsService |
| `controller_manager.proto` | ControllerManagerService |
| `game_coordinator.proto` | GameCoordinatorService |
| `menu.proto` | MenuService |
| `audio.proto` | AudioService |

Regenerate after changes:
```bash
make protos
```
