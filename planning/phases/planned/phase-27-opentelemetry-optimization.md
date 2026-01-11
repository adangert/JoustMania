# Phase 27: OpenTelemetry Optimization

**Status:** 📊 PLANNED
**Priority:** HIGH

## Goal
Reduce OpenTelemetry CPU/memory/network overhead for production deployment on Raspberry Pi

## Motivation
- Current implementation creates 480 spans/second during 8-player games
- Every controller state update creates a span (60 Hz × 8 controllers)
- BatchSpanProcessor buffers 512 spans in memory (64KB+)
- Network I/O every 5 seconds to OTLP collector
- Raspberry Pi CPU can't handle full instrumentation at 60Hz game loop
- Development-grade telemetry settings not suitable for production

## Current Overhead

**Span Creation Rate:**
- Controller state updates: 8 controllers × 60 Hz = 480 spans/sec
- Game loop ticks: 60 spans/sec
- RPC calls: ~20-30 spans/sec
- **Total: ~560 spans/second**

**Memory Usage:**
- BatchSpanProcessor queue: 512 spans buffered
- Each span: ~128 bytes (attributes + events)
- **Total: ~64KB buffer + object overhead**

**Network Impact:**
- Export batch every 5 seconds
- ~2,800 spans per batch
- Serialization + gRPC call overhead
- **Bandwidth: ~500KB/minute to Jaeger**

## Tasks

### 1. Implement Trace Sampling
- [ ] Add TraceIdRatioBased sampler to all services
  - [ ] Sample 10% of traces by default
  - [ ] Environment variable: `OTEL_TRACE_SAMPLE_RATE` (default: 0.1)
  - [ ] Preserve parent sampling decision for distributed traces
  - **Files:** All services with `init_telemetry()` function

```python
import os
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased

def init_telemetry(service_name: str):
    # Read sample rate from environment (default 10%)
    sample_rate = float(os.getenv('OTEL_TRACE_SAMPLE_RATE', '0.1'))

    # Use ParentBased to respect parent trace sampling decisions
    sampler = ParentBased(
        root=TraceIdRatioBased(sample_rate)
    )

    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: service_name}),
        sampler=sampler
    )

    trace.set_tracer_provider(provider)
```

- [ ] Document how to enable full tracing for debugging
  - [ ] `export OTEL_TRACE_SAMPLE_RATE=1.0` for 100% sampling
  - [ ] Add to development documentation
  - [ ] Add to troubleshooting guide

### 2. Reduce Span Creation in Hot Paths
- [ ] Remove spans from 60Hz controller state processing
  - [ ] Keep spans only for significant events (deaths, victories, game start/stop)
  - [ ] Remove per-update span creation in game loops
  - **Files:** `services/game_coordinator/games/ffa.py:201-244`

```python
# BEFORE (creates span every 16.7ms)
async def _game_loop(self):
    while self.running:
        with tracer.start_as_current_span("game_tick"):
            await self._process_frame()

# AFTER (create span once, add events for significant changes)
async def _game_loop(self):
    with tracer.start_as_current_span("game_session") as span:
        while self.running:
            await self._process_frame()

            # Only add events for significant game events
            if player_died:
                span.add_event("player_death", {"serial": serial})
```

- [ ] Use span.add_event() instead of child spans
  - [ ] Controller button presses: event instead of span
  - [ ] Player warnings: event instead of span
  - [ ] Score updates: event instead of span
  - **Files:** All game mode files

- [ ] Keep spans for these significant events:
  - Game start/stop
  - Player deaths
  - Victory/defeat
  - Admin mode entry/exit
  - Setting changes

### 3. Tune BatchSpanProcessor for RPi
- [ ] Reduce buffer sizes for memory-constrained environments
  - [ ] `max_queue_size=64` (down from 512)
  - [ ] `max_export_batch_size=32` (down from 512)
  - [ ] `schedule_delay_millis=10000` (export every 10s instead of 5s)
  - **Files:** All services with BatchSpanProcessor initialization

```python
from opentelemetry.sdk.trace.export import BatchSpanProcessor

processor = BatchSpanProcessor(
    exporter,
    max_queue_size=64,           # Reduced from 512
    max_export_batch_size=32,    # Reduced from 512
    schedule_delay_millis=10000  # Increased from 5000 (10s vs 5s)
)
```

- [ ] Add environment variable overrides
  - [ ] `OTEL_BATCH_QUEUE_SIZE` (default: 64)
  - [ ] `OTEL_BATCH_EXPORT_SIZE` (default: 32)
  - [ ] `OTEL_BATCH_DELAY_MS` (default: 10000)

### 4. Add Production Mode (Telemetry Disable)
- [ ] Add environment variable to completely disable telemetry
  - [ ] `OTEL_SDK_DISABLED=true` disables all tracing
  - [ ] No span creation, no export, no overhead
  - [ ] Document performance impact: ~15% CPU reduction
  - **Files:** All services

```python
import os

def init_telemetry(service_name: str):
    # Check if telemetry is disabled
    if os.getenv('OTEL_SDK_DISABLED', 'false').lower() == 'true':
        logger.info(f"OpenTelemetry disabled for {service_name}")
        # Use NoOpTracerProvider (no overhead)
        trace.set_tracer_provider(trace.NoOpTracerProvider())
        return

    # Normal telemetry initialization
    # ...
```

- [ ] Keep logging enabled when telemetry disabled
  - [ ] Logging independent of tracing
  - [ ] Structured logs still available
  - [ ] Service logs to stdout/stderr

- [ ] Document when to disable telemetry
  - [ ] Production deployments (unless debugging)
  - [ ] Resource-constrained environments
  - [ ] Performance-critical scenarios

### 5. Optimize Span Attributes
- [ ] Reduce attribute count on hot path spans
  - [ ] Remove redundant attributes
  - [ ] Move large attributes to events
  - [ ] Only include essential context
  - **Files:** All services creating spans

```python
# BEFORE (too many attributes)
with tracer.start_as_current_span("process_state") as span:
    span.set_attribute("controller.serial", serial)
    span.set_attribute("controller.battery", battery)
    span.set_attribute("controller.buttons", str(buttons))
    span.set_attribute("controller.accel.x", accel_x)
    span.set_attribute("controller.accel.y", accel_y)
    span.set_attribute("controller.accel.z", accel_z)
    # 10+ more attributes...

# AFTER (minimal attributes)
with tracer.start_as_current_span("process_state") as span:
    span.set_attribute("controller.serial", serial)
    # Only add other attributes if something significant happens
    if battery < 20:
        span.add_event("low_battery", {"level": battery})
```

## Expected Improvements

**Span Creation:**
- Before: 560 spans/second
- After: 48 spans/second (10% sampling + hot path removal)
- Reduction: -90%

**Memory Usage:**
- Before: 64KB BatchSpanProcessor buffer + object overhead
- After: 8KB buffer (64-span queue × 128 bytes)
- Reduction: -75%

**Network Traffic:**
- Before: 2,800 spans/batch every 5 seconds
- After: 320 spans/batch every 10 seconds
- Reduction: -90% (due to sampling + longer delay)

**CPU Usage:**
- Before: ~15% CPU on telemetry (span creation, serialization, export)
- After: ~2-3% CPU on telemetry
- Reduction: -12-13% overall CPU

## Raspberry Pi Impact

**Before:**
- Game Coordinator CPU: 40-45%
- Controller Manager CPU: 30-35%
- Memory: 200MB total (telemetry buffers)

**After:**
- Game Coordinator CPU: 25-30%
- Controller Manager CPU: 20-25%
- Memory: 120-140MB total

**Net Improvement:** ~15% CPU reduction, ~60MB memory saved

## Success Criteria

- ✅ Span creation rate < 50/sec during gameplay
- ✅ BatchSpanProcessor memory < 10KB
- ✅ OTLP export interval 10+ seconds
- ✅ No dropped spans due to buffer overflow
- ✅ CPU usage reduced by 10-15%
- ✅ Jaeger UI still shows critical traces
- ✅ Can enable full tracing with environment variable

## Configuration Examples

**Development (Full Tracing):**
```bash
export OTEL_TRACE_SAMPLE_RATE=1.0
export OTEL_BATCH_QUEUE_SIZE=512
export OTEL_BATCH_DELAY_MS=5000
```

**Production (Optimized):**
```bash
export OTEL_TRACE_SAMPLE_RATE=0.1
export OTEL_BATCH_QUEUE_SIZE=64
export OTEL_BATCH_DELAY_MS=10000
```

**Production (Telemetry Disabled):**
```bash
export OTEL_SDK_DISABLED=true
```

## Dependencies

- None - can be implemented independently
- Works well with Phase 18 (Game Loop CPU Optimization)
- Phase 18 metrics help measure impact of this phase

## Testing

- [ ] Measure span creation rate before/after
- [ ] Verify 10% sampling works correctly
- [ ] Test with OTEL_SDK_DISABLED=true
- [ ] Ensure critical traces still captured
- [ ] Test on Raspberry Pi 4 and Pi 5
- [ ] Run for 24+ hours to verify stability
