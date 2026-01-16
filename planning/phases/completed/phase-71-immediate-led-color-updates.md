# Phase 71: Immediate LED Color Updates on Change

**Status**: Complete
**Dependencies**: Phase 46 (Stream-Based Controller Feedback)
**Estimated Effort**: ~1 hour
**Type**: UX Improvement

---

## Overview

Improve LED color change responsiveness in the menu/lobby by updating colors immediately when they change, rather than waiting for the 4-second refresh cycle.

## Problem Statement

Currently, PS Move controller LEDs have a 5-second timeout in hardware. To keep LEDs alive, the Bluetooth backend refreshes LED colors every 4 seconds during state polling (`bluetooth_backend.py:299-311`):

```python
# Refresh LED color every 4 seconds (PSMove LEDs timeout after 5s)
if serial in self.led_colors and serial not in self._effect_active:
    current_time = time.time()
    last_led_update = getattr(self, '_last_led_update', {}).get(serial, 0)
    if current_time - last_led_update >= 4.0:
        r, g, b = self.led_colors[serial]
        with self._led_lock:
            move.set_leds(r, g, b)
            move.update_leds()
```

**The issue**: When a new color is set via `set_led_color()`, the LED is updated immediately. However, during the menu/lobby, if the color in `self.led_colors` is changed externally (e.g., via base color updates), the controller won't reflect the new color until the next 4-second refresh cycle.

**User-visible symptom**: When transitioning between menu states (e.g., controller becomes ready, game mode changes), the LED color update can be delayed by up to 4 seconds.

## Solution

Add a comparison check in the 4-second refresh logic: if the stored color differs from what was last sent to the controller, update immediately regardless of the 4-second timer.

### Current Flow

```
set_led_color() called → LED updated immediately → stored in self.led_colors
                                                           ↓
                                            4s refresh checks self.led_colors
                                            and re-sends (even if same color)
```

### Proposed Flow

```
set_led_color() called → LED updated immediately → stored in self.led_colors
                         also stores in self._last_sent_color[serial]
                                                           ↓
                                            4s refresh compares:
                                            - if led_colors != _last_sent_color: update immediately
                                            - else if 4s elapsed: refresh (keep-alive)
```

---

## Technical Design

### Changes to `bluetooth_backend.py`

#### 1. Track Last Sent Color

Add a dictionary to track what color was actually sent to each controller:

```python
def __init__(self):
    # ... existing code ...
    self._last_sent_color: dict[str, tuple[int, int, int]] = {}  # Phase 71
```

#### 2. Update `set_led_color()` to Track Sent Color

```python
async def set_led_color(self, serial: str, r: int, g: int, b: int) -> bool:
    # ... existing code ...
    if move:
        with self._led_lock:
            move.set_leds(r, g, b)
            move.update_leds()
        self.led_colors[serial] = (r, g, b)
        self._last_sent_color[serial] = (r, g, b)  # Phase 71: Track what was sent
        self._last_led_update[serial] = time.time()
        return True
    return False
```

#### 3. Update Refresh Logic in `get_controller_state()`

```python
# Phase 71: Check if color changed OR 4s elapsed (keep-alive)
if serial in self.led_colors and serial not in self._effect_active:
    current_time = time.time()
    last_led_update = getattr(self, '_last_led_update', {}).get(serial, 0)

    stored_color = self.led_colors[serial]
    last_sent = self._last_sent_color.get(serial)

    # Update if: color changed OR 4s elapsed (keep-alive)
    color_changed = stored_color != last_sent
    keepalive_needed = current_time - last_led_update >= 4.0

    if color_changed or keepalive_needed:
        r, g, b = stored_color
        with self._led_lock:
            move.set_leds(r, g, b)
            move.update_leds()
        self._last_sent_color[serial] = stored_color  # Phase 71
        if not hasattr(self, '_last_led_update'):
            self._last_led_update = {}
        self._last_led_update[serial] = current_time

        if color_changed:
            logger.debug(f"LED color changed for {serial}: {last_sent} → {stored_color}")
```

### Alternative: Menu Service Check

An alternative approach is to have the menu service compare colors before sending:

```python
async def _send_base_color(self, serial: str, color: tuple[int, int, int]) -> bool:
    # Phase 71: Only send if color actually changed
    current_color = self._controller_colors.get(serial)
    if current_color == color:
        return True  # No change needed

    # ... existing send logic ...
    self._controller_colors[serial] = color  # Track locally
```

**Recommendation**: Implement at the Bluetooth backend level (Option 1) as it's more robust and handles all sources of color changes, not just the menu service.

---

## Implementation Plan

### Task 1: Add Color Tracking

**File**: `services/controller_manager/bluetooth_backend.py`

1. Add `self._last_sent_color: dict[str, tuple[int, int, int]] = {}` in `__init__`
2. Update `set_led_color()` to store sent color in `_last_sent_color`
3. Clean up `_last_sent_color` when controller disconnects

### Task 2: Update Refresh Logic

**File**: `services/controller_manager/bluetooth_backend.py`

1. In `get_controller_state()`, compare `led_colors[serial]` with `_last_sent_color[serial]`
2. If different, update immediately and log the change
3. If same, only update if 4s elapsed (keep-alive behavior)

### Task 3: Testing

1. Manual test: Connect controller, change colors in menu, verify immediate update
2. Verify keep-alive still works (LED doesn't turn off after 5s of no changes)
3. Verify effects still work correctly (no interference with `_effect_active` check)

---

## Files to Modify

| File | Changes |
|------|---------|
| `services/controller_manager/bluetooth_backend.py` | Add `_last_sent_color` tracking, update refresh logic |

---

## Risks & Mitigations

### Risk 1: Increased LED Update Frequency

**Concern**: If colors are set frequently, we might send more updates than needed.

**Mitigation**: The comparison ensures we only send when color actually changes. No change = no extra update.

### Risk 2: Race Condition with Effects

**Concern**: Effect system sets colors directly; could conflict with base color tracking.

**Mitigation**: Existing `_effect_active` check already prevents refresh during effects. Phase 71 changes only apply when no effect is active.

---

## Expected Benefits

1. **Immediate feedback**: LED color changes are visible within ~16ms (one poll cycle) instead of up to 4 seconds
2. **Better UX in menus**: Color transitions feel responsive when:
   - Controller becomes ready (trigger press)
   - Game mode selection changes display colors
   - Controller state changes (admin mode, etc.)
3. **No performance impact**: Only additional comparison per poll cycle; no extra Bluetooth traffic unless color changed

---

## Testing Checklist

- [ ] LED updates immediately when `set_led_color()` called with new color
- [ ] LED updates immediately when `led_colors` dict modified externally
- [ ] LED stays lit after 5+ seconds with no color changes (keep-alive works)
- [ ] Effects still work correctly (flash, pulse, rainbow)
- [ ] No duplicate updates when color hasn't changed
- [ ] Controller disconnect cleans up `_last_sent_color` entry

---

**End of Phase 71 Documentation**
