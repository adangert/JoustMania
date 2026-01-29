# Controller Guide

Complete reference for using PS Move controllers with JoustMania.

## Button Layout

PS Move controllers have the following buttons:

- **MOVE Button** - Large middle button with PlayStation logo
- **TRIGGER** - Rear trigger button
- **X (Cross)** - Front face button (bottom)
- **O (Circle)** - Front face button (right)
- **Square** - Front face button (left)
- **Triangle** - Front face button (top)
- **PlayStation Button** - PS logo button (special functions)

## Menu Navigation

Navigate the game menu using physical controller buttons:

| Button | Action |
|--------|--------|
| **MOVE** | Cycle through available games |
| **TRIGGER** | Start selected game / Mark ready |

Available games cycle in order:
1. Joust FFA
2. Joust Teams
3. Tournament
4. Werewolf
5. Nonstop Joust

## Admin Mode

Access advanced settings by pressing **all 4 front buttons simultaneously** (X + O + Square + Triangle).

**Visual Feedback:** Controller flashes white 3 times when entering admin mode.

### Admin Commands

**Option Navigation (recommended):**

| Button | Function | Feedback |
|--------|----------|----------|
| **MOVE** | Cycle through settings | Shows option color (1s) |
| **TRIGGER** | Increase current setting value | Flashes based on value |
| **X (Cross)** | Decrease current setting value | Flashes based on value |

**Quick Access Functions:**

| Button | Function | Feedback |
|--------|----------|----------|
| **Circle (O)** | Cycle sensitivity (Slow/Medium/Fast) | Blue/Green/Red pulse |
| **Triangle** | Show battery levels on all controllers | Color-coded LEDs (2s) |
| **Square** | Toggle instruction audio | Green (on) / Red (off) |
| **PlayStation** | Exit admin mode | Returns to lobby |

### Admin Settings

**Number of Teams** (Light Blue):
- Range: 2-6 teams
- Feedback: Flashes N times (N = number of teams)

**Force Start Mode** (Purple):
- `All`: All connected controllers start
- `Trigger Only`: Only players who pressed trigger start
- Feedback: Green (All) / Red (Trigger Only)

**Sensitivity Levels**:
- **Slow** (Blue) - Lower thresholds, easier gameplay
- **Medium** (Green) - Default balanced gameplay
- **Fast** (Red) - Higher thresholds, faster paced

### Battery Display Colors

When Triangle is pressed in admin mode:
- **Green** - Battery > 66%
- **Yellow** - Battery 33-66%
- **Red** - Battery < 33%

## In-Game Controls

During gameplay:
- **Movement Detection** - Controller accelerometer/gyroscope detect jousting motions
- **TRIGGER** - Context-dependent (varies by game mode)
- **MOVE** - Context-dependent (varies by game mode)

Game-specific controls are announced at game start.

## Pairing Controllers

Controllers can be paired via:
1. **Dashboard UI** - http://localhost:8080 (recommended)
2. **Physical pairing mode** - Hold PlayStation button until LED blinks

## LED Feedback

Controllers provide visual feedback through LED colors for game state, team assignments, and warnings.

See [Controller LED Feedback Reference](controller-feedback.md) for complete details.

## Related Documentation

- [Controller LED Feedback](controller-feedback.md) - Complete LED color reference
- [Hardware Setup Guide](hardware-setup-guide.md) - Physical hardware setup
- [Controller Connectivity](CONTROLLER_CONNECTIVITY.md) - Bluetooth troubleshooting
