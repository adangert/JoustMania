# Phase 23: Admin Mode & Advanced Controls

**Status:** ✅ COMPLETE
**Date Completed:** 2026-01-11 (retroactively documented)
**Priority:** MEDIUM
**Estimated Effort:** Medium (4-6 hours)

## Goal

Add admin mode for on-the-fly game settings adjustment via controller, replicating the admin mode functionality from the original JoustMania.

## Motivation

**Original JoustMania Features:**
- Admin mode accessed by pressing all 4 front buttons simultaneously
- Controller LED changes to admin mode color
- Adjust sensitivity, toggle instructions, check battery levels
- Essential for convention/party mode setup
- Allow event hosts to adjust settings without stopping the game

**Benefits:**
- ✅ **Live adjustments**: Change settings during events without restart
- ✅ **Battery monitoring**: Check all controller battery levels at a glance
- ✅ **Quick sensitivity**: Adjust difficulty for different player skill levels
- ✅ **Convention ready**: Optimized for multi-game events
- ✅ **Feature parity**: Matches original JoustMania capabilities

## Implementation Summary

### Admin Mode Detection & State Management

**Files**: `services/menu/server.py:131-133, 695-836`

Implemented comprehensive admin mode state tracking:
- 4-button combo detection (X + O + Square + Triangle)
- Per-controller admin mode state
- Entry time tracking for duration metrics
- Visual feedback with white LED flash on entry
- Graceful exit with fade-out effect

```python
class MenuServicer:
    def __init__(self):
        self.admin_mode_active = False
        self.admin_mode_controller = None  # Serial of controller in admin mode
        self.admin_mode_entry_time = 0
        self.admin_current_option = 0  # Current admin option index
        self.admin_option_names = ["num_teams", "force_all_start"]
        self.admin_option_colors = [(0, 255, 255), (128, 0, 128)]  # Cyan, Purple
```

**Features:**
- Only one controller can be in admin mode at a time
- Admin mode doesn't interfere with other controllers
- Lobby feedback suspended for admin controller
- OpenTelemetry spans for admin operations

### Admin Functions Implemented

#### 1. Battery Display (`_handle_admin_battery`)
**File**: `services/menu/server.py:972-1029`

Shows battery level on all controllers with color-coded LEDs:
- **Green**: >66% battery remaining
- **Yellow**: 33-66% battery remaining
- **Red**: <33% battery remaining
- **Duration**: 2 seconds display time

**Button**: Triangle (△)

```python
async def _handle_admin_battery(self, serial: str):
    # Get all controllers
    controllers_response = await stub.GetControllers(controllers_request)

    # Show battery for each controller
    for ctrl in controllers_response.controllers:
        battery_percent = ctrl.battery

        # Determine color based on battery level
        if battery_percent > 66:
            color = RGB(r=0, g=255, b=0)  # Green
        elif battery_percent > 33:
            color = RGB(r=255, g=255, b=0)  # Yellow
        else:
            color = RGB(r=255, g=0, b=0)  # Red

        await stub.SetControllerColor(...)
```

#### 2. Option Cycling (`_handle_admin_cycle_option`)
**File**: `services/menu/server.py:1099-1149`

Cycle through admin options with visual feedback:
- **Num Teams**: Cyan color (0, 255, 255)
- **Force Start**: Purple color (128, 0, 128)
- **Duration**: 1 second display

**Button**: Move button

#### 3. Value Adjustment (`_handle_admin_increase_value`, `_handle_admin_decrease_value`)
**Files**: `services/menu/server.py:1150-1271`

Increase/decrease current option value with persistence:

**Num Teams:**
- Range: 2-6 teams
- Feedback: Flashes N times for N teams
- Validates range [2, 6]

**Force Start Mode:**
- Values: "true" (All) or "false" (Trigger Only)
- Feedback: Green (All) / Red (Trigger Only)
- Validates boolean values

**Buttons**: Trigger (increase), X/Cross (decrease)

#### 4. Admin Mode Entry/Exit
**Files**: `services/menu/server.py:712-836`

**Entry** (`_enter_admin_mode`):
- Detect 4-button combo (X + O + Square + Triangle)
- Show white LED flash (3 times)
- Set admin mode state
- Log entry event
- OpenTelemetry span

**Exit** (`_exit_admin_mode`):
- PlayStation button press
- White fade-out effect (200ms × 10 steps)
- Clear admin mode state
- Log duration
- OpenTelemetry span

### Proto Changes

**File**: `proto/controller_manager.proto`

Added button state tracking to ControllerState:
```protobuf
message ControllerState {
    // ... existing fields ...

    // Individual button states (Phase 23 - Admin Mode)
    bool cross_pressed = 10;
    bool circle_pressed = 11;
    bool square_pressed = 12;
    bool triangle_pressed = 13;
}
```

### Controller Manager Updates

**File**: `services/controller_manager/server.py`

Updated controller state streaming to include button states:
- Track cross, circle, square, triangle buttons
- Stream button state changes
- Support admin mode combo detection

### Visual Feedback System

**File**: `services/menu/server.py:1272-1338`

Implemented comprehensive visual feedback for admin actions:

```python
async def _show_value_feedback(self, serial: str, option_name: str, value: str):
    if option_name == "num_teams":
        # Flash white N times (N = number of teams)
        num_flashes = int(value)
        for _ in range(num_flashes):
            # Flash implementation
    elif option_name == "force_all_start":
        # Green (All) or Red (Trigger Only)
        color = (0, 255, 0) if value == "true" else (255, 0, 0)
        # Show pulse effect
```

## Testing

**File**: `services/menu/tests/test_lobby_feedback.py:236-282`

Implemented tests for admin mode:
- `test_admin_mode_white_flash`: Verifies entry visual feedback
- `test_admin_mode_skips_lobby_feedback`: Ensures lobby feedback suspended
- `test_admin_mode_exit`: Verifies exit cleanup
- `test_admin_mode_doesnt_affect_ready_state`: Confirms state isolation

All tests pass successfully.

## Documentation

**File**: `README.md:203-258`

Comprehensive admin mode documentation added:
- How to access admin mode (4-button combo)
- Visual feedback description (white flash)
- Two control schemes documented:
  - Option Navigation (Move/Trigger/Cross)
  - Quick Access Functions (Circle/Triangle/Square)
- All admin settings explained with visual feedback
- Battery display colors documented
- Settings persistence noted

## Files Modified

**New/Modified Files:**
- `services/menu/server.py` (admin mode implementation)
- `proto/controller_manager.proto` (button states)
- `services/controller_manager/server.py` (button tracking)
- `services/menu/tests/test_lobby_feedback.py` (admin tests)
- `README.md` (admin mode documentation)

**Lines of Code:**
- ~500 lines of admin mode logic
- ~50 lines of tests
- ~60 lines of documentation

## Success Criteria

- ✅ **Admin mode accessible**: 4-button combo detection works
- ✅ **Battery display**: Shows accurate color-coded battery levels
- ✅ **Visual feedback**: All admin actions provide LED feedback
- ✅ **Option cycling**: Move button cycles through settings
- ✅ **Value adjustment**: Trigger/Cross increase/decrease values
- ✅ **State isolation**: Admin mode doesn't affect other controllers
- ✅ **Graceful exit**: PlayStation button exits with fade-out
- ✅ **Tests passing**: All admin mode tests pass
- ✅ **Documentation**: README includes comprehensive admin guide

## Integration with Phase 28

Phase 23 implemented the admin mode framework and visual feedback. Phase 28 (Admin Mode Completion) added settings persistence:
- Sensitivity changes persist to Settings service
- Instruction toggle persists to Settings service
- Team count changes persist
- Force start mode persists

Together, these phases provide complete admin mode functionality with persistence.

## Expected Benefits

**Event Management:**
- Quick settings adjustments without stopping games
- Battery monitoring prevents mid-game failures
- Sensitivity tuning for mixed skill levels

**User Experience:**
- Intuitive controller-based configuration
- Clear visual feedback for all actions
- No need for WebUI access during events

**Feature Parity:**
- Matches original JoustMania admin capabilities
- Enhanced with better visual feedback
- Improved with OpenTelemetry observability

## Raspberry Pi Impact

- Minimal overhead: Admin processing only when active
- No impact on gameplay performance
- Settings changes propagate through existing gRPC channels
- LED effects use existing controller manager

**Phase 23: Admin Mode & Advanced Controls is COMPLETE.**
