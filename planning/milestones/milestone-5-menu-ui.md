# Milestone 5: Menu & User Interface

**Status:** Complete
**Phases:** 21, 23, 28, 39, 58-60, 70, 79, menu-1

## Summary

Menu service with controller-driven navigation, lobby system for player management, and comprehensive admin mode for system configuration.

## Background

Players interact with JoustMania entirely through their PS Move controllers:
- Navigate menus by tilting
- Select with trigger button
- Access admin mode via long PS button press

## Implementation

### Menu States

```
IDLE → MAIN_MENU → GAME_SELECTION → LOBBY → GAME_STARTING → GAME_RUNNING
                         ↓
                   ADMIN_MODE
```

### Controller Navigation

| Action | Control |
|--------|---------|
| Navigate up/down | Tilt controller |
| Select option | Press trigger |
| Back/Cancel | Press Move button |
| Admin mode | Hold PS button 3s |
| Ready up (lobby) | Press trigger |

### Lobby System

Pre-game staging area where players:
1. See their assigned color on LED
2. Press trigger to mark "ready"
3. Color pulses when ready
4. Game starts when all ready (or timeout)

```
Player joins → Color assigned → LED shows color
     ↓
Press trigger → Ready state → LED pulses
     ↓
All ready → Countdown → Game starts
```

### Admin Mode

Long-press PS button to access system controls:

| Option | Description |
|--------|-------------|
| **Pair Controllers** | Enter Bluetooth pairing mode |
| **Sensitivity** | Adjust Slow/Medium/Fast |
| **Volume** | Audio level control |
| **Restart Services** | Restart all microservices |
| **Exit** | Return to main menu |

### Battery Display

Controller LED indicates battery level:
- **Green** (100-60%) - Full/good
- **Yellow** (60-30%) - Medium
- **Red** (30-10%) - Low
- **Flashing Red** (<10%) - Critical

### Voice Feedback

Audio announcements for menu navigation:
- "Free for All" when selecting game mode
- "Ready" when player marks ready
- "3... 2... 1... Joust!" countdown
- Victory/defeat announcements

## Files Changed

- `services/menu/server.py` - gRPC servicer
- `services/menu/state_manager.py` - State machine
- `services/menu/handlers/` - Per-state handlers
- `services/menu/lobby.py` - Lobby management
- `services/webui/` - Flask web interface

## Commits

Key commits (see `git log --grep="menu\|lobby\|admin"` for complete list):

- `28275c9` refactor(menu): Extract MenuServicer into separate servicer.py file
- `cb2fff5` refactor(menu): Extract EventPublisher and ControllerEventLoop classes
- `f727471` refactor(menu): Integrate AdminModeHandler with StateManager
- `4f9772e` refactor(menu): Phase 5 - Integrate StateManager and handlers into MenuServicer
- `8e5157a` refactor(menu): Phase 2 - Create StateManager for controller state tracking
- `2dae79b` refactor(menu): Phase 1 - Extract utility classes (SOLID refactor)
- `391db94` refactor(menu): Extract AdminModeHandler to separate file

## Related Phases

- Phase 21: Menu controller integration
- Phase 23: Admin mode advanced controls
- Phase 28: Admin mode completion
- Phase 39: Menu lobby controller feedback
- Phase 58: Menu service improvements
- Phase 59: Menu service polish
- Phase 60: Menu audio feedback
- Phase 70: Menu battery display
- Phase 79: Admin mode enhancements
- Menu-1: Remove dimming for battery indication
