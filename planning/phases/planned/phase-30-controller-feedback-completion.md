# Phase 30: Controller Feedback Completion

**Status:** 🎮 PLANNED
**Priority:** MEDIUM - Parity with FFA game

## Goal
Add missing controller vibration and LED effects to Teams and Random Teams

## Motivation
- FFA game has complete controller feedback (warnings, deaths)
- Teams and Random Teams lack vibration and LED flashing
- Inconsistent user experience across game modes
- Visual/haptic feedback is critical for gameplay

## Tasks

**1. Teams Game - Warning Feedback**
- [ ] Add warning vibration at threshold
  - [ ] Medium vibration (128 intensity)
  - [ ] 200ms duration
  - [ ] Orange LED color
  - **Files:** `services/game_coordinator/games/teams.py:355-356`

```python
# At warning threshold
vibration_request = controller_manager_pb2.SetControllerVibrationRequest(
    serial=serial,
    intensity=128,
    duration_ms=200
)
await self.controller_client.SetControllerVibration(vibration_request)

color_request = controller_manager_pb2.SetControllerColorRequest(
    serial=serial,
    color=controller_manager_pb2.RGB(r=255, g=128, b=0),  # Orange
    duration_ms=300
)
await self.controller_client.SetControllerColor(color_request)
```

**2. Teams Game - Death Feedback**
- [ ] Add death vibration
  - [ ] Strong vibration (255 intensity)
  - [ ] 500ms duration
  - [ ] Red flash effect
  - **Files:** `services/game_coordinator/games/teams.py:400-420`

**3. Random Teams Game - Warning Feedback**
- [ ] Copy warning implementation from FFA
  - **Files:** `services/game_coordinator/games/random_teams.py:424-425`

**4. Random Teams Game - Death Feedback**
- [ ] Copy death implementation from FFA
  - **Files:** `services/game_coordinator/games/random_teams.py:469-489`

**5. Countdown Colors**
- [ ] Teams: Set team colors during countdown
  - [ ] 3 seconds: Team color
  - [ ] 2 seconds: White flash
  - [ ] 1 second: Green
  - **Files:** `services/game_coordinator/games/teams.py:212`

- [ ] Random Teams: RGB countdown sequence
  - [ ] 3: Red (255, 0, 0)
  - [ ] 2: Yellow (255, 255, 0)
  - [ ] 1: Green (0, 255, 0)
  - **Files:** `services/game_coordinator/games/random_teams.py:281`

**6. Testing**
- [ ] Test feedback doesn't cause lag on RPi
- [ ] Verify vibration intensity feels appropriate
- [ ] Check LED colors match team assignments
- [ ] Ensure multiple simultaneous vibrations work

## Expected Improvements
- Consistent feedback across all game modes
- Players can feel when in danger (warning vibration)
- Clear death indication (haptic + visual)
- Better game immersion

## Success Criteria
- Warning threshold triggers vibration + orange LED
- Death triggers strong vibration + red flash
- Countdown shows appropriate colors per game mode
- No performance degradation from feedback
