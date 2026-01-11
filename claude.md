# Claude Session Continuity Guide

**Last Updated:** 2026-01-11
**Project:** JoustMania - Multi-player gaming system using PS Move controllers

---

## Quick Start for New Sessions

**Current State:** Production-ready microservices architecture (Phases 1-17, 19, 21-22, 24-25 complete)
**Latest Achievement:** Phase 25 - Type Safety & Code Quality with Astral Tools (ty + ruff)
**Branch:** `dev-refactor`

### What to do first:
1. Read this file completely
2. Check `planning/IMPLEMENTATION_STATUS.md` for detailed phase status
3. Review recent commits: `git log --oneline -10`
4. Check current working directory: `git status`
5. Verify Docker services are healthy: `docker-compose ps`

---

## Project Overview

### What is JoustMania?

JoustMania is a local multiplayer party game system that runs on Raspberry Pi and uses PlayStation Move controllers. Players compete in various mini-games (jousting, zombies, etc.) with motion controls and LED feedback.

### Architecture Status

**✅ COMPLETE:** The monolithic codebase has been successfully refactored into a production-ready microservices architecture with:
- gRPC communication between services
- Docker containerization with docker-compose
- OpenTelemetry observability (Jaeger tracing)
- Redis pub/sub for events
- Health checks (gRPC Health protocol + HTTP)
- Type safety with ty and code quality with ruff
- Comprehensive documentation

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
  ├─ jaeger (distributed tracing UI, port 16686)
  ├─ otel-collector (OpenTelemetry, port 8889)
  ├─ settings (gRPC server, port 50051)
  ├─ controller-manager (gRPC server, port 50052, privileged for USB/BT)
  ├─ game-coordinator (gRPC server, port 50053)
  ├─ menu (gRPC server, port 50054)
  ├─ supervisor (gRPC server, port 50055)
  ├─ webui (HTTP server, port 80)
  └─ audio (gRPC server, port 50056, privileged for /dev/snd)
```

**Network:** All services run on `joustmania` bridge network
**Health:** All services implement gRPC Health protocol
**Tracing:** All gRPC calls instrumented with OpenTelemetry spans

---

## Major Completed Phases

### ✅ Phase 1-5: Microservices Foundation
- **Phase 1:** ControllerManager - Extracted controller polling to separate process
- **Phase 2:** GameCoordinator - Game lifecycle management
- **Phase 3:** Settings - Centralized settings with pub/sub
- **Phase 4:** ProcessSupervisor - Process management and health monitoring
- **Phase 5:** Menu - Menu UI as separate microservice
- **Phase 7:** Code restructuring with uv workspace

### ✅ Phase 8a-c: gRPC + Docker + OpenTelemetry
- **Phase 8a:** Converted all services from multiprocessing.Queue to gRPC
- **Phase 8b:** Dockerized all services with docker-compose
- **Phase 8c:** Integrated OpenTelemetry with Jaeger for distributed tracing

**Key Achievements:**
- All 7 services running in containers
- gRPC communication (100-500μs latency)
- Redis pub/sub for events
- Health checks on all services
- Jaeger UI at http://localhost:16686

### ✅ Phase 9-17: Architecture Refinement
- **Phase 9:** Architecture cleanup - Root directory organized, legacy code archived
- **Phase 10:** Scripts organization - Bash scripts in logical directories
- **Phase 11:** Comprehensive documentation - Architecture docs, READMEs
- **Phase 12:** Dependency modernization - All dependencies pinned to latest versions
- **Phase 14:** Shared protocol buffer package - Centralized proto contracts
- **Phase 15:** Docker Compose optimization - Port mappings without host binding
- **Phase 16:** Critical performance fixes - All services converted to async gRPC
- **Phase 17:** Network architecture improvements - Fixed Docker networking, gRPC channel options

### ✅ Phase 19: Controller Feedback System
- LED color control for game states
- Vibration/rumble effects
- Flash effects for events
- Complete game UX with physical feedback

### ✅ Phase 21-22: Game Mode Improvements
- **Phase 21:** Menu controller integration - Physical button navigation (MOVE/TRIGGER)
- **Phase 22:** Nonstop Joust game mode - Endless respawn with scoring and spawn protection

### ✅ Phase 24: Proper Service Health Checks
- gRPC Health protocol implemented on all services
- HTTP health endpoints for webui
- PSMove dependencies refactored (core/types.py split from core/common.py)
- Docker health checks using gRPC Health protocol
- All 9 services healthy and properly monitored

### ✅ Phase 25: Type Safety & Code Quality (LATEST)
- **ty 0.0.11** - Exceptionally fast type checker (10x-100x faster than mypy)
- **ruff 0.14.11** - Lightning-fast linter and formatter
- Comprehensive ruff configuration with 13 rule sets
- Helper scripts: `scripts/lint/check-types.sh`, `check-lint.sh`, `format.sh`, `check-all.sh`
- 119 files reformatted with consistent style
- 812 linting issues auto-fixed
- Type hints added to core/types.py, core/common.py, utils/colors.py
- Complete Astral tooling stack: uv + ruff + ty

---

## Current Architecture Details

### Service Breakdown

**Settings Service (port 50051)**
- Settings management with YAML persistence
- Schema validation
- Streaming subscriptions for real-time updates
- Dependencies: pyyaml, grpcio, grpcio-health-checking

**Controller Manager Service (port 50052)**
- Controller discovery (USB/Bluetooth)
- State streaming at 60Hz
- Battery monitoring
- Controller pairing
- Privileged mode for Bluetooth/USB access
- Dependencies: psmove, dbus-python, grpcio, grpcio-health-checking

**Game Coordinator Service (port 50053)**
- Game lifecycle management
- All 13 game modes (Joust FFA, Teams, Random Teams, Traitor, Werewolf, Zombies, Commander, Swapper, Fight Club, Tournament, Non Stop, Ninja, Random)
- Event streaming
- Dependencies: pygame, grpcio, grpcio-health-checking

**Menu Service (port 50054)**
- Menu UI rendering
- Controller navigation (MOVE/TRIGGER buttons)
- Game selection
- Admin settings
- Dependencies: pygame, grpcio, grpcio-health-checking

**Supervisor Service (port 50055)**
- Process orchestration
- Service health monitoring
- Lifecycle management
- Dependencies: grpcio, grpcio-health-checking

**Audio Service (port 50056)**
- Audio playback
- Sound effects
- Music management
- Privileged mode for /dev/snd access
- Dependencies: pygame, pyalsaaudio, grpcio, grpcio-health-checking

**WebUI Service (port 80)**
- Flask web interface
- Game configuration
- Controller status
- HTTP health endpoint at /health
- Dependencies: flask, grpcio

**Infrastructure Services**
- Redis (port 6379 internal) - Pub/sub messaging
- Jaeger (port 16686) - Distributed tracing UI
- OpenTelemetry Collector (port 8889) - Metrics export

---

## Development Workflow

### Running the System

**Docker Compose (Recommended):**
```bash
# Start all services
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

**Mock Environment (No Hardware):**
```bash
# Use mock controller manager (no real PS Move controllers needed)
docker-compose -f docker-compose.mock.yml up -d

# Configure mock controller count
# Edit docker-compose.mock.yml: MOCK_CONTROLLER_COUNT=4
```

**Access Points:**
- Web UI: http://localhost:80
- Jaeger UI: http://localhost:16686
- Prometheus metrics: http://localhost:8889/metrics

### Development Commands

**IMPORTANT: Always use `uv run` for Python commands!**

```bash
# Run tests
uv run pytest services/settings/tests/ -v

# Type checking
./scripts/lint/check-types.sh

# Linting
./scripts/lint/check-lint.sh

# Code formatting
./scripts/lint/format.sh

# All quality checks
./scripts/lint/check-all.sh

# Generate proto files (if .proto changed)
cd proto
./generate.sh
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
│   ├── server.py         # gRPC server (async)
│   ├── Dockerfile        # Container definition
│   └── pyproject.toml    # Dependencies
├── controller_manager/
│   ├── server.py         # gRPC server (async)
│   ├── mock_server.py    # Mock for testing without hardware
│   ├── Dockerfile        # Container definition
│   ├── Dockerfile.mock   # Mock container
│   └── pyproject.toml    # Dependencies
├── game_coordinator/
│   ├── server.py         # gRPC server (async)
│   ├── games/           # Game mode implementations
│   └── pyproject.toml
├── menu/
│   ├── server.py         # gRPC server (async)
│   └── pyproject.toml
├── supervisor/
│   ├── server.py         # gRPC server (async)
│   └── pyproject.toml
├── audio/
│   ├── server.py         # gRPC server (async)
│   ├── assets/          # Sound files
│   └── pyproject.toml
└── webui/
    ├── server.py         # Flask HTTP server
    └── pyproject.toml
```

### Core Infrastructure
```
core/
├── types.py              # Pure data types (no PSMove dependencies)
├── common.py             # PSMove utilities (requires psmove)
├── controller_state.py   # Controller state management
└── grpc_clients.py       # gRPC client helpers
```

### Protocol Buffers
```
proto/
├── settings.proto
├── controller_manager.proto
├── game_coordinator.proto
├── menu.proto
├── supervisor.proto
├── audio.proto
├── generate.sh          # Generates Python code from .proto files
└── pyproject.toml       # Shared proto package
```

### Configuration
```
docker-compose.yml        # Production compose file
docker-compose.mock.yml   # Mock environment (no hardware)
otel-collector-config.yaml # OpenTelemetry configuration
joustsettings.yaml       # Settings file (user-editable)
pyproject.toml           # Root workspace configuration
uv.lock                  # Dependency lock file
```

### Documentation
```
planning/
├── IMPLEMENTATION_STATUS.md   # Detailed phase status
├── CONTAINERIZATION_PLAN.md   # gRPC/Docker architecture
└── [other planning docs]
README.md                 # User-facing documentation
claude.md                 # This file (session continuity)
```

### Linting & Type Checking
```
scripts/lint/
├── check-types.sh       # Run ty type checker
├── check-lint.sh        # Run ruff linter
├── format.sh            # Run ruff formatter
└── check-all.sh         # Run all quality checks
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

## Next Session Checklist

When starting a new session:

- [ ] Read this entire file
- [ ] Check `planning/IMPLEMENTATION_STATUS.md` for latest status
- [ ] Run `git status` to see current state
- [ ] Run `git log --oneline -10` to see recent commits
- [ ] Check Docker services: `docker-compose ps`
- [ ] Review Jaeger traces: http://localhost:16686
- [ ] Verify uv is working: `uv --version`
- [ ] Check Python version: `python3 --version` (should be 3.9-3.12)

**Recent Achievements:**
- Phase 25 (Type Safety & Code Quality) - COMPLETE
- All services have health checks and proper error handling
- Complete Astral tooling stack integrated (uv + ruff + ty)

**Potential Next Tasks:**
- Review planning/IMPLEMENTATION_STATUS.md for remaining phases
- Consider additional game modes or features
- Performance optimization based on Jaeger traces
- Additional type hints for service implementations

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
- Production-ready microservices architecture
- All services containerized and healthy
- Type safety and code quality tools integrated
- Comprehensive observability with OpenTelemetry

---

*This document is maintained by Claude and updated at the end of significant sessions.*
*Last major update: 2026-01-11 - Post Phase 25 completion*
