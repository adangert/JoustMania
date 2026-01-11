# Phase 31: Controller Effects Implementation

**Status:** 🌈 PLANNED
**Priority:** LOW - Nice to have, not critical

## Goal
Implement animated controller effects (FLASH, PULSE, RAINBOW, FADE)

## Motivation
- Controller effects are stubbed but not implemented
- Games use PlayControllerEffect() but only solid colors work
- Admin mode uses FLASH/PULSE for feedback (currently doesn't work)
- Would enhance visual feedback significantly

## Tasks

**1. Effect Animation Framework**
- [ ] Create background task for effect animations
  - [ ] One task per controller with active effect
  - [ ] Cancellable (new effect stops old effect)
  - [ ] Async/await pattern
  - **Files:** `services/controller_manager/server.py:510-530`

```python
self.active_effects: Dict[str, asyncio.Task] = {}

async def _run_effect(self, serial: str, effect: ControllerEffect, ...):
    """Run effect animation loop."""
    if serial in self.active_effects:
        self.active_effects[serial].cancel()

    task = asyncio.create_task(self._effect_loop(serial, effect, ...))
    self.active_effects[serial] = task
```

**2. FLASH Effect**
- [ ] Implement rapid on/off flashing
  - [ ] Toggle between color and black
  - [ ] Speed parameter controls flash rate (1-10 = 1-10 Hz)
  - [ ] Duration_ms controls total effect time
  - **Files:** `services/controller_manager/server.py:540-560`

```python
async def _effect_flash(self, serial, color, duration_ms, speed):
    interval = 1.0 / speed  # seconds per flash
    end_time = time.time() + (duration_ms / 1000.0)

    while time.time() < end_time:
        self._set_led_color(serial, color)
        await asyncio.sleep(interval / 2)
        self._set_led_color(serial, (0, 0, 0))
        await asyncio.sleep(interval / 2)
```

**3. PULSE Effect**
- [ ] Implement smooth breathing effect
  - [ ] Fade from black to color to black
  - [ ] Speed controls pulse rate
  - [ ] Use sine wave for smooth brightness
  - **Files:** `services/controller_manager/server.py:562-582`

```python
import math

async def _effect_pulse(self, serial, color, duration_ms, speed):
    interval = 0.05  # 20 Hz update rate
    cycle_duration = 1.0 / speed
    end_time = time.time() + (duration_ms / 1000.0)

    start = time.time()
    while time.time() < end_time:
        elapsed = time.time() - start
        # Sine wave: 0 → 1 → 0
        brightness = (math.sin(2 * math.pi * elapsed / cycle_duration) + 1) / 2

        scaled_color = tuple(int(c * brightness) for c in color)
        self._set_led_color(serial, scaled_color)
        await asyncio.sleep(interval)
```

**4. RAINBOW Effect**
- [ ] Implement color cycling through spectrum
  - [ ] HSV color space rotation
  - [ ] Speed controls rotation rate
  - **Files:** `services/controller_manager/server.py:584-604`

```python
import colorsys

async def _effect_rainbow(self, serial, duration_ms, speed):
    interval = 0.05
    cycle_duration = 1.0 / speed
    end_time = time.time() + (duration_ms / 1000.0)

    start = time.time()
    while time.time() < end_time:
        elapsed = time.time() - start
        hue = (elapsed / cycle_duration) % 1.0

        rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        color = tuple(int(c * 255) for c in rgb)
        self._set_led_color(serial, color)
        await asyncio.sleep(interval)
```

**5. FADE_OUT / FADE_IN Effects**
- [ ] Implement linear fade effects
  - [ ] FADE_OUT: Current color → black
  - [ ] FADE_IN: Black → target color
  - **Files:** `services/controller_manager/server.py:606-626`

**6. Effect Cleanup**
- [ ] Cancel effects on controller disconnect
- [ ] Cancel effects when new effect starts
- [ ] Restore original color after effect completes
- [ ] Handle rapid effect changes gracefully

## Expected Improvements
- Admin mode feedback looks polished
- Victory celebrations more impressive
- Warning states more noticeable
- Better visual communication to players

## Success Criteria
- All 6 effects work smoothly
- Effects can be cancelled/replaced mid-animation
- No performance impact on RPi (< 5% CPU per effect)
- Effects synchronize across multiple controllers
