# Phase XX: Button-Based Game Modes

## Overview

Complete the remaining 2 game modes from original JoustMania that require button input support in the gameplay stream.

**Status:** Future / Blocked on button support infrastructure

## Background

During the game mode implementation effort, 6 of 8 missing modes were implemented:
- Swapper (completed)
- Traitor (completed)
- Werewolf (completed)
- Zombie (completed - without weapon system)
- Fight Club (completed)
- Tournament (completed)

The remaining 2 modes require trigger/button input which is not currently available in the gameplay stream:
- Speed Bomb
- Commander

## Prerequisites

### Button Support in Gameplay Stream

The `GameplayStreamControl` protobuf and controller manager need to be extended to include button state in the `ControllerState` message:

```protobuf
message ControllerState {
  string serial = 1;
  float accel_x = 2;
  float accel_y = 3;
  float accel_z = 4;
  // New fields needed:
  bool trigger_pressed = 5;
  bool move_pressed = 6;  // Main button
}
```

The controller manager backends (psmoveapi, hidapi) need to read and forward button state.

## Game Modes

### Speed Bomb

**Complexity:** Medium
**Original behavior:** Hot potato with a bomb

**Mechanics:**
- One player starts with the "bomb" (special color/rumble)
- Timer counts down (starts at 7s, decreases to 1s minimum over game)
- Press trigger to pass bomb to random other player
- Counter mechanic: Press trigger within 0.5s of receiving to reflect back
- When timer expires, bomb holder loses a life (starts with 2-3 lives)
- Last player with lives wins

**Key Implementation:**
```python
class SpeedBombPlayer(Player):
    has_bomb: bool = False
    lives: int = 3
    counter_window_until: float = 0.0  # Time window to counter

async def _handle_button_press(self, serial: str):
    player = self.players[serial]
    if player.has_bomb:
        # Pass bomb to random player
        self._pass_bomb(serial)
    elif time.time() < player.counter_window_until:
        # Counter! Send bomb back
        self._counter_bomb(serial)
```

### Commander

**Complexity:** High
**Original behavior:** Team commander with power abilities

**Mechanics:**
- 2 teams, each selects a commander (50s selection phase)
- Commander selection: Button press to volunteer, random if none/tie
- Power system: Commander charges power through team combat
- Button press activates "overdrive" (team gets boost, different color)
- Win condition: Kill enemy commander

**Key Implementation:**
```python
class CommanderPlayer(Player):
    is_commander: bool = False
    power_percent: float = 0.0
    power_state: PowerState = PowerState.CHARGING

class PowerState(Enum):
    CHARGING = "charging"
    READY = "ready"  # 100% charged
    ACTIVE = "active"  # Overdrive mode

async def _commander_selection_phase(self):
    # 50 second selection phase
    # Players press button to volunteer
    # Track volunteers per team
    # Select commander (volunteer or random)
```

## Implementation Plan

### Phase 1: Button Support Infrastructure

1. **Extend protobuf** - Add button state to `ControllerState`
2. **Update psmoveapi backend** - Read trigger/move button state
3. **Update hidapi backend** - Read trigger/move button state (if applicable)
4. **Update gameplay stream** - Forward button state to game coordinator

### Phase 2: Speed Bomb Implementation

1. Create `services/game_coordinator/games/speed_bomb.py`
2. Implement bomb passing/counter mechanics
3. Add timer acceleration logic
4. Add lives system
5. Register in game factory
6. Add to menu service

### Phase 3: Commander Implementation

1. Create `services/game_coordinator/games/commander.py`
2. Implement commander selection phase with button input
3. Implement power charging system
4. Implement overdrive activation
5. Implement commander death win condition
6. Register in game factory
7. Add to menu service

## Testing

- Unit tests for button event handling
- Integration tests with mock button presses
- Manual testing with real controllers

## Files to Create/Modify

### New Files
- `services/game_coordinator/games/speed_bomb.py`
- `services/game_coordinator/games/commander.py`

### Modify
- `proto/controller_manager.proto` - Add button state
- `services/controller_manager/backends/psmoveapi_backend.py` - Read buttons
- `services/controller_manager/server.py` - Forward button state
- `services/game_coordinator/game_factory.py` - Register new modes
- `services/menu/server.py` - Add modes to menu

## References

- Original JoustMania `games.py` for Speed Bomb logic
- Original JoustMania `games.py` for Commander logic
- Current gameplay stream implementation in `controller_manager/server.py`
