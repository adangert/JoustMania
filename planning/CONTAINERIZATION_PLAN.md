# JoustMania Containerization Plan

**Date:** 2026-01-10
**Purpose:** Containerize microservices with Docker and docker-compose
**Status:** Design Proposal (Phase 8 of Microservices Architecture)
**Updated:** 2026-01-10 - Changed from HTTP/REST to gRPC for performance

---

## Goals

1. Each microservice runs in its own Docker container
2. docker-compose orchestrates all services
3. Services communicate over network (not shared memory)
4. Hardware access (controllers, audio) properly mapped
5. Easy development and deployment

---

## Current State vs Target

### Current (Multiprocessing)
```
piparty.py (orchestrator)
  ├─→ Settings (Process, shared memory IPC)
  ├─→ ControllerManager (Process, shared memory IPC)
  ├─→ GameCoordinator (Process, shared memory IPC)
  ├─→ Menu (Process, shared memory IPC)
  └─→ Supervisor (Thread, manages above)
```

### Target (Docker Containers)
```
docker-compose.yml
  ├─→ settings (container, gRPC API)
  ├─→ controller-manager (container, gRPC API, USB/BT access)
  ├─→ game-coordinator (container, gRPC API, audio access)
  ├─→ menu (container, gRPC API, audio access)
  ├─→ orchestrator (container, gRPC client)
  └─→ redis (container, pub/sub for events)
```

---

## Architecture Changes Required

### 1. Replace IPC with Network Communication (gRPC)

**Why gRPC instead of HTTP/REST:**
- **Performance critical**: JoustMania is a real-time game running on Raspberry Pi 5
- **Binary protocol**: Protocol Buffers are faster than JSON parsing
- **HTTP/2 multiplexing**: Better connection handling
- **Strongly typed**: Compile-time validation with protobuf schemas
- **Streaming support**: Bi-directional streaming for events (alternative to Redis)
- **Lower latency**: ~3-10x faster than REST for small messages
- **Smaller payload**: Binary encoding reduces network overhead

**Current IPC (multiprocessing.Queue):**
```python
# Send command
command_queue.put({'command': 'get_settings', ...})

# Wait for response
response = response_queue.get(timeout=1.0)
```

**New IPC (gRPC):**
```python
# Send command via gRPC stub
import grpc
from services.settings import settings_pb2, settings_pb2_grpc

channel = grpc.insecure_channel('settings:50051')
stub = settings_pb2_grpc.SettingsServiceStub(channel)

response = stub.GetSettings(
    settings_pb2.GetSettingsRequest(),
    timeout=1.0
)
```

**Services become gRPC servers:**
- Each service runs gRPC server
- Exposes RPC methods defined in .proto files
- Returns typed protobuf messages
- Much faster than JSON/HTTP for game-critical paths

### 2. Events via Redis Pub/Sub

**Current (Queue):**
```python
event_queue.put({'event': 'game_started', ...})
```

**New (Redis):**
```python
redis_client.publish('events', json.dumps({
    'event': 'game_started',
    ...
}))
```

**Subscribers:**
```python
pubsub = redis_client.pubsub()
pubsub.subscribe('events')

for message in pubsub.listen():
    event = json.loads(message['data'])
    handle_event(event)
```

---

## Service Containerization

### Settings Service

**Protocol Buffer Definition (settings.proto):**
```protobuf
syntax = "proto3";

package joustmania.settings;

service SettingsService {
  rpc GetSettings(GetSettingsRequest) returns (GetSettingsResponse);
  rpc GetSetting(GetSettingRequest) returns (GetSettingResponse);
  rpc UpdateSetting(UpdateSettingRequest) returns (UpdateSettingResponse);
  rpc SubscribeToChanges(SubscribeRequest) returns (stream SettingChangeEvent);
}

message GetSettingsRequest {}

message GetSettingsResponse {
  map<string, string> settings = 1;
}

message GetSettingRequest {
  string key = 1;
}

message GetSettingResponse {
  string key = 1;
  string value = 2;
  bool success = 3;
  string error = 4;
}

message UpdateSettingRequest {
  string key = 1;
  string value = 2;
  string source = 3;
}

message UpdateSettingResponse {
  bool success = 1;
  string error = 2;
}

message SubscribeRequest {}

message SettingChangeEvent {
  string key = 1;
  string old_value = 2;
  string new_value = 3;
  string source = 4;
  int64 timestamp = 5;
}
```

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install protobuf compiler
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

# Copy service code
COPY services/settings/ /app/services/settings/
COPY core/common.py /app/core/common.py

# Install dependencies
RUN pip install --no-cache-dir \
    pyyaml \
    grpcio>=1.60.0 \
    grpcio-tools>=1.60.0 \
    redis \
    opentelemetry-distro \
    opentelemetry-exporter-otlp

# Generate gRPC code from .proto files
RUN python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    services/settings/settings.proto

# Expose gRPC port
EXPOSE 50051

# Run service
CMD ["python", "-m", "services.settings.server"]
```

**gRPC Service Methods:**
- `GetSettings()` - Get all settings
- `GetSetting(key)` - Get specific setting
- `UpdateSetting(key, value, source)` - Update setting
- `SubscribeToChanges()` - Stream of setting change events

**Port:** 50051

### ControllerManager Service

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PSMove and protobuf
RUN apt-get update && apt-get install -y \
    libudev-dev \
    libbluetooth-dev \
    libusb-dev \
    bluetooth \
    bluez \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Copy service code
COPY services/controller_manager/ /app/services/controller_manager/
COPY core/ /app/core/

# Install Python dependencies
RUN pip install --no-cache-dir \
    pyyaml \
    dbus-python \
    grpcio>=1.60.0 \
    grpcio-tools>=1.60.0 \
    redis \
    opentelemetry-distro \
    opentelemetry-exporter-otlp

# Generate gRPC code
RUN python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    services/controller_manager/controller_manager.proto

# Expose gRPC port
EXPOSE 50052

# Run service (privileged mode required for USB/BT)
CMD ["python", "-m", "services.controller_manager.server"]
```

**gRPC Service Methods:**
- `GetControllerCount()` - Get number of connected controllers
- `GetReadyControllers()` - Get list of ready controllers
- `GetControllers()` - Get all controller states
- `PairController(color)` - Pair new controller
- `RemoveController(serial)` - Remove controller
- `StreamControllerStates()` - Real-time controller state stream

**Port:** 50052

**docker-compose requirements:**
```yaml
controller-manager:
  privileged: true  # For USB/BT access
  network_mode: host  # For Bluetooth
  devices:
    - /dev/bus/usb:/dev/bus/usb  # USB devices
    - /dev/hidraw0:/dev/hidraw0  # HID devices
  volumes:
    - /var/run/dbus:/var/run/dbus  # D-Bus for Bluetooth
```

### GameCoordinator Service

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for audio and protobuf
RUN apt-get update && apt-get install -y \
    libasound2-dev \
    ffmpeg \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Copy service code
COPY services/game_coordinator/ /app/services/game_coordinator/
COPY core/ /app/core/
COPY games/ /app/games/
COPY audio/ /app/audio/

# Install Python dependencies
RUN pip install --no-cache-dir \
    pyyaml \
    pygame \
    pyalsaaudio \
    pydub \
    audioop-lts \
    grpcio>=1.60.0 \
    grpcio-tools>=1.60.0 \
    redis \
    opentelemetry-distro \
    opentelemetry-exporter-otlp

# Generate gRPC code
RUN python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    services/game_coordinator/game_coordinator.proto

# Expose gRPC port
EXPOSE 50053

CMD ["python", "-m", "services.game_coordinator.server"]
```

**gRPC Service Methods:**
- `StartGame(game_name, players)` - Start game
- `GetGameStatus()` - Get current game status
- `ForceEndGame()` - Force end current game
- `StreamGameEvents()` - Real-time game event stream

**Port:** 50053

**Audio access:**
```yaml
game-coordinator:
  devices:
    - /dev/snd:/dev/snd  # ALSA audio
  environment:
    - PULSE_SERVER=unix:/run/user/1000/pulse/native
  volumes:
    - /run/user/1000/pulse:/run/user/1000/pulse
```

### Menu Service

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libasound2-dev \
    ffmpeg \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Copy service code
COPY services/menu/ /app/services/menu/
COPY core/ /app/core/
COPY utils/ /app/utils/
COPY audio/ /app/audio/

# Install Python dependencies
RUN pip install --no-cache-dir \
    pyyaml \
    pygame \
    pyalsaaudio \
    pydub \
    audioop-lts \
    grpcio>=1.60.0 \
    grpcio-tools>=1.60.0 \
    redis \
    opentelemetry-distro \
    opentelemetry-exporter-otlp

# Generate gRPC code
RUN python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    services/menu/menu.proto

# Expose gRPC port
EXPOSE 50054

CMD ["python", "-m", "services.menu.server"]
```

**gRPC Service Methods:**
- `StartMenu()` - Start menu UI
- `StopMenu()` - Stop menu UI
- `GetMenuStatus()` - Get menu state
- `StreamMenuEvents()` - Real-time menu interaction stream

**Port:** 50054

### Supervisor Service

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install protobuf compiler
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

# Copy service code
COPY services/supervisor/ /app/services/supervisor/

# Install Python dependencies
RUN pip install --no-cache-dir \
    grpcio>=1.60.0 \
    grpcio-tools>=1.60.0 \
    redis

# Generate gRPC code
RUN python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    services/supervisor/supervisor.proto

# Expose gRPC port
EXPOSE 50055

CMD ["python", "-m", "services.supervisor.server"]
```

**gRPC Service Methods:**
- `GetProcessStatus(name)` - Get status of specific process
- `GetAllProcessStatus()` - Get status of all processes
- `RestartProcess(name)` - Restart failed process
- `GetHealthSummary()` - Get system health summary

**Port:** 50055

### Orchestrator (piparty.py)

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install protobuf compiler
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

# Copy orchestrator code
COPY piparty.py /app/
COPY webui.py /app/
COPY static/ /app/static/
COPY templates/ /app/templates/

# Install Python dependencies
RUN pip install --no-cache-dir \
    flask \
    Flask-WTF \
    grpcio>=1.60.0 \
    grpcio-tools>=1.60.0 \
    redis \
    python-dotenv

# Expose web UI port
EXPOSE 5000

CMD ["python", "piparty.py"]
```

**Port:** 5000 (Web UI - HTTP for browser access)
**Note:** Orchestrator uses Flask for web UI (HTTP) but gRPC for microservice communication

---

## docker-compose.yml

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  settings:
    build:
      context: .
      dockerfile: services/settings/Dockerfile
    ports:
      - "50051:50051"
    environment:
      - REDIS_URL=redis://redis:6379
      - GRPC_PORT=50051
    volumes:
      - ./joustsettings.yaml:/app/joustsettings.yaml
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "grpc_health_probe", "-addr=localhost:50051"]
      interval: 10s
      timeout: 3s
      retries: 3

  controller-manager:
    build:
      context: .
      dockerfile: services/controller_manager/Dockerfile
    ports:
      - "50052:50052"
    privileged: true
    network_mode: host
    environment:
      - REDIS_URL=redis://localhost:6379
      - SETTINGS_GRPC_URL=localhost:50051
      - GRPC_PORT=50052
    devices:
      - /dev/bus/usb:/dev/bus/usb
    volumes:
      - /var/run/dbus:/var/run/dbus
      - /var/lib/bluetooth:/var/lib/bluetooth
    depends_on:
      - redis
      - settings

  game-coordinator:
    build:
      context: .
      dockerfile: services/game_coordinator/Dockerfile
    ports:
      - "50053:50053"
    environment:
      - REDIS_URL=redis://redis:6379
      - SETTINGS_GRPC_URL=settings:50051
      - CONTROLLER_MANAGER_GRPC_URL=localhost:50052  # host network
      - GRPC_PORT=50053
    devices:
      - /dev/snd:/dev/snd
    volumes:
      - /run/user/1000/pulse:/run/user/1000/pulse
      - ./audio:/app/audio
    depends_on:
      - redis
      - settings
      - controller-manager

  menu:
    build:
      context: .
      dockerfile: services/menu/Dockerfile
    ports:
      - "50054:50054"
    environment:
      - REDIS_URL=redis://redis:6379
      - SETTINGS_GRPC_URL=settings:50051
      - CONTROLLER_MANAGER_GRPC_URL=localhost:50052  # host network
      - GRPC_PORT=50054
    devices:
      - /dev/snd:/dev/snd
    volumes:
      - /run/user/1000/pulse:/run/user/1000/pulse
      - ./audio:/app/audio
    depends_on:
      - redis
      - settings
      - controller-manager

  supervisor:
    build:
      context: .
      dockerfile: services/supervisor/Dockerfile
    ports:
      - "50055:50055"
    environment:
      - REDIS_URL=redis://redis:6379
      - SETTINGS_GRPC_URL=settings:50051
      - CONTROLLER_MANAGER_GRPC_URL=localhost:50052
      - GAME_COORDINATOR_GRPC_URL=game-coordinator:50053
      - MENU_GRPC_URL=menu:50054
      - GRPC_PORT=50055
    depends_on:
      - redis
      - settings
      - controller-manager
      - game-coordinator
      - menu

  orchestrator:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "5000:5000"  # Web UI (HTTP)
    environment:
      - REDIS_URL=redis://redis:6379
      - SUPERVISOR_GRPC_URL=supervisor:50055
    volumes:
      - ./static:/app/static
      - ./templates:/app/templates
    depends_on:
      - supervisor

volumes:
  redis-data:
```

---

## Implementation Steps

### Step 1: Convert IPC to gRPC (Network-Based)

For each service:
1. Define `.proto` file with service interface
2. Generate Python gRPC code with `grpc_tools.protoc`
3. Create `server.py` with gRPC server implementation
4. Replace Queue.put()/get() with gRPC stub calls
5. Replace event queues with Redis pub/sub (or gRPC streaming)

### Step 2: Create Dockerfiles

For each service:
1. Write Dockerfile
2. Install system dependencies
3. Install Python dependencies
4. Expose port
5. Set CMD

### Step 3: Create docker-compose.yml

1. Define all services
2. Set up networking
3. Configure hardware access (privileged, devices)
4. Set up volumes (audio, settings file)
5. Configure dependencies

### Step 4: Testing

```bash
# Build all images
docker-compose build

# Start all services
docker-compose up

# Check health
docker-compose ps

# View logs
docker-compose logs -f settings

# Stop all
docker-compose down
```

---

## Benefits

### Development
- ✅ Each service can be developed independently
- ✅ Easy to test individual services
- ✅ Reproducible environments
- ✅ No dependency conflicts

### Deployment
- ✅ Easy to deploy to any Docker host
- ✅ Can scale services independently
- ✅ Can deploy to Kubernetes later
- ✅ Version control for images

### Operations
- ✅ Easy to restart individual services
- ✅ Resource limits per container
- ✅ Better isolation
- ✅ Easier monitoring

---

## Challenges & Solutions

### Challenge 1: Hardware Access

**Problem:** ControllerManager needs USB/Bluetooth access

**Solution:**
- Use `privileged: true` in docker-compose
- Use `network_mode: host` for Bluetooth
- Map devices: `/dev/bus/usb`, `/dev/hidraw*`
- Map D-Bus socket for Bluetooth

### Challenge 2: Audio

**Problem:** Menu and GameCoordinator need audio output

**Solution:**
- Map ALSA devices: `/dev/snd`
- Map PulseAudio socket
- Or use host network mode

### Challenge 3: PSMove API

**Problem:** Compiled C library, not in PyPI

**Solution:**
- Build psmoveapi in Dockerfile
- Or use multi-stage build
- Or pre-build and copy binary

### Challenge 4: Shared Memory

**Problem:** Current code uses multiprocessing shared memory (Value, Array)

**Solution:**
- Remove shared memory dependencies
- Use HTTP for state queries
- Use Redis for shared state if needed
- Each service maintains its own state

---

## Migration Strategy

### Phase 8a: Convert to gRPC (Non-Docker)

1. Define `.proto` files for all services
2. Generate gRPC Python code
3. Convert each service to gRPC server (all services still on host)
4. Replace multiprocessing.Queue with gRPC stubs in piparty.py
5. Replace event queues with Redis pub/sub
6. Remove all old IPC code (no backward compatibility)
7. Test thoroughly on host

### Phase 8b: Dockerize

1. Create Dockerfiles for each service
2. Create docker-compose.yml
3. Build images
4. Test locally with docker-compose
5. Deploy to production

**Note:** Direct cutover to gRPC - no feature flags, no legacy code maintenance

---

## Estimated Effort

- **Step 1 (Network IPC):** 2-3 days
  - Convert each service to HTTP server
  - Update all IPC calls
  - Replace events with Redis

- **Step 2 (Dockerfiles):** 1 day
  - Write Dockerfiles for all services
  - Test builds

- **Step 3 (docker-compose):** 1 day
  - Wire up all services
  - Configure hardware access
  - Test end-to-end

**Total:** 4-5 days of focused work

---

## Next Steps

**Should we proceed?**

1. Start with Phase 8a (Network IPC) first?
2. Create HTTP server for Settings service (simplest)?
3. Test pattern, then replicate to other services?
4. Then move to Docker (Phase 8b)?

Or alternative:
- Skip containerization for now (hardware complexity)
- Focus on Phase 6 (Observability) instead?
- Containerize later for production?

---

## Recommendation

**Proceed with Phase 8a (gRPC conversion) first:**
- Biggest architectural change
- gRPC provides 3-10x better performance than REST (critical for game on Raspberry Pi)
- Binary protocol reduces CPU overhead
- Can test on host without Docker complexity
- Makes services truly independent
- Sets foundation for Docker later
- Direct cutover - removes all legacy IPC code

**Then proceed with:**
1. Phase 6 (Observability) - OpenTelemetry integration
2. Phase 8b (Docker) - Containerization
3. Phase 9 (Developer Tooling) - Linting, formatting, testing with uv

**Performance Impact:**
- Current: multiprocessing.Queue (shared memory, fast but not network-ready)
- gRPC: ~100-500μs latency for typical RPC call on localhost
- REST/JSON would be: ~1-5ms latency (10x slower)
- For 60 FPS game: 16ms budget per frame, gRPC leaves plenty of headroom

---

## Phase 9: Developer Tooling (Future)

**Goal:** Set up proper development tooling using uv for code quality, testing, and productivity.

### Tools to Add

**1. Code Quality:**
- **ruff** - Fast Python linter and formatter (replaces black, isort, flake8)
- **ty** - Static type checking
- **pre-commit** - Git hooks for automatic checks

**2. Testing:**
- **pytest** - Test framework
- **pytest-cov** - Coverage reporting
- **pytest-asyncio** - Async test support for gRPC
- **pytest-mock** - Mocking support

**3. Documentation:**
- **mkdocs** - Documentation site generator
- **mkdocs-material** - Material theme for docs
- **mkdocstrings[python]** - Auto-generate API docs from docstrings

**4. Development:**
- **ipython** - Enhanced Python REPL
- **grpcurl** - Test gRPC endpoints from CLI
- **grpc-health-probe** - Health checking for containers

### uv Configuration

Add to root `pyproject.toml`:

```toml
[tool.uv]
dev-dependencies = [
    "ruff>=0.1.0",
    "ty>=0.1.0",
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-asyncio>=0.21.0",
    "pytest-mock>=3.12.0",
    "pre-commit>=3.5.0",
    "ipython>=8.17.0",
    "mkdocs>=1.5.0",
    "mkdocs-material>=9.4.0",
    "mkdocstrings[python]>=0.24.0",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]
ignore = [
    "E501",  # line too long (handled by formatter)
]

[tool.ty]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
exclude = [
    "venv",
    ".venv",
    "build",
    "dist",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
addopts = [
    "--verbose",
    "--cov=services",
    "--cov=core",
    "--cov-report=term-missing",
    "--cov-report=html",
]

[tool.coverage.run]
omit = [
    "*/tests/*",
    "*/__pycache__/*",
    "*/venv/*",
    "*/.venv/*",
]
```

### Pre-commit Configuration

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.6
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: ty
        name: ty
        entry: uv run ty
        language: system
        types: [python]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
```

### Commands

```bash
# Install dev dependencies
uv sync --dev

# Run linter
uv run ruff check .

# Run formatter
uv run ruff format .

# Run type checker
uv run ty services/ core/

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov

# Install pre-commit hooks
uv run pre-commit install

# Generate docs
uv run mkdocs build
uv run mkdocs serve  # Live preview at http://localhost:8000
```

### Benefits

- **Consistent code style** across all services
- **Catch bugs early** with static type checking
- **Automated checks** via pre-commit hooks
- **Test coverage** tracking
- **Documentation** auto-generated from code
- **Fast feedback** (ruff is 10-100x faster than black/flake8)

### Implementation

This is Phase 9 and should be done after Phase 8b (Dockerization):
1. Add dev dependencies to root pyproject.toml
2. Create .pre-commit-config.yaml
3. Set up ruff and mypy configuration
4. Write initial tests for critical paths
5. Set up CI/CD pipeline (GitHub Actions) to run checks
6. Create documentation structure with mkdocs
