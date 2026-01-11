# Phase 41: Controller Data Stream Split

**Status**: Planned
**Priority**: Medium
**Complexity**: Medium
**Estimated Effort**: 4-6 hours

## Overview

Split controller data streaming into two separate gRPC endpoints optimized for their specific use cases:
1. **Button events stream** - Event-driven gRPC stream for discrete button press events (menu/lobby navigation)
2. **Gameplay data stream** - Continuous streaming endpoint for acceleration and game-critical data (gameplay only)

This architectural change improves efficiency, reduces unnecessary data transfer, and better aligns the data delivery model with actual usage patterns.

## Motivation

**Current State:**
- Single `StreamControllerStates` endpoint provides all controller data (buttons + acceleration + gyro)
- Menu service polls at 30Hz but only needs discrete button press events
- Game modes poll at 60Hz but only need acceleration data (no button presses currently)
- Significant wasted bandwidth sending button data during gameplay and acceleration data during menu

**Problems:**
1. **Inefficiency**: Menu constantly polls for button data even when no buttons are pressed
2. **Bandwidth waste**: Game modes receive unused button data at 60Hz during gameplay
3. **Coupling**: Button press handling and acceleration processing artificially coupled
4. **Polling overhead**: Menu must poll continuously instead of reacting to button events
5. **Not scalable**: Adding more button-driven features increases polling overhead

**Benefits of Split:**
- ✅ **Event-driven menu**: Button presses delivered as discrete events, no polling needed
- ✅ **Bandwidth reduction**: ~40% reduction in menu data (no acceleration/gyro)
- ✅ **Bandwidth reduction**: ~15% reduction in gameplay data (no button states)
- ✅ **Better architecture**: Event-driven for events, streaming for continuous data
- ✅ **Clearer separation**: Menu concerns vs gameplay concerns decoupled
- ✅ **Future-ready**: Easy to add button events during gameplay (pause menus, emotes) without affecting game loop

## Current Implementation

### Existing Stream (controller_manager.proto)
```protobuf
service ControllerManagerService {
  // Current unified stream - ALL data
  rpc StreamControllerStates(StreamRequest) returns (stream ControllerStateUpdate);
}

message ControllerState {
  string serial = 1;
  // ... other fields ...
  bool trigger_pressed = 4;
  bool move_pressed = 5;
  Vector3 accel = 9;       // Only needed by games
  Vector3 gyro = 10;       // Only needed by games
  bool cross_pressed = 11;
  bool circle_pressed = 12;
  bool square_pressed = 13;
  bool triangle_pressed = 14;
  bool ps_pressed = 15;
}
```

### Current Consumers

**Menu Service** (services/menu/server.py:402)
- Uses: `StreamControllerStates` at 30Hz
- Needs: Button press events only (trigger, move, cross, circle, square, triangle, ps)
- Wastes: Acceleration and gyro data

**Game Coordinator** (services/game_coordinator/games/base.py:348)
- Uses: `StreamControllerStates` at 60Hz
- Needs: Acceleration data only
- Wastes: Button state data

## Proposed Architecture

### New Button Events Stream

```protobuf
service ControllerManagerService {
  // NEW: Event-driven button press stream
  rpc StreamButtonEvents(ButtonEventStreamRequest) returns (stream ButtonEvent);

  // MODIFIED: Gameplay data only (no buttons)
  rpc StreamGameplayData(GameplayStreamRequest) returns (stream GameplayDataUpdate);

  // DEPRECATED: Keep for backward compatibility, mark for removal
  rpc StreamControllerStates(StreamRequest) returns (stream ControllerStateUpdate);
}

// Button event message
message ButtonEvent {
  string serial = 1;
  int64 timestamp = 2;        // Unix timestamp in milliseconds
  ButtonType button = 3;       // Which button
  ButtonAction action = 4;     // Press or release
  int32 battery = 5;          // Battery level at time of event
  RGB color = 6;              // Current controller color
}

enum ButtonType {
  BUTTON_TRIGGER = 0;
  BUTTON_MOVE = 1;
  BUTTON_CROSS = 2;
  BUTTON_CIRCLE = 3;
  BUTTON_SQUARE = 4;
  BUTTON_TRIANGLE = 5;
  BUTTON_PS = 6;
}

enum ButtonAction {
  ACTION_PRESS = 0;    // Button transitioned from released to pressed
  ACTION_RELEASE = 1;  // Button transitioned from pressed to released
}

message ButtonEventStreamRequest {
  // Empty - all button events are streamed
  // Could add filter options in future (e.g., specific buttons, controllers)
}

// Gameplay data message (no buttons)
message GameplayData {
  string serial = 1;
  int32 move_num = 2;
  int32 battery = 3;
  bool ready = 6;
  int32 team = 7;
  RGB color = 8;
  Vector3 accel = 9;      // Primary gameplay data
  Vector3 gyro = 10;      // Secondary gameplay data
  // NO button states
}

message GameplayDataUpdate {
  repeated GameplayData controllers = 1;
  int64 timestamp = 2;
}

message GameplayStreamRequest {
  int32 update_frequency_hz = 1;  // Desired frequency (default: 60)
}
```

## Implementation Tasks

### Task 1: Add Button Event Stream to Controller Manager
**File**: `services/controller_manager/server.py`

**Changes:**
- [ ] Add button state tracking per controller (detect press/release transitions)
- [ ] Implement `StreamButtonEvents` RPC
  - [ ] Track previous button states for each controller
  - [ ] Detect transitions (False → True = press, True → False = release)
  - [ ] Send `ButtonEvent` message for each transition
  - [ ] Include timestamp, serial, button type, action
- [ ] Add internal event queue for button events
- [ ] Handle multiple concurrent subscribers to button stream

**Code structure:**
```python
class ControllerManagerServicer:
    def __init__(self):
        # New: Button event tracking
        self.button_event_queue = asyncio.Queue()
        self.button_states = {}  # {serial: {button: bool}}

    async def StreamButtonEvents(self, request, context):
        """Stream button press/release events as they occur."""
        subscriber_queue = asyncio.Queue()
        # Subscribe to button events
        # Stream events to client

    def _detect_button_transitions(self, serial, controller_state):
        """Detect button press/release and queue events."""
        # Compare with previous state
        # Queue ButtonEvent for any transitions
```

**Lines**: ~150 new lines

### Task 2: Add Gameplay Data Stream to Controller Manager
**File**: `services/controller_manager/server.py`

**Changes:**
- [ ] Implement `StreamGameplayData` RPC
- [ ] Create `GameplayData` message from `ControllerState` (strip button fields)
- [ ] Support configurable frequency (default 60Hz)
- [ ] Reuse existing controller state reading logic

**Code structure:**
```python
async def StreamGameplayData(self, request, context):
    """Stream gameplay data (acceleration, gyro) without button states."""
    frequency = request.update_frequency_hz or 60
    interval = 1.0 / frequency

    while context.is_active():
        # Get controller states
        gameplay_data = [self._to_gameplay_data(c) for c in controllers]
        yield GameplayDataUpdate(controllers=gameplay_data, timestamp=...)
        await asyncio.sleep(interval)
```

**Lines**: ~100 new lines

### Task 3: Update Protocol Buffer Definitions
**File**: `proto/controller_manager.proto`

**Changes:**
- [ ] Add `ButtonEvent` message
- [ ] Add `ButtonType` enum
- [ ] Add `ButtonAction` enum
- [ ] Add `ButtonEventStreamRequest` message
- [ ] Add `GameplayData` message (ControllerState without buttons)
- [ ] Add `GameplayDataUpdate` message
- [ ] Add `GameplayStreamRequest` message
- [ ] Add `StreamButtonEvents` RPC
- [ ] Add `StreamGameplayData` RPC
- [ ] Deprecate `StreamControllerStates` (mark with comment)

**Lines**: ~80 new lines

### Task 4: Regenerate Protocol Buffers
**Files**: `proto/*_pb2.py`, `proto/*_pb2_grpc.py`

**Commands:**
```bash
cd proto
./generate_proto.sh
```

### Task 5: Update Menu Service to Use Button Events
**File**: `services/menu/server.py`

**Changes:**
- [ ] Replace `_button_monitor_loop` implementation
  - [ ] Remove: `StreamControllerStates` call
  - [ ] Add: `StreamButtonEvents` call
  - [ ] Process `ButtonEvent` messages directly
  - [ ] No need for state tracking (transitions handled by controller manager)
- [ ] Simplify `_process_button_state` → `_process_button_event`
  - [ ] Remove: Previous state tracking
  - [ ] Remove: Transition detection logic
  - [ ] Add: Direct event handling
- [ ] Update lobby feedback to use button events
- [ ] Handle connection/disconnection via event absence + periodic health check

**Before:**
```python
async for update in stub.StreamControllerStates(stream_request):
    for controller in update.controllers:
        await self._process_button_state(controller)  # Complex state tracking
```

**After:**
```python
async for event in stub.StreamButtonEvents(request):
    await self._handle_button_event(event)  # Direct event handling
```

**Lines**: ~100 lines modified, ~50 lines removed (net reduction: simpler code)

### Task 6: Update Game Modes to Use Gameplay Data Stream
**Files**:
- `services/game_coordinator/games/base.py`
- `services/game_coordinator/games/ffa.py`
- `services/game_coordinator/games/teams.py`
- `services/game_coordinator/games/random_teams.py`
- `services/game_coordinator/games/nonstop_joust.py`

**Changes:**
- [ ] Replace `StreamControllerStates` with `StreamGameplayData` in base class
- [ ] Update message handling to use `GameplayData` instead of `ControllerState`
- [ ] Update `_process_controller_state` to work with `GameplayData`
- [ ] No functional changes (games don't use button data)

**Lines**: ~20 lines modified across all game files

### Task 7: Update Tests
**Files**:
- `services/game_coordinator/test_ffa_integration.py`
- `services/game_coordinator/test_teams_integration.py`
- `services/game_coordinator/test_random_teams_integration.py`
- New: `services/controller_manager/test_button_events.py`

**Changes:**
- [ ] Update mock controller manager to provide both streams
  - [ ] Mock `StreamButtonEvents` (for menu tests)
  - [ ] Mock `StreamGameplayData` (for game tests)
  - [ ] Keep `StreamControllerStates` mock for backward compatibility
- [ ] Add unit tests for button event detection
  - [ ] Test press/release transitions
  - [ ] Test multiple subscribers
  - [ ] Test event ordering
- [ ] Add integration test for menu button events
- [ ] Verify game tests still pass with gameplay stream

**Lines**: ~200 new test lines

### Task 8: Add Backward Compatibility Period
**Files**: `services/controller_manager/server.py`

**Changes:**
- [ ] Keep `StreamControllerStates` functional (deprecated)
- [ ] Add logging when old endpoint is used
- [ ] Add metric to track old endpoint usage
- [ ] Plan removal for Phase 45 or later

**Lines**: ~20 lines

### Task 9: Update Documentation
**Files**:
- `proto/README.md`
- `services/controller_manager/README.md`
- `services/menu/README.md`

**Changes:**
- [ ] Document new button event stream architecture
- [ ] Document gameplay data stream
- [ ] Add migration guide from old to new streams
- [ ] Document ButtonEvent message format
- [ ] Add sequence diagrams showing event flow

**Lines**: ~100 documentation lines

### Task 10: Performance Testing
**Manual testing steps:**

- [ ] Test menu responsiveness with button event stream
  - [ ] Verify no latency increase
  - [ ] Verify button presses always detected
  - [ ] Test rapid button presses (button mashing)
- [ ] Test gameplay with gameplay data stream
  - [ ] Verify 60Hz acceleration data delivery
  - [ ] Verify game logic unchanged
  - [ ] Test all game modes (FFA, Teams, Random Teams, Nonstop Joust)
- [ ] Monitor network bandwidth
  - [ ] Compare old vs new stream bandwidth
  - [ ] Verify expected reduction (~30-40% for menu, ~15% for gameplay)
- [ ] Test concurrent streams
  - [ ] Multiple menu subscribers to button events
  - [ ] Game running while menu monitors buttons (edge case)

### Task 11: Integration Testing
**Files**: Integration test suite

- [ ] Run full integration test suite
- [ ] Test menu → game → menu transition
- [ ] Test admin mode button combos work with events
- [ ] Test lobby feedback with button events
- [ ] Verify Jaeger traces show correct stream usage

## File Changes Summary

### New Files:
- `services/controller_manager/test_button_events.py` (~200 lines)

### Modified Files:
- `proto/controller_manager.proto` (+80 lines)
- `services/controller_manager/server.py` (+250 lines)
- `services/menu/server.py` (~100 modified, -50 removed)
- `services/game_coordinator/games/base.py` (~10 lines)
- `services/game_coordinator/games/ffa.py` (~5 lines)
- `services/game_coordinator/games/teams.py` (~5 lines)
- `services/game_coordinator/games/random_teams.py` (~5 lines)
- `services/game_coordinator/games/nonstop_joust.py` (~5 lines)
- All integration test files (~50 lines each)
- Documentation files (~100 lines)

### Net Impact:
- **New code**: ~650 lines (controller manager + tests)
- **Modified code**: ~300 lines
- **Removed code**: ~50 lines (simplified menu logic)
- **Net increase**: ~600 lines (mostly new button event infrastructure)

## Success Criteria

- ✅ **Menu uses button events**: Menu service uses `StreamButtonEvents` instead of polling
- ✅ **Games use gameplay stream**: All game modes use `StreamGameplayData`
- ✅ **No regressions**: All existing functionality works (menu navigation, games, admin mode, lobby feedback)
- ✅ **All tests pass**: Integration tests and new unit tests pass
- ✅ **Performance improvement**: Measurable bandwidth reduction (30-40% menu, 15% gameplay)
- ✅ **Event latency**: Button events delivered within 20ms of press
- ✅ **Backward compatible**: Old `StreamControllerStates` still works (deprecated)
- ✅ **Documentation**: Architecture and migration guide complete

## Performance Expectations

### Bandwidth Savings

**Before (unified stream):**
- Menu: 30Hz × 200 bytes = 6 KB/s
- Gameplay: 60Hz × 200 bytes = 12 KB/s

**After (split streams):**
- Menu: ~5 button events/sec × 50 bytes = 0.25 KB/s (96% reduction!)
- Gameplay: 60Hz × 170 bytes = 10.2 KB/s (15% reduction)

**Total savings:**
- Menu: 6 KB/s → 0.25 KB/s (saves ~5.75 KB/s per menu session)
- Gameplay: 12 KB/s → 10.2 KB/s (saves ~1.8 KB/s per game)

### Latency

- **Button events**: < 20ms from physical press to event delivery
- **Gameplay data**: 16.67ms interval at 60Hz (unchanged)

## Future Enhancements (Not in Scope)

- **Phase 42+**: Add button events during gameplay for pause menus
- **Phase 42+**: Add haptic feedback events (controller → server direction)
- **Phase 43+**: Add gesture recognition events (complex button combos)
- **Phase 44+**: Add controller disconnection/reconnection events
- **Phase 45**: Remove deprecated `StreamControllerStates`

## Migration Strategy

### Stage 1: Add New Streams (Parallel)
- Deploy new button event and gameplay streams
- Keep old unified stream working
- No consumer changes yet

### Stage 2: Migrate Consumers
- Update menu to use button events
- Update games to use gameplay stream
- Test thoroughly

### Stage 3: Deprecation Period
- Log warnings when old stream is used
- Monitor metrics to ensure zero usage

### Stage 4: Removal (Future Phase)
- Remove `StreamControllerStates` endpoint
- Clean up old code

## Dependencies

- **Phase 8a** (gRPC Conversion) - ✅ Complete
- **Phase 21** (Button Monitoring) - ✅ Complete
- **Phase 39** (Lobby Feedback) - 🔄 In Progress (this phase supports it)

## Related Work

- **Phase 8a**: Established gRPC architecture
- **Phase 21**: Added button monitoring to menu
- **Phase 39**: Added lobby state feedback
- **Phase 37**: Cleaned up protobuf files (similar protobuf changes)

## Notes

- This is primarily an architectural improvement, not a feature addition
- No user-visible changes expected
- Significant internal benefits: efficiency, clarity, scalability
- Prepares for future features (pause menus, emotes, etc.)
- Event-driven architecture is more natural for button presses than polling

## Testing Strategy

### Unit Tests
- Button transition detection (press/release)
- Event queue management
- Multiple subscribers to button stream
- Gameplay data filtering (no buttons)

### Integration Tests
- Menu button navigation with events
- All game modes with gameplay stream
- Admin mode button combos
- Lobby feedback with button events

### Performance Tests
- Bandwidth measurement
- Latency measurement (button press to event)
- Stress test: rapid button mashing
- Concurrent stream handling

### Manual Tests
- Play through full menu → game → menu cycle
- Test all button combinations in admin mode
- Verify controller feedback still works
- Check Jaeger traces for proper span attribution
