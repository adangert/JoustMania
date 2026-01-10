# JoustMania Root Directory Cleanup Plan

**Date:** 2026-01-10
**Context:** After implementing microservices architecture, many root-level Python files are now duplicates or obsolete.

---

## Analysis of Root Python Files

### ❌ REMOVE - Duplicates (Already in services/)

These files have been moved to `services/` and are now duplicates:

1. **controller_manager.py** → `services/controller_manager/process.py`
   - Queue-based IPC version
   - Replaced by gRPC server in `services/controller_manager/server.py`
   - **Action:** DELETE

2. **game_coordinator.py** → `services/game_coordinator/process.py`
   - Queue-based IPC version
   - Replaced by gRPC server in `services/game_coordinator/server.py`
   - **Action:** DELETE

3. **settings_process.py** → `services/settings/process.py`
   - Queue-based IPC version
   - Replaced by gRPC server in `services/settings/server.py`
   - **Action:** DELETE

4. **process_supervisor.py** → `services/supervisor/process.py`
   - Queue-based IPC version
   - Replaced by gRPC server in `services/supervisor/server.py`
   - **Action:** DELETE

### ❌ REMOVE - Duplicates (Already in core/)

These files have been moved to `core/`:

5. **controller_state.py** → `core/controller_state.py`
   - **Action:** DELETE (already in core/)

6. **controller_process.py** → `core/controller_process.py`
   - **Action:** DELETE (already in core/)

7. **common.py** → `core/common.py`
   - **Action:** DELETE (already in core/)

### ❌ REMOVE - Duplicates (Already in utils/)

These files have been moved to `utils/`:

8. **pair.py** → `utils/pair.py`
   - **Action:** DELETE (already in utils/)

9. **colors.py** → `utils/colors.py`
   - **Action:** DELETE (already in utils/)

10. **piaudio.py** → `utils/piaudio.py`
    - **Action:** DELETE (already in utils/)

### ⚠️ DECIDE - Legacy Orchestrator

11. **piparty.py** (3000+ lines)
    - Old Queue-based orchestrator
    - Uses multiprocessing.Queue for IPC
    - **Options:**
      - A) DELETE - We have `piparty_grpc.py` now
      - B) KEEP - For backward compatibility until gRPC fully tested
      - C) ARCHIVE - Move to `legacy/` folder
    - **Recommendation:** Move to `legacy/` folder for now
    - **Note:** Check if `joust.py` or setup scripts still reference this

### ✅ KEEP - New gRPC Infrastructure

12. **piparty_grpc.py**
    - New gRPC-based orchestrator
    - Replaces piparty.py
    - **Action:** KEEP

13. **grpc_clients.py**
    - gRPC client library for all services
    - **Action:** KEEP

### ✅ KEEP - Web Interface

14. **webui.py**
    - Web interface for JoustMania
    - Still needed for HTTP server
    - **Action:** KEEP

### ✅ KEEP - Utilities & Tools

15. **audio_tool.py**
    - Audio testing utility
    - **Action:** KEEP (useful for debugging)

16. **clear_devices.py**
    - Device cleanup utility
    - **Action:** KEEP (useful for maintenance)

17. **controller_util.py**
    - Controller utility functions
    - **Action:** KEEP (or move to utils/)

18. **manualpair.py**
    - Manual pairing tool
    - **Action:** KEEP (useful for setup)

19. **update.py**
    - Update script
    - **Action:** KEEP (system maintenance)

20. **playwav.py**
    - Audio playback utility
    - **Action:** KEEP (or move to utils/)

### ✅ KEEP - System Integration

21. **jm_dbus.py**
    - D-Bus integration (Linux)
    - **Action:** KEEP

22. **win_jm_dbus.py**
    - D-Bus integration (Windows)
    - **Action:** KEEP

### ✅ KEEP - Testing

23. **conftest.py**
    - pytest configuration (mocks psmove)
    - **Action:** KEEP

24. **joust_test.py**
    - Test file
    - **Action:** KEEP (or move to testing/)

25. **pacemanager_test.py**
    - Test file
    - **Action:** KEEP (or move to testing/)

26. **test_orchestrator.py**
    - Test file
    - **Action:** KEEP (or move to testing/)

### ✅ KEEP - Game Utilities

27. **pacemanager.py**
    - Pace management for game dynamics (speed/intensity transitions)
    - Used by `games/ffa.py` (Free-For-All mode)
    - Manages weighted random transitions between game paces
    - **Action:** KEEP - Actively used

28. **player.py**
    - Player management classes
    - Used by `games/ffa.py` and potentially other game modes
    - **Action:** KEEP - Likely used by game implementations

### ✅ KEEP - Package Init

29. **__init__.py**
    - Package initialization
    - **Action:** KEEP

30. **base_logger.py**
    - Logging infrastructure
    - **Action:** KEEP (or move to core/)

---

## Cleanup Strategy

### Phase 1: Safe Removals (Confirmed Duplicates)

```bash
# Create a backup first
mkdir -p archive/root-backup-$(date +%Y%m%d)
cp *.py archive/root-backup-$(date +%Y%m%d)/

# Remove confirmed duplicates
rm controller_manager.py
rm game_coordinator.py
rm settings_process.py
rm process_supervisor.py
rm controller_state.py
rm controller_process.py
rm common.py
rm pair.py
rm colors.py
rm piaudio.py
```

**Impact:** None - These files exist in their new locations (services/, core/, utils/)

### Phase 2: Archive Legacy

```bash
# Create legacy folder
mkdir -p legacy

# Move old orchestrator
mv piparty.py legacy/

# Update any references
# Check: joust.py, setup.sh, systemd files
```

**Impact:** Need to update any scripts that reference `piparty.py`

### Phase 3: Organize Utilities

```bash
# Move utilities to utils/
mv controller_util.py utils/
mv playwav.py utils/
mv base_logger.py core/

# Update imports in files that use these
```

**Impact:** Minor - Need to update import statements

### Phase 4: Organize Tests

```bash
# Move tests to testing/
mv joust_test.py testing/
mv pacemanager_test.py testing/
mv test_orchestrator.py testing/
```

**Impact:** Minor - Update test runner if needed

### Phase 5: Investigate & Remove Unused

```bash
# Check usage of these files
grep -r "import pacemanager" .
grep -r "import player" .

# If unused, remove
rm pacemanager.py  # if unused
rm player.py       # if unused
```

**Impact:** Depends on usage

---

## Updated Root Directory Structure (After Cleanup)

```
JoustMania/
├── piparty_grpc.py          # New gRPC orchestrator (MAIN ENTRY POINT)
├── grpc_clients.py          # gRPC client library
├── webui.py                 # Web interface
├── update.py                # System updates
├── conftest.py              # pytest configuration
├── __init__.py              # Package init
│
├── jm_dbus.py               # D-Bus integration (Linux)
├── win_jm_dbus.py           # D-Bus integration (Windows)
│
├── audio_tool.py            # Audio testing utility
├── clear_devices.py         # Device cleanup utility
├── manualpair.py            # Manual pairing tool
│
├── core/                    # Core infrastructure
│   ├── controller_state.py
│   ├── controller_process.py
│   ├── common.py
│   └── base_logger.py       # MOVED from root
│
├── utils/                   # Utilities
│   ├── pair.py
│   ├── colors.py
│   ├── piaudio.py
│   ├── controller_util.py   # MOVED from root
│   └── playwav.py          # MOVED from root
│
├── services/                # Microservices
│   ├── settings/
│   ├── controller_manager/
│   ├── game_coordinator/
│   ├── menu/
│   └── supervisor/
│
├── testing/                 # Tests
│   ├── joust_test.py       # MOVED from root
│   ├── pacemanager_test.py # MOVED from root
│   └── test_orchestrator.py # MOVED from root
│
└── legacy/                  # Archived code
    └── piparty.py          # Old Queue-based orchestrator
```

---

## Files to Update After Cleanup

### 1. **joust.py** (Main entry point)
- Check if it imports `piparty.py`
- Update to use `piparty_grpc.py` instead

### 2. **setup.sh**
- Check if it references any removed files
- Update paths if needed

### 3. **systemd service files** (if any)
- Update ExecStart paths
- Update to run `piparty_grpc.py` instead of `piparty.py`

### 4. **README.md**
- Update documentation to reflect new structure
- Update startup instructions

### 5. **Import statements across codebase**
```bash
# Find files that import from root instead of core/utils
grep -r "^import controller_state" .
grep -r "^import common" .
grep -r "^import colors" .
grep -r "^import pair" .
grep -r "^import piaudio" .

# Should be:
# from core import controller_state, common
# from utils import colors, pair, piaudio
```

---

## Verification Steps

After cleanup, verify:

1. **gRPC Services Start:**
   ```bash
   docker-compose up --build
   ```

2. **Tests Still Pass:**
   ```bash
   cd testing/
   pytest
   ```

3. **Web UI Works:**
   ```bash
   python webui.py
   ```

4. **No Import Errors:**
   ```bash
   python -c "from core import common, controller_state"
   python -c "from utils import colors, pair, piaudio"
   python -c "import grpc_clients, piparty_grpc"
   ```

---

## Risk Assessment

### Low Risk (Safe to do now):
- ✅ Remove files already in services/, core/, utils/
- ✅ Move tests to testing/
- ✅ Move utilities to utils/

### Medium Risk (Test thoroughly):
- ⚠️ Archive piparty.py (check what still uses it)
- ⚠️ Update imports across codebase

### High Risk (Investigate first):
- ❌ Don't remove files until confirming they're unused
- ❌ Don't modify entry points without testing

---

## Recommended Execution Order

1. **Create backup** ✅
2. **Remove confirmed duplicates** (Phase 1) ✅
3. **Run tests to verify** ✅
4. **Organize utils/tests** (Phase 3-4) ✅
5. **Check joust.py and update if needed** ⚠️
6. **Archive piparty.py** (Phase 2) ⚠️
7. **Test full system** ✅
8. **Update documentation** ✅
9. **Commit cleanup** ✅

---

## Summary

**Total files analyzed:** 30
**Can remove immediately:** 10 (duplicates in services/, core/, utils/)
**Should archive:** 1 (piparty.py - old orchestrator)
**Should reorganize:** 5 (move to utils/ or testing/)
**Keep in root:** 14 (entry points, tools, system integration, game utilities)

**Expected root directory reduction:** ~50% fewer Python files

**Next steps:** Execute Phase 1 (safe removals) first, verify system works, then proceed with remaining phases.

---

# Bash Scripts Cleanup Analysis

**Date:** 2026-01-10
**Context:** After implementing cloud-native microservices architecture with Docker Compose, many bash scripts in the root directory are no longer relevant or need reorganization.

---

## Analysis of Root Bash Scripts

**Total Scripts Found:** 13

### ❌ ARCHIVE - Access Point Scripts (Not Needed for Microservices)

These scripts create/manage WiFi hotspot functionality for standalone Pi deployments:

1. **enable_ap.sh**
   - Creates WiFi hotspot "JoustMania" with NetworkManager
   - Sets up dnsmasq for http://joust.mania DNS redirect
   - **Purpose:** Standalone Pi without existing WiFi
   - **Microservice relevance:** ❌ Not needed - Docker/Kubernetes handle networking
   - **Action:** ARCHIVE to `legacy/`

2. **disable_ap.sh**
   - Removes WiFi hotspot configuration
   - Cleans up dnsmasq configuration
   - **Purpose:** Revert to normal WiFi
   - **Microservice relevance:** ❌ Not needed
   - **Action:** ARCHIVE to `legacy/`

**Verdict:** Only relevant if running JoustMania as standalone WiFi hotspot at events. For cloud-native deployments, networking is handled by infrastructure layer (Docker networks, Kubernetes ingress). If needed in future, should be a separate system service, not part of application stack.

---

### ❌ ARCHIVE - Legacy Launchers (Replaced by Docker)

These scripts launch the old Queue-based monolithic architecture:

3. **joust.sh**
   - Launches monolithic `piparty.py` with OpenTelemetry instrumentation
   - Starts OTel Collector in Docker container
   - Sets PYTHONPATH for PS Move API
   - **Purpose:** Main entry point for legacy architecture
   - **Microservice relevance:** ❌ Replaced by `docker-compose up`
   - **Action:** ARCHIVE to `legacy/`

4. **webui.sh**
   - Launches standalone Flask web UI for debugging
   - Runs legacy `webui.py` directly
   - **Purpose:** Debug web UI without full system
   - **Microservice relevance:** ❌ Web UI now containerized in `services/webui`
   - **Action:** ARCHIVE to `legacy/`

5. **kill_processes.sh**
   - Stops supervisor-managed piparty processes
   - Uses `supervisorctl` and `kill -9`
   - **Purpose:** Stop legacy processes for development
   - **Microservice relevance:** ❌ Replaced by `docker-compose down`
   - **Action:** ARCHIVE to `legacy/`

**Verdict:** All replaced by Docker Compose commands. Legacy orchestration no longer used.

---

### ⚠️ REFACTOR - Setup Script (Partially Relevant)

6. **setup.sh** (160 lines)
   - **What it does:**
     - Installs system dependencies (Python, Bluetooth, audio, Docker)
     - Compiles PS Move API from source
     - Sets up Python virtualenv with uv workspace
     - Configures supervisor for auto-start
     - Disables internal Bluetooth (Pi 4/5)
     - Configures Bluetooth pairing settings

   - **Still needed:**
     - ✅ Hardware dependencies (PS Move API, Bluetooth, USB drivers)
     - ✅ Docker installation
     - ✅ Audio system configuration

   - **No longer needed:**
     - ❌ Virtualenv/uv workspace (replaced by Docker containers)
     - ❌ Supervisor configuration (replaced by docker-compose)

   - **Recommendation:** Refactor into separate scripts:
     - `scripts/setup/setup_host.sh` - Host-level dependencies (Bluetooth, USB, audio, Docker)
     - `scripts/setup/build_psmoveapi.sh` - PS Move API compilation (may be needed in ControllerManager Dockerfile)

   - **Action:** REFACTOR and move to `scripts/setup/`

---

### ✅ KEEP - Testing Scripts (Still Useful)

7. **run_tests.sh**
   - Runs pytest for state-based architecture unit tests
   - Runs performance benchmarks
   - Color-coded output with detection for Pi vs dev machine
   - **Purpose:** Automated test runner
   - **Microservice relevance:** ✅ Still useful for local development
   - **Action:** MOVE to `scripts/testing/`

8. **controller_util_test.sh**
   - Launches controller utility for hardware testing
   - Sets PYTHONPATH for PS Move API
   - **Purpose:** Debug controller hardware
   - **Microservice relevance:** ⚠️ Potentially useful for debugging
   - **Action:** MOVE to `scripts/testing/` (if still needed)

9. **color_tests/pythonpath.sh**
   - Sets PYTHONPATH for PS Move API in color testing
   - **Purpose:** Environment setup for color tests
   - **Microservice relevance:** ✅ Useful for testing
   - **Action:** KEEP in `color_tests/` or move entire folder to `scripts/testing/color_tests/`

**Verdict:** Testing utilities are still valuable for local development and hardware debugging.

---

### ✅ KEEP - Hardware Configuration Scripts (Pi-Specific)

These are hardware-level utilities needed when running on Raspberry Pi, even with Docker:

10. **reset_bluetooth_connections.sh**
    - Runs `clear_devices.py` to clear Bluetooth pairings
    - Reboots system
    - **Purpose:** Fix controller pairing issues
    - **Microservice relevance:** ✅ Still needed for Pi hardware debugging
    - **Action:** MOVE to `scripts/hardware/`

11. **disable_internal_bluetooth.sh**
    - Disables on-board Bluetooth on Pi 4/5
    - Modifies `/boot/config.txt` or `/boot/firmware/config.txt`
    - **Purpose:** Use only external USB Bluetooth dongles (better range)
    - **Microservice relevance:** ⚠️ Functionality duplicated in `setup.sh`
    - **Action:** ARCHIVE (duplicate) - Already handled by setup.sh

12. **update_asound.sh**
    - Detects audio hardware (Pi 4 headphones vs Pi 5 USB audio)
    - Configures ALSA `/etc/asound.conf` for correct audio output
    - **Purpose:** Audio configuration for different Pi models
    - **Microservice relevance:** ✅ Still needed for Pi hardware
    - **Action:** MOVE to `scripts/hardware/`

13. **update_permissions.sh**
    - Fixes file ownership: `chown -R pi:pi .`
    - **Purpose:** Fix permission issues
    - **Microservice relevance:** ⚠️ Hardcoded to "pi" user - needs fix
    - **Recommendation:** Update to use `$USER` instead of hardcoded "pi"
    - **Action:** FIX and move to `scripts/hardware/`

**Verdict:** Hardware utilities are still needed for Pi deployments, but should be organized in `scripts/hardware/`.

---

## Bash Scripts Cleanup Strategy

### Phase 6: Archive Legacy Bash Scripts

```bash
# Create legacy directory if not exists
mkdir -p legacy

# Archive access point scripts
mv enable_ap.sh legacy/
mv disable_ap.sh legacy/

# Archive legacy launchers
mv joust.sh legacy/
mv webui.sh legacy/
mv kill_processes.sh legacy/

# Archive duplicate Bluetooth script
mv disable_internal_bluetooth.sh legacy/
```

**Impact:** None - These scripts are for legacy deployment model

---

### Phase 7: Organize Hardware Scripts

```bash
# Create scripts directory structure
mkdir -p scripts/hardware

# Move hardware configuration scripts
mv reset_bluetooth_connections.sh scripts/hardware/
mv update_asound.sh scripts/hardware/
mv update_permissions.sh scripts/hardware/

# Fix hardcoded username in update_permissions.sh
sed -i 's/chown -R pi:pi/chown -R $USER:$USER/g' scripts/hardware/update_permissions.sh
```

**Impact:** Low - Just organizational, scripts still work

---

### Phase 8: Organize Testing Scripts

```bash
# Create testing scripts directory
mkdir -p scripts/testing

# Move test runners
mv run_tests.sh scripts/testing/

# Optional: move controller utility test if still needed
mv controller_util_test.sh scripts/testing/

# Optional: move color tests
mv color_tests scripts/testing/
```

**Impact:** Low - May need to update paths in scripts

---

### Phase 9: Refactor Setup Script

```bash
# Create setup directory
mkdir -p scripts/setup

# Split setup.sh into:
# 1. scripts/setup/setup_host.sh - Host dependencies
# 2. scripts/setup/build_psmoveapi.sh - PS Move API compilation

# Keep original for now until refactored
cp setup.sh scripts/setup/setup_original.sh
```

**Action:** Manual refactoring needed to split into modular scripts

---

### Phase 10: Create Docker Helper Scripts (Optional)

```bash
# Create docker scripts directory
mkdir -p scripts/docker

# Create helper scripts
cat > scripts/docker/build.sh << 'EOF'
#!/bin/bash
docker-compose build "$@"
EOF

cat > scripts/docker/start.sh << 'EOF'
#!/bin/bash
docker-compose up "$@"
EOF

cat > scripts/docker/stop.sh << 'EOF'
#!/bin/bash
docker-compose down "$@"
EOF

chmod +x scripts/docker/*.sh
```

**Impact:** None - New convenience scripts

---

## Proposed Directory Structure for Scripts

```
JoustMania/
├── scripts/
│   ├── hardware/              # Pi-specific hardware utilities
│   │   ├── reset_bluetooth.sh
│   │   ├── update_asound.sh
│   │   └── update_permissions.sh (FIXED: $USER instead of pi)
│   │
│   ├── setup/                 # Installation scripts
│   │   ├── setup_host.sh      # Host dependencies (refactored)
│   │   └── build_psmoveapi.sh # PS Move API compilation (refactored)
│   │
│   ├── testing/               # Test utilities
│   │   ├── run_tests.sh
│   │   ├── controller_util_test.sh (optional)
│   │   └── color_tests/
│   │       └── pythonpath.sh
│   │
│   └── docker/                # Docker helper scripts (new)
│       ├── build.sh
│       ├── start.sh
│       └── stop.sh
│
├── legacy/                    # Archived scripts
│   ├── enable_ap.sh
│   ├── disable_ap.sh
│   ├── joust.sh
│   ├── webui.sh
│   ├── kill_processes.sh
│   └── disable_internal_bluetooth.sh (duplicate)
│
└── setup.sh                   # Keep original for now (until refactored)
```

---

## Script-by-Script Summary

| Script | Relevant? | Action | Destination |
|--------|-----------|--------|-------------|
| **enable_ap.sh** | ❌ No | Archive | `legacy/` |
| **disable_ap.sh** | ❌ No | Archive | `legacy/` |
| **joust.sh** | ❌ No | Archive (replaced by docker-compose) | `legacy/` |
| **webui.sh** | ❌ No | Archive (webui now containerized) | `legacy/` |
| **kill_processes.sh** | ❌ No | Archive (replaced by docker-compose down) | `legacy/` |
| **setup.sh** | ⚠️ Partial | Refactor into modular scripts | `scripts/setup/` |
| **run_tests.sh** | ✅ Yes | Move | `scripts/testing/` |
| **controller_util_test.sh** | ⚠️ Maybe | Move (if still useful) | `scripts/testing/` |
| **reset_bluetooth_connections.sh** | ✅ Yes | Move | `scripts/hardware/` |
| **disable_internal_bluetooth.sh** | ❌ Duplicate | Archive | `legacy/` |
| **update_asound.sh** | ✅ Yes | Move | `scripts/hardware/` |
| **update_permissions.sh** | ⚠️ Needs fix | Fix and move | `scripts/hardware/` |
| **color_tests/pythonpath.sh** | ✅ Yes | Keep or move folder | `scripts/testing/color_tests/` |

---

## Bash Scripts Cleanup Summary

**Total bash scripts analyzed:** 13

**Archive to legacy/ (not needed for microservices):** 6
- Access point scripts (2)
- Legacy launchers (3)
- Duplicate Bluetooth disable (1)

**Reorganize to scripts/** (still useful):** 6
- Hardware utilities (3)
- Testing scripts (3)

**Refactor (partial relevance):** 1
- setup.sh → Split into modular scripts

**Expected impact:**
- ✅ Cleaner root directory
- ✅ Better organization
- ✅ Clear separation: microservices vs hardware vs legacy
- ✅ Easier maintenance

---

## Verification After Bash Script Cleanup

1. **Test hardware scripts still work:**
   ```bash
   sudo scripts/hardware/reset_bluetooth.sh
   sudo scripts/hardware/update_asound.sh
   ```

2. **Test test runners:**
   ```bash
   scripts/testing/run_tests.sh
   ```

3. **Verify Docker workflows:**
   ```bash
   docker-compose up --build
   docker-compose down
   ```

4. **Check nothing references archived scripts:**
   ```bash
   grep -r "enable_ap.sh" .
   grep -r "joust.sh" .
   grep -r "webui.sh" .
   ```

---

## Overall Cleanup Summary (Python + Bash)

**Total Python files:** 30
- Remove: 10 (duplicates)
- Archive: 1 (piparty.py)
- Reorganize: 5
- Keep: 14

**Total Bash scripts:** 13
- Archive: 6 (legacy/not needed)
- Reorganize: 6 (scripts/)
- Refactor: 1 (setup.sh)

**Total root directory reduction:** ~60% fewer scripts in root

**Key benefits:**
- ✅ Clear separation of concerns (microservices/hardware/legacy)
- ✅ Better organization and discoverability
- ✅ Easier to understand what's relevant for cloud-native deployment
- ✅ Preserved hardware utilities for Pi deployments
- ✅ Archived legacy for reference without clutter
