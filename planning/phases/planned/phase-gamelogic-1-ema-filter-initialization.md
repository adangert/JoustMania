# Phase: Fix EMA Filter Initialization

**Status**: Planned
**Priority**: High (causes game-breaking bug)

## Problem

Players are dying simultaneously within 3-4 seconds of game start without moving. The EMA filter for acceleration starts at 0.0 and hasn't stabilized by the time the 1.5s grace period ends.

## Root Cause

```python
@dataclass
class Player:
    smoothed_accel: float = 0.0  # ← Starts at 0, not real acceleration
```

The EMA formula `smoothed = (smoothed * 4 + raw) / 5` takes 15-20 samples to reach true value (~1000 for gravity). Grace period ends before stabilization → false deaths.

## Fix

**File**: `services/game_coordinator/games/base.py`
**Method**: `_process_controller_state()`

```python
# Before (broken):
player.smoothed_accel = (player.smoothed_accel * 4 + accel_mag) / 5

# After (fixed):
if player.smoothed_accel == 0.0:
    player.smoothed_accel = accel_mag  # Prime with first reading
else:
    player.smoothed_accel = (player.smoothed_accel * 4 + accel_mag) / 5
```

## Testing

1. Start 2-player FFA game
2. Keep controllers motionless
3. Expected: No deaths in first 5 seconds
4. Move controllers → warnings then deaths (normal behavior)
