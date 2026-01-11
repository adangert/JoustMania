# Phase 33: Code Quality Improvements

**Status:** 💎 PLANNED
**Priority:** LOW - Technical debt

## Goal
Improve code maintainability and reduce duplication

## Motivation
- gRPC channel options duplicated 5+ times
- Type hints missing in many places
- Error handling inconsistent
- Logger info spam creates noise

## Tasks

**1. Shared Utilities Module**
- [ ] Create `common/grpc_utils.py`
  - [ ] Extract shared channel options
  - [ ] Create channel factory function
  - [ ] Add connection pooling helper
  - **Files:** `common/grpc_utils.py` (new)

```python
# common/grpc_utils.py
def get_optimized_channel_options():
    """Get standard gRPC channel options for JoustMania services."""
    return [
        ('grpc.keepalive_time_ms', 30000),
        ('grpc.keepalive_timeout_ms', 5000),
        ('grpc.keepalive_permit_without_calls', True),
        ('grpc.http2.max_pings_without_data', 2),
        ('grpc.initial_reconnect_backoff_ms', 1000),
        ('grpc.max_reconnect_backoff_ms', 5000),
        ('grpc.max_receive_message_length', 10 * 1024 * 1024),
        ('grpc.max_send_message_length', 10 * 1024 * 1024),
        ('grpc.default_compression_algorithm', grpc.Compression.Gzip),
    ]

def create_channel(address: str, **kwargs):
    """Create gRPC channel with standard options."""
    options = get_optimized_channel_options()
    return grpc.aio.insecure_channel(address, options=options, **kwargs)
```

- [ ] Update all services to use shared utilities
  - **Files:** All services with channel creation

**2. Type Hints**
- [ ] Add type hints to all game mode constructors
  - **Files:** `services/game_coordinator/games/*.py`

```python
from typing import Callable, Dict

def __init__(
    self,
    controller_manager_client: controller_manager_pb2_grpc.ControllerManagerServiceStub,
    settings_client: settings_pb2_grpc.SettingsServiceStub,
    event_publisher: Callable[[str, Dict[str, str]], None],
    game_id: str = ""
):
```

- [ ] Add type hints to service methods
- [ ] Enable mypy type checking in CI

**3. Error Message Standardization**
- [ ] Create error constants
  - **Files:** `common/errors.py` (new)

```python
class ServiceErrors(Enum):
    ALREADY_RUNNING = "Service is already running"
    ALREADY_STOPPED = "Service is already stopped"
    NOT_FOUND = "Resource not found"
    INVALID_INPUT = "Invalid input provided"
    SERVICE_UNAVAILABLE = "Service temporarily unavailable"
```

- [ ] Use constants in all error responses
- [ ] Consistent error format across services

**4. Logger Level Cleanup**
- [ ] Change high-frequency logs to DEBUG
  - [ ] Controller state updates: INFO → DEBUG
  - [ ] Button press events: INFO → DEBUG
  - [ ] gRPC channel creation: INFO → DEBUG
  - **Files:** All services

- [ ] Reserve INFO for significant events
  - [ ] Game start/stop
  - [ ] Player deaths/victories
  - [ ] Service startup/shutdown
  - [ ] Admin mode entry/exit

**5. Input Validation**
- [ ] Add validation to all gRPC endpoints
  - [ ] Button names in valid set
  - [ ] Game names in supported list
  - [ ] Serial numbers non-empty
  - [ ] Numeric ranges validated
  - **Files:** All service server.py files

```python
VALID_BUTTONS = {"trigger", "move", "cross", "circle", "square", "triangle", "ps"}

if button not in VALID_BUTTONS:
    return ProcessInputResponse(
        success=False,
        error=f"Invalid button: {button}"
    )
```

**6. Remove Code Duplication**
- [ ] Extract common game mode patterns
  - [ ] Countdown logic (identical in FFA, Teams, RandomTeams)
  - [ ] Death detection (similar across games)
  - [ ] Settings loading (duplicated)
  - **Files:** `services/game_coordinator/games/base_game.py` (new)

## Expected Improvements
- 30% reduction in code duplication
- Better IDE auto-completion (type hints)
- Consistent error messages
- Cleaner logs (less noise)
- Easier to add new game modes

## Success Criteria
- Zero code duplication for channel options
- All public methods have type hints
- mypy passes with no errors
- Logger output readable and useful
- All inputs validated before use
