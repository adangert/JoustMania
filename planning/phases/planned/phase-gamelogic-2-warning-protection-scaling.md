# Phase: Scale Warning Protection with Music Tempo

**Status**: Planned
**Priority**: Low (enhancement, not a bug)

## Current Behavior

Warning protection duration is fixed at 0.5 seconds:

```python
WARNING_PROTECTION_DURATION = 0.5
```

When warned, players have 0.5s to slow down before they can die.

## Issue

At higher music tempos (1.3x), thresholds are scaled up by 30%, making the game harder. But the warning window stays the same, giving players less relative time to react.

## Proposed Enhancement

Scale warning protection with music tempo:

```python
# In _warn_player():
speed_factor = self.music_speed / SLOW_MUSIC_SPEED
protection_duration = WARNING_PROTECTION_DURATION * speed_factor
player.warning_until = time.time() + protection_duration
```

At 1.3x tempo → 0.65s protection window (proportionally more time)

## Notes

- This is optional - current behavior may be intentional (harder = shorter reaction time)
- Needs playtesting to determine if it improves game feel
- Could also be a settings option
