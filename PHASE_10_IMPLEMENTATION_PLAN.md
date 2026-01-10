# Phase 10 Implementation Plan - Bash Scripts Cleanup & Organization

**Date:** 2026-01-10
**Status:** 📋 Planning
**Goal:** Organize bash scripts into proper directory structure for cloud-native architecture

---

## Current State Analysis

### Root Directory Scripts (12 files)

**Legacy Launchers (3) - To Archive:**
- `joust.sh` - Legacy launcher (replaced by docker-compose)
- `webui.sh` - Web UI launcher (replaced by docker-compose)
- `kill_processes.sh` - Process killer (replaced by docker-compose down)

**Access Point Scripts (2) - To Archive:**
- `enable_ap.sh` - WiFi access point setup (not needed for microservices)
- `disable_ap.sh` - WiFi access point teardown (not needed for microservices)

**Bluetooth Scripts (2) - One Duplicate:**
- `disable_internal_bluetooth.sh` - Duplicate of setup.sh functionality (ARCHIVE)
- `reset_bluetooth_connections.sh` - Hardware utility (KEEP, move to scripts/hardware/)

**Hardware Scripts (2) - To Organize:**
- `update_asound.sh` - ALSA audio configuration (move to scripts/hardware/)
- `update_permissions.sh` - Device permissions (move to scripts/hardware/, needs fix)

**Testing Scripts (2) - To Organize:**
- `run_tests.sh` - Test runner (move to scripts/testing/)
- `controller_util_test.sh` - Controller utility tests (move to scripts/testing/)

**Setup Script (1) - To Refactor:**
- `setup.sh` - Monolithic setup (split into modular scripts)

---

## Target Directory Structure

```
JoustMania/
├── scripts/
│   ├── hardware/           # Hardware configuration scripts
│   │   ├── reset_bluetooth_connections.sh
│   │   ├── update_asound.sh
│   │   └── update_permissions.sh
│   ├── testing/            # Testing scripts
│   │   ├── run_tests.sh
│   │   └── controller_util_test.sh
│   ├── setup/              # Modular setup scripts
│   │   ├── setup_host.sh        # Host system setup
│   │   └── build_psmoveapi.sh   # PS Move API build
│   └── docker/             # Docker helper scripts
│       ├── build.sh             # Build all images
│       ├── start.sh             # Start stack
│       └── stop.sh              # Stop and cleanup
├── legacy/
│   └── scripts/            # Archived legacy scripts
│       ├── joust.sh
│       ├── webui.sh
│       ├── kill_processes.sh
│       ├── enable_ap.sh
│       ├── disable_ap.sh
│       └── disable_internal_bluetooth.sh
└── setup.sh                # Thin wrapper calling scripts/setup/*
```

---

## Implementation Tasks

### Task 1: Create Directory Structure

**Create directories:**
```bash
mkdir -p scripts/hardware
mkdir -p scripts/testing
mkdir -p scripts/setup
mkdir -p scripts/docker
mkdir -p legacy/scripts
```

**Commit:** `feat: Create scripts directory structure for Phase 10`

---

### Task 2: Archive Access Point Scripts

**Files to archive:**
- `enable_ap.sh` → `legacy/scripts/enable_ap.sh`
- `disable_ap.sh` → `legacy/scripts/disable_ap.sh`

**Reason:** WiFi access point scripts not needed for cloud-native microservices deployment

**Commands:**
```bash
git mv enable_ap.sh legacy/scripts/
git mv disable_ap.sh legacy/scripts/
git commit -m "chore: Archive access point scripts to legacy"
```

---

### Task 3: Archive Legacy Launcher Scripts

**Files to archive:**
- `joust.sh` → `legacy/scripts/joust.sh`
- `webui.sh` → `legacy/scripts/webui.sh`
- `kill_processes.sh` → `legacy/scripts/kill_processes.sh`

**Reason:** Replaced by `docker-compose up/down`

**Commands:**
```bash
git mv joust.sh legacy/scripts/
git mv webui.sh legacy/scripts/
git mv kill_processes.sh legacy/scripts/
git commit -m "chore: Archive legacy launcher scripts (replaced by docker-compose)"
```

---

### Task 4: Archive Duplicate Bluetooth Script

**File to archive:**
- `disable_internal_bluetooth.sh` → `legacy/scripts/disable_internal_bluetooth.sh`

**Reason:** Functionality duplicated in setup.sh

**Commands:**
```bash
git mv disable_internal_bluetooth.sh legacy/scripts/
git commit -m "chore: Archive duplicate Bluetooth script"
```

---

### Task 5: Move Hardware Scripts

**Files to move:**
- `reset_bluetooth_connections.sh` → `scripts/hardware/reset_bluetooth_connections.sh`
- `update_asound.sh` → `scripts/hardware/update_asound.sh`
- `update_permissions.sh` → `scripts/hardware/update_permissions.sh`

**Commands:**
```bash
git mv reset_bluetooth_connections.sh scripts/hardware/
git mv update_asound.sh scripts/hardware/
git mv update_permissions.sh scripts/hardware/
git commit -m "feat: Move hardware scripts to scripts/hardware/"
```

---

### Task 6: Fix update_permissions.sh

**Issue:** Hardcoded username "pi" in script

**Fix:** Change to `$USER` variable

**File:** `scripts/hardware/update_permissions.sh`

**Changes:**
```bash
# Before:
chown pi:pi /path/to/file

# After:
chown $USER:$USER /path/to/file
```

**Commit:** `fix: Replace hardcoded 'pi' username with $USER in update_permissions.sh`

---

### Task 7: Move Testing Scripts

**Files to move:**
- `run_tests.sh` → `scripts/testing/run_tests.sh`
- `controller_util_test.sh` → `scripts/testing/controller_util_test.sh`

**Note:** Also move `color_tests/` directory if it exists

**Commands:**
```bash
git mv run_tests.sh scripts/testing/
git mv controller_util_test.sh scripts/testing/
# If color_tests/ exists:
# git mv color_tests/ scripts/testing/
git commit -m "feat: Move testing scripts to scripts/testing/"
```

---

### Task 8: Refactor setup.sh

**Goal:** Split monolithic setup.sh into modular scripts

**New scripts to create:**

1. **`scripts/setup/setup_host.sh`**
   - System dependencies (apt packages)
   - USB permissions
   - Bluetooth configuration
   - Audio configuration
   - System configuration

2. **`scripts/setup/build_psmoveapi.sh`**
   - Clone PS Move API
   - Build from source
   - Install to system

3. **`setup.sh`** (wrapper)
   - Thin wrapper that calls both scripts in order
   - Maintains backward compatibility

**Commit:** `refactor: Split setup.sh into modular scripts in scripts/setup/`

---

### Task 9: Create Docker Helper Scripts

**Optional but useful for developers**

1. **`scripts/docker/build.sh`**
```bash
#!/bin/bash
# Build all Docker images
docker-compose build --parallel
```

2. **`scripts/docker/start.sh`**
```bash
#!/bin/bash
# Start the full stack
docker-compose up -d
echo "Stack started. Jaeger UI: http://localhost:16686"
echo "Web UI: http://localhost:80"
```

3. **`scripts/docker/stop.sh`**
```bash
#!/bin/bash
# Stop and cleanup
docker-compose down
```

4. **`scripts/docker/logs.sh`**
```bash
#!/bin/bash
# Follow logs for a specific service
SERVICE=${1:-"all"}
if [ "$SERVICE" = "all" ]; then
  docker-compose logs -f
else
  docker-compose logs -f "$SERVICE"
fi
```

**Commit:** `feat: Add Docker helper scripts in scripts/docker/`

---

### Task 10: Update Script References

**Files that may reference moved scripts:**
- `README.md`
- `docs/*.md`
- `services/*/README.md`
- GitHub workflows (if any)
- Any setup instructions

**Search for references:**
```bash
grep -r "\.sh" *.md docs/ 2>/dev/null
```

**Update paths accordingly**

**Commit:** `docs: Update script paths in documentation`

---

### Task 11: Verify Scripts Work

**Test each moved script:**
```bash
# Hardware scripts
scripts/hardware/reset_bluetooth_connections.sh
scripts/hardware/update_asound.sh
scripts/hardware/update_permissions.sh

# Testing scripts
scripts/testing/run_tests.sh
scripts/testing/controller_util_test.sh

# Setup scripts
scripts/setup/setup_host.sh
scripts/setup/build_psmoveapi.sh
setup.sh  # Wrapper

# Docker scripts
scripts/docker/build.sh
scripts/docker/start.sh
scripts/docker/stop.sh
scripts/docker/logs.sh
```

**Commit:** `test: Verify all reorganized scripts work correctly`

---

### Task 12: Create README for scripts/

**Create `scripts/README.md`:**

```markdown
# JoustMania Scripts

Organized scripts for JoustMania cloud-native deployment.

## Directory Structure

- **hardware/** - Hardware configuration scripts (Bluetooth, audio, permissions)
- **testing/** - Test execution scripts
- **setup/** - Modular setup scripts for host system and dependencies
- **docker/** - Docker helper scripts for development

## Hardware Scripts

### reset_bluetooth_connections.sh
Resets Bluetooth connections and clears paired devices.

### update_asound.sh
Configures ALSA audio settings for optimal PS Move controller performance.

### update_permissions.sh
Sets up device permissions for USB and Bluetooth access.

## Testing Scripts

### run_tests.sh
Executes the full test suite (unit + integration tests).

### controller_util_test.sh
Tests controller utility functions.

## Setup Scripts

### setup_host.sh
Installs system dependencies and configures the host environment.

### build_psmoveapi.sh
Builds and installs PS Move API from source.

## Docker Scripts

### build.sh
Builds all Docker images for the microservices stack.

### start.sh
Starts the full Docker Compose stack.

### stop.sh
Stops and cleans up the Docker stack.

### logs.sh [service]
Follows logs for all services or a specific service.

## Legacy Scripts

Archived legacy scripts can be found in `../legacy/scripts/`.
These are preserved for reference but are no longer used in the cloud-native architecture.
```

**Commit:** `docs: Add README for scripts directory`

---

### Task 13: Create Completion Document

**Create `PHASE_10_COMPLETED.md`:**

Document all completed tasks, before/after comparison, metrics, and verification results.

**Commit:** `docs: Add Phase 10 completion summary`

---

## Success Criteria

- ✅ All bash scripts organized into proper directories
- ✅ Legacy scripts archived (not deleted)
- ✅ Hardware scripts in scripts/hardware/
- ✅ Testing scripts in scripts/testing/
- ✅ Setup scripts modularized in scripts/setup/
- ✅ Docker helper scripts created in scripts/docker/
- ✅ update_permissions.sh fixed (no hardcoded username)
- ✅ All scripts verified to work after move
- ✅ Documentation updated with new paths
- ✅ Root directory cleaner (12 → 1 shell scripts)
- ✅ Backward compatibility maintained (setup.sh wrapper)

---

## Metrics

### Before Phase 10
- Shell scripts in root: 12
- Organization: None (all in root)
- Setup script: Monolithic

### After Phase 10
- Shell scripts in root: 1 (setup.sh wrapper)
- Organization: 4 directories (hardware, testing, setup, docker)
- Legacy scripts: Archived to legacy/scripts/
- Setup script: Modular (2 scripts + wrapper)
- Docker helpers: 4 new convenience scripts

---

## Risks & Mitigations

**Risk 1:** Scripts break after moving
- **Mitigation:** Test each script after move

**Risk 2:** External tools/docs reference old paths
- **Mitigation:** Search codebase for script references, update all

**Risk 3:** Users' muscle memory (e.g., `./run_tests.sh`)
- **Mitigation:** Add note in commit messages, update README

**Risk 4:** Broken relative paths in scripts
- **Mitigation:** Review each script for relative paths, update if needed

---

## Git Commits

All changes in atomic commits:
1. Create directory structure
2. Archive access point scripts
3. Archive legacy launchers
4. Archive duplicate Bluetooth script
5. Move hardware scripts
6. Fix update_permissions.sh
7. Move testing scripts
8. Refactor setup.sh
9. Create Docker helper scripts
10. Update documentation
11. Verify scripts
12. Add scripts/README.md
13. Create completion summary

**Total:** 13 commits for clean git history

---

## Next Steps

After Phase 10 completion:
- Execute Phase 11: Documentation overhaul
- Execute Phase 12: Dependency updates
- Execute Phase 13: Game modes refactoring
