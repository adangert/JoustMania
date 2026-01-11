# Phase 44: OpenFeature Integration for Configuration Experiments

**Status:** 📋 PLANNED
**Priority:** MEDIUM
**Estimated Effort:** Small-Medium (1-2 days)
**Depends On:** Phase 43 (Runtime Configuration)

## Goal

Integrate [OpenFeature](https://openfeature.dev/) for feature flagging and A/B testing of JoustMania configurations. Enable controlled rollout of new settings and data-driven configuration experiments.

## Motivation

### Current Gap (Post-Phase 43)

**Phase 43 provides:**
- ✅ Runtime configuration (change Hz without restart)
- ✅ Live monitoring dashboards
- ✅ Manual configuration changes via gRPC

**Missing capabilities:**
- ❌ A/B testing configurations (30Hz vs 60Hz) with user segmentation
- ❌ Gradual rollout of new settings (canary deployments)
- ❌ Remote configuration management (no SSH needed)
- ❌ Experiment tracking (which config performed better)
- ❌ Multi-variant testing (test 3+ configs simultaneously)

### Use Cases

**1. Configuration Experiments**
```
Question: Is 30Hz or 60Hz better for 25 controllers?
Approach:
- 50% of games use 30Hz
- 50% of games use 60Hz
- Measure: CPU, latency, disconnects, player satisfaction
- After 50 games: Data shows winner
```

**2. Sensitivity Tuning**
```
Question: Should MEDIUM sensitivity threshold be 1.6 or 1.8?
Approach:
- Group A: threshold = 1.6
- Group B: threshold = 1.8
- Measure: Death count, false positives, player feedback
- Roll out winner to 100%
```

**3. Hardware-Specific Configs**
```
Feature flag: "pi5_optimized_settings"
- Pi 5: 60Hz (has CPU headroom)
- Pi 4: 30Hz (CPU constrained)
- Pi 3: 15Hz (very constrained)
- Auto-detect and apply
```

**4. Gradual Rollout**
```
New feature: Adaptive Hz
- Day 1: 10% of games get adaptive Hz
- Day 3: 50% of games
- Day 7: 100% if no issues
- Rollback if CPU >70%
```

## Architecture

### OpenFeature Components

**1. Feature Flag Provider**

Options:
- **LaunchDarkly** (SaaS, free tier for open source)
- **Flagsmith** (self-hosted or SaaS, open source)
- **PostHog** (includes analytics, open source)
- **File-based** (local YAML, simple for development)

**Recommendation:** Start with file-based, add cloud provider later

**2. Flag Definitions**

```yaml
# config/feature_flags.yaml

# Core performance flags
update_frequency_hz:
  type: number
  default: 30
  variants:
    - name: "low_power"
      value: 15
    - name: "balanced"
      value: 30
    - name: "high_performance"
      value: 60
  targeting:
    - rule: "controller_count > 20"
      variant: "balanced"
    - rule: "pi_model == 'Pi5'"
      variant: "high_performance"

sensitivity_threshold:
  type: number
  default: 1.6
  variants:
    - name: "control"
      value: 1.6
    - name: "treatment"
      value: 1.8
  rollout:
    percentage: 50  # 50% get treatment

enable_adaptive_hz:
  type: boolean
  default: false
  rollout:
    percentage: 10  # Canary: 10% of games

usb_check_interval_sec:
  type: number
  default: 30
  variants:
    - name: "frequent"
      value: 15
    - name: "normal"
      value: 30
    - name: "infrequent"
      value: 60
```

**3. Integration with Runtime Config**

```python
# services/game_coordinator/runtime_config.py

from openfeature import api
from openfeature.provider import InMemoryProvider

class RuntimeConfigManager:
    def __init__(self):
        self.config = GamePerformanceConfig()
        self._feature_client = None
        self._setup_openfeature()

    def _setup_openfeature(self):
        """Initialize OpenFeature with file-based provider."""
        # Use file-based provider for local development
        provider = InMemoryProvider()
        api.set_provider(provider)
        self._feature_client = api.get_client()

    async def get_config_for_context(self, context: dict) -> GamePerformanceConfig:
        """
        Get configuration based on feature flags and context.

        Context example:
        {
            "game_id": "game_123",
            "controller_count": 25,
            "pi_model": "Pi5",
            "game_mode": "FFA"
        }
        """
        # Fetch feature flags with context
        update_frequency_hz = self._feature_client.get_number_value(
            key="update_frequency_hz",
            default=30,
            evaluation_context=context
        )

        sensitivity_threshold = self._feature_client.get_number_value(
            key="sensitivity_threshold",
            default=1.6,
            evaluation_context=context
        )

        adaptive_hz = self._feature_client.get_boolean_value(
            key="enable_adaptive_hz",
            default=False,
            evaluation_context=context
        )

        # Update config from feature flags
        config = GamePerformanceConfig(
            update_frequency_hz=int(update_frequency_hz),
            adaptive_hz=adaptive_hz,
            # ... other flags
        )

        return config
```

**4. Context Enrichment**

```python
# services/game_coordinator/games/base.py

async def run(self):
    """Run game with feature-flag-driven configuration."""

    # Build evaluation context
    context = {
        "game_id": self.game_id,
        "game_mode": self.get_game_name(),
        "controller_count": len(self.players),
        "pi_model": get_pi_model(),  # Detect Pi 3/4/5
        "timestamp": time.time(),
    }

    # Get config from feature flags
    config_manager = get_config_manager()
    config = await config_manager.get_config_for_context(context)

    logger.info(f"Game starting with feature-flag config: "
                f"Hz={config.update_frequency_hz}, "
                f"adaptive={config.adaptive_hz}")

    # Rest of game logic uses this config
    # ...
```

### Experiment Tracking

**Metrics to Track:**
```python
# Emit to Prometheus with labels for experiment variant
game_performance_metric.labels(
    variant=context["variant"],  # "control" vs "treatment"
    hz=config.update_frequency_hz
).observe(value)
```

**Analysis:**
- Grafana query: Compare metric by variant
- Statistical significance test (t-test)
- Winner determination

### Remote Configuration (Cloud Provider)

**LaunchDarkly Integration:**
```python
from ldclient import LDClient, Config

# Initialize LaunchDarkly
ld_client = LDClient(Config("YOUR_SDK_KEY"))

# Evaluate flag
context = {
    "key": "game_123",
    "kind": "game",
    "controller_count": 25,
    "pi_model": "Pi5"
}

hz = ld_client.variation(
    key="update_frequency_hz",
    context=context,
    default=30
)
```

**Benefits:**
- Change flags remotely (no SSH)
- Instant rollback if issues
- Dashboard for non-technical users
- Experiment analytics built-in

## Implementation Plan

### Task 1: Install OpenFeature SDK

```bash
cd /home/simon/JoustMania
uv add openfeature-sdk
uv add openfeature-provider-file  # File-based provider for dev
```

### Task 2: Create Feature Flag Definitions

**File:** `config/feature_flags.yaml`

**Contents:**
- `update_frequency_hz` flag with variants
- `sensitivity_threshold` flag for A/B testing
- `enable_adaptive_hz` boolean flag
- Targeting rules based on context

### Task 3: Integrate with RuntimeConfigManager

**Changes to `runtime_config.py`:**
- Add `get_config_for_context(context)` method
- Add OpenFeature client initialization
- Add flag evaluation with context

### Task 4: Update Game Loop to Use Context

**Changes to `games/base.py`:**
- Build evaluation context before game start
- Fetch config from feature flags
- Log which variant was selected
- Emit variant label in metrics

### Task 5: Create Experiment Dashboard

**File:** `tools/experiment_dashboard.py`

**Features:**
- Show active experiments
- Display rollout percentages
- Compare variant performance
- Determine winner

### Task 6: Add Cloud Provider (Optional)

**Providers to evaluate:**
- LaunchDarkly (best UX, paid)
- Flagsmith (self-hosted, open source)
- PostHog (includes analytics)

### Task 7: Documentation

**Files:**
- `docs/feature-flags.md` - How to use OpenFeature
- `docs/experiments.md` - Running A/B tests
- `docs/configuration-rollout.md` - Gradual rollout guide

## Integration with Phase 43

**Phase 43 provides foundation:**
- ✅ Runtime configuration data structures
- ✅ Configuration change infrastructure
- ✅ Monitoring dashboards

**Phase 44 adds:**
- Feature flags for configuration values
- A/B testing framework
- Remote configuration management
- Experiment tracking

**Together:**
```
Phase 43: "What is the current config?"
Phase 44: "What should the config be for this game?"

Phase 43: Manual configuration via gRPC
Phase 44: Automated configuration via feature flags

Phase 43: Change config for all games
Phase 44: Change config for subset (A/B test)
```

## Example: A/B Testing Hz Settings

### Setup

**1. Define experiment in YAML:**
```yaml
update_frequency_hz:
  experiment: "hz_optimization_2024"
  variants:
    - name: "control_30hz"
      value: 30
      weight: 0.5
    - name: "treatment_60hz"
      value: 60
      weight: 0.5
```

**2. Game evaluates flag:**
```python
context = {
    "game_id": "game_123",
    "controller_count": 25,
    "pi_model": "Pi5"
}

config = await config_manager.get_config_for_context(context)
# Returns 30Hz or 60Hz based on 50/50 split
```

**3. Metrics emitted with variant:**
```python
game_loop_latency_ms.labels(
    variant=context["variant"]  # "control_30hz" or "treatment_60hz"
).observe(latency)
```

**4. Analysis in Grafana:**
```promql
# Compare average latency by variant
avg(game_loop_latency_ms{variant="control_30hz"})
avg(game_loop_latency_ms{variant="treatment_60hz"})
```

**5. Determine winner:**
- Control (30Hz): avg latency 33ms, CPU 22%
- Treatment (60Hz): avg latency 17ms, CPU 38%
- Decision: Keep 30Hz (16ms improvement not worth 16% CPU)

**6. Roll out winner:**
```yaml
update_frequency_hz:
  value: 30  # Winner rolled to 100%
```

## Talk Integration

**Slide Sequence:**

1. **Phase 43: Manual Configuration**
   - Show runtime config system
   - Demonstrate gRPC config change
   - Live dashboard updates

2. **Phase 44: Automated Experiments**
   - Show feature flag YAML
   - Explain A/B testing concept
   - Show how flags evaluate

3. **Live Demo: A/B Test**
   - Start 10 games
   - Show 5 get 30Hz, 5 get 60Hz
   - Live metrics dashboard compares variants
   - Determine winner in real-time

4. **Remote Configuration**
   - Show LaunchDarkly/Flagsmith dashboard
   - Change flag remotely
   - Instant application to new games
   - No SSH, no restart

5. **Gradual Rollout**
   - Show canary: 10% adaptive Hz
   - Metrics look good → increase to 50%
   - Metrics still good → 100%
   - (Or rollback if issues)

## Success Criteria

**Functional:**
- ⬜ Feature flags control Hz, sensitivity, adaptive mode
- ⬜ A/B testing assigns games to variants
- ⬜ Metrics tagged with variant for analysis
- ⬜ Remote configuration works (cloud provider)

**Performance:**
- ⬜ Flag evaluation <1ms overhead
- ⬜ Context building <5ms
- ⬜ No impact on game loop latency

**Observability:**
- ⬜ Experiment dashboard shows variant performance
- ⬜ Statistical significance calculated
- ⬜ Winner recommendation automated

## Dependencies

**Requires:**
- Phase 43: Runtime configuration system
- Phase 38: Prometheus metrics
- Phase 36: OpenTelemetry (for distributed context)

**Enables:**
- Data-driven configuration decisions
- Risk-free feature rollout
- Multi-variant testing at scale
- Remote configuration management

## Future Enhancements

**Phase 45: ML-Driven Configuration**
- Use experiment data to train model
- Predict optimal config for given context
- Auto-tune based on patterns

**Phase 46: User-Specific Flags**
- Per-player sensitivity preferences
- Controller-specific settings
- Adaptive learning per user

## Notes

**Why OpenFeature vs Custom Solution:**
- ✅ Vendor-neutral standard
- ✅ Multiple provider options
- ✅ Community best practices
- ✅ Swap providers without code changes

**Why File-Based Initially:**
- ✅ No external dependencies
- ✅ Version controlled (git)
- ✅ Easy to understand
- ✅ Upgrade to cloud later

**Why This Matters for Talk:**
- Shows evolution: hardcoded → runtime config → feature flags
- Demonstrates observability enabling experimentation
- Real-world example of A/B testing infrastructure
- Bridges dev practices (flags) with production (monitoring)
