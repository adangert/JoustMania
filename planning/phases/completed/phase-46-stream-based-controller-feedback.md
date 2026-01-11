# Phase 46: Stream-Based Controller Feedback

**Status**: Completed
**Dependencies**: Phase 45 (Adaptive Controller Filtering)
**Actual Effort**: ~2 hours
**Type**: Performance Optimization

---

## Overview

Extend the Phase 45 bidirectional streaming to include controller feedback commands (colors, effects, vibration) during gameplay. This eliminates the latency overhead of separate unary RPCs and provides ordering guarantees for feedback commands relative to controller state updates.

## Problem Statement

Currently, controller feedback (SetControllerColor, PlayControllerEffect, SetControllerVibration) uses separate unary RPCs. During gameplay, this creates:

1. **Latency overhead**: Each command requires a new RPC round-trip (~10-20ms total)
2. **No ordering guarantees**: Color changes and state updates can arrive out of order
3. **Context switching**: Server handles feedback on different code paths than streaming
4. **Missed optimization**: We already have an open bidirectional stream during gameplay

## Solution

Extend `GameplayStreamControl` to include feedback commands, allowing the Game Coordinator to send colors, effects, and vibration through the existing stream during gameplay.

### Hybrid Approach

**During Gameplay** (stream exists):
- Send feedback via `GameplayStreamControl` messages
- Benefits: Lower latency, ordering guarantees, no extra RPCs

**In Menus/Lobby** (no stream):
- Keep existing unary RPCs (SetControllerColor, etc.)
- Simplicity: No need to manage stream lifecycle outside gameplay

This hybrid approach maximizes performance where it matters (gameplay) while keeping menus simple.

---

## Technical Design

### Proto Changes

Extend `GameplayStreamControl` oneof to include feedback commands:

```protobuf
message GameplayStreamControl {
  oneof control {
    GameplayStreamConfig config = 1;           // Initial configuration (Phase 45)
    FilterUpdate filter_update = 2;            // Mid-stream filter change (Phase 45)
    ColorCommand color_command = 3;            // NEW: Set controller color
    EffectCommand effect_command = 4;          // NEW: Play controller effect
    VibrationCommand vibration_command = 5;    // NEW: Set controller vibration
  }
}

message ColorCommand {
  string serial = 1;          // Target controller (empty = all)
  Color color = 2;            // RGB color
}

message EffectCommand {
  string serial = 1;          // Target controller (empty = all)
  string effect_name = 2;     // Effect identifier
}

message VibrationCommand {
  string serial = 1;          // Target controller (empty = all)
  int32 duration_ms = 2;      // Vibration duration
  int32 intensity = 3;        // Vibration intensity (0-255)
}
```

**Design notes**:
- Reuse existing Color message definition
- Empty serial means "all controllers" (broadcast)
- Commands processed immediately when received
- No response needed (fire-and-forget like existing RPCs)

### Server Implementation

Update `StreamGameplayDataDynamic` to process feedback commands:

```python
async def read_client_updates():
    nonlocal current_hz, current_filter

    try:
        async for control_msg in request_iterator:
            if control_msg.HasField("config"):
                # ... existing config handling (Phase 45)

            elif control_msg.HasField("filter_update"):
                # ... existing filter handling (Phase 45)

            elif control_msg.HasField("color_command"):
                # NEW: Process color command
                cmd = control_msg.color_command
                target_serial = cmd.serial if cmd.serial else None

                for serial in self.tracked_controllers.keys():
                    if target_serial is None or serial == target_serial:
                        await self._set_controller_color_internal(
                            serial, cmd.color
                        )

                logger.debug(
                    f"[{subscriber_id}] Color command: "
                    f"serial={cmd.serial or 'all'}, "
                    f"rgb=({cmd.color.r},{cmd.color.g},{cmd.color.b})"
                )

            elif control_msg.HasField("effect_command"):
                # NEW: Process effect command
                cmd = control_msg.effect_command
                target_serial = cmd.serial if cmd.serial else None

                for serial in self.tracked_controllers.keys():
                    if target_serial is None or serial == target_serial:
                        await self._play_effect_internal(
                            serial, cmd.effect_name
                        )

                logger.debug(
                    f"[{subscriber_id}] Effect command: "
                    f"serial={cmd.serial or 'all'}, effect={cmd.effect_name}"
                )

            elif control_msg.HasField("vibration_command"):
                # NEW: Process vibration command
                cmd = control_msg.vibration_command
                target_serial = cmd.serial if cmd.serial else None

                for serial in self.tracked_controllers.keys():
                    if target_serial is None or serial == target_serial:
                        await self._set_vibration_internal(
                            serial, cmd.duration_ms, cmd.intensity
                        )

                logger.debug(
                    f"[{subscriber_id}] Vibration command: "
                    f"serial={cmd.serial or 'all'}, "
                    f"duration={cmd.duration_ms}ms, intensity={cmd.intensity}"
                )

    except Exception as e:
        logger.error(f"[{subscriber_id}] Error reading client updates: {e}")
```

**Key points**:
- Extract existing color/effect/vibration logic into `_*_internal()` methods
- Reuse this logic from both stream and unary RPCs
- Process commands in background task (non-blocking)
- Support broadcast (empty serial) and targeted commands

### Client Implementation

Update game modes to send feedback via stream during gameplay:

**Example: Sending color on death**
```python
# OLD (separate RPC)
await self.controller_client.SetControllerColor(
    controller_manager_pb2.SetControllerColorRequest(
        serial=serial,
        color=controller_manager_pb2.Color(r=255, g=0, b=0)
    )
)

# NEW (via stream during gameplay)
color_msg = controller_manager_pb2.GameplayStreamControl(
    color_command=controller_manager_pb2.ColorCommand(
        serial=serial,
        color=controller_manager_pb2.Color(r=255, g=0, b=0)
    )
)
await stream.write(color_msg)
```

**Example: Broadcast effect on game start**
```python
# Send to all controllers via stream
effect_msg = controller_manager_pb2.GameplayStreamControl(
    effect_command=controller_manager_pb2.EffectCommand(
        serial="",  # Empty = broadcast
        effect_name="game_start"
    )
)
await stream.write(effect_msg)
```

### Backward Compatibility

**Keep existing unary RPCs**:
- `SetControllerColor`
- `PlayControllerEffect`
- `SetControllerVibration`

**Usage**:
- Menu system: Continue using unary RPCs (no stream exists)
- Lobby: Continue using unary RPCs (stream not started yet)
- Gameplay: Use stream-based commands (stream already exists)

**Migration path**:
1. Add stream-based commands (Phase 46)
2. Update game modes to use stream during gameplay
3. Keep unary RPCs for non-gameplay contexts
4. Future: Could deprecate unary RPCs if all contexts use streams

---

## Performance Impact

### Latency Reduction

**Current (unary RPC)**:
```
Game Coordinator                Controller Manager
      |                                |
      |----> SetControllerColor ------>|
      |         (~10-20ms)             |
      |<----- Response ----------------|
      |                                |
```

**New (stream-based)**:
```
Game Coordinator                Controller Manager
      |                                |
      |-- (stream already open) -------|
      |                                |
      |-- color_command (in stream) -->|
      |    (~0-2ms, no round-trip)     |
      |                                |
```

**Savings**: ~10-18ms per feedback command

### Ordering Guarantees

**Current**: Color changes and state updates can arrive out of order

**Example race condition**:
```
Time T0: Player dies (client updates player.alive = False)
Time T1: Send SetControllerColor (red) - separate RPC
Time T2: Send filter update (remove from active list)

Server might receive in wrong order:
- Filter update arrives first → controller filtered
- Color command arrives second → controller not in active list, command fails
```

**New**: Commands sent on same stream arrive in order
```
Time T0: Player dies
Time T1: Send color_command (red) via stream
Time T2: Send filter_update via stream

Server receives in guaranteed order:
- Color command arrives first → color set
- Filter update arrives second → controller filtered (but color already set)
```

### Batching Potential

Can send multiple commands in quick succession without waiting for responses:

```python
# Kill multiple players at once (explosion effect)
for player in killed_players:
    color_msg = controller_manager_pb2.GameplayStreamControl(
        color_command=controller_manager_pb2.ColorCommand(
            serial=player.serial,
            color=controller_manager_pb2.Color(r=255, g=0, b=0)
        )
    )
    await stream.write(color_msg)  # Non-blocking

# Then send single filter update
filter_msg = controller_manager_pb2.GameplayStreamControl(
    filter_update=controller_manager_pb2.FilterUpdate(
        serials=list(alive_serials)
    )
)
await stream.write(filter_msg)
```

---

## Implementation Plan

### Task 1: Proto Definition

**File**: `proto/controller_manager.proto`

1. Add `ColorCommand` message
2. Add `EffectCommand` message
3. Add `VibrationCommand` message
4. Extend `GameplayStreamControl` oneof with 3 new fields
5. Regenerate Python code

**Verification**: Import new messages in Python REPL

### Task 2: Server Implementation

**File**: `services/controller_manager/server.py`

1. Extract color logic into `_set_controller_color_internal(serial, color)`
2. Extract effect logic into `_play_effect_internal(serial, effect_name)`
3. Extract vibration logic into `_set_vibration_internal(serial, duration, intensity)`
4. Update `SetControllerColor` to call internal method
5. Update `PlayControllerEffect` to call internal method
6. Update `SetControllerVibration` to call internal method
7. Add color_command handling in `read_client_updates()`
8. Add effect_command handling in `read_client_updates()`
9. Add vibration_command handling in `read_client_updates()`

**Verification**: Use grpcurl to send commands via stream, check logs

### Task 3: Client Implementation

**File**: `services/game_coordinator/games/base.py`

1. Update `_handle_death()` to send color via stream if stream exists
2. Update game start to send effects via stream
3. Add helper method `_send_controller_color(serial, color)`
4. Add helper method `_send_controller_effect(serial, effect_name)`

**File**: `services/game_coordinator/games/nonstop_joust.py`

1. Update respawn logic to send colors via stream
2. Update any nonstop-specific effects to use stream

**Verification**: Play game, check colors change on death/respawn via stream

### Task 4: Metrics

**File**: `services/controller_manager/metrics.py`

Add counter for stream-based commands:

```python
# Phase 46: Stream-based feedback commands
stream_commands_total = Counter(
    'controller_stream_commands_total',
    'Total feedback commands received via stream',
    ['command_type']  # 'color', 'effect', 'vibration'
)
```

**Usage**:
```python
# In read_client_updates()
metrics.stream_commands_total.labels(command_type='color').inc()
metrics.stream_commands_total.labels(command_type='effect').inc()
metrics.stream_commands_total.labels(command_type='vibration').inc()
```

**Verification**: Check `/metrics` endpoint, verify counters increment

### Task 5: Testing

**File**: `tests/integration/test_stream_feedback.py` (new)

Tests:
1. Send color_command via stream, verify controller changes color
2. Send effect_command via stream, verify effect plays
3. Send vibration_command via stream, verify vibration triggers
4. Send broadcast commands (empty serial), verify all controllers affected
5. Verify ordering: color then filter update
6. Verify stream commands work alongside filter updates
7. Verify unary RPCs still work (backward compatibility)

**File**: `tools/validate_stream_feedback.py` (new)

Validation checks:
1. Proto messages defined correctly
2. Server processes all 3 command types
3. Metrics defined and accessible
4. Helper methods extracted properly

**Verification**: All tests pass, validation script succeeds

---

## Metrics to Add

```python
# Phase 46: Stream-based feedback commands (Controller Manager)
from prometheus_client import Counter

stream_commands_total = Counter(
    'controller_stream_commands_total',
    'Total feedback commands received via stream',
    ['command_type']  # 'color', 'effect', 'vibration'
)
```

**Usage in code**:
```python
# When processing color_command
metrics.stream_commands_total.labels(command_type='color').inc()

# When processing effect_command
metrics.stream_commands_total.labels(command_type='effect').inc()

# When processing vibration_command
metrics.stream_commands_total.labels(command_type='vibration').inc()
```

---

## Testing Strategy

### Unit Tests

**Test 1: Color command processing**
```python
async def test_color_command_via_stream():
    # Send color_command via stream
    # Verify _set_controller_color_internal() called
    # Verify color applied to controller
```

**Test 2: Effect command processing**
```python
async def test_effect_command_via_stream():
    # Send effect_command via stream
    # Verify _play_effect_internal() called
    # Verify effect triggered
```

**Test 3: Broadcast commands**
```python
async def test_broadcast_color_command():
    # Send color_command with serial=""
    # Verify all tracked controllers receive color
```

### Integration Tests

**Test 4: Ordering guarantees**
```python
async def test_command_ordering():
    # Send color_command followed by filter_update
    # Verify color arrives before filter
    # Verify color still applied even if filtered after
```

**Test 5: Mixed commands**
```python
async def test_mixed_stream_commands():
    # Send: config → filter_update → color_command → effect_command
    # Verify all processed in order
```

**Test 6: Backward compatibility**
```python
async def test_unary_rpcs_still_work():
    # Call SetControllerColor (unary RPC)
    # Verify it still works
    # Verify same internal method used
```

### Performance Tests

**Test 7: Latency comparison**
```python
async def test_stream_vs_unary_latency():
    # Measure 100 color commands via unary RPC
    # Measure 100 color commands via stream
    # Expect stream to be 5-10ms faster per command
```

---

## Risks & Mitigations

### Risk 1: Complexity of Hybrid Approach

**Concern**: Two ways to send feedback (stream vs unary) could confuse developers

**Mitigation**:
- Document clearly: "Use stream during gameplay, unary in menus"
- Add helper methods that choose automatically based on context
- Future: Could add wrapper that picks the right approach

### Risk 2: Stream Write Failures

**Concern**: What if `stream.write()` fails during gameplay?

**Mitigation**:
- Wrap in try/except, fall back to unary RPC
- Log failure for debugging
- Color/effect failures are non-critical (game continues)

### Risk 3: Command Processing Overhead

**Concern**: Processing feedback in background task could slow down stream

**Mitigation**:
- Commands are lightweight (just setting color/effect)
- Background task runs concurrently with main stream loop
- No blocking operations in command handlers

---

## Expected Benefits

### Latency Improvement

**Per-command savings**: 10-18ms
**Typical game scenario**: 25-player FFA with ~10 color changes/effects per second
**Total savings**: ~100-180ms per second of gameplay latency overhead

### Ordering Guarantees

**Eliminates race conditions**:
- Color changes always arrive before filter updates
- Multiple effects on same controller arrive in order
- State updates and feedback stay synchronized

### Cleaner Architecture

**Unified gameplay communication**:
- All gameplay-related messages on one stream
- No context switching between stream and unary RPCs
- Easier to reason about message ordering

---

## Future Enhancements (Not in Scope)

**Phase 47+: Dynamic Hz Updates**
- Use same stream to adjust update_frequency_hz mid-game
- Could reduce Hz in late game for additional savings

**Phase 48+: Batched Commands**
- Add BatchCommand message for multiple colors/effects at once
- Further reduce overhead for simultaneous effects

**Phase 49+: Response Stream**
- Send acknowledgments for critical commands
- Enable error handling for failed commands

---

## Summary

Phase 46 extends the Phase 45 bidirectional stream to include controller feedback commands, providing:

✅ **Lower latency**: 10-18ms savings per command
✅ **Ordering guarantees**: Commands arrive in sequence
✅ **Cleaner architecture**: All gameplay messages on one channel
✅ **Backward compatible**: Existing unary RPCs continue working
✅ **Low complexity**: ~2 hours of implementation

**Next Steps**:
1. Task 1: Proto definition
2. Task 2: Server implementation
3. Task 3: Client implementation
4. Task 4: Metrics
5. Task 5: Testing

---

**End of Phase 46 Plan**
