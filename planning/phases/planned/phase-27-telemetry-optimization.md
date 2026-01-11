# Phase 27: Telemetry Optimization

**Status:** 📊 PLANNED
**Priority:** HIGH - Telemetry overhead significant on RPi

## Goal
Reduce OpenTelemetry CPU/memory/network overhead for production deployment

## Motivation
- Current implementation creates 480 spans/second during 8-player games
- BatchSpanProcessor buffers 512 spans in memory (64KB+)
- Network I/O every 5 seconds even to remote OTLP collector
- RPi CPU can't handle full instrumentation at 60Hz game loop

## Tasks

**1. Span Sampling**
- [ ] Implement trace sampling in all services
  - [ ] Use `TraceIdRatioBased(0.1)` - sample 10% of traces
  - [ ] Environment variable to control sample rate
  - [ ] Document how to enable full tracing for debugging
  - **Files:** All service telemetry initialization functions

```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

sample_rate = float(os.getenv('OTEL_TRACE_SAMPLE_RATE', '0.1'))
sampler = TraceIdRatioBased(sample_rate)
provider = TracerProvider(resource=resource, sampler=sampler)
```

**2. Reduce Span Creation in Game Loops**
- [ ] Remove spans from hot path (60Hz controller state processing)
  - [ ] Keep spans only for significant events (deaths, victories)
  - [ ] Remove per-update span creation
  - **Files:** `services/game_coordinator/games/ffa.py:201-244`, `teams.py:224-290`, `random_teams.py:293-357`

- [ ] Batch multiple events into single span
  - [ ] Create one span per game tick, add events for player states
  - [ ] Use `span.add_event()` instead of child spans for minor events

**3. BatchSpanProcessor Tuning**
- [ ] Reduce buffer size for memory-constrained environments
  - [ ] `max_queue_size=64` (down from 512)
  - [ ] `max_export_batch_size=32` (down from 512)
  - [ ] `schedule_delay_millis=10000` (export every 10s instead of 5s)
  - **Files:** All service telemetry init

**4. Disable Telemetry in Production Mode**
- [ ] Add environment variable to disable telemetry entirely
  - [ ] `OTEL_SDK_DISABLED=true` for maximum performance
  - [ ] Document performance impact: ~15% CPU reduction
  - [ ] Keep logging enabled even when telemetry disabled

**5. Logger Level Optimization**
- [ ] Change frequent logs to DEBUG level
  - [ ] Controller state updates: INFO → DEBUG
  - [ ] Button press events: INFO → DEBUG
  - [ ] Keep game start/stop/deaths at INFO
  - **Files:** All services with high-frequency logging

## Expected Improvements
- 90% reduction in span creation (480/sec → 48/sec)
- 75% reduction in memory usage (BatchSpanProcessor buffer)
- 50% reduction in network traffic to OTLP collector
- 15% overall CPU reduction with sampling

## Raspberry Pi Impact
- Game coordinator CPU: 40% → 25%
- Controller manager CPU: 30% → 20%
- Memory footprint: 200MB → 120MB total

## Success Criteria
- Span creation rate < 50/sec during gameplay
- BatchSpanProcessor memory < 8KB
- OTLP export every 10+ seconds
- No dropped spans due to buffer overflow
- CPU usage sustainable for 24+ hour operation
