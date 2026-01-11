# Phase 28: Admin Mode Completion

**Status:** ✅ COMPLETE
**Date Completed:** 2026-01-11 (retroactively documented)
**Priority:** MEDIUM
**Dependency:** Phase 23 (Admin Mode & Advanced Controls)

## Goal

Complete admin mode implementation with actual settings persistence, making Phase 23's visual feedback functionally operational.

## Motivation

**Phase 23 Status:**
- ✅ Admin mode detection and state management
- ✅ Visual feedback for all admin actions
- ✅ Battery display functionality
- ❌ Sensitivity cycling showed feedback but didn't change settings
- ❌ Instruction toggle showed feedback but didn't affect audio
- ❌ Team/force start changes didn't persist

**Problem:**
- Users saw visual feedback but settings didn't actually change
- No integration with Settings service for persistence
- Admin mode was "pretty but powerless"

**Solution:**
- Connect admin handlers to Settings service
- Implement GetSetting/UpdateSetting RPC calls
- Add settings validation and error handling
- Ensure settings persist to joustsettings.yaml

## Implementation Summary

### 1. Sensitivity Persistence

**File**: `services/menu/server.py:895-971`

Implemented full sensitivity cycling with Settings service integration:

```python
async def _handle_admin_sensitivity(self, serial: str):
    """
    Handle sensitivity cycling in admin mode (Phase 28).

    Cycles through: Slow (0) → Medium (1) → Fast (2) → Slow
    """
    # Get current sensitivity from Settings service
    settings_stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
    get_request = settings_pb2.GetSettingRequest(key="sensitivity")
    get_response = await settings_stub.GetSetting(get_request)
    current = int(get_response.value) if get_response.value else 1

    # Validate current value is in range
    if current < 0 or current > 2:
        logger.warning(f"Invalid sensitivity value {current}, resetting to 1")
        current = 1

    # Cycle: 0 (slow) → 1 (medium) → 2 (fast) → 0
    new_value = str((current + 1) % 3)

    # Update setting in Settings service
    update_request = settings_pb2.UpdateSettingRequest(
        key="sensitivity",
        value=new_value,
        source="admin_mode"  # Track that change came from admin
    )
    await settings_stub.UpdateSetting(update_request)

    # Visual feedback: Color by sensitivity level
    sensitivity_colors = [
        (0, 0, 255),    # Slow: Blue
        (0, 255, 0),    # Medium: Green
        (255, 0, 0)     # Fast: Red
    ]
    color = sensitivity_colors[int(new_value)]

    # Show color pulse
    effect_request = controller_manager_pb2.PlayControllerEffectRequest(
        serial=serial,
        effect=controller_manager_pb2.ControllerEffect.EFFECT_PULSE,
        color=controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]),
        duration_ms=800,
        speed=5,
    )
    await controller_stub.PlayControllerEffect(effect_request)

    logger.info(f"Sensitivity changed by admin: {current} → {new_value}")
```

**Features:**
- Gets current value from Settings service
- Validates value is in range [0, 2]
- Cycles to next sensitivity level
- Updates Settings service with source="admin_mode"
- Shows color-coded visual feedback
- Logs change with old/new values
- OpenTelemetry span with event

**Settings Integration:**
- Setting key: "sensitivity"
- Values: "0" (slow), "1" (medium), "2" (fast)
- Persists to joustsettings.yaml automatically
- Game Coordinator reads updated value on next game start

**Visual Feedback:**
- **Slow (0)**: Blue pulse (0, 0, 255)
- **Medium (1)**: Green pulse (0, 255, 0)
- **Fast (2)**: Red pulse (255, 0, 0)
- Duration: 800ms pulse effect

### 2. Instruction Toggle Persistence

**File**: `services/menu/server.py:1030-1097`

Implemented instruction toggle with Settings service integration:

```python
async def _handle_admin_instructions(self, serial: str):
    """
    Handle instruction toggle in admin mode (Phase 28).

    Toggles instruction display on/off.
    """
    # Get current instruction state from Settings service
    settings_stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
    get_request = settings_pb2.GetSettingRequest(key="instructions")
    get_response = await settings_stub.GetSetting(get_request)
    current = get_response.value if get_response.value else "true"

    # Toggle: true ↔ false
    new_value = "false" if current == "true" else "true"

    # Update setting in Settings service
    update_request = settings_pb2.UpdateSettingRequest(
        key="instructions",
        value=new_value,
        source="admin_mode"
    )
    await settings_stub.UpdateSetting(update_request)

    # Visual feedback: Green (enabled) or Red (disabled)
    if new_value == "true":
        color = controller_manager_pb2.RGB(r=0, g=255, b=0)  # Green - enabled
    else:
        color = controller_manager_pb2.RGB(r=255, g=0, b=0)  # Red - disabled

    # Show color pulse
    effect_request = controller_manager_pb2.PlayControllerEffectRequest(
        serial=serial,
        effect=controller_manager_pb2.ControllerEffect.EFFECT_PULSE,
        color=color,
        duration_ms=800,
        speed=5,
    )
    await controller_stub.PlayControllerEffect(effect_request)

    logger.info(f"Instructions toggled by admin: {current} → {new_value}")
```

**Features:**
- Gets current state from Settings service
- Toggles between "true" and "false"
- Updates Settings service with source="admin_mode"
- Shows color-coded visual feedback
- Logs toggle event
- OpenTelemetry span with event

**Settings Integration:**
- Setting key: "instructions"
- Values: "true" (enabled), "false" (disabled)
- Persists to joustsettings.yaml automatically
- Audio service respects setting in real-time

**Visual Feedback:**
- **Enabled (true)**: Green pulse (0, 255, 0)
- **Disabled (false)**: Red pulse (255, 0, 0)
- Duration: 800ms pulse effect

### 3. Team Count Adjustment with Persistence

**Files**: `services/menu/server.py:1150-1210, 1211-1271`

Implemented team count cycling with Settings service integration:

**Increase Handler:**
```python
async def _handle_admin_increase_value(self, serial: str):
    """Increase the value of the current admin option."""
    option_name = self.admin_option_names[self.admin_current_option]

    # Get current value
    get_request = settings_pb2.GetSettingRequest(key=option_name)
    get_response = await stub.GetSetting(get_request)
    current_value = get_response.value

    if option_name == "num_teams":
        # Cycle: 2 → 3 → 4 → 5 → 6 → 2
        current = int(current_value) if current_value else 2
        # Validate range [2, 6]
        if current < 2 or current > 6:
            logger.warning(f"Invalid num_teams value {current}, resetting to 2")
            current = 2
        new_value = str((current % 6) + 1) if current < 6 else "2"

    # Update setting
    update_request = settings_pb2.UpdateSettingRequest(
        key=option_name, value=new_value, source="admin_mode"
    )
    await stub.UpdateSetting(update_request)

    # Visual feedback
    await self._show_value_feedback(serial, option_name, new_value)
```

**Features:**
- Gets current value from Settings service
- Validates value is in range [2, 6]
- Cycles to next/previous team count
- Updates Settings service with source="admin_mode"
- Shows visual feedback (flashes N times for N teams)
- Logs change event
- Error handling for invalid values

**Settings Integration:**
- Setting key: "num_teams"
- Values: "2", "3", "4", "5", "6"
- Persists to joustsettings.yaml automatically
- Game Coordinator uses value for team-based games

**Visual Feedback:**
- Flashes white LED N times (N = number of teams)
- Each flash: 200ms on, 100ms off
- Total duration: ~1.5-3 seconds depending on team count

### 4. Force Start Mode with Persistence

**Files**: `services/menu/server.py:1150-1210, 1211-1271`

Implemented force start toggle with Settings service integration:

```python
if option_name == "force_all_start":
    # Toggle: true ↔ false
    # Validate boolean
    if current_value not in ["true", "false"]:
        logger.warning(f"Invalid force_all_start value {current_value}, resetting to false")
        current_value = "false"
    new_value = "true" if current_value == "false" else "false"

# Update setting
update_request = settings_pb2.UpdateSettingRequest(
    key=option_name, value=new_value, source="admin_mode"
)
await stub.UpdateSetting(update_request)

# Visual feedback
await self._show_value_feedback(serial, option_name, new_value)
```

**Features:**
- Gets current state from Settings service
- Validates boolean value ("true" or "false")
- Toggles between modes
- Updates Settings service with source="admin_mode"
- Shows color-coded visual feedback
- Logs toggle event
- Error handling for invalid values

**Settings Integration:**
- Setting key: "force_all_start"
- Values: "true" (All), "false" (Trigger Only)
- Persists to joustsettings.yaml automatically
- Menu service uses value when force-starting games

**Visual Feedback:**
- **All (true)**: Green pulse (0, 255, 0) - 800ms
- **Trigger Only (false)**: Red pulse (255, 0, 0) - 800ms

### 5. Settings Validation

**Validation Rules Implemented:**

**Sensitivity:**
- Range: [0, 2]
- Default on invalid: 1 (medium)
- Warning logged if out of range

**Instructions:**
- Values: "true" or "false"
- Default on invalid: "true"
- Implicit validation (toggle assumes boolean)

**Num Teams:**
- Range: [2, 6]
- Default on invalid: 2
- Warning logged if out of range
- Cycle wraps around (6 → 2, 2 → 6)

**Force Start:**
- Values: "true" or "false"
- Default on invalid: "false"
- Warning logged if invalid
- Toggle handles validation

**Error Handling:**
```python
try:
    # Get/update setting
    ...
except Exception as e:
    logger.error(f"Error changing sensitivity: {e}", exc_info=True)
    # Span records error
    # Controller remains functional
```

All admin handlers wrap operations in try/except blocks to prevent crashes.

### 6. OpenTelemetry Integration

**All admin handlers emit structured traces:**

```python
with tracer.start_as_current_span("admin_sensitivity") as span:
    span.set_attribute("controller.serial", serial)

    # ... perform operation ...

    span.add_event("sensitivity_changed", {
        "old_value": current,
        "new_value": new_value,
        "sensitivity_name": sensitivity_names[int(new_value)]
    })
```

**Benefits:**
- Track admin mode usage patterns
- Monitor settings changes over time
- Debug issues with setting persistence
- Correlate admin actions with game outcomes

## Channel Management

**Phase 26 Integration:**

All admin handlers use persistent gRPC channels:
```python
# Reuse persistent channels (Phase 26)
settings_stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
controller_stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(
    self.controller_channel
)
```

**Benefits:**
- Reduced connection overhead
- Faster admin operations
- Better resource utilization
- Consistent with rest of menu service

## Documentation Updates

**File**: `README.md:228`

Added note about settings persistence:
```markdown
**Note:** Sensitivity and instruction settings persist to the Settings service
and apply to all subsequent games.
```

Documentation already included:
- Sensitivity levels and colors
- Instruction toggle feedback
- Team count range and feedback
- Force start mode options and feedback

## Files Modified

**Core Implementation:**
- `services/menu/server.py` (settings persistence added to admin handlers)

**No new files created** - Phase 28 enhanced existing Phase 23 implementation

**Lines of Code:**
- ~200 lines of Settings service integration
- ~100 lines of validation logic
- ~50 lines of error handling

## Success Criteria

- ✅ **Sensitivity cycling updates Settings service**
- ✅ **New sensitivity applies to next game**
- ✅ **Instruction toggle affects audio playback**
- ✅ **Team count changes persist**
- ✅ **Force start mode persists**
- ✅ **Settings persist to joustsettings.yaml**
- ✅ **Visual feedback matches actual state**
- ✅ **Settings validation prevents invalid values**
- ✅ **Error handling prevents crashes**
- ✅ **OpenTelemetry spans track all admin actions**

## Integration with Other Phases

**Phase 23 (Admin Mode & Advanced Controls):**
- Provided admin mode framework
- Implemented visual feedback system
- Created admin handler stubs

**Phase 26 (Network Architecture Improvements):**
- Persistent gRPC channels used by admin handlers
- Reduced connection overhead
- Better performance

**Phase 38 (Production Metrics & Monitoring):**
- Admin actions can be tracked via metrics
- Settings changes visible in Grafana
- OpenTelemetry traces correlate with metrics

## Expected Benefits

**Functional Admin Mode:**
- Settings actually change when admin adjusts them
- Visual feedback accurately reflects saved state
- Changes persist across games and restarts

**Settings Visibility:**
- WebUI shows current settings
- Settings service maintains consistency
- All services read from same source of truth

**Event Management:**
- Hosts can tune gameplay without stopping
- Sensitivity adjusts for skill levels
- Instructions can be silenced for experienced players
- Team count easily adjusted between games

**Reliability:**
- Validation prevents invalid settings
- Error handling prevents crashes
- Logging aids troubleshooting

## Raspberry Pi Impact

**Performance:**
- Minimal overhead: Only 2-3 gRPC calls per admin action
- Persistent channels reduce connection cost
- Settings updates are async and non-blocking
- No impact on gameplay performance

**Storage:**
- Settings persist to joustsettings.yaml (< 1KB)
- No additional disk usage

## Testing Validation

**Manual Testing Verified:**
1. ✅ Sensitivity changes take effect in next game
2. ✅ Instruction toggle stops/starts audio prompts
3. ✅ Team count changes apply to team-based games
4. ✅ Force start mode affects game start behavior
5. ✅ Settings visible in WebUI after admin change
6. ✅ Settings persist across service restarts
7. ✅ Invalid values are caught and reset
8. ✅ Errors don't crash menu service

**Automated Tests:**
- Phase 23 tests still pass (admin mode entry/exit)
- Settings service tests cover persistence
- Integration tests verify end-to-end flow

## Future Enhancements

Potential additions (not in scope):
- Convention mode toggle (add/remove games from rotation)
- Controller removal via PlayStation button hold
- Additional admin options (spawn protection, game duration)
- Admin mode timeout (auto-exit after inactivity)

## Completion Notes

Phase 28 successfully completed the admin mode implementation started in Phase 23. The combination of these phases provides:
- Full admin mode functionality matching original JoustMania
- Enhanced with better visual feedback
- Improved with proper settings persistence
- Monitored with OpenTelemetry observability

**Phase 28: Admin Mode Completion is COMPLETE.**
