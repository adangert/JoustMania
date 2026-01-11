# Phase 18: Game Loop CPU Optimization

**Status:** ⚡ PLANNED
**Priority:** HIGH

## Goal
Reduce CPU usage and memory allocations in 60Hz game loop

## Motivation
- Controller state rebuilt on every tick (O(N) allocations)
- 4 controllers × 60 Hz = 240 protobuf allocations/second
- Each allocation: ControllerState + 2 Vector3 objects
- Python object allocations cause GC pressure on Raspberry Pi
- Unnecessary CPU cycles wasted rebuilding unchanged state

## Current Overhead

**State Rebuild Per Tick** - `controller_manager/server.py:289-292`
```python
controllers = [
    self._build_controller_state_message(serial, info)
    for serial, info in self.tracked_controllers.items()
]
```

**Impact:**
- Creates new protobuf objects every 16.7ms
- 240 allocations/second with 4 controllers
- Garbage collection pauses disrupt 60 FPS timing
- Memory fragmentation on Raspberry Pi

## Tasks

### 1. State Caching in Controller Manager
- [ ] Add state cache to tracked_controllers dict
  - [ ] Store previous ControllerState protobuf message
  - [ ] Add dirty flag per controller
  - [ ] Only rebuild message when hardware state changes
  - **Files:** `services/controller_manager/server.py:289-292`

```python
class ControllerManagerServicer:
    def __init__(self):
        self.tracked_controllers = {}  # {serial: {move, cached_state, dirty, ...}}

    def _build_or_get_cached_state(self, serial, info):
        """Return cached state if unchanged, rebuild if dirty."""
        if info.get('dirty', True):
            # Rebuild state
            state = self._build_controller_state_message(serial, info)
            info['cached_state'] = state
            info['dirty'] = False
            return state
        else:
            # Return cached
            return info['cached_state']

    def _mark_controller_dirty(self, serial):
        """Mark controller state as changed (needs rebuild)."""
        if serial in self.tracked_controllers:
            self.tracked_controllers[serial]['dirty'] = True
```

- [ ] Mark controller dirty on hardware changes
  - [ ] Battery level change
  - [ ] Button state change
  - [ ] Accelerometer/gyroscope change
  - [ ] Connection status change

### 2. Protobuf Object Pooling
- [ ] Create object pool for ControllerState messages
  - [ ] Pre-allocate pool of 10 ControllerState objects
  - [ ] Pre-allocate pool of 20 Vector3 objects
  - [ ] Reuse with `.Clear()` instead of recreating
  - **Files:** `services/controller_manager/server.py`

```python
from collections import deque

class MessagePool:
    """Pool of reusable protobuf messages."""

    def __init__(self, message_class, pool_size=10):
        self.pool = deque([message_class() for _ in range(pool_size)])
        self.message_class = message_class

    def get(self):
        """Get a message from pool or create new if empty."""
        if self.pool:
            msg = self.pool.popleft()
            msg.Clear()
            return msg
        return self.message_class()

    def return_msg(self, msg):
        """Return message to pool for reuse."""
        self.pool.append(msg)

# In ControllerManagerServicer
self.controller_state_pool = MessagePool(controller_manager_pb2.ControllerState)
self.vector3_pool = MessagePool(controller_manager_pb2.Vector3)
```

- [ ] Update message building to use pooled objects
- [ ] Return messages to pool after streaming

### 3. Game Loop Performance Metrics
- [ ] Add frame timing instrumentation
  - [ ] Track frame time (P50, P95, P99 percentiles)
  - [ ] Track allocation count per frame
  - [ ] Track GC pause duration
  - **Files:** `services/game_coordinator/games/ffa.py`, `teams.py`, `random_teams.py`

```python
import time
from collections import deque

class GamePerformanceMetrics:
    """Track game loop performance metrics."""

    def __init__(self, window_size=300):  # 5 seconds at 60 FPS
        self.frame_times = deque(maxlen=window_size)
        self.gc_pauses = deque(maxlen=window_size)

    def record_frame(self, frame_time_ms, gc_pause_ms=0):
        self.frame_times.append(frame_time_ms)
        if gc_pause_ms > 0:
            self.gc_pauses.append(gc_pause_ms)

    def get_stats(self):
        """Return P50, P95, P99 frame times."""
        if not self.frame_times:
            return {}

        sorted_times = sorted(self.frame_times)
        count = len(sorted_times)

        return {
            'p50': sorted_times[int(count * 0.5)],
            'p95': sorted_times[int(count * 0.95)],
            'p99': sorted_times[int(count * 0.99)],
            'avg_gc_pause': sum(self.gc_pauses) / len(self.gc_pauses) if self.gc_pauses else 0
        }
```

- [ ] Export metrics to Prometheus
  - [ ] Add `/metrics` endpoint to Game Coordinator
  - [ ] Expose frame_time_p50, frame_time_p95, frame_time_p99
  - [ ] Expose gc_pause_count, gc_pause_duration

### 4. Memory Profiling Tools
- [ ] Add memory profiling hooks
  - [ ] Track object count per type
  - [ ] Track memory usage per service
  - [ ] Environment variable: `ENABLE_MEMORY_PROFILING=true`

## Expected Improvements

**CPU Usage:**
- Before: 240 allocations/second
- After: 10-20 allocations/second (only on changes)
- Reduction: -10-15% overall CPU

**Memory:**
- Before: 240 new objects/second + GC overhead
- After: Pooled object reuse
- Reduction: -30-40% memory pressure

**GC Pauses:**
- Before: Frequent pauses (every 2-3 seconds)
- After: Rare pauses (every 10-15 seconds)
- Reduction: -50% GC pause frequency

**Frame Timing:**
- Before: P99 = 20-25ms (occasional drops)
- After: P99 = 12-15ms (consistent)
- Improvement: More stable 60 FPS

## Raspberry Pi Impact

**Before:**
- CPU: 60-70% during 8-player games
- Memory: 200MB with fragmentation
- GC pauses: 5-10ms every 2-3 seconds

**After:**
- CPU: 45-55% during 8-player games
- Memory: 120-140MB, less fragmentation
- GC pauses: 2-5ms every 10-15 seconds

## Success Criteria

- ✅ Controller state only rebuilt when hardware changes
- ✅ Frame time P99 < 15ms consistently
- ✅ CPU usage < 50% during 8-player games
- ✅ GC pause frequency reduced by 50%
- ✅ No observable impact on gameplay smoothness
- ✅ Memory usage reduced by 30%+

## Dependencies

- None - can be implemented independently
- Complements Phase 27 (OpenTelemetry Optimization)
- Metrics useful for measuring Phase 27 impact

## Testing

- [ ] Benchmark before/after with 8 mock controllers
- [ ] Run for 1 hour continuous gameplay
- [ ] Measure frame time distribution
- [ ] Verify GC pause reduction
- [ ] Test on Raspberry Pi 4 and Pi 5
