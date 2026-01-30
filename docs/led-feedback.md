# Controller LED Feedback Reference (Menu System)

> **See Also:** [controller-feedback.md](./controller-feedback.md) for comprehensive LED documentation including game states, team colors, and troubleshooting. This document focuses specifically on menu/lobby LED behavior and audio integration.

This document describes LED color states in the JoustMania menu system.

## Overview

Controllers provide visual feedback through their LED to communicate:
- Connection status
- Ready state
- Current game mode
- Admin mode status
- Setting changes

## Lobby Mode

When the menu is running, controllers display colors based on their lobby state and the selected game mode.

### Connection Sequence

```
[Controller connects]
    │
    ▼
┌─────────────────┐
│  Green Flash    │  300ms - Acknowledges connection
│  (0, 255, 0)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Dim Game Color │  Persistent - Waiting for ready
│  (50% brightness)│
└────────┬────────┘
         │ [Trigger press]
         ▼
┌─────────────────┐
│ Bright Game Color│  Persistent - Ready to play
│ (100% brightness)│
└─────────────────┘
```

### Game Mode Colors

Each game mode has a distinct base color used for lobby feedback:

| Game Mode | Color Name | RGB Value | Hex |
|-----------|------------|-----------|-----|
| JoustFFA | Orange | (255, 140, 0) | `#FF8C00` |
| JoustTeams | Blue | (0, 100, 255) | `#0064FF` |
| Tournament | Purple | (150, 0, 255) | `#9600FF` |
| Werewolf | Green | (0, 255, 100) | `#00FF64` |
| NonstopJoust | Pink | (255, 50, 120) | `#FF3278` |

### Lobby States

| State | LED Behavior | Duration | Description |
|-------|--------------|----------|-------------|
| Just Connected | Green flash | 300ms | Welcome acknowledgment |
| Connected | Dim game color | Persistent | 50% brightness of game mode color |
| Ready | Bright game color | Persistent | 100% brightness, trigger was pressed |

**Note:** Once a controller becomes "ready" (trigger pressed), it stays ready until the menu stops or the controller disconnects. Releasing the trigger does not un-ready the controller.

## Admin Mode

Admin mode is entered by pressing all 4 face buttons (Cross + Circle + Square + Triangle) simultaneously.

### Admin Mode Sequence

```
[All 4 face buttons held]
    │
    ▼
┌─────────────────┐
│  White Flash    │  600ms - 3 flashes at ~5Hz
│ (255, 255, 255) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Persistent White│  Until exit or timeout (60s)
│ (255, 255, 255) │
└────────┬────────┘
         │ [PS button or timeout]
         ▼
┌─────────────────┐
│ Restore Lobby   │  Returns to game mode color
│     Color       │  (dim or bright based on ready state)
└─────────────────┘
```

### Admin Mode Base State

| State | LED Color | RGB | Duration |
|-------|-----------|-----|----------|
| Entry flash | White | (255, 255, 255) | 600ms (3 flashes) |
| Active | White | (255, 255, 255) | Persistent |
| Exit | Game color | Varies | Restored |

### Option Cycling (Move Button)

When cycling through admin options with the Move button:

| Option | Color | RGB | Duration |
|--------|-------|-----|----------|
| num_teams | Light Blue | (0, 100, 255) | 1000ms |
| force_all_start | Purple | (150, 0, 255) | 1000ms |

After showing the option color, the LED returns to white.

Use **Select** to increase and **Start** to decrease the current option value.

### Game Mode Cycling (Cross Button)

Pressing Cross cycles through game modes with visual and audio feedback:

| Feedback | Description |
|----------|-------------|
| Color flash | Game mode color pulse (600ms) |
| Voice | Game mode name announced |

### Force Start (Trigger Hold)

Hold Trigger for 3 seconds to force start the game:

| State | LED Behavior | Duration |
|-------|--------------|----------|
| Holding | LED dims progressively | 0-3 seconds |
| Released early | Returns to white | Immediate |
| Completed | Game starts | After 3 seconds |

### Setting Changes

#### Sensitivity (Circle Button)

Cycles through sensitivity levels with a color pulse:

| Level | Name | Color | RGB | Duration |
|-------|------|-------|-----|----------|
| 0 | Slow | Blue | (0, 0, 255) | 800ms pulse |
| 1 | Medium | Green | (0, 255, 0) | 800ms pulse |
| 2 | Fast | Red | (255, 0, 0) | 800ms pulse |

#### Battery Display (Triangle Button)

Shows battery level on ALL connected controllers:

| Battery Level | Color | RGB | Duration |
|---------------|-------|-----|----------|
| > 66% | Green | (0, 255, 0) | 2000ms |
| 33% - 66% | Yellow | (255, 255, 0) | 2000ms |
| < 33% | Red | (255, 0, 0) | 2000ms |

#### Instructions Toggle (Square Button)

Shows the new instruction state:

| State | Color | RGB | Duration |
|-------|-------|-----|----------|
| Enabled | Green | (0, 255, 0) | 800ms pulse |
| Disabled | Red | (255, 0, 0) | 800ms pulse |

#### Team Count (Select/Start on num_teams)

Shows the new team count with white brightness gradient + voice:

| Teams | Brightness | RGB | Voice |
|-------|------------|-----|-------|
| 2 | Dim | (80, 80, 80) | "Two" |
| 3 | | (124, 124, 124) | "Three" |
| 4 | | (167, 167, 167) | "Four" |
| 5 | | (211, 211, 211) | "Five" |
| 6 | Bright | (255, 255, 255) | "Six" |

#### Force All Start (Select/Start on force_all_start)

Shows the new toggle state with voice:

| State | Color | RGB | Duration | Voice |
|-------|-------|-----|----------|-------|
| true (require all) | Green | (0, 255, 0) | 800ms | "True" |
| false (2+ starts) | Red | (255, 0, 0) | 800ms | "False" |

## Color Quick Reference

### All Colors Used

| Color | RGB | Hex | Used For |
|-------|-----|-----|----------|
| White | (255, 255, 255) | `#FFFFFF` | Admin mode, team count flashes |
| Green | (0, 255, 0) | `#00FF00` | Connection, battery high, enabled states |
| Yellow | (255, 255, 0) | `#FFFF00` | Battery medium |
| Red | (255, 0, 0) | `#FF0000` | Battery low, disabled states, fast sensitivity |
| Blue | (0, 0, 255) | `#0000FF` | Slow sensitivity |
| Light Blue | (0, 100, 255) | `#0064FF` | num_teams option, JoustTeams |
| Purple | (150, 0, 255) | `#9600FF` | force_all_start option, Tournament |
| Orange | (255, 140, 0) | `#FF8C00` | JoustFFA |
| Green (game) | (0, 255, 100) | `#00FF64` | Werewolf |
| Pink | (255, 50, 120) | `#FF3278` | NonstopJoust |

### State Diagram

```
                    ┌──────────────────────────────────────┐
                    │           MENU RUNNING               │
                    └──────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
            ┌───────────┐     ┌───────────┐     ┌───────────┐
            │  LOBBY    │     │  ADMIN    │     │   GAME    │
            │  MODE     │────▶│  MODE     │     │ STARTING  │
            └───────────┘     └───────────┘     └───────────┘
                 │                  │
                 │                  │
    ┌────────────┼────────────┐    │
    │            │            │    │
    ▼            ▼            ▼    ▼
┌────────┐ ┌──────────┐ ┌───────┐ ┌───────────┐
│Connected│ │  Ready   │ │ White │ │  Various  │
│Dim Color│ │Bright Col│ │       │ │ Feedback  │
└────────┘ └──────────┘ └───────┘ └───────────┘
```

## Implementation Notes

- **Rate limiting**: Lobby color updates are limited to max 2 per second per controller
- **Persistence**: Colors with `duration_ms=0` persist until explicitly changed
- **Flash effect**: Uses `EFFECT_FLASH` at speed 5 (~5Hz)
- **Pulse effect**: Uses `EFFECT_PULSE` for smooth feedback

## Audio Feedback

> **Note:** Audio feedback was implemented in [Phase 60](../planning/phases/completed/phase-60-menu-audio-feedback.md).

For headless operation, voice announcements will complement LED feedback:
- Game mode selection announcements
- Sensitivity change announcements ("Slow sensitivity", "Fast sensitivity")
- Instructions toggle ("Instructions on", "Instructions off")
- Lobby sounds (connection beep, ready confirmation)

## See Also

- [Menu Service README](../services/menu/README.md) - API documentation
- [Controller Manager](../services/controller_manager/README.md) - LED control API
- [Phase 60: Menu Audio Feedback](../planning/phases/completed/phase-60-menu-audio-feedback.md) - Audio feedback implementation
