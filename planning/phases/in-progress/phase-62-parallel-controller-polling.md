# Phase 62: Parallel Controller Polling

## Overview

Optimize controller state polling by reading all controllers concurrently using `asyncio.gather()` instead of sequentially. This reduces polling latency from O(n × latency) to O(latency), enabling better performance on Raspberry Pi and support for large player counts (up to 24 controllers).

## Problem Statement

### Current Implementation (Sequential)

```python
# services/controller_manager/server.py:258-278
for serial in serials:
    state = self._run_in_discovery_loop(self.backend.get_controller_state(serial))
    # process state...
```

Each controller is polled one after another, blocking until completion:

```
|-- Ctrl 1 --|-- Ctrl 2 --|-- Ctrl 3 --|-- Ctrl 4 --|
     3ms          3ms          3ms          3ms
Total: 12ms
```

### Impact

| Controllers | Sequential Time | 60Hz Budget (16ms) | Status |
|-------------|-----------------|-------------------|--------|
| 4 | 12ms | 4ms margin | ⚠️ Tight |
| 8 | 24ms | -8ms | ❌ Can't sustain |
| 24 | 72ms | -56ms | ❌ Impossible |

## Solution

### Parallel Polling with asyncio.gather()

```python
async def get_all_states():
    coros = [self.backend.get_controller_state(serial) for serial in serials]
    return await asyncio.gather(*coros, return_exceptions=True)

results = self._run_in_discovery_loop(get_all_states())
```

All controllers polled concurrently:

```
|-- Ctrl 1 --|
|-- Ctrl 2 --|
|-- Ctrl 3 --|
|-- Ctrl 4 --|
     3ms
Total: 3ms (75% reduction)
```

### Why This Works on Raspberry Pi

- **asyncio is single-threaded**: No thread explosion, minimal memory (~2KB per coroutine)
- **I/O-bound operation**: CPU is idle during Bluetooth wait regardless of controller count
- **Same CPU usage**: Whether waiting for 1 or 24 controllers, CPU load is ~5%

## Implementation Plan

### 1. Modify `_update_controller_states()` in server.py

Replace sequential loop with parallel gather pattern.

### 2. Update `_spawn_controller_process()`

Consider batching initial state reads for multiple simultaneous connections.

### 3. Add Metrics

- `controller_poll_batch_size`: Number of controllers polled per cycle
- `controller_poll_duration_seconds`: Time to poll all controllers

### 4. Test with Mock Backend

Verify parallel behavior works correctly with mock controllers.

### 5. Integration Testing

Run full integration test suite to ensure no regressions.

## Files to Modify

| File | Changes |
|------|---------|
| `services/controller_manager/server.py` | Parallel polling in `_update_controller_states()` |
| `services/controller_manager/metrics.py` | Add batch polling metrics (optional) |

## Performance Expectations

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| 4 controllers poll time | 12ms | 3ms | 75% |
| 8 controllers poll time | 24ms | 3-5ms | 85% |
| 24 controllers poll time | 72ms | 5-15ms | 80-93% |
| Max sustainable controllers @ 60Hz | ~5 | 24+ | 5x |

## Testing Strategy

1. **Unit test**: Mock backend with artificial delays to verify parallel behavior
2. **Integration test**: Existing mock environment tests (should pass unchanged)
3. **Performance test**: Log poll duration before/after with 4 mock controllers

## Rollback Plan

Revert to sequential polling if issues arise. The change is isolated to `_update_controller_states()`.

## Dependencies

- None (uses existing asyncio infrastructure)

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Bluetooth adapter doesn't handle concurrent reads | Low | PSMove library is thread-safe; test on real hardware |
| Race condition in state updates | Low | Single lock acquisition after all reads complete |
| Exception in one controller blocks others | None | `return_exceptions=True` isolates failures |

## Success Criteria

- [ ] All integration tests pass
- [ ] Poll duration reduced by >50% with 4 controllers
- [ ] No increase in CPU usage
- [ ] Code is clean and well-documented
