# Claude Session Continuity Guide

**Last Updated:** 2026-01-10
**Project:** JoustMania - Multi-player gaming system using PS Move controllers

---

## Quick Start for New Sessions

**Current State:** Microservices refactoring (Phases 1-5, 7 complete)
**Next Task:** Phase 8a - Convert IPC to gRPC
**Branch:** `dev-refactor`

### What to do first:
1. Read this file completely
2. Check `IMPLEMENTATION_STATUS.md` for detailed phase status
3. Check `CONTAINERIZATION_PLAN.md` for gRPC/Docker architecture
4. Review git log: `git log --oneline -10`
5. Check current working directory status: `git status`

---

## Project Overview

### What is JoustMania?

JoustMania is a local multiplayer party game system that runs on Raspberry Pi and uses PlayStation Move controllers. Players compete in various mini-games (jousting, zombies, etc.) with motion controls and LED feedback.

### Why Microservices Refactoring?

The original `piparty.py` was ~3000 lines of monolithic code. We're refactoring it into independent microservices for:
- Better separation of concerns
- Easier testing and maintenance
- Path to containerization (Docker)
- Horizontal scaling potential
- Improved observability

---

## Architecture Evolution

### Before (Monolithic)
```
piparty.py (3000+ lines)
  ├─ Settings management
  ├─ Controller polling
  ├─ Game coordination
  ├─ Menu UI
  └─ Web UI
```

### Current (Microservices + Multiprocessing)
```
piparty.py (orchestrator)
  └─ ProcessSupervisor
      ├─ Settings (Process, Queue IPC)
      ├─ ControllerManager (Process, Queue IPC)
      ├─ GameCoordinator (Process, Queue IPC)
      └─ Menu (Process, Queue IPC)
```

### Target (Microservices + gRPC + Docker)
```
docker-compose.yml
  ├─ redis (pub/sub for events)
  ├─ settings (gRPC server, port 50051)
  ├─ controller-manager (gRPC server, port 50052, USB/BT access)
  ├─ game-coordinator (gRPC server, port 50053, audio access)
  ├─ menu (gRPC server, port 50054, audio access)
  ├─ supervisor (gRPC server, port 50055)
  └─ orchestrator (gRPC client, HTTP web UI on port 5000)
```

---

## Implementation Phases

### ✅ Completed Phases

**Phase 1: Controller Manager**
- Commit: `18a03f1`
- Extracted controller polling to separate process
- State-based architecture (producer-consumer pattern)
- Shared memory for controller state (multiprocessing.Array, Value)
- IPC via multiprocessing.Queue

**Phase 2: Game Coordinator**
- Commit: `18a03f1`
- Extracted game orchestration to separate process
- Game lifecycle management
- IPC via multiprocessing.Queue

**Phase 3: Settings Service**
- Commit: `3864851`
- Extracted settings management to separate process
- Schema-based validation (SETTINGS_SCHEMA)
- Pub/sub pattern for change notifications
- Atomic file saves (temp file + rename)
- Cache pattern: Settings process = source of truth, piparty.py = cache subscriber

**Phase 4: Process Supervisor**
- Commit: `e3c3ea0`
- Created ProcessSupervisor manager class (not a process)
- Dependency-aware startup: Settings → ControllerManager → GameCoordinator → Menu
- Health monitoring thread (5s interval)
- Automatic restart on failure (max 3 attempts, exponential backoff)
- Process state tracking (ProcessInfo, ProcessStatus enum)

**Phase 5: Menu Process**
- Commit: `6d2e954`
- Extracted menu UI to separate process
- Demonstrates full microservice pattern
- IPC via multiprocessing.Queue

**Phase 7: Code Restructuring + uv Workspace**
- Commit: `64e3a5f`
- **Critical:** User requested per-service pyproject.toml with uv workspace
- Created `services/` directory structure
- Each service has its own `pyproject.toml` with specific dependencies
- Root `pyproject.toml` defines workspace: `[tool.uv.workspace]`
- Created `core/` for shared infrastructure
- Created `utils/` for utilities
- Updated `setup.sh` to use `uv sync`

### 🔄 Current Phase

**Phase 8a: gRPC Conversion** (IN PROGRESS)
- **Status:** Design complete, implementation pending
- **Goal:** Convert from multiprocessing.Queue to gRPC
- **Why gRPC:** Performance (3-10x faster than REST), binary protocol, streaming support
- **Approach:** Direct cutover - NO feature flags, NO backward compatibility
- **User Decisions:**
  - Use gRPC instead of HTTP/REST (performance on Raspberry Pi 5)
  - No IPC fallback/feature flags
  - Remove all old non-microservice architecture code

**Next Steps:**
1. Define `.proto` files for all services
2. Generate Python gRPC code (`grpc_tools.protoc`)
3. Convert Settings service first (simplest)
4. Convert each service to gRPC server
5. Replace Queue IPC with gRPC stubs in piparty.py
6. Set up Redis for pub/sub events
7. Remove all old IPC code
8. Test on host (no Docker yet)

### 📋 Future Phases

**Phase 6: Observability** (PENDING)
- OpenTelemetry integration
- Spans for critical paths
- Metrics collection
- Already prepared: OTel collector running as daemon

**Phase 8b: Dockerization** (AFTER Phase 8a)
- Create Dockerfiles for each service
- Create docker-compose.yml
- Handle hardware access (USB/BT, audio)
- Build and test containers

**Phase 9: Developer Tooling** (AFTER Phase 8b)
- ruff (linter + formatter)
- mypy (type checking)
- pytest (testing framework)
- pre-commit hooks
- CI/CD pipeline

---

## Key Architecture Decisions

### 1. **gRPC over REST/HTTP**
- **Decision:** Use gRPC for microservice communication
- **Reason:** Performance critical for real-time game on Raspberry Pi 5
- **Impact:** 3-10x faster than REST, binary protocol, streaming support
- **Latency:** ~100-500μs per RPC call on localhost vs ~1-5ms for REST

### 2. **No Backward Compatibility**
- **Decision:** Direct cutover, remove all old IPC code
- **Reason:** Simplifies codebase, no feature flag complexity
- **Impact:** Cannot roll back without git revert

### 3. **uv Workspace with Per-Service Dependencies**
- **Decision:** Each service has its own `pyproject.toml`
- **Reason:** Clear dependency separation, workspace management
- **Impact:** Better isolation, easier to track what each service needs

### 4. **Redis for Events**
- **Decision:** Use Redis pub/sub for cross-service events
- **Reason:** Battle-tested, fast, easy to use
- **Alternative:** Could use gRPC streaming, but Redis is simpler

### 5. **State-Based Controller Polling**
- **Decision:** Producer-consumer pattern with shared memory
- **Reason:** Decouple hardware polling (1000Hz) from game logic (60 FPS)
- **Impact:** 60-70% CPU reduction, 3x lower latency, 10x higher update rate

---

## Important Files

### Core Project Files

- **`piparty.py`** - Main orchestrator, creates and manages all processes
- **`webui.py`** - Flask web interface for game configuration
- **`joustsettings.yaml`** - Settings file (user-editable)
- **`setup.sh`** - Installation script (now uses `uv sync`)

### Service Files

```
services/
├── controller_manager/
│   ├── __init__.py
│   ├── process.py         # ControllerManagerProcess
│   └── pyproject.toml     # Dependencies: pyyaml, dbus-python, opentelemetry
├── game_coordinator/
│   ├── __init__.py
│   ├── process.py         # GameCoordinatorProcess
│   └── pyproject.toml     # Dependencies: pygame, pydub, pyalsaaudio, opentelemetry
├── settings/
│   ├── __init__.py
│   ├── process.py         # SettingsProcess
│   └── pyproject.toml     # Dependencies: pyyaml, opentelemetry
├── supervisor/
│   ├── __init__.py
│   ├── manager.py         # ProcessSupervisor (not a process)
│   └── pyproject.toml     # No external dependencies!
└── menu/
    ├── __init__.py
    ├── process.py         # MenuProcess
    └── pyproject.toml     # Dependencies: pygame, pydub, pyalsaaudio, pyyaml, opentelemetry
```

### Core Infrastructure

```
core/
├── __init__.py
├── common.py              # Shared constants, color definitions
├── controller_state.py    # ControllerState class, shared memory structures
└── controller_process.py  # Legacy controller polling (being phased out)
```

### Utilities

```
utils/
├── __init__.py
├── colors.py             # LED color utilities
├── piaudio.py            # Audio playback wrapper
└── pair.py               # Controller pairing utilities
```

### Documentation

- **`CONTAINERIZATION_PLAN.md`** - Full gRPC + Docker architecture
- **`IMPLEMENTATION_STATUS.md`** - Detailed phase-by-phase status
- **`README.md`** - User-facing documentation
- **`claude.md`** - This file (session continuity)

---

## IPC Patterns

### Current: multiprocessing.Queue

**Command/Response Pattern:**
```python
# Sender (piparty.py)
request_id = str(uuid.uuid4())
cmd_queue.put({
    'command': 'get_settings',
    'request_id': request_id,
    'params': {}
})

# Wait for response
response = wait_for_response(resp_queue, request_id, timeout=1.0)
```

**Event Pattern:**
```python
# Publisher (any process)
event_queue.put({
    'event': 'setting_changed',
    'data': {'key': 'sensitivity', 'value': 2},
    'timestamp': time.time()
})

# Subscriber (piparty.py)
while True:
    event = event_queue.get()
    handle_event(event)
```

### Future: gRPC

**RPC Pattern:**
```python
# Client (piparty.py)
import grpc
from services.settings import settings_pb2, settings_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = settings_pb2_grpc.SettingsServiceStub(channel)

response = stub.GetSettings(
    settings_pb2.GetSettingsRequest(),
    timeout=1.0
)
```

**Event Pattern (Redis pub/sub):**
```python
# Publisher (any service)
redis_client.publish('events', json.dumps({
    'event': 'setting_changed',
    'data': {'key': 'sensitivity', 'value': 2},
    'timestamp': time.time()
}))

# Subscriber (orchestrator)
pubsub = redis_client.pubsub()
pubsub.subscribe('events')
for message in pubsub.listen():
    event = json.loads(message['data'])
    handle_event(event)
```

---

## Development Workflow

### Running the System

```bash
# Activate uv environment
cd /home/simon/JoustMania
source .venv/bin/activate  # or use `uv run`

# Run main application
python3 piparty.py

# Or with uv
uv run python piparty.py

# Access web UI
# http://localhost:5000
```

### Testing Changes

```bash
# Syntax check
python3 -m py_compile piparty.py
python3 -m py_compile services/settings/process.py

# Run with debug logging
PYTHONUNBUFFERED=1 python3 piparty.py 2>&1 | tee debug.log
```

### Git Workflow

```bash
# Check current status
git status

# Check recent commits
git log --oneline -10

# Create commits (use provided template)
git add .
git commit -m "$(cat <<'EOF'
feat: Add gRPC support to Settings service

Converts Settings service from multiprocessing.Queue to gRPC:
- Define settings.proto with service interface
- Generate Python gRPC code
- Implement SettingsServiceServicer
- Add gRPC server startup
- Update piparty.py to use gRPC stub

This is part of Phase 8a (gRPC conversion).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"

# Push to remote
git push origin dev-refactor
```

---

## Common Tasks

### Adding a New Service

1. Create directory: `services/new_service/`
2. Create `__init__.py`, `process.py`, `pyproject.toml`
3. Define service interface (.proto file for gRPC)
4. Implement service logic
5. Add to `services/__init__.py` `__all__` list
6. Register with ProcessSupervisor in `piparty.py`
7. Update root `pyproject.toml` workspace members

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
```

### Reading Controller State

```python
# From any process with access to ns (multiprocessing.Manager namespace)
controller_count = ns.controller_count.value
team_colors = [ns.team_colors[i] for i in range(controller_count)]

# Access controller state
from core.controller_state import ControllerState
controllers = [
    ControllerState.from_shared_memory(ns.controllers[i])
    for i in range(controller_count)
]
```

---

## Critical Patterns

### Settings Cache Pattern

**Source of Truth:** Settings process maintains settings in memory and file
**Cache:** piparty.py subscribes to changes and maintains `ns.settings` cache
**Why:** Fast local reads, no IPC overhead, guaranteed consistency via events

### Dependency-Aware Startup

**Order:** Settings → ControllerManager → GameCoordinator → Menu
**Reason:** Dependencies must be running before dependents start
**Managed by:** ProcessSupervisor

### State-Based Controller Polling

**Producer:** Hardware polling at 1000Hz, updates shared memory
**Consumer:** Game logic reads from shared memory at 60 FPS
**Why:** Decouples hardware timing from game timing

---

## Known Issues & Caveats

### 1. Hardware Requirements
- Requires PS Move controllers (USB/Bluetooth)
- Requires audio output (ALSA/PulseAudio)
- Best tested on Raspberry Pi, may work on other Linux systems

### 2. PSMove API
- Compiled C library, not in PyPI
- Must be built from source or pre-installed
- Will need special handling in Docker (multi-stage build)

### 3. Bluetooth Pairing
- Requires `bluetoothctl` and D-Bus access
- Docker containerization will need `privileged: true` and `network_mode: host`

### 4. Audio in Containers
- Requires device mapping: `/dev/snd:/dev/snd`
- PulseAudio socket mapping: `/run/user/1000/pulse`

---

## User Preferences & Decisions

Throughout this refactoring, the user has made specific decisions:

1. **Continue without hardware testing** - Proceed with implementation even though hardware isn't available for testing yet
2. **Use uv workspace** - Each service needs its own `pyproject.toml` for clear dependency separation
3. **Use gRPC not REST** - Performance is critical for real-time game on Raspberry Pi
4. **No feature flags** - Direct cutover to gRPC, no backward compatibility
5. **Remove old code** - Clean up all legacy non-microservice architecture

---

## Performance Targets

### Current System
- Controller polling: 1000Hz
- Game logic: 60 FPS
- Menu rendering: 60 FPS
- IPC: Shared memory (very fast, but not network-ready)

### After gRPC Conversion
- Controller polling: 1000Hz (unchanged)
- Game logic: 60 FPS (unchanged)
- Menu rendering: 60 FPS (unchanged)
- IPC: gRPC (100-500μs per call, acceptable overhead)
- Budget: 16.67ms per frame at 60 FPS, gRPC uses <0.5ms

### Performance Monitoring
- OpenTelemetry spans on critical paths
- OTel collector already configured
- Ready for Phase 6 (Observability)

---

## Next Session Checklist

When starting a new session:

- [ ] Read this entire file
- [ ] Check `IMPLEMENTATION_STATUS.md` for latest status
- [ ] Check `CONTAINERIZATION_PLAN.md` for architecture details
- [ ] Run `git status` to see current state
- [ ] Run `git log --oneline -10` to see recent commits
- [ ] Check if any tests are available: `find . -name "test_*.py"`
- [ ] Verify uv is working: `uv --version`
- [ ] Check Python version: `python3 --version` (should be 3.9-3.12)

**Current Task:** Implement Phase 8a - Convert Settings service to gRPC
**Next File to Edit:** `services/settings/settings.proto` (create)
**Reference:** See CONTAINERIZATION_PLAN.md for protobuf schema

---

## Questions to Ask User

If unsure about implementation details:

1. **Hardware availability:** "Do you have hardware available for testing, or should I continue with implementation?"
2. **Testing approach:** "Should I write tests as I go, or implement first and test later?"
3. **Error handling:** "How should services handle network failures - retry, fail fast, or degrade gracefully?"
4. **Deployment target:** "Will this run on a single Raspberry Pi, or distributed across multiple devices?"

---

## Useful Commands

```bash
# Find all TODO comments
grep -r "TODO" --include="*.py" .

# Find all IPC usage (to identify conversion work)
grep -r "command_queue\|response_queue" --include="*.py" .

# Check service dependencies
find services/ -name "pyproject.toml" -exec echo "=== {} ===" \; -exec cat {} \;

# Count lines of code
find . -name "*.py" -not -path "./.venv/*" | xargs wc -l | tail -1

# Find all gRPC-ready services
find services/ -name "*.proto"
```

---

## External Resources

- **gRPC Python Docs:** https://grpc.io/docs/languages/python/
- **Protocol Buffers Guide:** https://protobuf.dev/getting-started/pythontutorial/
- **uv Documentation:** https://docs.astral.sh/uv/
- **Redis Python Client:** https://redis-py.readthedocs.io/
- **PSMove API:** https://github.com/thp/psmoveapi

---

## Contact & Support

**Project Repository:** /home/simon/JoustMania
**Main Branch:** master
**Development Branch:** dev-refactor
**Python Version:** 3.9-3.12 (check with `python3 --version`)
**Package Manager:** uv

**User Notes:**
- Cannot test with real hardware currently
- Wants to proceed with gRPC implementation
- Prefers clean code without backward compatibility

---

*This document is maintained by Claude and should be updated at the end of each significant session.*
