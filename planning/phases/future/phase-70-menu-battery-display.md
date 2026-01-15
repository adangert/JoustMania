# Phase 70: Move Battery Display to Menu Service

> **Status**: Future
>
> **Prerequisites**: Phase 69 (shared builder images)
>
> **Impact**: UX improvement, cleaner separation of concerns

## Overview

Move battery level display and warnings from controller-manager to the menu service. Battery status should be shown in the menu (non-intrusive) rather than during gameplay (distracting).

## Motivation

Currently, the controller-manager's monitoring system shows battery warnings by flashing controller LEDs. This is problematic because:

1. **Gameplay interruption**: Battery warnings during a game are distracting and can affect player performance
2. **Wrong responsibility**: Controller-manager should report state, not make UX decisions
3. **Limited feedback**: LED flashing is the only feedback mechanism available in controller-manager

The menu service is the right place for battery display because:
- Players are not actively playing, so warnings are not disruptive
- Menu has access to audio for optional audio warnings
- Menu controls the game flow and can warn before starting

## Design

### LED Brightness Based on Battery Level

In menu/lobby state, adjust the "dim" (not ready) LED brightness based on battery.
Full brightness (100%) is reserved for the "ready" state.

| Battery Level | Not Ready (Dim) | Ready |
|---------------|-----------------|-------|
| 5 (100%) | 50% | 100% |
| 4 (80%) | 45% | 100% |
| 3 (60%) | 40% | 100% |
| 2 (40%) | 30% | 100% |
| 1 (20%) | 20% | 100% |
| 0 (critical) | 15% + slow pulse | 100% |

This provides subtle, non-intrusive feedback:
- **Not ready**: Dimmer = lower battery (players can compare their controller to others)
- **Ready**: Always full brightness (clear "I'm ready" signal)

Players can glance at their dim controller brightness to gauge battery level before readying up.

### Pre-Game Battery Warning

Before starting a game, check all controller battery levels:

```
┌─────────────────────────────────────────┐
│         LOW BATTERY WARNING             │
│                                         │
│  Controller 1 (Blue): 20% battery       │
│  Controller 3 (Green): 40% battery      │
│                                         │
│  Start anyway?  [MOVE] Yes  [PS] Cancel │
└─────────────────────────────────────────┘
```

- Show warning if any controller is ≤ 40% (configurable threshold)
- List affected controllers with their colors
- Allow players to start anyway or cancel to charge
- Optional: Play warning audio tone

### Battery Status in WebUI

Add battery indicators to the WebUI controller list:

```
Controllers:
  🔵 Player 1 - ████░ 80%
  🔴 Player 2 - █████ 100%
  🟢 Player 3 - ██░░░ 40% ⚠️
  🟡 Player 4 - █████ 100%
```

## Implementation

### Changes to Controller Manager

1. **Remove** battery warning logic from `monitoring.py`
2. **Keep** battery level reporting in controller state
3. **Remove** LED flashing for low battery

### Changes to Menu Service

1. **Add** battery-aware LED brightness calculation
2. **Add** pre-game battery check before `start_game()`
3. **Add** optional audio warning for low battery
4. **Update** controller color assignment to factor in brightness

### Changes to WebUI

1. **Add** battery level display to controller list
2. **Add** visual warning indicator for low batteries

## Tasks

- [ ] Remove battery warning logic from controller-manager monitoring.py
- [ ] Add `get_battery_brightness_factor(level: int) -> float` to menu service
- [ ] Update menu LED color setting to apply brightness factor
- [ ] Add battery check before game start in menu service
- [ ] Add low battery warning UI/flow in menu
- [ ] Optional: Add audio warning for low battery
- [ ] Add battery display to WebUI controller list
- [ ] Update settings to include battery warning threshold
- [ ] Test with various battery levels
- [ ] Update documentation

## Configuration

Add to settings:

```yaml
battery:
  # Warn before game if any controller below this level (0-5)
  warning_threshold: 2  # 40%

  # Enable LED brightness adjustment based on battery
  brightness_adjustment: true

  # Enable pre-game warning
  pre_game_warning: true

  # Enable audio warning
  audio_warning: false
```

## Future Enhancements

- Battery history tracking (predict remaining play time)
- Per-controller battery alerts via WebUI notifications
- Charging detection and status display
- Battery health monitoring over time

## References

- Controller Manager monitoring.py (current battery logic)
- Menu service LED handling
- WebUI controller display
