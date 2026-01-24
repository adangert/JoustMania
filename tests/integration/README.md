# JoustMania Integration Tests

Integration tests for JoustMania using testcontainers and the mock hardware environment.

## Overview

This is a separate Python package that contains integration tests for the entire JoustMania stack. It uses:

- **pytest** - Test framework
- **pytest-asyncio** - Async test support
- **testcontainers-python** - Docker Compose orchestration
- **grpcio** - gRPC client for service communication
- **protobuf** - Protocol buffer support

## Why a Separate Module?

Keeping integration tests as a separate module provides:

1. **Clean separation** - Test dependencies don't pollute the main application
2. **Independent versioning** - Test tools can be updated independently
3. **Clear documentation** - All test requirements are in one place
4. **Workspace member** - Part of the uv workspace but isolated

## Structure

```
tests/integration/
├── pyproject.toml              # Test dependencies and configuration
├── README.md                   # This file
└── test_mock_environment.py    # Integration tests using mock environment
```

## Dependencies

### Required System Packages

For running tests locally (not needed in Docker):

```bash
# Ubuntu/Debian
sudo apt-get install python3.12-dev

# macOS
# No additional packages needed
```

### Python Dependencies

All Python dependencies are managed in `pyproject.toml`:

- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Coverage reporting
- `testcontainers>=4.0.0` - Docker Compose orchestration
- `grpcio>=1.50.0` - gRPC client
- `grpcio-tools>=1.50.0` - gRPC tools
- `protobuf>=4.21.0` - Protocol buffers

## Installation

From the project root:

```bash
# Sync all workspace members including integration tests
uv sync --all-packages

# Or sync just the integration tests module
uv sync --package joustmania-integration-tests
```

## Running Tests

### Quick Start (Using Makefile)

```bash
# From project root - builds images locally
make test

# Using prebuilt images from GHCR (faster, no build required)
make test-with-pulled

# Using specific image tag
IMAGE_TAG=dev-refactor make test-with-pulled

# With pause for Jaeger inspection
make test-mock-pause
```

### Using pytest Directly

```bash
# From project root - builds images locally
uv run --package joustmania-integration-tests pytest tests/integration/ -v

# Using prebuilt images from GHCR
USE_PREBUILT_IMAGES=true uv run --package joustmania-integration-tests pytest tests/integration/ -v

# Using specific image tag
USE_PREBUILT_IMAGES=true IMAGE_TAG=dev-refactor uv run --package joustmania-integration-tests pytest tests/integration/ -v

# With pause for Jaeger inspection
PAUSE_BEFORE_TEARDOWN=1 uv run --package joustmania-integration-tests pytest tests/integration/ -v -s
```

### From integration tests directory

```bash
cd tests/integration

# Run all tests
uv run pytest -v

# Run specific test
uv run pytest test_mock_environment.py::test_mock_controller_manager_connection -v

# With pause
PAUSE_BEFORE_TEARDOWN=1 uv run pytest -v -s
```

## Test Coverage

The integration tests cover:

- ✅ Mock controller manager connection
- ✅ Controller control API (movement, death, buttons, reset)
- ✅ Full FFA game lifecycle
- ✅ Full Teams game lifecycle
- ✅ Controller state streaming at 60Hz
- ✅ Distributed tracing propagation across services
- ✅ Multiple games in sequence

## How Tests Work

### Docker Compose Orchestration

Tests use `testcontainers-python` to:

1. Start `docker-compose.yml` environment
2. Wait for all services to be healthy
3. Run test scenarios via gRPC
4. Tear down environment (or pause for inspection)

### Test Fixture

The tests use `docker-compose.yml` which automatically includes `docker-compose.override.yml`
and `docker-compose.ci.yml` for testing. By default, images are built locally to test the current code.
Set `USE_PREBUILT_IMAGES=true` to pull images from GHCR instead.

```python
@pytest.fixture(scope="session")
def docker_compose():
    """Fixture to start docker-compose mock environment.

    Uses docker-compose.yml with overrides for testing.
    
    Environment Variables:
        USE_PREBUILT_IMAGES: Set to "true" to pull images from GHCR
        IMAGE_TAG: Specify image tag to pull (default: latest)
    """
    use_prebuilt = os.getenv("USE_PREBUILT_IMAGES", "false").lower() == "true"
    image_tag = os.getenv("IMAGE_TAG", "latest")
    
    compose = DockerCompose(
        context=".",
        compose_file_name=[
            "docker-compose.yml",
            "docker-compose.override.yml",
            "docker-compose.ci.yml",
        ],
        pull=use_prebuilt,
        build=not use_prebuilt,
    )
    compose.start()
    yield compose
    compose.stop()
```

### gRPC Communication

Tests communicate with services via gRPC:

```python
# Connect to game coordinator
game_channel = grpc.aio.insecure_channel('localhost:50053')
game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

# Start game
response = await game_client.StartGame(
    game_coordinator_pb2.StartGameRequest(mode="FFA")
)
```

### Mock Controller Control

Tests control mock controllers via the control API:

```python
# Connect to mock control API
mock_channel = grpc.aio.insecure_channel('localhost:50062')
mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(mock_channel)

# Simulate death
await mock_client.SimulateDeath(
    controller_manager_mock_pb2.DeathRequest(serial="mock_controller_0")
)
```

## Inspecting Traces

When using `PAUSE_BEFORE_TEARDOWN=1`:

1. Tests run normally
2. Environment stays up after tests complete
3. Open Jaeger UI: http://localhost:16686
4. Search for traces: `service="game-coordinator-service"`
5. Inspect distributed traces across all services
6. Press ENTER in terminal to tear down

## Troubleshooting

### Docker Daemon Not Running

```
Error: Cannot connect to the Docker daemon
```

**Solution:** Start Docker Desktop or Docker daemon

### Port Already in Use

```
Error: bind: address already in use
```

**Solution:** Stop other JoustMania instances or change ports in docker-compose.yml

### Services Not Ready

```
ERROR: Connection refused
```

**Solution:** Increase wait time in test fixture or check service logs:

```bash
docker-compose -f docker-compose.yml logs
```

### Import Errors

```
ModuleNotFoundError: No module named 'grpc'
```

**Solution:** Ensure dependencies are installed:

```bash
uv sync --package joustmania-integration-tests
```

### Protobuf Import Issues

```
ModuleNotFoundError: No module named 'controller_manager_mock_pb2'
```

**Solution:** Ensure protobuf files are generated and imports are correct. Check that you're running from project root.

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: uv sync --all-packages

      - name: Run integration tests
        run: ./scripts/testing/test-mock.py
```

## Related Documentation

- **[Mock Environment Guide](../../services/controller_manager/MOCK_ENVIRONMENT.md)** - Complete mock hardware documentation
- **[Phase 14 Plan](../../planning/PHASE_14_MOCK_HARDWARE.md)** - Implementation details
- **[Game Coordinator README](../../services/game_coordinator/README.md)** - Game modes architecture
- **[Distributed Tracing](../../services/game_coordinator/DISTRIBUTED_TRACING.md)** - OpenTelemetry setup

## Development

### Adding New Tests

1. Create test function in `test_mock_environment.py`
2. Use `docker_compose` fixture for environment
3. Use gRPC clients to communicate with services
4. Use mock control API to simulate controller events

```python
@pytest.mark.asyncio
async def test_my_new_scenario(docker_compose):
    """Test description."""
    game_channel = grpc.aio.insecure_channel('localhost:50053')
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    # Your test logic here

    await game_channel.close()
```

### Running Subset of Tests

```bash
# Run tests matching pattern
uv run pytest -k "ffa" -v

# Run specific test file
uv run pytest test_mock_environment.py -v

# Run with verbose output
uv run pytest -vv

# Run with output capture disabled
uv run pytest -s
```

### Coverage Reports

```bash
# Run with coverage
uv run pytest --cov=. --cov-report=html

# View coverage report
open htmlcov/index.html
```

## Performance

Integration tests using testcontainers:

- **Startup time:** ~20-30 seconds (building + starting services)
- **Test execution:** ~10-20 seconds per test
- **Teardown time:** ~5 seconds
- **Total:** ~2-3 minutes for full suite

Parallelization is not recommended as tests share the same docker-compose environment.

## Contributing

When adding integration tests:

1. Keep tests focused and independent
2. Use descriptive test names
3. Clean up resources (gRPC channels, etc.)
4. Document expected behavior
5. Add to this README if needed
