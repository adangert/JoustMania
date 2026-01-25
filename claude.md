# Claude Session Continuity Guide

**Last Updated:** 2026-01-19
**Project:** JoustMania - Multi-player gaming system using PS Move controllers

---

## Quick Start for New Sessions

**Current State:** Production-ready microservices with full observability stack
**Completed Work:** 71 phases completed (see GitHub issues #12-#20 for milestones)
**Latest Work:** Observability improvements, Menu refactoring, Audio span naming
**Branch:** `dev-refactor`

### What to do first:
1. Read this file completely
2. Review recent commits: `git log --oneline -10`
3. Check current working directory: `git status`
4. Check GitHub issues: `gh issue list`
5. Verify Docker services: `make up` or `docker-compose ps`

---

## Project Overview

### What is JoustMania?

JoustMania is a local multiplayer party game system that runs on Raspberry Pi and uses PlayStation Move controllers. Players compete in various mini-games (jousting, zombies, etc.) with motion controls and LED feedback.

### Architecture Status

**✅ COMPLETE:** Production-ready microservices architecture with full observability:
- **gRPC communication** between all services (async, streaming)
- **Docker containerization** with docker-compose and Makefile
- **Full observability stack:**
  - OpenTelemetry → Jaeger (distributed tracing)
  - Prometheus (metrics collection)
  - Grafana (dashboards: game analytics, controller health, host metrics)
  - Loki (log aggregation)
- **Backend abstraction** for controllers (Bluetooth/USB/Mock)
- **Event streaming** via gRPC (no polling for game state)
- Health checks (gRPC Health protocol)
- Type safety with ruff linting

---

## Architecture Evolution

### Before (Monolithic - DEPRECATED)
```
piparty.py (3000+ lines)
  ├─ Settings management
  ├─ Controller polling
  ├─ Game coordination
  ├─ Menu UI
  └─ Web UI
```

### Current (Microservices + gRPC + Docker) ✅
```
docker-compose.yml
  ├─ redis (pub/sub for events, port 6379 internal)
  ├─ settings (gRPC server, port 50051)
  ├─ controller-manager (gRPC server, port 50052, privileged for USB/BT)
  ├─ game-coordinator (gRPC server, port 50053)
  ├─ menu (gRPC server, port 50054)
  ├─ supervisor (gRPC server, port 50055)
  ├─ audio (gRPC server, port 50056, privileged for /dev/snd)
  ├─ webui (HTTP server, port 80)
  │
  │  Observability Stack:
  ├─ otel-collector (OpenTelemetry, port 4317 gRPC, 8889 metrics)
  ├─ jaeger (distributed tracing UI, port 16686)
  ├─ prometheus (metrics collection, port 9090)
  ├─ grafana (dashboards, port 3000)
  └─ loki (log aggregation, port 3100)
```

**Network:** All services run on `joustmania` bridge network
**Health:** All services implement gRPC Health protocol
**Tracing:** All gRPC calls instrumented with OpenTelemetry spans
**Metrics:** Prometheus scrapes all services on port 8000
**Dashboards:** Grafana at http://localhost:3000 (game-analytics, controller-overview, bluetooth-adapter, host-metrics)

---

## Major Completed Work

**71 phases completed** - See GitHub milestone issues #12-#20 for details.

### Foundation (Phases 1-17)
- Microservices extraction (Settings, ControllerManager, GameCoordinator, Menu, Supervisor, Audio)
- gRPC communication with async servers
- Docker containerization with docker-compose
- OpenTelemetry integration with Jaeger tracing
- Health checks on all services

### Observability (Phases 36-46, 70-79)
- **Prometheus metrics** on all services (port 8000)
- **Grafana dashboards:** game-analytics, controller-overview, bluetooth-adapter, host-metrics, system-overview
- **Loki** for log aggregation
- **Dynamic filtering** for gameplay data streams (Phase 45-46)
- **Span naming improvements** - descriptive spans like `PlaySound:congratulations`
- **Event streaming** - replaced polling with `StreamGameEvents`

### Controller Manager (Phases 57, 62, 71-73, 77)
- **Backend abstraction** - Bluetooth, USB, and Mock backends via factory pattern
- **Parallel controller polling** - improved throughput
- **Immediate LED updates** - no batching delay
- **Controller reconnection** - LED color restoration on reconnect
- **Docker hotplug** - USB controller detection in containers

### Menu Service (Phases 58-60, 79)
- **SOLID refactoring** - StateManager, handlers, event loop extraction
- **Battery display** in lobby
- **Audio feedback** for navigation
- **Admin mode** - game selection via Select+Start buttons

### Game Coordinator (Phases 61, 70)
- **Normalized game flow** - consistent color_assignment phase across all modes
- **Dynamic music system** - tempo changes based on game state
- **Sensitivity metrics** - thresholds visible in Grafana

### Infrastructure (Phases 73-76, 78)
- **GHCR builder images** - faster CI builds
- **Host metrics dashboard** - Raspberry Pi monitoring (CPU, memory, temperature)
- **Pairing daemon observability** - Python rewrite with tracing
- **Centralized enums** - `lib/types.py` for Games, Sensitivity, GameEvent

---

## Current Architecture Details

### Application Services

**Settings Service (port 50051, metrics 8000)**
- Settings management with YAML persistence
- Streaming subscriptions for real-time updates

**Controller Manager Service (port 50052, metrics 8000)**
- Backend abstraction: Bluetooth, USB, or Mock (via `CONTROLLER_BACKEND` env var)
- State streaming at 60Hz with dynamic filtering
- Button event streaming (separate from state for efficiency)
- LED color control with immediate updates
- Controller effects (flash, pulse, rainbow, fade)
- Privileged mode for Bluetooth/USB access

**Game Coordinator Service (port 50053, metrics 8000)**
- 13 game modes (FFA, Teams, Random Teams, Traitor, Werewolf, Zombies, Commander, Swapper, Fight Club, Tournament, Nonstop, Ninja, Random)
- Event streaming via `StreamGameEvents` (game_started, game_ended, player_death)
- Sensitivity-based thresholds with metrics

**Menu Service (port 50054, metrics 8000)**
- SOLID architecture with StateManager and handlers
- Controller navigation (MOVE/TRIGGER/SELECT/START buttons)
- Admin mode for game selection and force-start
- Battery display in lobby

**Supervisor Service (port 50055, metrics 8000)**
- Game orchestration between Menu and GameCoordinator
- Service health monitoring

**Audio Service (port 50056, metrics 8000)**
- Sound effects with descriptive span names (`PlaySound:congratulations`)
- Dynamic music with tempo control
- Voice selection system
- Privileged mode for /dev/snd access

**WebUI Service (port 80)**
- Flask web interface for game configuration

### Observability Stack

**OpenTelemetry Collector (port 4317 gRPC, 8889 metrics)**
- Receives traces from all services
- Forwards to Jaeger and Prometheus

**Jaeger (port 16686)**
- Distributed tracing UI
- Search by service, operation, or tags

**Prometheus (port 9090)**
- Metrics collection from all services
- Scrapes /metrics endpoints on port 8000

**Grafana (port 3000)**
- Dashboards: game-analytics, controller-overview, bluetooth-adapter, host-metrics, system-overview
- Default credentials: admin/admin

**Loki (port 3100)**
- Log aggregation from all containers
- Query via Grafana

**Redis (port 6379 internal)**
- Pub/sub for cross-service events

---

## Development Workflow

### Running the System

**Using Makefile (Recommended):**
```bash
# Start all services (builds images first)
make up

# Regenerate protobuf files
make protos

# Clean proto files
make clean-protos

# Show all targets
make help
```

**Docker Compose directly:**
```bash
# Start all services
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f [service-name]

# Stop all services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

**Mock Environment (No Hardware):**
```bash
# Set mock backend
CONTROLLER_BACKEND=mock docker-compose up -d

# Or edit docker-compose.override.yml
# environment:
#   - CONTROLLER_BACKEND=mock
#   - MOCK_CONTROLLER_COUNT=4
```

**Access Points:**
- Web UI: http://localhost:80
- Jaeger UI: http://localhost:16686
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090

### Development Commands

```bash
# Run unit tests
make test  # or: uv run pytest tests/unit/ -v

# Run integration tests (requires Docker)
uv run pytest tests/integration/ -v

# Linting and formatting (via pre-commit)
uv run ruff check .
uv run ruff format .

# Generate proto files
make protos
```

### Git Workflow

```bash
# Check current status
git status

# Check recent commits
git log --oneline -10

# Create commit
git add .
git commit -m "$(cat <<'EOF'
feat: Add new feature

Description of changes made.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"

# Push to remote
git push origin dev-refactor
```

---

## Important Files & Directories

### Service Files
```
services/
├── settings/
│   └── server.py         # Settings management
├── controller_manager/
│   ├── server.py         # Main gRPC server
│   ├── backend.py        # Abstract backend interface
│   ├── backend_factory.py # Creates Bluetooth/USB/Mock backend
│   ├── mock_backend.py   # Mock controller simulation
│   ├── mock_control_service.py  # Test control API
│   └── effects_base.py   # LED effects (flash, pulse, rainbow)
├── game_coordinator/
│   ├── server.py         # Game lifecycle management
│   ├── games/            # Game mode implementations (ffa.py, teams.py, etc.)
│   └── metrics.py        # Prometheus metrics
├── menu/
│   ├── server.py         # Entry point
│   ├── servicer.py       # gRPC servicer
│   ├── state_manager.py  # Controller state tracking
│   └── handlers/         # Connected, Ready, Admin handlers
├── supervisor/
│   └── server.py         # Orchestration
├── audio/
│   ├── server.py         # Audio playback
│   └── music_player.py   # Dynamic music with tempo control
├── grafana/
│   └── dashboards/       # JSON dashboard definitions
├── prometheus/
│   └── prometheus.yml    # Scrape configuration
└── loki/
    └── loki-config.yaml  # Log aggregation config
```

### Core Libraries
```
lib/
├── types.py              # Centralized enums (Games, Sensitivity, GameEvent)
├── colors.py             # Color definitions
├── telemetry.py          # OpenTelemetry initialization
├── system_metrics.py     # CPU/memory/temperature metrics
└── controller_constants.py  # Button/state key constants
```

### Protocol Buffers
```
proto/
├── settings.proto
├── controller_manager.proto
├── controller_manager_mock.proto  # Mock control API
├── game_coordinator.proto
├── menu.proto
├── supervisor.proto
├── audio.proto
└── generate_proto.sh     # Regenerates *_pb2.py files
```

### Configuration
```
Makefile                  # Build targets (protos, up, test)
docker-compose.yml        # Production compose
docker-compose.override.yml  # Development overrides
docker-compose.ci.yml     # CI/CD configuration
pyproject.toml            # Root workspace + ruff config
uv.lock                   # Dependency lock
```

### Documentation
```
docs/                     # Technical documentation
README.md                 # User documentation
claude.md                 # This file (session continuity)

# Planning is now tracked via GitHub Issues:
# - Milestones #12-#20: Completed work (71 phases)
# - Issues #21-#26: Planned features
# - See: gh issue list
```

---

## Communication Patterns

### gRPC (Service-to-Service)

**Unary RPC (Request-Response):**
```python
# Client
import grpc
from proto import settings_pb2, settings_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = settings_pb2_grpc.SettingsServiceStub(channel)

response = stub.GetSetting(
    settings_pb2.GetSettingRequest(key='sensitivity'),
    timeout=1.0
)
print(response.value)
```

**Server Streaming (Real-time Updates):**
```python
# Client - subscribe to setting changes
for event in stub.SubscribeToSettings(
    settings_pb2.SubscribeRequest(pattern='*')
):
    print(f"Setting changed: {event.key} = {event.value}")
```

**Async gRPC Server:**
```python
import grpc.aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

async def serve():
    server = grpc.aio.server()

    # Add service
    settings_pb2_grpc.add_SettingsServiceServicer_to_server(
        SettingsServiceServicer(), server
    )

    # Add health check
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(
        health_servicer, server
    )

    server.add_insecure_port('[::]:50051')
    await server.start()
    await server.wait_for_termination()
```

### Redis Pub/Sub (Events)

**Publisher:**
```python
import redis
import json

redis_client = redis.Redis(host='redis', port=6379)
redis_client.publish('events', json.dumps({
    'event': 'game_started',
    'data': {'mode': 'JoustFFA', 'players': 4},
    'timestamp': time.time()
}))
```

**Subscriber:**
```python
pubsub = redis_client.pubsub()
pubsub.subscribe('events')
for message in pubsub.listen():
    if message['type'] == 'message':
        event = json.loads(message['data'])
        handle_event(event)
```

---

## Performance Characteristics

### Latency Targets
- **Controller polling:** 1000Hz (hardware constraint)
- **Game logic:** 60 FPS
- **Menu rendering:** 60 FPS
- **gRPC calls:** 100-500μs per call
- **Frame budget:** 16.67ms at 60 FPS (gRPC uses <0.5ms)

### Observability
- **OpenTelemetry:** All gRPC calls instrumented with spans
- **Jaeger UI:** Distributed trace visualization at http://localhost:16686
- **Prometheus:** Metrics exported on port 8889
- **Health Checks:** All services report health status

---

## Key Architecture Decisions

### 1. **gRPC over REST/HTTP**
- **Decision:** Use gRPC for microservice communication
- **Reason:** Performance critical for real-time game on Raspberry Pi 5
- **Impact:** 3-10x faster than REST, binary protocol, streaming support
- **Latency:** ~100-500μs per RPC call on localhost vs ~1-5ms for REST

### 2. **Docker Containerization**
- **Decision:** Full Docker containerization with docker-compose
- **Reason:** Deployment consistency, dependency isolation, easy scaling
- **Impact:** Production-ready deployment, mock environment for testing

### 3. **uv Workspace with Per-Service Dependencies**
- **Decision:** Each service has its own `pyproject.toml`
- **Reason:** Clear dependency separation, workspace management
- **Impact:** Better isolation, easier to track what each service needs

### 4. **Redis for Events**
- **Decision:** Use Redis pub/sub for cross-service events
- **Reason:** Battle-tested, fast, easy to use
- **Implementation:** All services can publish/subscribe to event channels

### 5. **State-Based Controller Polling**
- **Decision:** Producer-consumer pattern with gRPC streaming
- **Reason:** Decouple hardware polling (1000Hz) from game logic (60 FPS)
- **Impact:** 60-70% CPU reduction, 3x lower latency, 10x higher update rate

### 6. **Async gRPC Servers**
- **Decision:** All services use async gRPC (grpc.aio)
- **Reason:** Better performance, non-blocking I/O
- **Impact:** Improved throughput and resource utilization

### 7. **Type Safety with ty + Code Quality with ruff**
- **Decision:** Use Astral's ty and ruff instead of mypy/black/flake8
- **Reason:** 10x-100x faster, native uv integration, comprehensive tooling
- **Impact:** Fast feedback loop, consistent code style, type safety

---

## Known Issues & Caveats

### 1. Hardware Requirements
- Requires PS Move controllers (USB/Bluetooth)
- Requires audio output (ALSA/PulseAudio)
- Best tested on Raspberry Pi, may work on other Linux systems

### 2. PSMove API
- Compiled C library, not in PyPI
- Must be built from source or pre-installed
- Docker multi-stage build handles compilation

### 3. Bluetooth Pairing
- Requires `bluetoothctl` and D-Bus access
- Docker needs `privileged: true` and device mounts
- Mock environment available for testing without hardware

### 4. Audio in Containers
- Requires device mapping: `/dev/snd:/dev/snd`
- Privileged mode for audio service
- Mock mode can simulate audio playback

---

## Task Tracking (GitHub Issues)

**All planning is now tracked via GitHub Issues:**

```bash
# View all issues
gh issue list

# View open planned features
gh issue list --state open

# View completed milestones
gh issue list --state closed --label milestone
```

**Milestone Issues (Completed Work):**
- #12: Microservices Architecture
- #13: Observability Stack
- #14: Controller Manager Evolution
- #15: Game System
- #16: Menu & User Interface
- #17: Audio System
- #18: Infrastructure & DevOps
- #19: Performance Optimization
- #20: Code Quality & Maintenance

**Planned Feature Issues:**
- #21: Feature Flags & Dynamic Configuration
- #22: OpenTelemetry Optimization for Raspberry Pi
- #23: Redis Player Profiles
- #24: Game Mode-Specific Tracking
- #25: Web UI Enhancements
- #26: Experimentation Framework & Tools

---

## Next Session Checklist

When starting a new session:

- [ ] Read this file (focus on Recent Work section)
- [ ] Run `git status` and `git log --oneline -10`
- [ ] Check GitHub issues: `gh issue list`
- [ ] Start services if needed: `make up`
- [ ] Check Jaeger: http://localhost:16686
- [ ] Check Grafana: http://localhost:3000

**Recent Work (Jan 2026):**
- Migrated planning to GitHub issues (#12-#26)
- Removed `GetGameStatus` RPC - now using `StreamGameEvents` for efficiency
- Audio span naming improvements (`PlaySound:congratulations`)
- Centralized enums in `lib/types.py` (Games, Sensitivity, GameEvent)
- Menu service SOLID refactoring (StateManager, handlers)
- Game coordinator color_assignment phase normalization

**Planned Work (see GitHub issues):**
- #21: Feature Flags & Dynamic Configuration
- #22: OpenTelemetry Optimization for Raspberry Pi
- #23: Redis Player Profiles

---

## Common Tasks

### Adding Type Hints to a Module

```bash
# 1. Add type imports
from typing import Optional, Any
from collections.abc import Callable

# 2. Add function signatures
def my_function(param: str, count: int = 0) -> list[str]:
    return [param] * count

# 3. Run type checker
./scripts/lint/check-types.sh

# 4. Run linter
./scripts/lint/check-lint.sh

# 5. Format code
./scripts/lint/format.sh
```

### Adding a New Game Mode

1. Create game file in `services/game_coordinator/games/`
2. Implement game logic with async methods
3. Add to game mode registry
4. Update proto definitions if needed
5. Test in mock environment
6. Add documentation

### Updating Dependencies

```bash
# Add dependency to a service
cd services/settings
uv add redis

# Add dev dependency to root
cd /home/simon/JoustMania
uv add --dev pytest

# Sync all dependencies
uv sync

# Rebuild Docker images
docker-compose up -d --build
```

### Viewing Traces

1. Open Jaeger UI: http://localhost:16686
2. Select service from dropdown
3. Search for traces
4. Analyze latency and call patterns

---

## Useful Commands

```bash
# Find all TODO comments
grep -r "TODO" --include="*.py" services/

# Check service dependencies
find services/ -name "pyproject.toml" -exec echo "=== {} ===" \; -exec cat {} \;

# Count lines of code
find services/ -name "*.py" | xargs wc -l | tail -1

# Find all proto files
find . -name "*.proto"

# Check Docker resource usage
docker stats

# View service logs
docker-compose logs -f settings
docker-compose logs -f controller-manager

# Restart a specific service
docker-compose restart settings

# Execute command in container
docker-compose exec settings bash
```

---

## External Resources

- **gRPC Python Docs:** https://grpc.io/docs/languages/python/
- **Protocol Buffers Guide:** https://protobuf.dev/getting-started/pythontutorial/
- **uv Documentation:** https://docs.astral.sh/uv/
- **ty Documentation:** https://docs.astral.sh/ty/
- **ruff Documentation:** https://docs.astral.sh/ruff/
- **Redis Python Client:** https://redis-py.readthedocs.io/
- **PSMove API:** https://github.com/thp/psmoveapi
- **OpenTelemetry Python:** https://opentelemetry.io/docs/languages/python/
- **Docker Compose:** https://docs.docker.com/compose/

---

## Contact & Support

**Project Repository:** /home/simon/JoustMania
**Main Branch:** master
**Development Branch:** dev-refactor
**Python Version:** 3.9-3.12 (check with `python3 --version`)
**Package Manager:** uv
**Container Orchestration:** docker-compose

**Current Status:**
- Production-ready microservices (see milestone issues #12-#20)
- Full observability stack (Jaeger, Prometheus, Grafana, Loki)
- Backend abstraction for controllers (Bluetooth/USB/Mock)
- Event streaming architecture (no polling)
- Planning tracked via GitHub issues (#21-#26 for planned features)

---

*This document is maintained by Claude and updated at the end of significant sessions.*
*Last major update: 2026-01-19 - Migrated planning to GitHub issues, removed phase management scripts*
