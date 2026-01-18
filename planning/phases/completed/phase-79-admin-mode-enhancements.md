# Phase 79: Admin Mode Enhancements

## Overview

Fix regressions and add missing features to the new admin mode implementation to match the original functionality.

## Problem Statement

The new admin mode (Phase 23/28) was missing several features from the original implementation:

1. **Sensitivity Levels**: Only 3 levels (0-2) instead of 5 levels (0-4)
2. **Force Start Game**: No way to force start without all players ready
3. **Game Mode Selection**: No way to change game mode (was available via Select/Start)

Additionally, game mode selection was previously available to any player, causing accidental game changes. The new implementation restricts it to admin mode only.

## Changes Made

### 1. Sensitivity - All 5 Levels Restored

**File:** `services/menu/server.py` - `_handle_admin_sensitivity()`

| Level | Name | Color | Sound |
|-------|------|-------|-------|
| 0 | Ultra Slow | Dark Blue | slow_sensitivity.wav |
| 1 | Slow | Light Blue | slow_sensitivity.wav |
| 2 | Medium | Green | mid_sensitivity.wav |
| 3 | Fast | Orange | fast_sensitivity.wav |
| 4 | Ultra Fast | Red | fast_sensitivity.wav |

Cycles: 0 → 1 → 2 → 3 → 4 → 0

### 2. Force Start Game (Trigger Hold 2s)

**File:** `services/menu/server.py`

- Added `admin_trigger_hold_start` and `admin_force_start_pending` state fields
- Trigger tap: Increases current setting value (existing)
- Trigger hold 2s: Force starts game regardless of ready state

```python
# In _process_admin_commands()
if controller.trigger_pressed:
    if not prev_state["trigger"]:
        # Start tracking hold time
        self.admin_trigger_hold_start = current_time
    elif hold_duration >= 2.0:
        await self._handle_admin_force_start(controller.serial)
```

### 3. Game Mode Selection (Admin Only)

**Files:**
- `proto/controller_manager.proto` - Added `select_pressed` (17) and `start_pressed` (18) fields
- `services/controller_manager/server.py` - Populate new fields in ControllerState
- `services/controller_manager/mock_server.py` - Support in mock controllers
- `services/menu/server.py` - Handle Select/Start in admin mode

| Button | Action |
|--------|--------|
| SELECT | Cycle game mode backward |
| START | Cycle game mode forward |

Only available in admin mode - prevents accidental game mode changes by players.

## Updated Admin Mode Button Map

| Button | Action |
|--------|--------|
| **Trigger (tap)** | Increase current setting value |
| **Trigger (hold 2s)** | Force start game |
| **Cross** | Decrease current setting value |
| **Move** | Cycle through settings (num_teams, force_all_start) |
| **Select** | Cycle game mode backward |
| **Start** | Cycle game mode forward |
| **Circle** | Cycle sensitivity (5 levels) |
| **Triangle** | Show battery levels |
| **Square** | Toggle instructions |
| **PS** | Exit admin mode |

## Protobuf Changes

**File:** `proto/controller_manager.proto`

```protobuf
message ControllerState {
  // ... existing fields ...

  // Additional button states (Phase 79 - Admin Mode Game Selection)
  bool select_pressed = 17;     // Select button
  bool start_pressed = 18;      // Start button
}
```

## Files Modified

| File | Changes |
|------|---------|
| `services/menu/server.py` | 5-level sensitivity, force start, game mode selection |
| `services/controller_manager/server.py` | Populate select/start in ControllerState |
| `services/controller_manager/mock_server.py` | Support select/start in mock |
| `proto/controller_manager.proto` | Add select_pressed, start_pressed fields |

## Tasks

- [x] Fix sensitivity to cycle through all 5 levels (0-4)
- [x] Add force start game (trigger hold 2s)
- [x] Add game mode selection (Select/Start) in admin mode only
- [x] Update protobuf with select_pressed and start_pressed
- [x] Update controller_manager to populate new fields
- [x] Update mock_server for testing support
- [x] Update prev_state tracking in menu service

## Testing

1. Enter admin mode (hold all 4 face buttons)
2. Press Circle repeatedly - should cycle through 5 sensitivity levels
3. Press Start/Select - should cycle game modes
4. Hold Trigger for 2 seconds - should force start game
5. Normal players cannot change game mode (Select/Start do nothing outside admin mode)

## Comparison with Original

| Feature | Original (legacy) | New (Phase 79) |
|---------|-------------------|----------------|
| Sensitivity levels | 5 | 5 (restored) |
| Force start | Trigger hold 2s | Trigger hold 2s |
| Game mode selection | Any player (Select/Start) | Admin only (Select/Start) |
| Add/remove random_modes | Cross button | Not needed |
| random_team_size | Move cycle | Replaced with num_teams |
