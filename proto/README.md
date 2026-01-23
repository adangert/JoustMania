# JoustMania Protocol Buffer Schemas

This directory contains all protocol buffer (protobuf) schemas for the JoustMania microservices architecture. It serves as the **single source of truth** for all gRPC service contracts.

## Overview

The `proto/` directory is a shared workspace package (`joustmania-proto`) that all microservices depend on. This centralized approach eliminates the need to copy individual `.proto` files or generated Python code between services.

## Package Structure

```
proto/
├── README.md                           # This file
├── pyproject.toml                      # joustmania-proto package definition
├── __init__.py                         # Package initialization
├── generate_proto.sh                   # Script to generate Python code from .proto files
│
├── settings.proto                      # Settings service schema
├── controller_manager.proto            # Controller manager service schema
├── controller_manager_mock.proto       # Mock controller control API
├── game_coordinator.proto              # Game coordinator service schema
├── menu.proto                          # Menu service schema
├── audio.proto                         # Audio service schema
│
└── *_pb2.py, *_pb2_grpc.py            # Generated Python code (auto-generated)
```

## Protocol Buffer Schemas

### 1. Settings Service (`settings.proto`)
**Port:** 50051
**Purpose:** Centralized configuration management with validation and change notifications

**Key RPCs:**
- `GetSettings` - Retrieve all settings
- `GetSetting` - Get a specific setting by key
- `UpdateSetting` - Update a setting value with validation
- `SubscribeToChanges` - Stream setting change events (server streaming)

**Features:**
- Schema-based validation
- Atomic YAML file saves
- Real-time change notifications
- Pattern-based subscriptions

### 2. Controller Manager Service (`controller_manager.proto`)
**Port:** 50052
**Purpose:** PS Move controller lifecycle management and real-time state streaming

**Key RPCs:**
- `StreamButtonEvents` - Bidirectional stream for button events and LED control
- `StreamGameplayData` - Bidirectional stream for gameplay data with dynamic filtering
- `PlayControllerEffect` - Play visual effects (flash, pulse, rainbow)

**Features:**
- Background hardware discovery (1Hz polling)
- High-frequency state streaming (up to 1000Hz)
- Graceful mock mode when hardware unavailable
- Automatic controller health monitoring
- LED state ownership via bidirectional streaming

### 3. Controller Manager Mock API (`controller_manager_mock.proto`)
**Port:** 50062
**Purpose:** Control mock controllers for testing without hardware

**Key RPCs:**
- `AddMockController` - Add a simulated controller
- `RemoveMockController` - Remove a mock controller
- `UpdateMockController` - Update mock controller state (position, buttons, etc.)
- `TriggerMockButton` - Simulate button press

**Use Case:** Testing and development without physical PS Move hardware

### 4. Game Coordinator Service (`game_coordinator.proto`)
**Port:** 50053
**Purpose:** Game lifecycle management and event streaming

**Key RPCs:**
- `StartGame` - Start a game with specified mode and settings
- `ForceEndGame` - Terminate current game
- `StreamGameEvents` - Stream game events (server streaming)

**Game Modes:** 13 modes including Joust FFA, Teams, Traitor, Swapper, Tournament, etc.

**Events:**
- Game start/end
- Player deaths/eliminations
- Team changes
- Score updates

### 5. Menu Service (`menu.proto`)
**Port:** 50054
**Purpose:** Menu UI state management and input processing

**Key RPCs:**
- `StartMenu` - Start menu with controller count
- `StopMenu` - Stop menu
- `GetMenuStatus` - Get current menu state
- `ProcessInput` - Process button press or web command
- `StreamMenuEvents` - Stream menu events (server streaming)

**Input Types:**
- Button presses (trigger, select, middle)
- Web commands (start game, mode selection)

### 6. Audio Service (`audio.proto`)
**Port:** 50056
**Purpose:** Audio playback management

**Key RPCs:**
- `PlaySound` - Play a sound effect
- `PlayMusic` - Play background music with looping
- `StopMusic` - Stop current music
- `SetVolume` - Adjust volume
- `GetAudioStatus` - Get playback status

**Features:**
- Mock mode for headless testing
- Volume control
- Music looping

## Generating Python Code

### Automatic Generation

Run the generation script to compile all `.proto` files:

```bash
cd proto/
./generate_proto.sh
```

This will generate `*_pb2.py` and `*_pb2_grpc.py` files for all schemas.

## Bytecode Pre-compilation (Phase 47)

For optimal startup performance on Raspberry Pi, protobuf Python files are pre-compiled to optimized bytecode.

### Why Pre-compilation?

- **50-60% faster startup**: Pre-compiled `.pyc` files load instantly
- **Critical for Pi**: Raspberry Pi CPU is slow at runtime compilation
- **Docker optimization**: Bytecode is included in images

### Generating Protos with Bytecode

The `generate_proto.sh` script automatically:
1. Generates `_pb2.py` and `_pb2_grpc.py` files from `.proto` schemas
2. Fixes imports to use absolute imports
3. Compiles to optimized bytecode (`.opt-2.pyc` files in `__pycache__/`)

```bash
# From project root
make protos
# or
bash proto/generate_proto.sh
```

### Bytecode Files

Bytecode files are stored in `proto/__pycache__/` and are:
- **Tracked in git** (exception to normal .gitignore rules)
- **Included in Docker images** (exception to normal .dockerignore)
- **Optimized with -OO flag** (smallest, fastest, strips docstrings)

**DO NOT** manually delete `proto/__pycache__/` unless regenerating protos.

### When to Regenerate

Regenerate protos when:
- `.proto` files are modified
- Python version changes (different bytecode format)
- protobuf library version changes

```bash
make clean-protos  # Remove generated files
make protos        # Regenerate everything
```

### Manual Generation (per schema)

If you need to regenerate a specific schema:

```bash
python -m grpc_tools.protoc \
  --proto_path=. \
  --python_out=. \
  --grpc_python_out=. \
  settings.proto
```

### What Gets Generated

For each `.proto` file (e.g., `settings.proto`), two files are generated:
- `settings_pb2.py` - Message classes (requests, responses, data structures)
- `settings_pb2_grpc.py` - Service stubs and servicers (client and server interfaces)

## Using in Services

All services depend on the `joustmania-proto` package in their `pyproject.toml`:

```toml
[project]
dependencies = [
    "joustmania-proto",
    # ... other dependencies
]
```

### In Service Code

Import generated code directly:

```python
# Import message classes
from proto import settings_pb2

# Import service stubs
from proto import settings_pb2_grpc

# Create a gRPC channel
channel = grpc.insecure_channel('localhost:50051')
stub = settings_pb2_grpc.SettingsServiceStub(channel)

# Make RPC calls
request = settings_pb2.GetSettingsRequest()
response = stub.GetSettings(request)
```

### In Dockerfiles

The proto package is copied once and used by all services:

```dockerfile
# Copy shared proto package
COPY proto /app/proto

# Install dependencies (includes joustmania-proto)
RUN uv sync --frozen
```

## Benefits of Centralized Schemas

✅ **Single source of truth** - All protobuf schemas in one place
✅ **No duplication** - No copying pb2 files between services
✅ **Easier maintenance** - Update once, all services benefit
✅ **Cleaner Dockerfiles** - Just `COPY proto/` instead of individual files
✅ **Better versioning** - Proto package can be versioned independently
✅ **Consistent generation** - One script generates all Python code

## Protobuf Best Practices

### Message Naming
- Use PascalCase for messages: `GetSettingsRequest`, `ControllerState`
- Use snake_case for fields: `controller_count`, `is_ready`

### Field Numbering
- Never change field numbers (breaks backward compatibility)
- Reserve deleted field numbers to prevent reuse
- Use field numbers 1-15 for frequently used fields (1 byte encoding)

### Service Naming
- Service names match the microservice: `SettingsService`, `MenuService`
- RPC names use imperative verbs: `GetSettings`, `StartGame`, `UpdateSetting`

### Streaming RPCs
- Server streaming for real-time updates (e.g., `StreamGameEvents`, `StreamMenuEvents`)
- Bidirectional streaming for interactive control (e.g., `StreamButtonEvents`, `StreamGameplayData`)
- Use `stream` keyword in proto definition
- Handle disconnections gracefully

## Dependencies

The proto package requires:
- `grpcio` - gRPC runtime
- `grpcio-tools` - Protobuf compiler (for generation)
- `protobuf` - Protocol buffer runtime

These are specified in `proto/pyproject.toml`.

## Development Workflow

### Adding a New Service

1. Create `new_service.proto` in this directory
2. Define messages and service interface
3. Run `./generate_proto.sh` to generate Python code
4. Add service to workspace in root `pyproject.toml`
5. Import in service implementation:
   ```python
   from proto import new_service_pb2, new_service_pb2_grpc
   ```

### Modifying an Existing Schema

1. Edit the `.proto` file
2. Run `./generate_proto.sh`
3. Rebuild all affected services
4. Test thoroughly (protobuf changes can break compatibility)

### Version Management

For breaking changes:
- Consider creating versioned packages (e.g., `joustmania-proto-v2`)
- Use protobuf's `package` directive for namespacing
- Maintain backward compatibility when possible

## Testing

### With grpcurl

Test services using grpcurl (requires reflection enabled):

```bash
# List services
grpcurl -plaintext localhost:50051 list

# List methods
grpcurl -plaintext localhost:50051 list joustmania.SettingsService

# Call RPC
grpcurl -plaintext -d '{}' \
  localhost:50051 \
  joustmania.SettingsService/GetSettings
```

### With Python Client

```python
import grpc
from proto import settings_pb2, settings_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = settings_pb2_grpc.SettingsServiceStub(channel)

request = settings_pb2.GetSettingsRequest()
response = stub.GetSettings(request)
print(response.settings)
```

## Documentation

For detailed API documentation, see:
- **Service READMEs:** Each service has a `services/*/README.md` with usage examples
- **Architecture docs:** `docs/ARCHITECTURE.md` for system overview
- **API reference:** `docs/API.md` for complete gRPC API documentation

## Troubleshooting

### Import Errors

If you get import errors like `ModuleNotFoundError: No module named 'proto'`:

1. Check that proto package is in your workspace: `uv sync`
2. Verify `pyproject.toml` includes `joustmania-proto` dependency
3. Run `./generate_proto.sh` to ensure Python code is generated

### Regeneration Needed

If you modify a `.proto` file, you must regenerate Python code:

```bash
cd proto/
./generate_proto.sh
```

Then rebuild affected Docker images:

```bash
docker-compose build <service-name>
```

### gRPC Connection Errors

If services can't connect:
- Verify ports are correct (see port numbers above)
- Check that services are running: `docker-compose ps`
- Use `docker-compose logs <service>` to check for errors
- Ensure services use correct hostnames (e.g., `settings:50051` not `localhost:50051`)

## Related Documentation

- **Phase 14 Implementation:** `planning/IMPLEMENTATION_STATUS.md` (lines 1291-1338)
- **Docker Compose:** `docker-compose.yml`, `docker-compose.mock.yml`
- **Service Architecture:** `docs/ARCHITECTURE.md`
- **Development Guide:** `docs/DEVELOPMENT.md`

---

**Package Version:** 0.1.0
**Created:** Phase 14 - 2026-01-10
**Purpose:** Centralize all protocol buffer schemas for JoustMania microservices
