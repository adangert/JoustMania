# Phase 18 & 27 Split Proposal

**Goal:** Split overlapping Phase 18 & 27 into 3 concise, focused phases

---

## Current Situation

**Phase 18 + 27 Combined Tasks:**
1. State caching (controller state rebuild optimization)
2. OTel span sampling (10% rate)
3. Reduce span creation in game loops
4. BatchSpanProcessor tuning
5. Protobuf object pooling
6. Logger level cleanup (INFO → DEBUG)
7. OTEL_SDK_DISABLED environment variable
8. Game loop performance metrics

**Problem:** Too broad - mixes game logic, telemetry, and logging concerns

---

## Proposed 3-Phase Split

### Phase 18: Game Loop CPU Optimization

**Focus:** Core game performance - CPU and memory in the hot path

**Priority:** HIGH
**Goal:** Reduce CPU usage and memory allocations in 60Hz game loop

**Tasks:**
- [ ] Implement state caching in Controller Manager
  - [ ] Cache controller state between ticks
  - [ ] Only rebuild on actual hardware changes (dirty flag)
  - [ ] Reduce from 240 allocations/sec to ~10-20/sec
  - **Files:** `services/controller_manager/server.py:289-292`

- [ ] Protobuf object pooling
  - [ ] Pool ControllerState messages
  - [ ] Pool Vector3 messages
  - [ ] Reuse with `.Clear()` instead of recreating
  - **Files:** `services/controller_manager/server.py`

- [ ] Game loop performance metrics
  - [ ] Track frame time (P50, P95, P99)
  - [ ] Track GC pauses
  - [ ] Export to Prometheus
  - **Files:** All game mode files

**Expected Improvements:**
- CPU: -10-15% (fewer allocations)
- Memory: -30-40% (object pooling)
- GC pauses: -50% (reduced allocation pressure)

**Success Criteria:**
- Controller state only rebuilt when hardware changes
- Frame time P99 < 15ms
- CPU usage < 50% during 8-player games

---

### Phase 27: OpenTelemetry Optimization

**Focus:** Reduce observability overhead for production deployment

**Priority:** HIGH
**Goal:** Minimize OpenTelemetry CPU/memory/network impact on Raspberry Pi

**Tasks:**
- [ ] Implement trace sampling
  - [ ] Add `TraceIdRatioBased(0.1)` - sample 10% of traces
  - [ ] Environment variable: `OTEL_TRACE_SAMPLE_RATE` (default 0.1)
  - [ ] Document how to enable full tracing for debugging
  - **Files:** All services with `init_telemetry()`

- [ ] Reduce span creation in hot paths
  - [ ] Remove spans from 60Hz controller processing
  - [ ] Keep spans only for significant events (deaths, victories, game start/stop)
  - [ ] Use `span.add_event()` instead of child spans for minor events
  - **Files:** `services/game_coordinator/games/*.py`

- [ ] Tune BatchSpanProcessor for constrained environments
  - [ ] `max_queue_size=64` (down from 512)
  - [ ] `max_export_batch_size=32` (down from 512)
  - [ ] `schedule_delay_millis=10000` (export every 10s instead of 5s)
  - **Files:** All services with BatchSpanProcessor

- [ ] Add production mode
  - [ ] Environment variable: `OTEL_SDK_DISABLED=true`
  - [ ] Document performance impact (~15% CPU reduction)
  - [ ] Keep logging enabled when telemetry disabled
  - **Files:** All services

**Expected Improvements:**
- Span creation: -90% (480/sec → 48/sec)
- Memory: -75% (BatchSpanProcessor buffer)
- Network to OTLP collector: -90% (10% sampling)
- CPU: -15% overall

**Success Criteria:**
- Span creation rate < 50/sec during gameplay
- BatchSpanProcessor memory < 8KB
- OTLP export interval 10+ seconds
- No dropped spans due to buffer overflow

---

### Phase 35: Logging Optimization

**Focus:** Reduce logging overhead and improve log quality

**Priority:** MEDIUM
**Goal:** Clean up excessive logging that creates noise and CPU overhead

**Tasks:**
- [ ] Audit and cleanup logger levels
  - [ ] Controller state updates: INFO → DEBUG
  - [ ] Button press events: INFO → DEBUG
  - [ ] gRPC channel creation: INFO → DEBUG
  - [ ] Game loop ticks: INFO → DEBUG
  - **Files:** All services

- [ ] Reserve INFO level for significant events only
  - [ ] Game start/stop
  - [ ] Player deaths/victories
  - [ ] Service startup/shutdown
  - [ ] Admin mode entry/exit
  - [ ] Setting changes

- [ ] Add environment variable controls
  - [ ] `LOG_LEVEL` (DEBUG, INFO, WARNING, ERROR)
  - [ ] Default to INFO in production, DEBUG in development
  - [ ] Per-service overrides: `SETTINGS_LOG_LEVEL`, etc.

- [ ] Optimize log formatting
  - [ ] Remove unnecessary timestamps (journald already adds them)
  - [ ] Simplify log format for high-frequency events
  - [ ] Add structured logging for critical events

**Expected Improvements:**
- Log output volume: -80% (less noise)
- CPU: -5% (fewer string operations)
- Log readability: significantly improved
- Easier debugging (signal vs noise)

**Success Criteria:**
- INFO level logs readable and actionable
- No DEBUG logs in production by default
- Log volume < 100 lines/minute during gameplay
- Critical events always logged at INFO/WARNING

---

## Comparison: Before vs After

### Before (2 overlapping phases)
- **Phase 18:** Game Loop & Telemetry Optimization (too broad)
- **Phase 27:** Telemetry Optimization (duplicate work)

### After (3 focused phases)
- **Phase 18:** Game Loop CPU Optimization (game performance)
- **Phase 27:** OpenTelemetry Optimization (observability overhead)
- **Phase 35:** Logging Optimization (debugging overhead)

---

## Implementation Order

**Recommended sequence:**

1. **Phase 18 first** - Game loop optimization
   - Direct impact on gameplay FPS
   - Foundation for measuring other optimizations
   - Provides baseline metrics

2. **Phase 27 second** - OpenTelemetry optimization
   - Biggest overhead reduction (480 spans/sec → 48)
   - Depends on Phase 18 metrics to measure impact
   - Critical for RPi deployment

3. **Phase 35 third** - Logging optimization
   - Lower priority (only ~5% CPU impact)
   - Makes debugging easier for future work
   - Can be done anytime

---

## Benefits of This Split

1. **Clear Separation of Concerns**
   - Game logic optimization (Phase 18)
   - Observability optimization (Phase 27)
   - Debugging optimization (Phase 35)

2. **Independent Implementation**
   - Each phase can be completed separately
   - No dependencies between phases
   - Different code areas affected

3. **Measurable Impact**
   - Each phase has clear success metrics
   - Easy to measure individual improvements
   - Can prioritize based on measured impact

4. **Easier Testing**
   - Smaller scope per phase
   - Easier to isolate regressions
   - Clear rollback boundaries

5. **Flexible Prioritization**
   - Can skip Phase 35 if time-constrained
   - Phase 18 + 27 are critical for RPi
   - Phase 35 is nice-to-have polish
