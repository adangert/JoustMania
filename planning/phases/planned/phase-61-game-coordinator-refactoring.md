# Phase 61: Game Coordinator Server Refactoring

**Status:** PLANNED
**Priority:** MEDIUM
**Estimated Effort:** Medium (1-2 days)

## Goal

Extract cohesive logic from the game coordinator `server.py` (730 lines) into focused modules to improve maintainability, testability, and code organization.

## Motivation

The `server.py` file has grown to handle multiple responsibilities:
- gRPC service implementation
- Game instantiation/factory logic
- Event publishing/streaming
- gRPC client lifecycle management
- Telemetry initialization
- System metrics collection

This violates the Single Responsibility Principle and makes the code harder to:
- Test individual components in isolation
- Understand the flow at a glance
- Modify one concern without risking others
- Reuse logic across services

## Current State Analysis

### File: `services/game_coordinator/server.py` (730 lines)

| Lines | Component | Responsibility |
|-------|-----------|----------------|
| 68-94 | `init_telemetry()` | OpenTelemetry setup |
| 108-151 | `__init__()` | Initialization, config |
| 152-210 | Client management | gRPC channel lifecycle |
| 212-277 | `StartGame()` | RPC handler |
| 279-458 | Game loop | Thread management, game factory |
| 460-513 | `GetGameStatus()` | RPC handler |
| 515-558 | `ForceEndGame()` | RPC handler |
| 560-638 | Event streaming | Pub/sub implementation |
| 640-656 | `shutdown()` | Cleanup |
| 659-727 | `serve()` | Server bootstrap |

## Extraction Plan

### Task 1: Extract Telemetry Initialization to Shared Library

**Files:**
- Create: `lib/telemetry.py`
- Modify: `services/game_coordinator/server.py`

**Rationale:** `init_telemetry()` is nearly identical across all services. Extract to shared library.

**New Module: `lib/telemetry.py`**
```python
"""
Shared OpenTelemetry initialization for JoustMania services.
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def init_telemetry(service_name: str | None = None, version: str = "1.0.0") -> trace.Tracer:
    """
    Initialize OpenTelemetry with OTLP exporter.

    Args:
        service_name: Service name (defaults to OTEL_SERVICE_NAME env var)
        version: Service version

    Returns:
        Configured tracer instance
    """
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    service_name = service_name or os.getenv("OTEL_SERVICE_NAME", "unknown-service")

    resource = Resource(
        attributes={
            SERVICE_NAME: service_name,
            SERVICE_VERSION: version,
            "service.namespace": "joustmania",
        }
    )

    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    GrpcInstrumentorServer().instrument()
    GrpcInstrumentorClient().instrument()

    logger.info(f"OpenTelemetry initialized: {service_name} -> {otlp_endpoint}")
    return trace.get_tracer(service_name)
```

**Lines Removed from server.py:** ~30

---

### Task 2: Extract Game Factory

**Files:**
- Create: `services/game_coordinator/game_factory.py`
- Modify: `services/game_coordinator/server.py`

**Rationale:** The if/elif chain for game instantiation (lines 327-422) is a classic Factory pattern. Extracting it:
- Makes adding new game modes trivial
- Enables testing game creation independently
- Removes ~100 lines from server.py

**New Module: `services/game_coordinator/game_factory.py`**
```python
"""
Game Factory - Creates game instances based on game mode name.
"""

import logging
from typing import Callable, Optional

from services.game_coordinator.games import ffa, nonstop_joust, random_teams, teams
from services.game_coordinator.games.base import GameBase

logger = logging.getLogger(__name__)


# Game mode name mappings (lowercase -> canonical name)
GAME_MODE_ALIASES = {
    # FFA
    "ffa": "ffa",
    "free-for-all": "ffa",
    "joust free-for-all": "ffa",
    # Teams
    "teams": "teams",
    "joust teams": "teams",
    # Random Teams
    "random teams": "random_teams",
    "joust random teams": "random_teams",
    "random_teams": "random_teams",
    # Nonstop Joust
    "nonstop": "nonstop_joust",
    "nonstop joust": "nonstop_joust",
    "nonstopjoust": "nonstop_joust",
}


class GameFactory:
    """Factory for creating game instances."""

    @staticmethod
    def create_game(
        game_name: str,
        controller_manager_client,
        settings_client,
        event_publisher: Callable,
        audio_client,
        game_id: str,
        initial_players: list,
        settings: dict[str, str] | None = None,
    ) -> Optional[GameBase]:
        """
        Create a game instance based on game mode name.

        Args:
            game_name: Game mode name (case-insensitive, supports aliases)
            controller_manager_client: gRPC client for controller manager
            settings_client: gRPC client for settings service
            event_publisher: Callback for publishing game events
            audio_client: gRPC client for audio service
            game_id: Unique game identifier
            initial_players: List of Player protobuf messages
            settings: Optional game-specific settings dict

        Returns:
            Game instance or None if game mode not found

        Raises:
            ValueError: If game mode is not recognized
        """
        settings = settings or {}
        canonical_name = GAME_MODE_ALIASES.get(game_name.lower())

        if canonical_name is None:
            raise ValueError(f"Unknown game mode: '{game_name}'")

        common_args = {
            "controller_manager_client": controller_manager_client,
            "settings_client": settings_client,
            "event_publisher": event_publisher,
            "audio_client": audio_client,
            "game_id": game_id,
            "initial_players": initial_players,
        }

        if canonical_name == "ffa":
            logger.info("Creating FFA game")
            return ffa.FFAGame(**common_args)

        elif canonical_name == "teams":
            num_teams = int(settings.get("num_teams", "2"))
            logger.info(f"Creating Teams game with {num_teams} teams")
            return teams.SimpleTeamsGame(num_teams=num_teams, **common_args)

        elif canonical_name == "random_teams":
            num_teams = int(settings.get("num_teams", "2"))
            logger.info(f"Creating Random Teams game with {num_teams} teams")
            return random_teams.RandomTeamsGame(num_teams=num_teams, **common_args)

        elif canonical_name == "nonstop_joust":
            logger.info("Creating Nonstop Joust game")
            return nonstop_joust.NonstopJoustGame(**common_args)

        # Should never reach here due to alias check above
        raise ValueError(f"Game mode '{canonical_name}' not implemented")

    @staticmethod
    def get_supported_modes() -> list[str]:
        """Return list of canonical game mode names."""
        return list(set(GAME_MODE_ALIASES.values()))

    @staticmethod
    def is_valid_mode(game_name: str) -> bool:
        """Check if a game mode name is valid."""
        return game_name.lower() in GAME_MODE_ALIASES
```

**Lines Removed from server.py:** ~100

---

### Task 3: Extract Event Bus

**Files:**
- Create: `services/game_coordinator/event_bus.py`
- Modify: `services/game_coordinator/server.py`

**Rationale:** Event publishing and streaming (lines 560-638) form a cohesive pub/sub system that can be independently tested and potentially reused.

**New Module: `services/game_coordinator/event_bus.py`**
```python
"""
Event Bus - Pub/sub system for game events.
"""

import asyncio
import logging
import threading
import time
from typing import Callable, Optional

from opentelemetry import trace

from proto import game_coordinator_pb2

logger = logging.getLogger(__name__)


class EventBus:
    """
    Thread-safe event bus for game coordinator events.

    Supports:
    - Multiple async subscribers via queues
    - State synchronization callbacks
    - Span event recording for observability
    """

    def __init__(self, state_sync_callback: Optional[Callable[[str], None]] = None):
        """
        Initialize event bus.

        Args:
            state_sync_callback: Optional callback(event_type) for state synchronization
        """
        self.subscribers: dict[str, asyncio.Queue] = {}
        self.event_lock = asyncio.Lock()
        self._state_lock = threading.Lock()
        self._state_sync_callback = state_sync_callback

    async def subscribe(self, subscriber_id: str, max_queue_size: int = 100) -> asyncio.Queue:
        """
        Subscribe to events.

        Args:
            subscriber_id: Unique subscriber identifier
            max_queue_size: Maximum queue size before events are dropped

        Returns:
            Queue that will receive GameEvent messages
        """
        event_queue = asyncio.Queue(maxsize=max_queue_size)
        async with self.event_lock:
            self.subscribers[subscriber_id] = event_queue
        logger.info(f"New event subscriber: {subscriber_id}")
        return event_queue

    async def unsubscribe(self, subscriber_id: str):
        """Remove a subscriber."""
        async with self.event_lock:
            if subscriber_id in self.subscribers:
                del self.subscribers[subscriber_id]
        logger.info(f"Event subscriber removed: {subscriber_id}")

    def publish(self, event_type: str, data: dict[str, str]):
        """
        Publish an event to all subscribers (thread-safe).

        Args:
            event_type: Type of event (e.g., "game_started", "player_death")
            data: Event data as string key-value pairs
        """
        # Thread-safe subscriber snapshot
        with self._state_lock:
            subscribers_snapshot = dict(self.subscribers)

        # Notify state sync callback
        if self._state_sync_callback:
            self._state_sync_callback(event_type)

        # Record as span event
        current_span = trace.get_current_span()
        if current_span.is_recording():
            attributes = {
                "event.type": event_type,
                "subscribers.count": len(subscribers_snapshot),
                **{k: str(v) for k, v in data.items()},
            }
            current_span.add_event(event_type, attributes=attributes)

        # Create protobuf event
        string_data = {k: str(v) for k, v in data.items()}
        event = game_coordinator_pb2.GameEvent(
            event_type=event_type,
            data=string_data,
            timestamp=int(time.time() * 1000),
        )

        # Publish to all subscribers
        for sub_id, event_queue in subscribers_snapshot.items():
            try:
                event_queue.put_nowait(event)
                logger.debug(f"Published {event_type} to subscriber {sub_id}")
            except asyncio.QueueFull:
                logger.warning(f"Subscriber {sub_id} queue full, skipping event")
            except Exception as e:
                logger.error(f"Error publishing to subscriber {sub_id}: {e}")
```

**Lines Removed from server.py:** ~80

---

### Task 4: Extract gRPC Client Manager

**Files:**
- Create: `services/game_coordinator/client_manager.py`
- Modify: `services/game_coordinator/server.py`

**Rationale:** gRPC client lifecycle (init, cleanup) is a separate concern from game coordination logic.

**New Module: `services/game_coordinator/client_manager.py`**
```python
"""
gRPC Client Manager - Manages connections to dependent services.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from lib.grpc_utils import create_channel
from proto import audio_pb2_grpc, controller_manager_pb2_grpc, settings_pb2_grpc

logger = logging.getLogger(__name__)


@dataclass
class ServiceClients:
    """Container for gRPC service clients."""
    controller_manager: Optional[controller_manager_pb2_grpc.ControllerManagerServiceStub] = None
    settings: Optional[settings_pb2_grpc.SettingsServiceStub] = None
    audio: Optional[audio_pb2_grpc.AudioServiceStub] = None


class ClientManager:
    """
    Manages gRPC client connections to dependent services.

    Handles:
    - Lazy connection initialization
    - Graceful channel cleanup
    - Configuration from environment
    """

    def __init__(self):
        """Initialize client manager with service addresses from environment."""
        self.controller_manager_address = (
            f"{os.getenv('CONTROLLER_MANAGER_HOST', 'controller-manager')}:"
            f"{os.getenv('CONTROLLER_MANAGER_PORT', '50052')}"
        )
        self.settings_address = (
            f"{os.getenv('SETTINGS_HOST', 'settings')}:"
            f"{os.getenv('SETTINGS_PORT', '50051')}"
        )
        self.audio_address = (
            f"{os.getenv('AUDIO_HOST', 'audio')}:"
            f"{os.getenv('AUDIO_PORT', '50054')}"
        )

        self._controller_manager_channel = None
        self._settings_channel = None
        self._audio_channel = None

        self.clients = ServiceClients()

    async def initialize(self) -> ServiceClients:
        """
        Initialize all gRPC client connections.

        Returns:
            ServiceClients with initialized stubs
        """
        try:
            # Controller Manager
            self._controller_manager_channel = create_channel(self.controller_manager_address)
            self.clients.controller_manager = controller_manager_pb2_grpc.ControllerManagerServiceStub(
                self._controller_manager_channel
            )
            logger.info(f"Connected to ControllerManager at {self.controller_manager_address}")

            # Settings
            self._settings_channel = create_channel(self.settings_address)
            self.clients.settings = settings_pb2_grpc.SettingsServiceStub(self._settings_channel)
            logger.info(f"Connected to Settings at {self.settings_address}")

            # Audio
            self._audio_channel = create_channel(self.audio_address)
            self.clients.audio = audio_pb2_grpc.AudioServiceStub(self._audio_channel)
            logger.info(f"Connected to Audio at {self.audio_address}")

        except Exception as e:
            logger.error(f"Failed to initialize gRPC clients: {e}")
            self.clients = ServiceClients()  # Reset to None clients

        return self.clients

    async def cleanup(self):
        """Close all gRPC channels."""
        channels = [
            ("controller_manager", self._controller_manager_channel),
            ("settings", self._settings_channel),
            ("audio", self._audio_channel),
        ]

        for name, channel in channels:
            if channel:
                try:
                    await channel.close()
                    logger.debug(f"Closed {name} channel")
                except Exception as e:
                    logger.warning(f"Error closing {name} channel: {e}")

        self._controller_manager_channel = None
        self._settings_channel = None
        self._audio_channel = None
        self.clients = ServiceClients()

        logger.info("All gRPC channels closed")
```

**Lines Removed from server.py:** ~70

---

### Task 5: Extract System Metrics Collector

**Files:**
- Modify: `services/game_coordinator/metrics.py`
- Modify: `services/game_coordinator/server.py`

**Rationale:** The `collect_system_metrics()` nested function can be moved to the metrics module for consistency.

**Add to `services/game_coordinator/metrics.py`:**
```python
async def start_system_metrics_collector(interval: float = 10.0):
    """
    Start background task to collect system metrics.

    Args:
        interval: Collection interval in seconds
    """
    import asyncio
    import psutil

    process = psutil.Process()
    loop = asyncio.get_event_loop()

    while True:
        try:
            cpu_percent = await loop.run_in_executor(
                None, lambda: process.cpu_percent(interval=None)
            )
            mem_info = await loop.run_in_executor(None, process.memory_info)
            thread_count = await loop.run_in_executor(None, process.num_threads)

            process_cpu_percent.set(cpu_percent)
            process_memory_mb.set(mem_info.rss / 1024 / 1024)
            process_threads.set(thread_count)
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")

        await asyncio.sleep(interval)
```

**Lines Removed from server.py:** ~25

---

## Summary of Changes

| Module | Lines Added | Lines Removed from server.py |
|--------|-------------|------------------------------|
| `lib/telemetry.py` | ~45 | ~30 |
| `game_factory.py` | ~100 | ~100 |
| `event_bus.py` | ~100 | ~80 |
| `client_manager.py` | ~90 | ~70 |
| `metrics.py` (addition) | ~25 | ~25 |
| **Total** | ~360 | ~305 |

**Final server.py size:** ~425 lines (from 730)

## Resulting Architecture

```
services/game_coordinator/
├── server.py              # gRPC handlers + orchestration (~425 lines)
├── game_factory.py        # Game instantiation
├── event_bus.py           # Pub/sub for game events
├── client_manager.py      # gRPC client lifecycle
├── metrics.py             # Prometheus metrics + collector
└── games/
    ├── base.py
    ├── ffa.py
    ├── teams.py
    ├── random_teams.py
    └── nonstop_joust.py

lib/
├── telemetry.py           # Shared OTEL init (NEW)
└── grpc_utils.py          # Existing shared utilities
```

## Testing

### Unit Tests to Add

- `tests/game_coordinator/test_game_factory.py`
  - Test each game mode creation
  - Test invalid mode handling
  - Test alias resolution

- `tests/game_coordinator/test_event_bus.py`
  - Test subscribe/unsubscribe
  - Test publish to multiple subscribers
  - Test queue full handling

- `tests/game_coordinator/test_client_manager.py`
  - Test initialization
  - Test cleanup
  - Test partial failure handling

### Integration Tests

- Existing integration tests should continue to pass
- No API changes

## Success Criteria

- [ ] server.py reduced to <450 lines
- [ ] Each extracted module has single responsibility
- [ ] All existing tests pass
- [ ] New unit tests for extracted modules
- [ ] No changes to gRPC API
- [ ] Integration tests pass

## Dependencies

- None (internal refactoring only)

## Performance Impact

**Negligible:**
- Same code, different organization
- Slightly more module imports (microseconds)
- No runtime behavior changes

## Risks

**Low:**
- Internal refactoring only
- No API changes
- Comprehensive test coverage ensures correctness

## Implementation Order

1. **Task 1: Telemetry** - Lowest risk, highest reuse potential
2. **Task 2: Game Factory** - Biggest impact, well-defined boundaries
3. **Task 3: Event Bus** - Clean separation, improves testability
4. **Task 4: Client Manager** - Moderate impact
5. **Task 5: Metrics Collector** - Smallest change

## Notes

- Each task can be implemented and tested independently
- Consider adding the extracted modules to other services that have similar patterns
- The `lib/telemetry.py` module could replace init_telemetry() in all services in a follow-up
