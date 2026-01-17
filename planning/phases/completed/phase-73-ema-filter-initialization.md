# Phase 73: Fix EMA Filter Initialization

**Status**: Complete

## Problem

Players were dying simultaneously within 3-4 seconds of game start without moving. The EMA (exponential moving average) filter for acceleration started at 0.0 and hadn't stabilized by the time the 1.5s grace period ended, causing false death detections.

## Root Cause

```python
@dataclass
class Player:
    smoothed_accel: float = 0.0  # Started at 0, not real acceleration (~1000)
```

The EMA formula `smoothed = (smoothed * 4 + raw) / 5` takes 15-20 samples to reach the true resting value. Grace period ended before stabilization → false deaths.

## Fix

**File**: `services/game_coordinator/games/base.py`
**Method**: `_process_controller_state()` (line 594-598)

Initialize the filter with the first real reading instead of letting it ramp up from zero:

```python
if player.smoothed_accel == 0.0:
    player.smoothed_accel = accel_mag  # Prime filter with first real reading
else:
    player.smoothed_accel = (player.smoothed_accel * 4 + accel_mag) / 5
```

## Result

- EMA immediately tracks actual controller state
- No false deaths at game start
- Normal death detection works after grace period
