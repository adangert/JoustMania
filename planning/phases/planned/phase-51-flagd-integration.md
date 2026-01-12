# Phase 52: Flagd Integration

**Status**: 📋 PLANNED
**Priority**: High
**Estimated Effort**: 1 week
**Dependencies**: Phase 49 (Profiles), Phase 51 (Rewards)
**Blocks**: Phase 53 (Web UI needs flag API)

---

## Overview

Replace the settings service with flagd for dynamic, runtime-configurable feature flags. Enable A/B testing, context-aware configuration, and real-time updates without service restarts.

**Goals:**
- Deploy flagd container alongside services
- Implement OpenFeature client in game coordinator
- Migrate existing settings to flag definitions
- Create flag evaluation with context (game mode, controller count, etc.)
- Enable runtime flag updates without restarts
- Prepare for Web UI flag management (Phase 53)

---

## Why This Phase Matters

**Current problems with settings service:**
- YAML file editing requires server restart
- No runtime configuration changes during demos
- No A/B testing capabilities
- No feature targeting based on context
- Separate from runtime config system

**After this phase:**
- Real-time flag updates without restarts
- Context-aware evaluation (different configs for different scenarios)
- Built-in experimentation (A/B tests, percentage rollouts)
- Centralized flag management
- Foundation for Web UI control (Phase 53)

---

## Architecture

### Component Overview

```
┌────────────────────────────────────────┐
│  Web UI (Phase 53)                     │
│  - Flag management interface           │
│  - Exposes /api/flags/config endpoint  │
└────────────────┬───────────────────────┘
                 │
                 │ HTTP sync (every 10s)
                 ▼
        ┌────────────────┐
        │  flagd         │  Standalone daemon
        │  (Sidecar)     │  - Syncs from HTTP
        │                │  - Evaluates flags
        └────────┬───────┘  - Serves via gRPC
                 │
                 │ gRPC - EvaluateFlag()
                 │
                 ▼
        ┌────────────────┐
        │ Game           │
        │ Coordinator    │  - OpenFeature client
        │                │  - Context evaluation
        └────────────────┘  - Fallback to defaults
```

### Flag Evaluation Flow

```
1. Game starts → Create evaluation context
   {
     "game_mode": "FFA",
     "controller_count": 25,
     "pi_model": "Pi5"
   }

2. Request flag value → OpenFeature client
   update_hz = client.get_number_value(
       "update_frequency_hz",
       default=30,
       context={"game_mode": "FFA", "controller_count": 25}
   )

3. Client calls flagd → gRPC EvaluateFlag()

4. Flagd evaluates targeting rules:
   - IF controller_count > 20 THEN return 30 (balanced)
   - IF pi_model == "Pi5" THEN return 60 (high_performance)
   - ELSE return 30 (default)

5. Return value → Game uses evaluated config
```

---

## Flag Definitions

### Core Performance Flags

```json
{
  "update_frequency_hz": {
    "state": "ENABLED",
    "variants": {
      "low_power": 15,
      "balanced": 30,
      "high_performance": 60
    },
    "defaultVariant": "balanced",
    "targeting": [
      {
        "if": [
          {"==": [{"var": "controller_count"}, 25]},
          "balanced",
          null
        ]
      },
      {
        "if": [
          {"==": [{"var": "pi_model"}, "Pi5"]},
          "high_performance",
          "balanced"
        ]
      }
    ]
  },

  "sensitivity_mode": {
    "state": "ENABLED",
    "variants": {
      "slowest": "SLOWEST",
      "slow": "SLOW",
      "medium": "MEDIUM",
      "fast": "FAST",
      "fastest": "FASTEST"
    },
    "defaultVariant": "medium"
  },

  "enable_audio": {
    "state": "ENABLED",
    "variants": {
      "on": true,
      "off": false
    },
    "defaultVariant": "on"
  }
}
```

### Experimental Flags

```json
{
  "streaming_mode": {
    "state": "ENABLED",
    "variants": {
      "bidirectional": "bidirectional",
      "unary_fallback": "unary_fallback",
      "hybrid": "hybrid"
    },
    "defaultVariant": "bidirectional",
    "targeting": [
      {
        "percentage": {
          "bidirectional": 50,
          "unary_fallback": 50
        }
      }
    ]
  },

  "enable_adaptive_rewards": {
    "state": "ENABLED",
    "variants": {
      "on": true,
      "off": false
    },
    "defaultVariant": false,
    "targeting": [
      {
        "if": [
          {"in": [{"var": "game_mode"}, ["FFA", "Nonstop"]]},
          "on",
          "off"
        ]
      }
    ]
  },

  "enable_dynamic_filtering": {
    "state": "ENABLED",
    "variants": {
      "on": true,
      "off": false
    },
    "defaultVariant": true
  }
}
```

### Team Mode Flags

```json
{
  "default_team_count": {
    "state": "ENABLED",
    "variants": {
      "two": 2,
      "three": 3,
      "four": 4
    },
    "defaultVariant": "two"
  },

  "nonstop_duration_seconds": {
    "state": "ENABLED",
    "variants": {
      "short": 60,
      "medium": 120,
      "long": 300
    },
    "defaultVariant": "medium"
  }
}
```

---

## Implementation Tasks

### Task 1: Add Flagd to Docker Compose

**File**: `docker-compose.yml`

```yaml
services:
  flagd:
    image: ghcr.io/open-feature/flagd:latest
    container_name: flagd
    command:
      - start
      - --uri
      - http://web-ui:8080/api/flags/config  # Will be implemented in Phase 53
      - --sync-provider
      - http
      - --sync-interval
      - 10s
    ports:
      - "8013:8013"  # gRPC port
    depends_on:
      - web-ui
    networks:
      - joustmania
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  game-coordinator:
    # ... existing config ...
    depends_on:
      - flagd  # Add dependency
    environment:
      - FLAGD_HOST=flagd
      - FLAGD_PORT=8013
```

**Testing flagd without Web UI (Phase 52):**

For Phase 52, use file-based sync until Web UI is ready:

```yaml
  flagd:
    command:
      - start
      - --uri
      - file:///flags/flags.json
      - --sync-provider
      - file
    volumes:
      - ./config/flags.json:/flags/flags.json:ro
```

Create `config/flags.json`:
```json
{
  "flags": {
    "update_frequency_hz": {
      "state": "ENABLED",
      "variants": {
        "balanced": 30,
        "high": 60
      },
      "defaultVariant": "balanced"
    },
    "enable_adaptive_rewards": {
      "state": "ENABLED",
      "variants": {
        "on": true,
        "off": false
      },
      "defaultVariant": false
    }
  }
}
```

### Task 2: Install OpenFeature SDK

**File**: `pyproject.toml`

```toml
[tool.poetry.dependencies]
openfeature-sdk = "^0.5.0"
openfeature-provider-flagd = "^0.2.0"
```

Install:
```bash
cd services/game_coordinator
poetry add openfeature-sdk openfeature-provider-flagd
```

### Task 3: Create FlagClient Wrapper

**File**: `services/game_coordinator/flags/client.py`

```python
"""OpenFeature flag client wrapper."""

import logging
import os
from typing import Any, Optional

from openfeature import api
from openfeature.evaluation_context import EvaluationContext
from openfeature.contrib.provider.flagd import FlagdProvider

logger = logging.getLogger(__name__)


class FlagClient:
    """Wrapper around OpenFeature client with JoustMania-specific context."""

    def __init__(self, flagd_host: str = "flagd", flagd_port: int = 8013):
        self.flagd_host = flagd_host
        self.flagd_port = flagd_port
        self._client = None
        self._connected = False

    def connect(self):
        """Connect to flagd and set up OpenFeature provider."""

        if self._connected:
            return

        try:
            # Create flagd provider
            provider = FlagdProvider(
                host=self.flagd_host,
                port=self.flagd_port
            )

            # Set as OpenFeature provider
            api.set_provider(provider)

            # Get client
            self._client = api.get_client()

            self._connected = True
            logger.info(f"Connected to flagd at {self.flagd_host}:{self.flagd_port}")

        except Exception as e:
            logger.error(f"Failed to connect to flagd: {e}", exc_info=True)
            logger.warning("Will use default flag values")
            self._connected = False

    def get_number(
        self,
        flag_key: str,
        default: float,
        game_mode: Optional[str] = None,
        controller_count: Optional[int] = None,
        **kwargs
    ) -> float:
        """
        Get number flag value.

        Args:
            flag_key: Flag key
            default: Default value if flag unavailable
            game_mode: Current game mode (for context)
            controller_count: Number of controllers (for context)
            **kwargs: Additional context attributes

        Returns:
            Flag value or default
        """

        if not self._connected:
            logger.debug(f"Flag '{flag_key}' using default: {default} (not connected)")
            return default

        try:
            # Build evaluation context
            context_dict = {}
            if game_mode:
                context_dict["game_mode"] = game_mode
            if controller_count is not None:
                context_dict["controller_count"] = controller_count
            context_dict.update(kwargs)

            context = EvaluationContext(**context_dict)

            # Evaluate flag
            result = self._client.get_number_value(
                flag_key=flag_key,
                default_value=default,
                evaluation_context=context
            )

            logger.debug(
                f"Flag '{flag_key}' evaluated: {result} "
                f"(context: {context_dict})"
            )

            return result

        except Exception as e:
            logger.error(f"Error evaluating flag '{flag_key}': {e}", exc_info=True)
            return default

    def get_string(
        self,
        flag_key: str,
        default: str,
        game_mode: Optional[str] = None,
        **kwargs
    ) -> str:
        """Get string flag value."""

        if not self._connected:
            return default

        try:
            context_dict = {}
            if game_mode:
                context_dict["game_mode"] = game_mode
            context_dict.update(kwargs)

            context = EvaluationContext(**context_dict)

            result = self._client.get_string_value(
                flag_key=flag_key,
                default_value=default,
                evaluation_context=context
            )

            logger.debug(f"Flag '{flag_key}' evaluated: {result}")
            return result

        except Exception as e:
            logger.error(f"Error evaluating flag '{flag_key}': {e}", exc_info=True)
            return default

    def get_boolean(
        self,
        flag_key: str,
        default: bool,
        game_mode: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Get boolean flag value."""

        if not self._connected:
            return default

        try:
            context_dict = {}
            if game_mode:
                context_dict["game_mode"] = game_mode
            context_dict.update(kwargs)

            context = EvaluationContext(**context_dict)

            result = self._client.get_boolean_value(
                flag_key=flag_key,
                default_value=default,
                evaluation_context=context
            )

            logger.debug(f"Flag '{flag_key}' evaluated: {result}")
            return result

        except Exception as e:
            logger.error(f"Error evaluating flag '{flag_key}': {e}", exc_info=True)
            return default


# Global flag client instance
_flag_client: Optional[FlagClient] = None


def get_flag_client() -> FlagClient:
    """Get global flag client instance."""
    global _flag_client
    if _flag_client is None:
        flagd_host = os.getenv("FLAGD_HOST", "flagd")
        flagd_port = int(os.getenv("FLAGD_PORT", "8013"))
        _flag_client = FlagClient(flagd_host, flagd_port)
        _flag_client.connect()
    return _flag_client
```

### Task 4: Integrate into Game Coordinator

**File**: `services/game_coordinator/server.py`

Initialize flag client at startup:

```python
from services.game_coordinator.flags.client import get_flag_client

async def serve():
    """Start game coordinator gRPC server."""

    # Initialize flag client
    flag_client = get_flag_client()
    logger.info("Flag client initialized")

    # ... rest of server startup ...
```

**File**: `services/game_coordinator/games/base.py`

Use flags instead of runtime config:

```python
from services.game_coordinator.flags.client import get_flag_client

class BaseGameMode(ABC):

    async def _game_loop(self):
        """Game loop with flag-based configuration."""

        logger.info("Starting game loop...")

        flag_client = get_flag_client()

        # Get configuration from flags (context-aware)
        update_frequency_hz = flag_client.get_number(
            "update_frequency_hz",
            default=30,
            game_mode=self.get_game_name(),
            controller_count=len(self.players)
        )

        streaming_mode = flag_client.get_string(
            "streaming_mode",
            default="bidirectional",
            game_mode=self.get_game_name()
        )

        enable_rewards = flag_client.get_boolean(
            "enable_adaptive_rewards",
            default=False,
            game_mode=self.get_game_name()
        )

        logger.info(
            f"Flag evaluation: Hz={update_frequency_hz}, "
            f"mode={streaming_mode}, rewards={enable_rewards}"
        )

        # Use evaluated values
        if streaming_mode == "bidirectional":
            await self._game_loop_bidirectional(update_frequency_hz)
        elif streaming_mode == "unary_fallback":
            await self._game_loop_unary(update_frequency_hz)

        # Apply rewards if enabled
        if enable_rewards and self.reward_engine:
            for player in self.players.values():
                await self.reward_engine.evaluate_and_apply(player, "per_game")
```

### Task 5: Migrate Settings Service Flags

**Current joustsettings.yaml → Flag mappings:**

| Setting | Flag Key | Type | Default |
|---------|----------|------|---------|
| `sensitivity` | `sensitivity_mode` | string | "MEDIUM" |
| `instructions` | `show_instructions` | boolean | true |
| `num_teams` | `default_team_count` | number | 2 |
| `nonstop_time_limit` | `nonstop_duration_seconds` | number | 120 |
| `play_audio` | `enable_audio` | boolean | true |
| `random_modes` | `random_mode_pool` | string[] | ["FFA","Teams"] |

**Migration strategy:**

1. **Phase 52:** Read from both (flags primary, settings fallback)
   ```python
   sensitivity = flag_client.get_string(
       "sensitivity_mode",
       default=settings.get("sensitivity", "MEDIUM")
   )
   ```

2. **Phase 53:** Settings service becomes read-only
3. **Phase 54+:** Remove settings service entirely

**File**: `services/game_coordinator/games/base.py`

```python
async def _load_settings(self):
    """Enhanced to read from flags first, settings as fallback."""

    flag_client = get_flag_client()

    # Try flag first, fallback to settings
    sensitivity_str = flag_client.get_string(
        "sensitivity_mode",
        default=None,
        game_mode=self.get_game_name()
    )

    if not sensitivity_str:
        # Fallback to settings service
        response = await self.settings_client.GetSettings(...)
        sensitivity_str = response.settings.get("sensitivity", "MEDIUM")

    # Parse sensitivity
    if sensitivity_str.upper() in Sensitivity.__members__:
        self.sensitivity = Sensitivity[sensitivity_str.upper()]

    logger.info(f"Sensitivity loaded: {self.sensitivity.name}")
```

### Task 6: Add Flag Change Metrics

**File**: `services/game_coordinator/metrics.py`

```python
# Flag evaluation metrics
flag_evaluations_total = Counter(
    'flag_evaluations_total',
    'Total flag evaluations',
    ['flag_key', 'variant']
)

flag_evaluation_errors_total = Counter(
    'flag_evaluation_errors_total',
    'Total flag evaluation errors',
    ['flag_key', 'error_type']
)

flag_evaluation_duration_seconds = Histogram(
    'flag_evaluation_duration_seconds',
    'Time to evaluate flag',
    ['flag_key'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1]
)

flagd_connection_status = Gauge(
    'flagd_connection_status',
    'Flagd connection status (1=connected, 0=disconnected)'
)
```

Update FlagClient to emit metrics:

```python
def get_number(self, flag_key, default, **kwargs):
    """Enhanced with metrics."""

    start_time = time.time()

    try:
        result = self._client.get_number_value(...)

        # Emit metrics
        from services.game_coordinator import metrics
        metrics.flag_evaluations_total.labels(
            flag_key=flag_key,
            variant=str(result)
        ).inc()
        metrics.flag_evaluation_duration_seconds.labels(
            flag_key=flag_key
        ).observe(time.time() - start_time)

        return result

    except Exception as e:
        metrics.flag_evaluation_errors_total.labels(
            flag_key=flag_key,
            error_type=type(e).__name__
        ).inc()
        return default
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/unit/flags/test_client.py`

```python
def test_flag_client_number_evaluation():
    """Test number flag evaluation."""

    client = FlagClient(host="localhost", port=8013)
    client.connect()

    value = client.get_number(
        "update_frequency_hz",
        default=30,
        controller_count=25
    )

    assert value in [15, 30, 60]  # Valid variants


def test_flag_client_fallback_on_error():
    """Test fallback to default when flagd unavailable."""

    client = FlagClient(host="invalid", port=9999)
    client.connect()  # Will fail

    value = client.get_number("update_frequency_hz", default=30)

    assert value == 30  # Used default


def test_flag_context_evaluation():
    """Test context-aware flag evaluation."""

    client = FlagClient()
    client.connect()

    # Different contexts should potentially get different values
    value_ffa = client.get_number(
        "update_frequency_hz",
        default=30,
        game_mode="FFA",
        controller_count=10
    )

    value_nonstop = client.get_number(
        "update_frequency_hz",
        default=30,
        game_mode="Nonstop",
        controller_count=25
    )

    # Values may differ based on targeting rules
    logger.info(f"FFA: {value_ffa}, Nonstop: {value_nonstop}")
```

### Integration Tests

**File**: `tests/integration/test_flagd_integration.py`

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_flagd_in_game_loop():
    """Test flag evaluation during actual gameplay."""

    # Start flagd container (or assume running)
    # Create game
    game = FFAGame(...)

    # Run game (will evaluate flags)
    await game.run()

    # Verify flags were evaluated
    # Check metrics for flag_evaluations_total


@pytest.mark.integration
@pytest.mark.asyncio
async def test_flag_change_during_gameplay():
    """Test that flag changes propagate within 10 seconds."""

    # Start game
    game = FFAGame(...)

    # Record initial Hz
    initial_hz = game.update_frequency_hz

    # Change flag in flagd (via file or API)
    update_flag("update_frequency_hz", 60)

    # Wait for sync (10s)
    await asyncio.sleep(12)

    # Start new game
    game2 = FFAGame(...)
    await game2.run()

    # Verify new game uses updated flag
    assert game2.update_frequency_hz == 60
```

### Manual Testing Checklist

**Test 1: Flagd Connection**
- [ ] Start flagd container: `docker compose up -d flagd`
- [ ] Check logs: `docker logs flagd`
- [ ] Verify sync: "Successfully synced flags"
- [ ] Query metric: `flagd_connection_status` should be 1

**Test 2: Flag Evaluation**
- [ ] Start FFA game with 10 controllers
- [ ] Check logs for "Flag evaluation: Hz=..."
- [ ] Verify value from `update_frequency_hz` flag
- [ ] Query metric: `flag_evaluations_total{flag_key="update_frequency_hz"}`

**Test 3: Context-Aware Evaluation**
- [ ] Update flag with targeting: `controller_count > 20 → Hz=30`
- [ ] Start game with 25 controllers
- [ ] Verify Hz=30 (not default)
- [ ] Start game with 10 controllers
- [ ] Verify Hz=default

**Test 4: Flag Change Propagation**
- [ ] Update `config/flags.json`: change `update_frequency_hz` to 60
- [ ] Wait 12 seconds (sync interval + buffer)
- [ ] Start new game
- [ ] Verify Hz=60
- [ ] Check logs: "Flag 'update_frequency_hz' evaluated: 60"

**Test 5: Fallback to Defaults**
- [ ] Stop flagd: `docker compose stop flagd`
- [ ] Start game
- [ ] Verify game uses default values
- [ ] Check logs: "not connected" warnings
- [ ] Check metric: `flagd_connection_status` should be 0

---

## Files to Create

```
services/game_coordinator/flags/
├── __init__.py
├── client.py              # FlagClient wrapper
└── definitions.py         # Flag schema definitions (for Phase 53)

config/
└── flags.json             # Initial flag definitions (file-based)

tests/unit/flags/
└── test_client.py

tests/integration/
└── test_flagd_integration.py
```

## Files to Modify

- `docker-compose.yml` - Add flagd service
- `docker-compose.mock.yml` - Add flagd service
- `pyproject.toml` - Add OpenFeature dependencies
- `services/game_coordinator/server.py` - Initialize flag client
- `services/game_coordinator/games/base.py` - Use flags instead of runtime config
- `services/game_coordinator/metrics.py` - Add flag metrics

---

## Migration Path

### Week 1: Flagd Setup (Phase 52)

**Days 1-2:** Infrastructure
- Add flagd to docker-compose
- Create initial flags.json
- Deploy and test flagd connectivity

**Days 3-4:** Client Implementation
- Implement FlagClient wrapper
- Add unit tests
- Integrate into game coordinator

**Days 5-6:** Migration
- Update game loop to use flags
- Implement fallback logic (flags → settings → defaults)
- Test with multiple game modes

**Day 7:** Validation
- Integration testing
- Performance testing
- Documentation

### Post-Phase 52: Parallel Operation

**Weeks 2-3:** Both systems running
- Flags primary, settings fallback
- Monitor for discrepancies
- Build confidence in flagd

### Phase 53: Web UI Integration

- Replace file-based sync with HTTP endpoint
- Add flag management UI
- Settings service becomes read-only

### Phase 54+: Deprecation

- Remove settings service calls
- Remove joustsettings.yaml
- Remove settings service container

---

## Success Criteria

- [ ] Flagd container deploys successfully
- [ ] OpenFeature client connects to flagd
- [ ] Flags evaluated with context (game mode, controller count)
- [ ] Flag changes propagate within 10 seconds
- [ ] Fallback to defaults when flagd unavailable
- [ ] All existing settings migrated to flags
- [ ] Flag evaluation <5ms (p95)
- [ ] Metrics track flag evaluations and errors
- [ ] Unit tests pass (>85% coverage)
- [ ] Integration tests pass
- [ ] No gameplay regressions
- [ ] Documentation complete

---

## Rollback Plan

If issues arise:

1. **Environment variable**: `USE_FLAGS=false` to disable flag client
2. **Graceful fallback**: Flag evaluation errors use defaults
3. **Keep settings service**: Run in parallel for quick rollback
4. **Revert docker-compose**: Remove flagd, use old config

---

## Next Phase

**Phase 53: Web UI Enhancements** will:
- Create flag management interface in Web UI
- Implement `/api/flags/config` HTTP endpoint for flagd sync
- Add player profile viewer
- Create experiment dashboard
- Enable runtime flag updates via UI

**Dependencies**: Requires Phase 52 flagd integration to be stable.

---

**End of Phase 52**
