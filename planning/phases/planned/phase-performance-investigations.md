# JoustMania Performance Investigation

## Status

**Phase 72 completed** (2026-01-17): Initial quick wins implemented.

---

## Phase 72: Completed Optimizations

### 1. Parallel RSSI Checks
- **File:** `services/controller_manager/monitoring.py`
- **Change:** Sequential `for` loop → `asyncio.gather()`
- **Impact:** O(n) → O(1) latency for RSSI checks (runs every 10s)

### 2. Increased Game Loop Frequency
- **Files:** `services/game_coordinator/runtime_config.py`, `games/base.py`
- **Change:** 30 Hz → 60 Hz default
- **Impact:** 2x more responsive death detection, halved input latency

### 3. Separated LED Updates from Polling
- **Files:** `services/controller_manager/bluetooth_backend.py`, `server.py`
- **Change:** Removed LED I/O from `get_controller_state()`, added dedicated `update_all_leds()` at 20Hz
- **Impact:** Polling path now pure sensor reads - no hardware writes blocking the loop

---

## Remaining Investigation Items

### High Priority

#### Benchmark Against Monolith
- [ ] Run `legacy/tests/joust_test.py` on original code to get baseline numbers
- [ ] Create equivalent benchmark for microservices pipeline
- [ ] Compare: polling rate, buffer depth, end-to-end latency
- [ ] Document the gap (if any) and acceptable thresholds

#### Prometheus Dashboard Setup
- [ ] Create dashboard with key metrics:
  - `poll_batch_duration_seconds` - should be <10ms
  - `game_actual_update_frequency_hz` - should match configured 60Hz
  - `stream_updates_total` rate - verify streaming is stable
- [ ] Set alerts for regression detection

#### Load Testing
- [ ] Test with 8+ mock controllers simultaneously
- [ ] Monitor CPU usage on Raspberry Pi under load
- [ ] Check for frame drops or queue overflows
- [ ] Validate button event queue doesn't overflow (server.py:1952)

### Medium Priority

#### Loki Log Correlation (when deployed)
```logql
# Find slow operations
{container="controller_manager"} |= "duration" | json | duration_ms > 50

# Trace correlation
{container=~"controller_manager|game_coordinator"} |= "trace_id=<ID>"

# Error spikes
{container="controller_manager"} |= "error" | rate[1m]
```

#### Jaeger Trace Analysis
- [ ] Filter for `controller_manager` spans > 10ms
- [ ] Identify slowest streaming RPCs
- [ ] Check for span explosion (too many child spans)

#### Observability Overhead Check
- [ ] Profile with tracing enabled vs disabled
- [ ] Consider sampling high-frequency traces (1 in 100)
- [ ] Remove debug logging from hot paths if needed

### Low Priority / Future

#### Button Event Queue Fix
- [ ] Change `put_nowait()` to `await queue.put()` in server.py:1952
- [ ] Prevents lost button events under high load

#### gRPC Streaming Optimization
- [ ] Evaluate batching multiple controller states per message
- [ ] Check protobuf encoding overhead
- [ ] Consider message pooling for high-frequency streams

#### Process-per-Controller Model
- [ ] Evaluate if returning to multiprocessing improves throughput
- [ ] Trade-off: complexity vs GIL bypass
- [ ] Only consider if benchmarks show Python GIL as bottleneck

---

## Key Metrics to Monitor

| Metric | Target | Prometheus Query |
|--------|--------|------------------|
| Poll batch duration | <10ms | `histogram_quantile(0.95, rate(poll_batch_duration_seconds_bucket[5m]))` |
| Actual game Hz | ~60Hz | `game_actual_update_frequency_hz` |
| Stream update rate | stable | `rate(stream_updates_total[1m])` |
| CPU usage | <50% | `process_cpu_percent{service="controller_manager"}` |

---

## Reference

**Hardware capabilities (from `joust_test.py`):**
- Old PS Move controllers: ~176 Hz (88 messages × 2 frames)
- New PS Move controllers: ~790 Hz
- Buffer depth: 64-160 messages

**Architecture:**
```
psmoveapi (790Hz) → ControllerManager → gRPC stream (60Hz) → GameCoordinator
                         ↓
                    LED updates (20Hz, separate path)
```

**Repository:** https://github.com/WatchMeJoustMyFlags/JoustMania/tree/dev-refactor
