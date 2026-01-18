# Phase 77: Controller Reconnection LED Fix

## Overview

Fix an issue where PS Move controllers that disconnect and reconnect don't light up. The reconnected controller would remain dark because stale handles weren't cleaned up and base colors weren't restored.

**Status:** Completed

---

## Problem

When a controller disconnected (e.g., PS button pressed to turn off, or Bluetooth signal lost) and then reconnected:

1. Controller LED stays dark/off
2. Controller appears in tracking but is marked as "idle"
3. Polling shows `active=1, idle=2` even though controller just reconnected

### Symptoms in Logs

```
13:09:43,022 - Controller count changed: 2 -> 3, tracked: 3
13:09:43,042 - Scan complete: found 3 serials: [...], now tracking 3
13:09:43,893 - Polling 1/3 controllers (active=1, idle=2)
```

The controller was detected but:
- Only 1 of 3 was being actively polled
- LED color was never set

---

## Root Cause Analysis

### Backend Issue (`bluetooth_backend.py`)

In `get_connected_controllers()`:
1. When controller count changed (disconnect), scan ran
2. `seen_serials` was built with currently connected controllers
3. **BUG**: Controllers NOT in `seen_serials` were NOT removed from `self.controllers`
4. On reconnect, the serial was already in `self.controllers` (stale handle)
5. New handle was discarded at line 498: `if serial not in self.controllers`
6. Polling used the stale handle which failed silently

### Server Issue (`server.py`)

In `_check_for_new_controllers()`:
1. Only checked for NEW controllers (not in `tracked_controllers`)
2. Never detected disconnections
3. `tracked_controllers` retained stale entries
4. `base_colors` was never restored on reconnection

---

## Solution

### 1. Backend: Clean Up Stale Handles

After scanning, remove controllers from `self.controllers` that are no longer connected:

```python
# Clean up controllers that are no longer connected
stale_serials = set(self.controllers.keys()) - set(seen_serials)
for stale_serial in stale_serials:
    logger.info(f"Controller {stale_serial} no longer in scan - removing stale handle")
    del self.controllers[stale_serial]
    # Clean up all associated tracking data...
```

### 2. Server: Detect Disconnections and Restore Colors

In `_check_for_new_controllers()`:

```python
# Check for disconnected controllers
disconnected_serials = tracked_serials - connected_set
for serial in disconnected_serials:
    logger.info(f"Controller {serial} disconnected - cleaning up server tracking")
    # Clean up tracking but KEEP base_colors for reconnection
    del self.tracked_controllers[serial]
    # ... other cleanup ...

# On reconnection, restore saved base color
if serial in self.base_colors:
    color = self.base_colors[serial]
    logger.info(f"Restoring base color for reconnected controller {serial}: {color}")
    await self._set_controller_color_internal(serial, color)
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Preserve `base_colors` across disconnections** | Allows LED color restoration on reconnect without menu re-sending |
| **Clean up in discovery loop** | Synchronous detection ensures no stale state |
| **Restore color immediately after spawn** | User sees LED light up as soon as controller reconnects |

---

## Files Modified

| File | Change |
|------|--------|
| `services/controller_manager/bluetooth_backend.py` | Remove stale controllers from `self.controllers` after scan detects count change |
| `services/controller_manager/server.py` | Detect disconnections, clean up tracking (keep `base_colors`), restore LED on reconnect |

---

## Expected Log Output After Fix

### Disconnect:
```
Controller count changed: 3 -> 2, tracked: 3
Controller 00:06:f5:ed:88:8c no longer in scan - removing stale handle
Scan complete: found 2 serials: [...], now tracking 2
Controller 00:06:f5:ed:88:8c disconnected - cleaning up server tracking
```

### Reconnect:
```
Controller count changed: 2 -> 3, tracked: 2
New controller connected: 00:06:f5:ed:88:8c (index 2)
Scan complete: found 3 serials: [...], now tracking 3
Discovered new controller: 00:06:f5:ed:88:8c
Restoring base color for reconnected controller 00:06:f5:ed:88:8c: (255, 140, 0)
```

---

## Testing

1. Connect 3 controllers to lobby (all light up with lobby color)
2. Press PS button on one controller to turn it off
3. Verify log shows disconnect cleanup
4. Turn controller back on
5. Verify:
   - Log shows reconnection and color restoration
   - Controller LED lights up with correct lobby color
   - Controller appears in polling as "active"

---

## Related Work

- **Phase 39**: Menu lobby controller feedback (sets base colors)
- **Phase 71**: Immediate LED color updates (LED state ownership)
- **Phase 72**: LED update separation from polling path
