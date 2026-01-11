# Phase 18: Game Loop & Telemetry Optimization

**Status:** ⚡ PLANNED
**Priority:** MEDIUM

## Goal
Optimize CPU-intensive operations and reduce telemetry overhead

## Motivation
- Controller state rebuilt on every tick (O(N) allocations)
- OpenTelemetry creates spans at 60 Hz (high overhead)
- No span sampling = 100% of traces sent to collector
- Python object allocations cause GC pressure

## Current Overhead

**1. State Rebuild Per Tick** - `controller_manager/server.py:289-292`
```python
controllers = [
    self._build_controller_state_message(serial, info)
    for serial, info in self.tracked_controllers.items()
]
```
- Creates new protobuf objects every 16.7ms
- 4 controllers × 60 Hz = 240 allocations/sec
- Each allocation: ControllerState + 2 Vector3 objects

**2. No OTel Sampling** - All services
- Every RPC creates spans (100% sampling)
- Game loop creates spans at 60 Hz
- Each span has attributes + events
- Batch processor sends to collector over network

**3. Protobuf Message Allocations**
- No object pooling or reuse
- Garbage collection overhead
- Memory fragmentation on Raspberry Pi

## Tasks

- [ ] Implement state caching in Controller Manager
  - [ ] Cache controller state between ticks
  - [ ] Only rebuild on actual hardware changes
  - [ ] Use dirty flag to track changes
  - [ ] File: `services/controller_manager/server.py:289-292`

- [ ] Add OpenTelemetry sampling
  - [ ] Configure `TraceIdRatioBased` sampler (10% rate)
  - [ ] Apply to all services
  - [ ] Higher sampling for errors/slow spans
  - [ ] Files: All `services/*/server.py` (init_telemetry)

- [ ] Optimize protobuf object allocation
  - [ ] Object pooling for frequently used messages
  - [ ] Reuse message objects where possible
  - [ ] Consider using `Clear()` instead of recreating

- [ ] Add game loop performance metrics
  - [ ] Track frame time (P50, P95, P99)
  - [ ] Track GC pauses
  - [ ] Track network latency
  - [ ] Export to Prometheus

## OpenTelemetry Sampling Configuration

```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBasedTraceIdRatio

sampler = ParentBasedTraceIdRatio(
    root=TraceIdRatioBased(0.1),  # Sample 10% of root spans
)

trace.set_tracer_provider(
    TracerProvider(
        resource=Resource.create({SERVICE_NAME: service_name}),
        sampler=sampler
    )
)
```

## Expected Improvements
- CPU usage: -5-10% (less OTel overhead)
- Memory: -20-30% (less protobuf allocations)
- Network to OTel collector: -90% (10% sampling)
- GC pauses: -30-40% (fewer allocations)

## Success Criteria
- CPU utilization during gameplay <60%
- Frame time P99 <17ms
- OTel collector ingestion rate <100 spans/sec
- No observable impact on gameplay from telemetry
