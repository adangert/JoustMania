# Testing Guidelines

## Unit Tests

Run unit tests from within the service directory using `uv`:

```bash
cd services/<service-name>
uv run pytest                      # Run all tests
uv run pytest -v                   # Verbose output
uv run pytest -x                   # Stop on first failure
uv run pytest -k test_name         # Run specific test
uv run pytest tests/test_file.py   # Run specific file
```

Each service has its own virtual environment managed by `uv`. The `pyproject.toml` in each service defines test dependencies.

## Integration Tests

Integration tests run with Docker Compose:

```bash
make test                    # Full test suite (starts and stops containers)
SKIP_TEARDOWN=1 make test    # Keep containers running after tests
```

Use `SKIP_TEARDOWN=1` when:
- Debugging test failures
- Inspecting container logs
- Running tests repeatedly during development
- Checking Grafana dashboards or Jaeger traces

To manually stop containers after using SKIP_TEARDOWN:
```bash
docker compose -f docker-compose.test.yml down
```

## Test Structure

Each service follows this pattern:
```
services/<service>/
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Pytest fixtures
│   ├── test_servicer.py     # gRPC servicer tests
│   └── test_<module>.py     # Unit tests per module
└── pyproject.toml           # Test deps in [project.optional-dependencies]
```

## Proto Changes

After modifying `.proto` files:
```bash
make protos    # Regenerate Python bindings
make test      # Run full integration tests
```

## Mocking

- Use `unittest.mock` for service dependencies
- Controller Manager has a mock backend (`CONTROLLER_BACKEND=mock`)
- Tests use `MockControllerManagerService`, `MockSettingsService`, etc.
