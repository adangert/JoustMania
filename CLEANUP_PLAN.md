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
