# Phase 9: Architecture Cleanup & Completion

**Date:** 2026-01-10
**Goal:** Complete cloud-native microservices architecture with proper organization
**Target:** 7-service architecture, clean directory structure, real games playable

---

## Architecture Decisions

### ✅ Confirmed Decisions

1. **Pairing:** ControllerManager service (privileged container with DBus + USB)
2. **Audio:** New AudioService (7th microservice, privileged for `/dev/snd/`)
3. **Colors:** Keep as shared library in `utils/colors.py` (no service needed)
4. **Games:** Move to `services/game_coordinator/games/` (domain logic owned by service)
5. **Platform:** Linux/Raspberry Pi only (delete Windows files)

### Final Architecture: 7 Microservices

| Service | Port | Privileged? | Purpose |
|---------|------|-------------|---------|
| Settings | 50051 | No | Settings management |
| ControllerManager | 50052 | **Yes** | PS Move I/O + Bluetooth pairing |
| GameCoordinator | 50053 | No | Game logic execution |
| Menu | 50054 | No | Menu UI + navigation |
| Supervisor | 50055 | No | Health monitoring |
| WebUI | 80 | No | Web interface |
| **Audio** ✅ NEW | 50056 | **Yes** | Audio playback + mixing |

**Privileged services (2):**
- ControllerManager - Bluetooth + USB hardware
- Audio - Audio device (`/dev/snd/`)

---

## Phase 9 Tasks

### Task 1: Archive Legacy Files ✅ LOW RISK

**Action:** Move old Queue-based implementations to `legacy/`

```bash
mkdir -p legacy

# Queue-based service implementations (replaced by gRPC)
mv piparty.py legacy/                # Old orchestrator (3000+ lines)
mv piparty_grpc.py legacy/           # gRPC orchestrator (not needed - Supervisor handles this)
mv controller_manager.py legacy/     # Old Queue version
mv game_coordinator.py legacy/       # Old Queue version
mv settings_process.py legacy/       # Old Queue version
mv process_supervisor.py legacy/     # Old Queue version
mv webui.py legacy/                  # Old Queue version (replaced by services/webui)
```

**Files moved:** 7
**Verification:** Services still run (they use `services/*` code)

---

### Task 2: Delete Duplicate & Windows Files ✅ LOW RISK

**Action:** Remove confirmed duplicates and Windows-specific code

```bash
# Duplicates (already in core/)
rm controller_state.py controller_process.py common.py base_logger.py

# Duplicates (already in utils/)
rm pair.py colors.py piaudio.py

# Windows-specific (not needed for Linux/Raspberry Pi)
rm win_jm_dbus.py win_pair.py

# Total removed: 10 files
```

**Verification:** No import errors (these exist in proper locations)

---

### Task 3: Create AudioService ⚠️ MEDIUM RISK

**Why needed:**
- Multiple containers can't share audio device (`/dev/snd/`)
- Need coordination between menu music and game music
- Priority-based mixing (game sounds interrupt menu music)

#### 3a. Create Audio Protobuf Schema

**Create:** `services/audio/audio.proto`

```protobuf
syntax = "proto3";

package joustmania.audio;

// Audio Service - Manages audio playback and mixing
service AudioService {
  // Play a sound effect (one-shot)
  rpc PlaySound(PlaySoundRequest) returns (PlaySoundResponse);

  // Play background music (looping)
  rpc PlayMusic(PlayMusicRequest) returns (PlayMusicResponse);

  // Stop music track
  rpc StopMusic(StopMusicRequest) returns (StopMusicResponse);

  // Change music tempo (real-time speed adjustment)
  rpc ChangeTempo(ChangeTempoRequest) returns (ChangeTempoResponse);

  // Set master volume
  rpc SetVolume(SetVolumeRequest) returns (SetVolumeResponse);

  // Get current playback status
  rpc GetStatus(GetStatusRequest) returns (GetStatusResponse);
}

// Audio priority levels
enum AudioPriority {
  LOW = 0;      // Menu music
  MEDIUM = 1;   // Game music
  HIGH = 2;     // Sound effects
  CRITICAL = 3; // Victory/death sounds
}

// Request/Response messages
message PlaySoundRequest {
  string file_path = 1;      // e.g. "audio/Joust/sounds/death.wav"
  float volume = 2;          // 0.0 to 1.0
  AudioPriority priority = 3;
}

message PlaySoundResponse {
  bool success = 1;
  string error = 2;
}

message PlayMusicRequest {
  string file_pattern = 1;   // e.g. "audio/Joust/music/*.wav" (glob pattern)
  bool loop = 2;
  float tempo = 3;           // 1.0 = normal speed, 1.5 = 50% faster
  AudioPriority priority = 4;
}

message PlayMusicResponse {
  string track_id = 1;       // UUID for this music track
  bool success = 2;
  string error = 3;
}

message StopMusicRequest {
  string track_id = 1;
}

message StopMusicResponse {
  bool success = 1;
  string error = 2;
}

message ChangeTempoRequest {
  string track_id = 1;
  float new_tempo = 2;       // New playback speed
  float transition_duration = 3;  // Seconds to smoothly transition
}

message ChangeTempoResponse {
  bool success = 1;
  string error = 2;
}

message SetVolumeRequest {
  float volume = 1;  // 0.0 to 1.0
}

message SetVolumeResponse {
  bool success = 1;
  string error = 2;
}

message GetStatusRequest {}

message GetStatusResponse {
  string current_track_id = 1;
  string current_track_file = 2;
  bool is_playing = 3;
  float volume = 4;
  float tempo = 5;
  int32 queued_sounds_count = 6;
  bool success = 7;
  string error = 8;
}
```

#### 3b. Generate Python Code

```bash
cd services/audio
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. audio.proto
# Fix imports in generated files
```

#### 3c. Implement Audio Server

**Create:** `services/audio/server.py`

Key responsibilities:
- Audio hardware management (ALSA/pygame)
- Priority-based audio queue
- Background music with tempo control
- Sound effect mixing
- OpenTelemetry instrumentation

**Create:** `services/audio/playback.py` (refactored from `utils/piaudio.py`)

#### 3d. Create Audio Dockerfile

**Create:** `services/audio/Dockerfile`

```dockerfile
FROM python:3.11-slim as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml /app/
COPY services/audio/pyproject.toml /app/services/audio/

RUN pip install --no-cache-dir uv
WORKDIR /app/services/audio
RUN uv pip install --system -e .

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --from=builder /app/pyproject.toml /app/
COPY services/audio/ /app/services/audio/
COPY audio/ /app/audio/

ENV PYTHONPATH=/app
ENV OTEL_SERVICE_NAME=audio-service
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
ENV OTEL_TRACES_EXPORTER=otlp
ENV OTEL_METRICS_EXPORTER=none
ENV OTEL_LOGS_EXPORTER=none

EXPOSE 50056

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:50056'); channel.channel_ready()" || exit 1

CMD ["python", "services/audio/server.py"]
```

#### 3e. Create pyproject.toml

**Create:** `services/audio/pyproject.toml`

```toml
[project]
name = "joustmania-audio"
version = "1.0.0"
description = "Audio microservice for JoustMania"
requires-python = ">=3.9,<3.13"
dependencies = [
    # Audio libraries
    "pygame>=2.5.0",
    "pyalsaaudio>=0.10.0",
    "numpy>=1.24.0",
    "scipy>=1.11.0",
    "pydub>=0.25.0",

    # gRPC
    "grpcio>=1.60.0",
    "grpcio-tools>=1.60.0",

    # OpenTelemetry
    "opentelemetry-distro>=0.43b0",
    "opentelemetry-exporter-otlp>=1.22.0",
    "opentelemetry-instrumentation-grpc>=0.43b0",
]

[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"
```

#### 3f. Add to docker-compose.yml

```yaml
  # Audio Service
  audio:
    build:
      context: .
      dockerfile: services/audio/Dockerfile
    container_name: joustmania-audio
    privileged: true  # Required for audio device access
    devices:
      - /dev/snd:/dev/snd  # Audio hardware
    volumes:
      - ./audio:/app/audio:ro  # Audio files (read-only)
    ports:
      - "50056:50056"
    environment:
      - OTEL_SERVICE_NAME=audio-service
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
    depends_on:
      otel-collector:
        condition: service_healthy
    networks:
      - joustmania
    restart: unless-stopped
```

**Verification:**
- Build succeeds
- Service starts
- Can play test sound via gRPC

---

### Task 4: Move Pairing to ControllerManager ⚠️ MEDIUM RISK

**Action:** ControllerManager owns Bluetooth pairing

#### 4a. Move Pairing Code

```bash
# Move pairing implementation
mv utils/pair.py services/controller_manager/pairing.py
mv jm_dbus.py services/controller_manager/bluetooth.py
```

#### 4b. Update ControllerManager Dockerfile

**Already has dbus dependencies** (from earlier fix), just verify:

```dockerfile
# Builder stage
RUN apt-get install -y --no-install-recommends \
    gcc \
    pkg-config \
    libbluetooth-dev \
    libusb-dev \
    libdbus-1-dev \    # ✓ Already there
    libglib2.0-dev \   # ✓ Already there
    && rm -rf /var/lib/apt/lists/*

# Runtime stage
RUN apt-get install -y --no-install-recommends \
    libbluetooth3 \
    libusb-1.0-0 \
    libdbus-1-3 \      # ✓ Already there
    libglib2.0-0 \     # ✓ Already there
    && rm -rf /var/lib/apt/lists/*
```

#### 4c. Update docker-compose.yml

**Add privileged mode + DBus:**

```yaml
  controller-manager:
    build:
      context: .
      dockerfile: services/controller_manager/Dockerfile
    container_name: joustmania-controller-manager
    privileged: true  # ✅ ADD: For Bluetooth pairing
    network_mode: host  # ✅ ADD: For Bluetooth
    volumes:
      - /var/run/dbus:/var/run/dbus  # ✅ ADD: DBus for BlueZ
    devices:
      - /dev/bus/usb:/dev/bus/usb  # Already have this
    environment:
      - DBUS_SYSTEM_BUS_ADDRESS=unix:path=/var/run/dbus/system_bus_socket  # ✅ ADD
      - OTEL_SERVICE_NAME=controller-manager-service
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
    depends_on:
      otel-collector:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - joustmania
    restart: unless-stopped
```

#### 4d. Add PairController RPC

**Update:** `services/controller_manager/controller_manager.proto`

```protobuf
service ControllerManagerService {
  // ... existing RPCs ...

  // Pair a new controller (when plugged via USB)
  rpc PairController(PairControllerRequest) returns (PairControllerResponse);
}

message PairControllerRequest {
  string serial = 1;  // Controller serial (optional, auto-detect if empty)
}

message PairControllerResponse {
  bool success = 1;
  string error = 2;
  string paired_serial = 3;  // Serial of paired controller
  string bluetooth_adapter = 4;  // Which hci adapter it was paired to
}
```

#### 4e. Implement Auto-Pairing

**Update:** `services/controller_manager/server.py`

Add background USB detection thread that calls pairing logic when USB controller detected.

**Verification:**
- Plug USB controller
- Press button on Move
- Controller auto-pairs
- Shows up in controller list

---

### Task 5: Move Games to GameCoordinator ⚠️ HIGH RISK

**Action:** Game logic belongs in GameCoordinator service

#### 5a. Create games/ Directory

```bash
mkdir -p services/game_coordinator/games
```

#### 5b. Move Game Files

```bash
# Move core game files
mv games/game.py services/game_coordinator/games/base.py
mv player.py services/game_coordinator/games/
mv pacemanager.py services/game_coordinator/games/

# Move selected game modes (simplest 3)
mv games/ffa.py services/game_coordinator/games/
mv games/joust_teams.py services/game_coordinator/games/
mv games/joust_random_teams.py services/game_coordinator/games/

# Create __init__.py
touch services/game_coordinator/games/__init__.py
```

#### 5c. Update Imports in Game Files

**In all moved game files:**

```python
# OLD
import pacemanager
import player
from games import game

# NEW
from games import base as game_base
from games import player
from games import pacemanager
```

#### 5d. Update GameCoordinator Server

**Update:** `services/game_coordinator/server.py`

Remove mock game loop, implement real game execution:

```python
# OLD (mock)
def _run_game_loop(self):
    """Run the game loop in background thread."""
    self.game_state = game_coordinator_pb2.GameState.RUNNING
    game_duration = 30
    elapsed = 0

    while self.game_running and elapsed < game_duration:
        time.sleep(1)
        elapsed += 1

# NEW (real games)
from games import ffa, joust_teams, joust_random_teams

def _run_game_loop(self):
    """Run the actual game."""
    with tracer.start_as_current_span("game_execution") as span:
        self.game_state = game_coordinator_pb2.GameState.RUNNING

        # Initialize game based on requested mode
        if self.game_name == "ffa":
            game_instance = ffa.FFA(self.players, self.settings)
        elif self.game_name == "joust_teams":
            game_instance = joust_teams.JoustTeams(self.players, self.settings)
        elif self.game_name == "joust_random_teams":
            game_instance = joust_random_teams.JoustRandomTeams(self.players, self.settings)
        else:
            logger.error(f"Unknown game mode: {self.game_name}")
            self.game_state = game_coordinator_pb2.GameState.FAILED
            return

        span.set_attribute("game.mode", self.game_name)

        try:
            # Run game loop
            game_instance.run()

            # Game finished
            winner = game_instance.get_winner()
            self._publish_event("game_over", {"winner": winner})

        except Exception as e:
            logger.error(f"Game execution error: {e}", exc_info=True)
            self.game_state = game_coordinator_pb2.GameState.FAILED
            self._publish_event("game_error", {"error": str(e)})

        finally:
            self.game_state = game_coordinator_pb2.GameState.STOPPED
            self.game_running = False
```

**Verification:**
- Start FFA game
- Game runs to completion (not mock)
- Winner determined correctly
- Traces show actual game logic

---

### Task 6: Reorganize Remaining Files ✅ LOW RISK

**Action:** Move tests and tools to proper directories

#### 6a. Create Directories

```bash
mkdir -p testing
mkdir -p tools
```

#### 6b. Move Test Files

```bash
# Move tests
mv joust_test.py testing/
mv pacemanager_test.py testing/
mv test_orchestrator.py testing/
mv games/ffa_test.py testing/

# Create __init__.py
touch testing/__init__.py

# Keep conftest.py in root (pytest needs it there)
```

#### 6c. Move Tools

```bash
# Move standalone tools
mv audio_tool.py tools/
mv clear_devices.py tools/
mv manualpair.py tools/
```

**Verification:** Tests still run from `testing/` directory

---

### Task 7: Update Dockerfiles (Remove Unnecessary Copies) ✅ LOW RISK

**Action:** Only copy what each service needs

#### Currently ALL services do:
```dockerfile
COPY games/ /app/games/  # WASTEFUL - only GameCoordinator needs games
```

#### Update:

**GameCoordinator Dockerfile:** Keep games (moved to services/game_coordinator/games/)
```dockerfile
# Already correct - games are in services/game_coordinator/games/
COPY services/game_coordinator/ /app/services/game_coordinator/
```

**Menu, Settings, Supervisor, WebUI Dockerfiles:** Remove games
```dockerfile
# REMOVE this line:
# COPY games/ /app/games/

# Only copy what's needed:
COPY core/ /app/core/
COPY utils/ /app/utils/
COPY services/<service>/ /app/services/<service>/
```

**Benefits:**
- Smaller Docker images (~500KB per service)
- Faster builds
- Clearer dependencies

**Verification:** All services build successfully

---

### Task 8: Update Import Statements 🔍 HIGH RISK

**Action:** Fix imports across codebase

#### Find files with wrong imports:

```bash
# Find imports from root that should be from core/
grep -r "^import common" services/ core/ utils/
grep -r "^import controller_state" services/ core/
grep -r "^import controller_process" services/ core/

# Find imports of moved files
grep -r "^import player" services/
grep -r "^import pacemanager" services/
grep -r "from piaudio import" services/
```

#### Update to correct imports:

```python
# OLD
import common
import controller_state
import player
import pacemanager
from piaudio import Audio

# NEW
from core import common
from core import controller_state
from games import player, pacemanager  # (in GameCoordinator)
from core.grpc_clients import AudioClient  # (instead of piaudio)
```

**Verification:**
- No import errors
- All services start
- Run: `python -c "from core import common; from utils import colors"`

---

### Task 9: Expand gRPC Clients Library ⚠️ MEDIUM RISK

**Action:** Complete gRPC client implementations

**Currently:** `grpc_clients.py` only has `SettingsClient`

**Need to add:**
- ControllerManagerClient
- MenuClient
- GameCoordinatorClient
- SupervisorClient
- AudioClient ✅ NEW
- WebUIClient (if needed)

**Create:** `core/grpc_clients.py` (expand existing file)

**Verification:** Services can call each other via clients

---

### Task 10: Test Complete System ✅ CRITICAL

**Action:** End-to-end testing

#### Build and Start

```bash
# Clean rebuild
docker-compose down -v
docker-compose up --build

# Check all services started
docker-compose ps
```

#### Verify Services

```bash
# Should see 10 containers:
# - redis, jaeger, otel-collector
# - settings, controller-manager, game-coordinator, menu, supervisor, webui, audio (7 services)
```

#### Test Web UI

1. Open: http://localhost:80/
2. Check settings page loads
3. Check battery status page (if controllers connected)

#### Test Audio

```bash
# From another service, test audio RPC
# (or use grpcurl)
grpcurl -plaintext localhost:50056 joustmania.audio.AudioService/GetStatus
```

#### Test Game Flow

1. WebUI: Select game mode (FFA)
2. WebUI: Click "Start Game"
3. Menu service receives command
4. GameCoordinator starts FFA game
5. Game runs to completion (NOT mock!)
6. Check Jaeger traces: http://localhost:16686
   - Should see traces for entire game flow
   - Menu → GameCoordinator → Audio (music/sounds)

#### Test Pairing (if USB controller available)

1. Plug USB controller into Raspberry Pi
2. Press button on Move controller
3. Check ControllerManager logs for pairing
4. Controller should appear in controller list

#### Run Tests

```bash
cd testing/
pytest -v
```

**Success criteria:**
- ✅ All 7 services start
- ✅ Web UI accessible
- ✅ Can start a real game (not mock)
- ✅ Audio plays (music + sound effects)
- ✅ Pairing works (if tested)
- ✅ Traces visible in Jaeger
- ✅ No import errors
- ✅ Tests pass

---

## Final Directory Structure

```
JoustMania/
├── core/                     # Shared core infrastructure
│   ├── __init__.py
│   ├── common.py
│   ├── controller_state.py
│   ├── controller_process.py
│   ├── base_logger.py
│   └── grpc_clients.py      # All 7 service clients
│
├── utils/                    # Shared utilities
│   ├── __init__.py
│   ├── colors.py            # KEEP AS LIBRARY
│   └── (piaudio.py removed - now AudioService)
│
├── services/                 # Microservices (7 total)
│   ├── settings/
│   │   ├── server.py
│   │   ├── settings.proto
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   ├── controller_manager/
│   │   ├── server.py
│   │   ├── pairing.py       # MOVED from utils/pair.py
│   │   ├── bluetooth.py     # MOVED from jm_dbus.py
│   │   ├── controller_manager.proto
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   ├── game_coordinator/
│   │   ├── server.py
│   │   ├── game_coordinator.proto
│   │   ├── games/           # Game implementations
│   │   │   ├── __init__.py
│   │   │   ├── base.py      # MOVED from games/game.py
│   │   │   ├── player.py    # MOVED from root
│   │   │   ├── pacemanager.py  # MOVED from root
│   │   │   ├── ffa.py
│   │   │   ├── joust_teams.py
│   │   │   └── joust_random_teams.py
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   ├── menu/
│   ├── supervisor/
│   ├── webui/
│   └── audio/               # ✅ NEW SERVICE
│       ├── server.py
│       ├── playback.py      # Audio implementation
│       ├── audio.proto
│       ├── Dockerfile
│       └── pyproject.toml
│
├── testing/                  # All tests
│   ├── __init__.py
│   ├── joust_test.py
│   ├── pacemanager_test.py
│   ├── test_orchestrator.py
│   └── ffa_test.py
│
├── tools/                    # Standalone tools
│   ├── audio_tool.py
│   ├── clear_devices.py
│   └── manualpair.py
│
├── legacy/                   # Archived code
│   ├── piparty.py
│   ├── piparty_grpc.py
│   ├── controller_manager.py
│   ├── game_coordinator.py
│   ├── settings_process.py
│   ├── process_supervisor.py
│   └── webui.py
│
├── templates/                # Web UI templates
├── static/                   # Web UI static
├── audio/                    # Audio files
│
├── docker-compose.yml        # 7 services + infrastructure
├── otel-collector-config.yaml
├── pyproject.toml
├── conftest.py               # pytest config (KEEP in root)
├── __init__.py
├── jm_dbus.py               # REMOVE (moved to controller_manager/)
└── update.py                 # Update script

# Windows files REMOVED:
# - win_jm_dbus.py
# - win_pair.py

# Root directory: 7 files (vs 31 before)
```

---

## Risk Assessment

### Low Risk (Safe)
- ✅ Archive legacy files
- ✅ Delete duplicates & Windows files
- ✅ Move tests to testing/
- ✅ Move tools to tools/
- ✅ Update Dockerfiles (remove unnecessary copies)

### Medium Risk (Test thoroughly)
- ⚠️ Create AudioService (new service, test audio playback)
- ⚠️ Move pairing to ControllerManager (test auto-pairing)
- ⚠️ Expand gRPC clients (test inter-service communication)

### High Risk (Critical path)
- ❌ Move games to GameCoordinator (test actual gameplay!)
- ❌ Update import statements (test all services start)

---

## Execution Order

**Recommended sequence to minimize risk:**

1. ✅ **Archive & Delete** (Task 1-2) - Safe cleanup
2. ⚠️ **Create AudioService** (Task 3) - Test in isolation
3. ⚠️ **Move Pairing** (Task 4) - Test pairing works
4. ✅ **Reorganize Files** (Task 6) - Low risk moves
5. ❌ **Move Games** (Task 5) - Critical, test extensively
6. ✅ **Update Dockerfiles** (Task 7) - Optimization
7. ❌ **Update Imports** (Task 8) - Fix all references
8. ⚠️ **Expand gRPC Clients** (Task 9) - Complete library
9. ✅ **Test Everything** (Task 10) - End-to-end verification

---

## Success Metrics

After Phase 9 completion:

### Architecture
- ✅ 7 microservices with clear responsibilities
- ✅ 2 privileged services (ControllerManager, Audio)
- ✅ 5 unprivileged services
- ✅ All services communicate via gRPC
- ✅ Full OpenTelemetry observability

### Code Organization
- ✅ Root directory: 7 files (vs 31)
- ✅ Games in GameCoordinator service
- ✅ Pairing in ControllerManager service
- ✅ Audio as dedicated service
- ✅ Tests in testing/
- ✅ Tools in tools/
- ✅ Legacy in legacy/

### Functionality
- ✅ Can play real games (FFA, teams, random teams)
- ✅ Audio works (music + sound effects, proper mixing)
- ✅ Auto-pairing works (USB controller → paired)
- ✅ Web UI works (all routes functional)
- ✅ All services healthy
- ✅ Traces in Jaeger

### Docker
- ✅ All services containerized
- ✅ Proper privilege separation
- ✅ Optimized image sizes
- ✅ Health checks working
- ✅ Clean restart behavior

---

## Next Step

Ready to execute Phase 9? I recommend starting with Tasks 1-2 (cleanup) since they're safe and will immediately declutter the root directory.

Should we begin?
