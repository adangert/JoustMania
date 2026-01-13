# Phase 58: Menu Service Improvements

**Status:** ✅ COMPLETE
**Priority:** MEDIUM-HIGH
**Estimated Effort:** Medium (1-2 days)

## Goal

Address implementation gaps, bugs, and documentation issues in the menu service to improve reliability and maintainability.

## Motivation

The menu service is a central piece of JoustMania, handling game selection, controller lobby feedback, and admin mode. A code review identified several issues:

1. **Broken imports** that will fail at runtime
2. **Missing disconnection handling** causing stale state
3. **No admin mode timeout** risking stuck controllers
4. **Unused metrics** reducing observability
5. **Incomplete documentation** hindering maintenance

## Issues Identified

### Critical (Runtime Failures)
- Wrong import paths in admin handlers (`services.controller_manager` instead of `proto`)

### High Priority (Reliability)
- Controller disconnection not tracked (stale state accumulation)
- No reconnection logic in button_monitor_loop
- No admin mode timeout (controllers stuck forever)

### Medium Priority (Quality)
- gRPC metrics defined but never used
- GetMenuStatus is sync while others are async
- Dead code in _update_lobby_feedback
- Auto-start threshold hardcoded (should use settings)
- No GAME_STARTING state recovery

### Low Priority (Polish)
- README.md is a stub
- Test coverage gaps
- State cleanup for disconnected controllers

## Tasks

### Task 1: Fix Broken Imports in Admin Handlers

**Files:** `services/menu/server.py`

Fix the incorrect imports in `_handle_admin_sensitivity`, `_handle_admin_battery`, `_handle_admin_instructions`, and `_handle_admin_cycle_option`.

**Current (broken):**
```python
from services.controller_manager import (
    controller_manager_pb2,
    controller_manager_pb2_grpc,
)
```

**Fixed:**
```python
from proto import (
    controller_manager_pb2,
    controller_manager_pb2_grpc,
)
```

### Task 2: Add Controller Disconnection Handling

**Files:** `services/menu/server.py`

Track which controllers are in the current update and remove stale ones:

```python
async def _button_monitor_loop(self):
    # ... existing code ...
    async for update in stub.StreamControllerStates(stream_request):
        # Track controllers in this update
        current_serials = {c.serial for c in update.controllers}

        # Detect disconnections
        disconnected = self.connected_controllers - current_serials
        for serial in disconnected:
            await self._handle_controller_disconnect(serial)

        # ... rest of existing processing ...

async def _handle_controller_disconnect(self, serial: str):
    """Clean up state for a disconnected controller."""
    self.connected_controllers.discard(serial)
    self.ready_controllers.discard(serial)
    self.controller_button_states.pop(serial, None)
    self.last_button_press_time.pop(serial, None)
    self.controller_lobby_state.pop(serial, None)
    self.last_lobby_feedback_update.pop(serial, None)

    # Update ready count
    self.ready_controller_count = len(self.ready_controllers)

    # If admin mode controller disconnected, exit admin mode
    if self.admin_mode_active and serial == self.admin_mode_controller:
        self.admin_mode_active = False
        self.admin_mode_controller = None

    logger.info(f"Controller {serial} disconnected, state cleaned up")
```

### Task 3: Add Admin Mode Timeout

**Files:** `services/menu/server.py`

Add a 60-second timeout for admin mode to prevent stuck controllers:

```python
# In _process_button_state, add timeout check:
if self.admin_mode_active:
    # Check for timeout (60 seconds)
    if time.time() - self.admin_mode_entry_time > 60:
        logger.info("Admin mode timed out after 60 seconds")
        await self._exit_admin_mode()
        return
```

### Task 4: Add Button Monitor Reconnection Logic

**Files:** `services/menu/server.py`

Wrap the stream in a retry loop:

```python
async def _button_monitor_loop(self):
    """Monitor controller buttons with automatic reconnection."""
    from proto import controller_manager_pb2, controller_manager_pb2_grpc

    retry_delay = 1.0
    max_retry_delay = 30.0

    while self.button_monitor_running:
        try:
            stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(
                self.controller_channel
            )
            logger.info("Button monitor connected to Controller Manager")
            retry_delay = 1.0  # Reset on successful connection

            stream_request = controller_manager_pb2.StreamRequest(update_frequency_hz=30)
            async for update in stub.StreamControllerStates(stream_request):
                if not self.button_monitor_running:
                    return
                # ... process update ...

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Button monitor error: {e}, reconnecting in {retry_delay}s")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)
```

### Task 5: Instrument gRPC Metrics

**Files:** `services/menu/server.py`, `services/menu/metrics.py`

Add metrics instrumentation to RPC methods:

```python
async def StartMenu(self, request, context):
    start_time = time.time()
    try:
        # ... existing code ...
        metrics.grpc_requests_total.labels(method="StartMenu", status="ok").inc()
        return response
    except Exception as e:
        metrics.grpc_requests_total.labels(method="StartMenu", status="error").inc()
        raise
    finally:
        duration = time.time() - start_time
        metrics.grpc_request_duration_seconds.labels(method="StartMenu").observe(duration)
```

### Task 6: Make GetMenuStatus Async

**Files:** `services/menu/server.py`

Convert to async for consistency:

```python
async def GetMenuStatus(self, request, context):
    """Get current menu status."""
    # ... rest of implementation unchanged ...
```

### Task 7: Remove Dead Code

**Files:** `services/menu/server.py`

Remove unused line in `_update_lobby_feedback`:

```python
# Remove this line (result is unused):
# self.controller_lobby_state.get(serial, "connected")
```

### Task 8: Add GAME_STARTING Recovery

**Files:** `services/menu/server.py`

Add a method to recover from GAME_STARTING if game fails to start:

```python
async def _reset_to_running(self):
    """Reset menu to RUNNING state (e.g., if game start failed)."""
    if self.state == menu_pb2.MenuState.GAME_STARTING:
        self.state = menu_pb2.MenuState.RUNNING
        await self._publish_event("game_start_cancelled", {})
        logger.info("Menu reset to RUNNING state")
```

And add a ProcessInput handler:

```python
elif input_type == "reset_menu":
    await self._reset_to_running()
```

### Task 9: Update README Documentation

**Files:** `services/menu/README.md`

Replace stub with comprehensive documentation covering:
- Service overview and purpose
- gRPC API reference
- Event types
- Admin mode controls
- Configuration options
- Health checks

### Task 10: Fix Test Issues

**Files:** `services/menu/tests/test_lobby_feedback.py`

- Fix sync/async mismatch in `test_stop_menu_clears_lobby_state`
- Add missing test cases for button monitoring

## Testing

### Manual Testing Checklist

- [ ] Start menu service - verify no import errors
- [ ] Connect/disconnect controllers - verify state cleanup
- [ ] Enter admin mode, wait 60s - verify auto-exit
- [ ] Kill controller-manager, restart - verify reconnection
- [ ] Check Prometheus metrics at :8000/metrics - verify gRPC metrics present

### Automated Tests

- [ ] Existing tests pass
- [ ] New disconnection handling tests
- [ ] Admin timeout test

## Success Criteria

- ✅ No import errors at runtime
- ✅ Controllers properly cleaned up on disconnect
- ✅ Admin mode times out after 60 seconds
- ✅ Button monitor reconnects after errors
- ✅ gRPC metrics appear in Prometheus
- ✅ GetMenuStatus is async
- ✅ Dead code removed
- ✅ README.md has useful documentation
- ✅ All tests pass

## Dependencies

- Phase 39 (Menu Lobby Controller Feedback) - ✅ Complete
- Phase 21 (Menu Controller Integration) - ✅ Complete

## Performance Impact

**Negligible:**
- Disconnection tracking: O(n) where n = connected controllers (typically < 10)
- Admin timeout check: Single comparison per button state update
- Reconnection: Only triggered on errors

## Notes

- These are mostly bug fixes and quality improvements
- No changes to the public API
- Backward compatible

## Completion Summary

**Completed:** 2026-01-13

### Changes Made

1. **Fixed broken imports** in admin handlers (`_handle_admin_sensitivity`, `_handle_admin_battery`, `_handle_admin_instructions`, `_handle_admin_cycle_option`) - changed from `services.controller_manager` to `proto`

2. **Added controller disconnection handling** - New `_handle_controller_disconnect()` method cleans up all state when controllers disconnect, including exiting admin mode if the admin controller disconnects

3. **Added admin mode timeout** - Admin mode now auto-exits after 60 seconds of inactivity

4. **Added button monitor reconnection** - Exponential backoff retry loop (1s to 30s) when connection to controller-manager fails

5. **Instrumented gRPC metrics** - All RPC methods now track request counts and durations via Prometheus

6. **Made GetMenuStatus async** - Consistent with other RPC methods

7. **Removed dead code** - Unused `controller_lobby_state.get()` call in `_update_lobby_feedback`

8. **Added GAME_STARTING recovery** - New `reset_menu` input type allows cancelling a stuck game start

9. **Updated README.md** - Comprehensive documentation including API reference, lobby feedback, admin mode controls, metrics, and configuration

10. **Fixed test issues** - Made `test_stop_menu_clears_lobby_state` async, added `TestControllerDisconnection` test class
