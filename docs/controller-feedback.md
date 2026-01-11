# Controller LED Feedback Reference

JoustMania provides comprehensive visual feedback through PS Move controller LEDs to help players understand game state, connection status, team assignments, and more.

## Table of Contents

- [Menu/Lobby States](#menulobby-states)
- [Game States](#game-states)
- [Team Colors](#team-colors)
- [Game Mode Colors](#game-mode-colors)
- [Connection States](#connection-states)
- [Troubleshooting](#troubleshooting)

## Menu/Lobby States

Controllers display game-mode-specific colors in the menu/lobby to help players identify which game is selected.

| State | Color | Behavior | Description |
|-------|-------|----------|-------------|
| **Just Connected** | Dim game-mode color | Solid | Controller detected, not ready to start |
| **Ready for Game** | Bright game-mode color | Solid | Trigger pressed, ready to start |
| **Connection Acknowledgment** | Green (0, 255, 0) | Flash 300ms | Welcome flash when controller first connects |
| **Admin Mode** | White (255, 255, 255) | Solid | Configuring game settings |
| **Low Battery** | Red | Slow pulse | <20% battery remaining, charge soon |

### Game Mode Colors (Lobby)

Each game mode has a distinct color to help players know which game is selected:

| Game Mode | Lobby Color (RGB) | Dim (Connected) | Bright (Ready) |
|-----------|------------------|-----------------|----------------|
| **JoustFFA** | Orange (255, 140, 0) | (127, 70, 0) | (255, 140, 0) |
| **JoustTeams** | Blue (0, 100, 255) | (0, 50, 127) | (0, 100, 255) |
| **Tournament** | Purple (150, 0, 255) | (75, 0, 127) | (150, 0, 255) |
| **Werewolf** | Green (0, 255, 100) | (0, 127, 50) | (0, 255, 100) |
| **NonstopJoust** | Pink (255, 50, 120) | (127, 25, 60) | (255, 50, 120) |

**Note:** Dim = 50% brightness (connected but not ready), Bright = 100% brightness (ready to start)

### Admin Mode

Press all 4 front buttons simultaneously (Cross + Circle + Square + Triangle) to enter admin mode:

1. **Entry**: White flash (3 times, ~600ms)
2. **Active**: Persistent white LED
3. **Exit**: Press PlayStation button
4. **Restore**: Returns to lobby color (dim/bright based on ready state)

## Game States

### Countdown (All Modes)

| Phase | Color | Duration | Description |
|-------|-------|----------|-------------|
| **3 seconds** | Red | 1 second | Game starting in 3... |
| **2 seconds** | Yellow | 1 second | Game starting in 2... |
| **1 second** | Green | 1 second | Game starting in 1... |
| **GO!** | Game color | Persistent | Countdown complete, game starts |

### In-Game Colors

#### FFA (Free-For-All)
- Each player gets a **unique color** generated using HSV color space
- Colors evenly distributed for maximum distinction
- Examples: Red, Yellow, Green, Cyan, Blue, Magenta, etc.
- Helps identify individual players during chaotic gameplay

#### Nonstop Joust
- Each player gets a **unique color** (same as FFA)
- Colors persist through respawns
- Helps track individual performance and rivalries

#### Team Games (Teams, Random Teams, Tournament)
- Players display their **team color**
- Color assignment phase before countdown:
  - **Random Teams**: 5-second pulsing team colors (team formation announcement)
  - **Regular Teams**: 2-second solid team colors (team identification)
- Team colors maintained throughout gameplay

### Special Game Events

| Event | Color | Effect | Duration | Description |
|-------|-------|--------|----------|-------------|
| **Death Warning** | Orange (255, 140, 0) | Flash | 200ms | Controller moving too much, near death |
| **Death** | Red (255, 0, 0) | Solid | Until respawn | Player eliminated |
| **Victory** | Rainbow | Cycle | 2 seconds | Winner celebration |
| **Respawn (Nonstop)** | Player color | Fade in | 3 seconds | Returning to game after death |
| **Spawn Protection** | Player color | Dim pulse | 2 seconds | Invulnerable after respawn |

## Team Colors

Team colors used in Teams, Random Teams, and Tournament modes:

| Team # | Name | RGB | Description |
|--------|------|-----|-------------|
| 0 | Pink | (255, 108, 108) | Soft pink |
| 1 | Magenta | (255, 0, 192) | Bright magenta |
| 2 | Orange | (255, 64, 0) | Vibrant orange |
| 3 | Yellow | (255, 255, 0) | Pure yellow |
| 4 | Green | (0, 255, 0) | Pure green |
| 5 | Turquoise | (0, 255, 255) | Cyan/Turquoise |
| 6 | Blue | (0, 0, 255) | Pure blue |
| 7 | Purple | (96, 0, 255) | Deep purple |

**Note:** Colors are carefully chosen for maximum visual distinction. Team assignments in Random Teams are randomized from this palette.

## Game Mode Colors

See [Game Mode Colors (Lobby)](#game-mode-colors-lobby) table above.

## Connection States

| State | Effect | Description |
|-------|--------|-------------|
| **Connected** | Dim game-mode color | Bluetooth connected to menu |
| **Disconnected** | LED off | Controller turned off or out of range |
| **Low Battery** | Red pulse (overrides other colors) | <20% battery (level 0 or 1 out of 5) |
| **Initial Connection** | Green flash | Acknowledgment flash when first connecting |

### Low Battery Warning

- **Trigger**: Battery level ≤ 1 (out of 5) = <20% remaining
- **Frequency**: Every 30 seconds (automatic background monitoring)
- **Visual**: Red pulse (3 cycles: bright red → dim red)
- **Duration**: ~2 seconds per warning
- **Override**: Temporarily overrides current color, then restores
- **Log**: Warnings logged to controller manager service

## Troubleshooting

### Controller stuck on dim game-mode color

**Possible causes:**
- Trigger not fully released
- Controller in sleep mode

**Solutions:**
- Release trigger button completely
- Press any button to wake controller
- Check if controller is actually ready (trigger pressed)

### Controller doesn't change color

**Possible causes:**
- Bluetooth connection lost
- Controller manager service not running
- LED hardware failure

**Solutions:**
- Check Bluetooth connection (controller should be vibrating on movement)
- Verify controller manager service is running: `docker ps | grep controller-manager`
- Check service logs: `docker logs controller-manager`
- Reconnect controller (turn off and back on)
- Check for error messages in logs

### Low battery warning won't stop

**Cause:** Battery critically low (<20%)

**Solutions:**
- Charge controller via USB
- Replace batteries (if using replaceable batteries)
- Warning will stop automatically once battery level rises above 20%
- Warning frequency: Every 30 seconds (this is normal behavior)

### Controller shows wrong team color

**Possible causes:**
- Team assignment mismatch
- Controller connected mid-game

**Solutions:**
- Check team assignments in game logs
- Restart game to reassign teams
- Ensure controller connected before game start

### Colors not distinct enough

**Cause:** Similar colors generated for nearby players

**Note:** This is rare but can happen with many players

**Solutions:**
- Colors automatically distributed in HSV space for maximum distinction
- Visual distinction improves with fewer players
- Team modes use pre-defined color palette (always distinct)

### Admin mode white LED stuck

**Possible causes:**
- PlayStation button not responding
- Admin mode exit handler failed

**Solutions:**
- Press PlayStation button to exit admin mode
- Restart menu service if stuck
- Controller will return to lobby color on next menu start

## Color Design Philosophy

JoustMania's LED feedback follows these principles:

1. **Contextual**: Colors match game context (menu vs game, team vs individual)
2. **Progressive**: Dim → Bright indicates readiness progression
3. **Distinct**: Maximum color separation for easy identification
4. **Consistent**: Same colors mean same things across modes
5. **Informative**: Critical states (low battery, death) override normal colors
6. **Responsive**: Immediate feedback for player actions

## Technical Details

### Color Generation (FFA/Nonstop)

Unique player colors generated using `utils.colors.generate_colors()`:
- Distributes colors evenly in HSV (Hue-Saturation-Value) space
- Maximizes hue separation for easy distinction
- Full saturation and value for vibrant colors
- Deterministic order for consistent assignment

### LED Update Rate

- **Menu/Lobby**: Max 2 updates/second per controller (rate limited)
- **Game Phase**: Updates on state changes only
- **Effects**: Variable rate (pulse: ~3Hz, flash: ~5Hz, rainbow: continuous)

### Battery Monitoring

- **Check Frequency**: Every 30 seconds (background task)
- **Warning Threshold**: Battery level ≤ 1 (out of 5) = <20%
- **Warning Cooldown**: 30 seconds between warnings per controller
- **Implementation**: `controller_manager/server.py:_check_battery_levels()`

### Color Assignment Timing

| Game Mode | Phase | Timing | Effect |
|-----------|-------|--------|--------|
| FFA | ffa_colors_phase | 1 second before countdown | Unique colors, solid |
| Nonstop | nonstop_colors_phase | 1 second before countdown | Unique colors, solid |
| Teams | team_colors_phase | 2 seconds before countdown | Team colors, solid |
| Random Teams | team_formation_phase | 5 seconds before countdown | Team colors, pulsing |

## Related Documentation

- [Architecture](../planning/ARCHITECTURE_ANALYSIS.md) - System architecture
- [Phase 39 Implementation](../planning/phases/in-progress/phase-39-menu-lobby-controller-feedback.md) - Implementation details
- [Controller Manager](../services/controller_manager/README.md) - Controller service documentation
- [Menu Service](../services/menu/README.md) - Menu service documentation

## Version History

- **Phase 39** (2026-01): Complete LED feedback system
  - Menu/lobby game-mode-specific colors
  - Admin mode white LED
  - Team color assignment
  - Low battery warnings
  - Unique player colors (FFA/Nonstop)
