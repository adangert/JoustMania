# JoustMania Microservices Architecture - Cleanup & Gaps Analysis

**Date:** 2026-01-10
**Purpose:** Identify gaps in microservices architecture and plan final cloud-native structure
**Context:** After completing 6 microservices (Phase 8c), analyze remaining root files to determine what's missing

---

## Current Microservices Architecture (Phase 8c Complete)

###  Implemented Services (6 total)

1. **Settings Service** (port 50051)
   - Manages joustsettings.yaml
   - Get/update settings via gRPC
   - 37 comprehensive tests passing
   - OpenTelemetry instrumentation

2. **ControllerManager Service** (port 50052)
   - PS Move controller discovery & pairing
   - Real-time controller state streaming
   - Battery status monitoring
   - Mock mode for testing without hardware

3. **GameCoordinator Service** (port 50053)
   - Game lifecycle management
   - Real-time game event streaming
   - **Currently has mock game loop** ⚠️ NEEDS GAME IMPLEMENTATIONS

4. **Menu Service** (port 50054)
   - Menu state management
   - Input processing (buttons, web commands)
   - Game selection navigation
   - Event streaming

5. **Supervisor Service** (port 50055)
   - Process health monitoring
   - Background health check loop (5s interval)
   - System-wide health summary
   - Process restart capability

6. **WebUI Service** (port 80) ✅ NEW (Phase 8c)
   - Flask HTTP/REST API
   - Web interface for settings & game control
   - **gRPC client to all backend services** (no more Queue-based IPC)
   - Maintains backward compatibility with existing routes

### Infrastructure Services

- **Redis** (port 6379) - Pub/sub messaging
- **Jaeger** (port 16686) - Distributed tracing UI
- **OpenTelemetry Collector** (port 4317) - OTLP receiver

---

## Root Directory Analysis

### Total Python files in root: 31

**Distribution:**
- 11 confirmed duplicates (already in services/, core/, utils/)
- 1 legacy orchestrator (piparty.py)
- 1 new orchestrator (piparty_grpc.py) - **UNCLEAR IF NEEDED**
- 5 shared libraries (need proper packaging)
- 6 utilities/tools
- 3 system integration files
- 4 test files

### Key Question: Why are these files still in root?

Having files in root suggests one of:
1. **Duplicates** - Already moved to services/, should delete
2. **Shared libraries** - Need proper packaging in core/ or utils/
3. **Missing service functionality** - Service needs this code but doesn't have it yet
4. **Missing services** - Should this be a separate service?

---

## Critical Gap: Game Implementations Not Integrated

### The Problem

**GameCoordinator service currently has a MOCK game loop:**
```python
# services/game_coordinator/server.py
def _run_game_loop(self):
    """Run the game loop in background thread."""
    self.game_state = game_coordinator_pb2.GameState.RUNNING
    game_duration = 30
    elapsed = 0
    
    # MOCK: Just sleeps for 30 seconds and publishes random events
    while self.game_running and elapsed < game_duration:
        time.sleep(1)
        elapsed += 1
        
        # Mock random player deaths
        if elapsed % 10 == 0:
            alive_players = [p for p in self.players if p.alive]
            if alive_players:
                player = random.choice(alive_players)
                player.alive = False
```

**Real game implementations exist in root directory:**
- `games/` directory with 15+ game modes
- `player.py` (234 lines) - Player management classes
- `pacemanager.py` (72 lines) - Game dynamics utility

**Current situation:**
- Games are copied into ALL services via Dockerfiles (`COPY games/ /app/games/`)
- But games are NOT ACTUALLY USED by any service!
- GameCoordinator just runs a mock 30-second loop

### The Solution: Move Games to Core Package

**Proposed structure:**
```
core/
  games/
    __init__.py
    base.py          # from games/game.py - base game class
    player.py        # MOVED from root
    pacemanager.py   # MOVED from root
    ffa.py           # MOVED from games/
    joust_ffa.py     # Simple mode
    joust_teams.py   # Simple mode
    tournament.py    # Medium complexity
    werewolf.py      # Medium complexity
```

**Why this works:**
- Games are **shared library code** used by GameCoordinator
- Only GameCoordinator service needs to import `core.games`
- Other services don't need games copied to them
- Simpler game modes only (for cloud-native PoC)

**Services that need games:**
- ✅ GameCoordinator - YES (runs games)
- ❌ Settings - NO
- ❌ ControllerManager - NO
- ❌ Menu - NO
- ❌ Supervisor - NO
- ❌ WebUI - NO

---

## File-by-File Analysis

### Category 1: DELETE - Confirmed Duplicates (11 files)

| File | Duplicate Location | Action |
|------|-------------------|--------|
| `controller_manager.py` | `services/controller_manager/process.py` | DELETE |
| `game_coordinator.py` | `services/game_coordinator/process.py` | DELETE |
| `settings_process.py` | `services/settings/process.py` | DELETE |
| `process_supervisor.py` | `services/supervisor/process.py` | DELETE |
| `webui.py` ✅ NEW | `services/webui/server.py` | DELETE |
| `controller_state.py` | `core/controller_state.py` | DELETE |
| `controller_process.py` | `core/controller_process.py` | DELETE |
| `common.py` | `core/common.py` | DELETE |
| `pair.py` | `utils/pair.py` | DELETE |
| `colors.py` | `utils/colors.py` | DELETE |
| `piaudio.py` | `utils/piaudio.py` | DELETE |

**Impact:** None - these are legacy Queue-based versions

### Category 2: ARCHIVE - Legacy Orchestrator (1 file)

| File | Lines | Purpose | Action |
|------|-------|---------|--------|
| `piparty.py` | 3000+ | Old Queue-based orchestrator | ARCHIVE to `legacy/` |

**Question:** What about `piparty_grpc.py`?

### Category 3: MOVE TO core/games/ - Game Implementations (3 files + directory)

| File | Lines | Purpose | Destination |
|------|-------|---------|-------------|
| `player.py` | 234 | Player management classes | `core/games/player.py` |
| `pacemanager.py` | 72 | Game dynamics utility | `core/games/pacemanager.py` |
| `games/game.py` | 634 | Base game class | `core/games/base.py` |
| `games/ffa.py` | ~100 | Free-for-all game mode | `core/games/ffa.py` |
| `games/joust_ffa.py` | ~50 | Simple joust mode | `core/games/joust_ffa.py` |
| `games/joust_teams.py` | ~50 | Team joust mode | `core/games/joust_teams.py` |

**Impact:** HIGH - Enables actual gameplay in GameCoordinator service

### Category 4: MOVE TO core/ - Shared Infrastructure (2 files)

| File | Purpose | Destination |
|------|---------|-------------|
| `base_logger.py` | Logging infrastructure | `core/base_logger.py` |
| `grpc_clients.py` | gRPC client library | `core/grpc_clients.py` |

**Note:** `grpc_clients.py` currently only has SettingsClient, needs all 6 service clients

### Category 5: MOVE TO utils/ - Utilities (3 files)

| File | Purpose | Destination |
|------|---------|-------------|
| `controller_util.py` | Controller utility functions | `utils/controller_util.py` |
| `playwav.py` | Audio playback utility | `utils/playwav.py` |
| `win_pair.py` | Windows pairing utility | `utils/win_pair.py` |

### Category 6: MOVE TO testing/ - Tests (4 files)

| File | Destination |
|------|-------------|
| `joust_test.py` | `testing/joust_test.py` |
| `pacemanager_test.py` | `testing/pacemanager_test.py` |
| `test_orchestrator.py` | `testing/test_orchestrator.py` |
| `games/ffa_test.py` | `testing/ffa_test.py` |

**Keep in root:** `conftest.py` (pytest needs it there)

### Category 7: MOVE TO tools/ - Standalone Tools (3 files)

| File | Purpose | Destination |
|------|---------|-------------|
| `audio_tool.py` | Audio testing utility | `tools/audio_tool.py` |
| `clear_devices.py` | Device cleanup utility | `tools/clear_devices.py` |
| `manualpair.py` | Manual pairing tool | `tools/manualpair.py` |

### Category 8: KEEP IN ROOT - System Integration (4 files)

| File | Purpose | Why Keep |
|------|---------|----------|
| `jm_dbus.py` | D-Bus integration (Linux) | System-level |
| `win_jm_dbus.py` | D-Bus integration (Windows) | System-level |
| `update.py` | Update script | Entry point |
| `__init__.py` | Package initialization | Required |

### Category 9: DECIDE - Orchestrator (1 file)

| File | Lines | Purpose | Options |
|------|-------|---------|---------|
| `piparty_grpc.py` | 270 | gRPC orchestrator | A) Keep, B) Remove (Supervisor does this), C) Integrate into Supervisor |

**Need to investigate:** What does piparty_grpc.py do that Supervisor doesn't?

---

## Proposed Final Directory Structure

```
JoustMania/
├── core/                     # Shared core infrastructure
│   ├── __init__.py
│   ├── common.py
│   ├── controller_state.py
│   ├── controller_process.py
│   ├── base_logger.py        # MOVED from root
│   ├── grpc_clients.py       # MOVED from root (+ expanded)
│   │
│   └── games/                # Game implementations (NEW)
│       ├── __init__.py
│       ├── base.py           # MOVED from games/game.py
│       ├── player.py         # MOVED from root
│       ├── pacemanager.py    # MOVED from root
│       ├── ffa.py            # MOVED from games/
│       ├── joust_ffa.py      # MOVED from games/
│       ├── joust_teams.py    # MOVED from games/
│       ├── tournament.py     # MOVED from games/ (optional)
│       └── werewolf.py       # MOVED from games/ (optional)
│
├── utils/                    # Utilities
│   ├── __init__.py
│   ├── pair.py
│   ├── colors.py
│   ├── piaudio.py
│   ├── controller_util.py    # MOVED from root
│   ├── playwav.py            # MOVED from root
│   └── win_pair.py           # MOVED from root
│
├── services/                 # Microservices (6 services)
│   ├── settings/
│   ├── controller_manager/
│   ├── game_coordinator/     # UPDATE: Use core.games
│   ├── menu/
│   ├── supervisor/
│   └── webui/
│
├── testing/                  # All tests (NEW)
│   ├── __init__.py
│   ├── joust_test.py         # MOVED from root
│   ├── pacemanager_test.py   # MOVED from root
│   ├── test_orchestrator.py  # MOVED from root
│   └── ffa_test.py           # MOVED from games/
│
├── tools/                    # Standalone tools (NEW)
│   ├── audio_tool.py         # MOVED from root
│   ├── clear_devices.py      # MOVED from root
│   └── manualpair.py         # MOVED from root
│
├── legacy/                   # Archived code (NEW)
│   ├── piparty.py            # MOVED from root
│   ├── controller_manager.py # MOVED from root
│   ├── game_coordinator.py   # MOVED from root
│   ├── settings_process.py   # MOVED from root
│   ├── process_supervisor.py # MOVED from root
│   └── webui.py              # MOVED from root
│
├── templates/                # Web UI templates
├── static/                   # Web UI static files
│
├── docker-compose.yml
├── otel-collector-config.yaml
├── pyproject.toml
├── conftest.py               # KEEP (pytest needs it)
├── __init__.py               # KEEP
├── jm_dbus.py                # KEEP (system integration)
├── win_jm_dbus.py            # KEEP (system integration)
└── update.py                 # KEEP (entry point)
```

**Root directory after cleanup: 8 files** (vs 31 currently)

---

## Dockerfile Updates Required

### Current Problem

All services copy `games/` directory but only GameCoordinator needs it:

```dockerfile
# services/menu/Dockerfile (WASTEFUL)
COPY games/ /app/games/

# services/game_coordinator/Dockerfile (WASTEFUL)
COPY games/ /app/games/

# services/webui/Dockerfile (WASTEFUL)
COPY games/ /app/games/
```

### Proposed Solution

Only copy what each service needs:

```dockerfile
# services/game_coordinator/Dockerfile (NEEDS games)
COPY core/ /app/core/
COPY utils/ /app/utils/
# games/ is now in core/games/, no separate copy needed

# services/menu/Dockerfile (NO games needed)
COPY core/ /app/core/
COPY utils/ /app/utils/
# Remove: COPY games/ /app/games/

# services/webui/Dockerfile (NO games needed)
COPY core/ /app/core/
COPY utils/ /app/utils/
# Remove: COPY games/ /app/games/
```

**Benefits:**
- Smaller Docker images (remove ~500KB per service)
- Faster builds (less to copy)
- Clearer dependencies

---

## Implementation Plan (Phase 9 - Cleanup)

### Step 1: Archive Legacy Files ✅ LOW RISK

```bash
mkdir -p legacy
mv piparty.py legacy/
mv controller_manager.py legacy/
mv game_coordinator.py legacy/
mv settings_process.py legacy/
mv process_supervisor.py legacy/
mv webui.py legacy/
```

**Verification:** Services still run (they use services/* code)

### Step 2: Create New Directory Structure ⚠️ MEDIUM RISK

```bash
# Create new directories
mkdir -p core/games
mkdir -p testing
mkdir -p tools

# Move to core/
mv base_logger.py core/
mv grpc_clients.py core/

# Move to core/games/
mv player.py core/games/
mv pacemanager.py core/games/
mv games/game.py core/games/base.py
mv games/ffa.py core/games/
mv games/joust_ffa.py core/games/
mv games/joust_teams.py core/games/
# Create __init__.py
touch core/games/__init__.py

# Move to utils/
mv controller_util.py utils/
mv playwav.py utils/
mv win_pair.py utils/

# Move to testing/
mv joust_test.py testing/
mv pacemanager_test.py testing/
mv test_orchestrator.py testing/
mv games/ffa_test.py testing/
touch testing/__init__.py

# Move to tools/
mv audio_tool.py tools/
mv clear_devices.py tools/
mv manualpair.py tools/
```

**Verification:** All moved files exist in new locations

### Step 3: Delete Duplicates ✅ LOW RISK

```bash
rm controller_state.py controller_process.py common.py
rm pair.py colors.py piaudio.py
```

**Verification:** No import errors (these already exist in core/ and utils/)

### Step 4: Update Import Statements 🔍 HIGH RISK

**Files to update:**
- `services/game_coordinator/server.py` - Import from `core.games`
- All files that import `player` or `pacemanager`
- All files that import `common`, `colors`, etc. from wrong locations

```python
# OLD (wrong)
import player
import pacemanager
import common
from games import game

# NEW (correct)
from core.games import player, pacemanager
from core.games import base as game_base
from core import common
from utils import colors
```

**Verification:** Run imports test, no circular dependencies

### Step 5: Update GameCoordinator Service ⚠️ HIGH RISK

1. Update `services/game_coordinator/server.py`
2. Remove mock game loop
3. Import actual game classes from `core.games`
4. Implement real game execution
5. Update Dockerfile to copy `core/` (already does this)

**Verification:** Can start and run a real FFA game

### Step 6: Update Dockerfiles 📦 MEDIUM RISK

Remove unnecessary `COPY games/` from:
- services/menu/Dockerfile
- services/settings/Dockerfile
- services/supervisor/Dockerfile
- services/webui/Dockerfile

Keep only in:
- services/game_coordinator/Dockerfile (uses core/games/)
- services/controller_manager/Dockerfile (if needed)

**Verification:** Docker builds succeed, image sizes reduced

### Step 7: Complete gRPC Clients Library ⚠️ MEDIUM RISK

Update `core/grpc_clients.py` to include all service clients:

```python
# Currently only has:
class SettingsClient

# Need to add:
class ControllerManagerClient
class MenuClient
class GameCoordinatorClient
class SupervisorClient
class WebUIClient (if needed)
```

**Verification:** Services can communicate via gRPC

### Step 8: Test Complete System ✅ CRITICAL

```bash
# Clean rebuild
docker-compose down
docker-compose up --build

# Verify all services start
docker-compose ps

# Test web UI
curl http://localhost:80/

# Test game flow
# 1. Access web UI
# 2. Select game mode (FFA)
# 3. Start game
# 4. Verify game runs (not mock)
# 5. Check Jaeger traces (http://localhost:16686)

# Run tests
cd testing/
pytest
```

---

## Questions to Resolve

### 1. piparty_grpc.py - Keep or Remove?

**Current State:** 270-line gRPC orchestrator in root

**Investigation needed:**
- Read piparty_grpc.py to understand what it does
- Does Supervisor already do this?
- Who calls piparty_grpc.py?
- Is it still needed in microservices architecture?

**Options:**
- A) DELETE - Supervisor handles orchestration
- B) KEEP - Still needed for startup coordination
- C) INTEGRATE - Merge functionality into Supervisor service

### 2. Which Game Modes to Include?

**Available:** 15+ game modes in `games/`

**For cloud-native PoC, include:**
- ✅ ffa.py - Free-for-all (simplest)
- ✅ joust_ffa.py - Joust free-for-all
- ✅ joust_teams.py - Team mode
- ⚠️ tournament.py - Medium complexity
- ⚠️ werewolf.py - Medium complexity
- ❌ Others - Too complex for initial PoC

**Recommendation:** Start with 3 simplest modes (ffa, joust_ffa, joust_teams)

### 3. gRPC Clients - Single File or Directory?

**Options:**
- A) `core/grpc_clients.py` - Single file with all clients
- B) `core/grpc/` - Directory with one file per service
- C) Each service has its own client code

**Recommendation:** Option A (single file) for simplicity

### 4. Shared Library Package Name?

**Current:** `core/` and `utils/`

**Alternative:** `joustmania_core/` and `joustmania_utils/`

**Recommendation:** Keep `core/` and `utils/` (simpler, already works)

---

## Summary

### What We Have (After Phase 8c)
- ✅ 6 microservices with gRPC communication
- ✅ Full OpenTelemetry observability
- ✅ Docker Compose orchestration
- ✅ Redis pub/sub
- ✅ Jaeger distributed tracing
- ✅ WebUI converted to gRPC client

### What's Missing
- ❌ Game implementations not integrated into GameCoordinator
- ❌ Games and shared libraries not properly packaged
- ❌ Root directory cluttered with 31 Python files
- ❌ Incomplete gRPC client library
- ❌ Dockerfiles copying unnecessary files

### What Phase 9 Will Accomplish
1. **Archive** 6 legacy files to `legacy/`
2. **Move** game implementations to `core/games/` package
3. **Move** shared libraries to proper locations
4. **Move** tests to `testing/`
5. **Move** tools to `tools/`
6. **Delete** 11 duplicate files
7. **Update** GameCoordinator to run real games
8. **Update** import statements across codebase
9. **Complete** gRPC client library
10. **Clean** root directory (31 → 8 files)

### Final State (After Phase 9)
```
Root directory: 8 files
- conftest.py, __init__.py, jm_dbus.py, win_jm_dbus.py, update.py
- docker-compose.yml, otel-collector-config.yaml, pyproject.toml

Organized structure:
- core/ (shared infrastructure + games)
- utils/ (utilities)
- services/ (6 microservices)
- testing/ (all tests)
- tools/ (standalone tools)
- legacy/ (archived code)
```

---

## Next Action

**RECOMMENDED:** Before implementing Phase 9:

1. ✅ Review this analysis with user
2. ❓ Answer the 4 questions above
3. ❓ Decide on piparty_grpc.py fate
4. ❓ Choose which game modes to include
5. 📅 Execute Phase 9 step-by-step with testing after each step

**CRITICAL:** Focus on planning before implementation, as requested by user.
