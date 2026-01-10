# JoustMania Restructuring Plan

**Date:** 2026-01-09
**Purpose:** Organize microservices into clean folder structure with dependency management
**Status:** Implementation Plan

---

## Current State

### File Structure
```
JoustMania/
├── controller_manager.py        (Phase 1 - microservice)
├── game_coordinator.py          (Phase 2 - microservice)
├── settings_process.py          (Phase 3 - microservice)
├── process_supervisor.py        (Phase 4 - manager)
├── controller_state.py          (shared infrastructure)
├── controller_process.py        (controller tracking logic)
├── piparty.py                   (main entry point, monolith)
├── piaudio.py                   (audio utilities)
├── webui.py                     (web interface)
├── common.py, colors.py, etc.   (shared utilities)
├── games/                       (game implementations)
├── testing/                     (tests)
└── setup.sh                     (dependency installation)
```

### Dependency Management
- **Current**: All dependencies installed via setup.sh into virtualenv
- **Problem**: No requirements.txt, hard to reproduce environment
- **Problem**: No version pinning
- **Problem**: System packages mixed with Python packages

---

## Proposed Structure

### New Folder Layout

```
JoustMania/
├── services/                    # Microservices directory
│   ├── __init__.py
│   ├── controller_manager/
│   │   ├── __init__.py
│   │   └── process.py
│   ├── game_coordinator/
│   │   ├── __init__.py
│   │   └── process.py
│   ├── settings/
│   │   ├── __init__.py
│   │   └── process.py
│   └── supervisor/
│       ├── __init__.py
│       └── manager.py
│
├── core/                        # Core infrastructure
│   ├── __init__.py
│   ├── controller_state.py      # State-based architecture
│   ├── controller_process.py    # Controller tracking
│   └── common.py                # Shared types/enums
│
├── audio/                       # Audio system (existing)
│   └── ... (existing files)
│
├── games/                       # Game implementations (existing)
│   └── ... (existing files)
│
├── web/                         # Web UI
│   ├── __init__.py
│   ├── webui.py
│   ├── static/                  # Move from root
│   └── templates/               # Move from root
│
├── utils/                       # Utilities
│   ├── __init__.py
│   ├── colors.py
│   ├── piaudio.py
│   └── pair.py
│
├── testing/                     # Tests (existing)
│   └── ... (existing files)
│
├── piparty.py                   # Main entry point
├── joust.py                     # Service starter
├── pyproject.toml               # Python dependencies (uv)
├── requirements.txt             # Generated from pyproject.toml
├── setup.sh                     # System dependencies only
└── README.md
```

---

## Dependency Management

### Use `uv` for Python Dependency Management

**Why uv:**
- Fast dependency resolution
- Compatible with pip
- Generates lock files
- Works with pyproject.toml

### pyproject.toml

```toml
[project]
name = "joustmania"
version = "2.0.0"
description = "Multi-player gaming system using PS Move controllers"
requires-python = ">=3.9,<3.13"
dependencies = [
    "flask>=2.0.0",
    "Flask-WTF>=1.0.0",
    "pyalsaaudio>=0.9.0",
    "pydub>=0.25.0",
    "pyyaml>=6.0",
    "dbus-python>=1.2.0",
    "python-dotenv>=0.19.0",
    "pygame>=2.0.0",
    "opentelemetry-distro>=0.43b0",
    "opentelemetry-exporter-otlp>=1.22.0",
    "audioop-lts>=0.2.0",  # For Python >= 3.13
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
]

[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[tool.uv]
dev-dependencies = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
]
```

### Updated setup.sh

Only install system dependencies:
- Remove Python package installation
- Keep system packages (bluez, alsa, etc.)
- Keep psmoveapi build
- Add: `uv sync` to install Python deps

---

## Migration Steps

### Step 1: Create New Directory Structure

```bash
mkdir -p services/{controller_manager,game_coordinator,settings,supervisor}
mkdir -p core
mkdir -p web
mkdir -p utils
```

### Step 2: Move Microservices

```bash
# Controller Manager
mv controller_manager.py services/controller_manager/process.py
echo "from .process import *" > services/controller_manager/__init__.py

# Game Coordinator
mv game_coordinator.py services/game_coordinator/process.py
echo "from .process import *" > services/game_coordinator/__init__.py

# Settings
mv settings_process.py services/settings/process.py
echo "from .process import *" > services/settings/__init__.py

# Supervisor
mv process_supervisor.py services/supervisor/manager.py
echo "from .manager import *" > services/supervisor/__init__.py
```

### Step 3: Move Core Infrastructure

```bash
mv controller_state.py core/
mv controller_process.py core/
cp common.py core/  # Keep copy in root for backward compat initially
```

### Step 4: Move Utilities

```bash
mv colors.py utils/
mv piaudio.py utils/
mv pair.py utils/
mv win_pair.py utils/
```

### Step 5: Move Web

```bash
mv webui.py web/
mv static web/
mv templates web/
```

### Step 6: Update Imports

Update piparty.py:
```python
# Old
import controller_manager
import game_coordinator
import settings_process
import process_supervisor

# New
from services import controller_manager
from services import game_coordinator
from services import settings
from services import supervisor as process_supervisor
from core import controller_state, controller_process
from utils import colors, piaudio, pair
```

### Step 7: Create pyproject.toml and Install uv

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create pyproject.toml (as shown above)

# Sync dependencies
uv sync

# Generate requirements.txt for compatibility
uv pip compile pyproject.toml -o requirements.txt
```

### Step 8: Update setup.sh

Remove Python package installation, add:
```bash
# Install uv if not present
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Sync Python dependencies
cd $HOMEDIR/JoustMania
uv sync --python $PYTHON
```

---

## Legacy Code to Remove

### Files to Delete (Replaced by Microservices)

**None yet** - Keep legacy paths for now until fully tested

### Feature Flags to Eventually Remove

Once tested with hardware:
```python
# In piparty.py
self.use_state_based_tracking = True  # Eventually remove flag, make default
self.use_controller_manager_process = True  # Remove flag
self.use_game_coordinator_process = True  # Remove flag
self.use_settings_process = True  # Remove flag
self.use_process_supervisor = True  # Remove flag
```

### Legacy Methods to Remove

After full migration, these can be removed from piparty.py:
- `track_move()` - replaced by state-based tracking
- `start_game()` - replaced by GameCoordinator
- Manual process startup code - replaced by Processor
- Manual settings management - replaced by Settings process

---

## Benefits

### Better Organization
- ✅ Clear separation of microservices
- ✅ Easier to navigate codebase
- ✅ Logical grouping of related code

### Dependency Management
- ✅ Explicit dependency declarations
- ✅ Version pinning
- ✅ Reproducible environments
- ✅ Faster dependency resolution with uv
- ✅ Lock file for exact versions

### Maintainability
- ✅ Each service is self-contained
- ✅ Clear import paths
- ✅ Easier to add new services
- ✅ Better for IDE navigation

### Deployment
- ✅ Easier to containerize individual services
- ✅ Clear dependency requirements
- ✅ Standard Python packaging

---

## Implementation Timeline

1. **Create directory structure** - 10 minutes
2. **Move files** - 20 minutes
3. **Update imports** - 30 minutes
4. **Create pyproject.toml** - 15 minutes
5. **Test imports** - 15 minutes
6. **Update setup.sh** - 15 minutes
7. **Test full installation** - 30 minutes

**Total:** ~2.5 hours

---

## Testing Strategy

### After Restructuring

1. **Syntax Check**: All Python files compile
2. **Import Check**: All imports resolve correctly
3. **Unit Tests**: Run existing test suite
4. **Integration Test**: Start all processes
5. **Hardware Test**: Test with real controllers (when available)

### Validation

```bash
# Check syntax
python3 -m py_compile piparty.py

# Check imports
python3 -c "from services import controller_manager, game_coordinator, settings, supervisor"

# Run tests
./run_tests.sh

# Start system (dry run)
python3 joust.py
```

---

## Rollback Plan

If restructuring causes issues:

1. **Git revert**: `git revert HEAD`
2. **Old structure preserved**: All old files still in repo history
3. **Feature flags**: Can disable new structure via flags

---

## Next Steps

1. Create directory structure
2. Move files
3. Create __init__.py files
4. Update imports in piparty.py
5. Create pyproject.toml
6. Install uv
7. Test
8. Update setup.sh
9. Commit

---

## Approval

**Design by:** Claude Sonnet 4.5
**Date:** 2026-01-09
**Status:** Ready for Implementation
