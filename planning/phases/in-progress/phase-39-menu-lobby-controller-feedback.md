# Phase 39: Menu & Lobby Controller Feedback

**Status:** 🚧 IN PROGRESS
**Priority:** MEDIUM-HIGH
**Estimated Effort:** Medium (2-3 days)

## Goal

Implement complete controller LED feedback for menu and lobby states to match original JoustMania UX. Controllers should provide clear visual feedback for connection status, ready state, team assignment, and battery warnings.

## Motivation

**Current Gaps:**
- Controllers have NO visual feedback when connected to menu
- Players can't tell if controllers are ready for a game
- No indication of team assignment before/during games
- No proactive low battery warnings (controllers die mid-game)
- Missing the "slightly orange → bright orange" lobby feedback from original JoustMania

**User Experience Impact:**
- Players don't know if their controller is detected
- Can't tell which controllers are ready to start
- Confusing team assignment (especially in Teams/Random Teams modes)
- Batteries die unexpectedly during gameplay
- Feels disconnected compared to original JoustMania

## Expected Behavior (Original JoustMania)

### Lobby/Menu States
1. **Just Connected**: Slightly orange LED (dim)
2. **Ready for Game**: Bright orange LED
3. **In Admin Mode**: White LED
4. **Low Battery (<20%)**: Slow red pulse (override other states)

### Game States
5. **Team Assignment**: Show team color (red, blue, green, yellow)
6. **Countdown**: Red → Yellow → Green (already implemented ✅)
7. **In Game**: Team color or white for FFA (partially implemented)
8. **Death**: Red flash (already implemented ✅)
9. **Victory**: Rainbow (already implemented ✅)

### Special States
10. **Pairing Mode**: Fast white pulse
11. **Reconnecting**: Slow white pulse
12. **Disconnected**: LED off (automatic)

## Architecture

### Controller State Machine

```
┌──────────────┐
│ Disconnected │ (LED: Off)
└──────┬───────┘
       │ Connect
       ▼
┌──────────────┐     Trigger Press
│  Connected   │ ──────────────────► ┌─────────┐
│  (Menu)      │                     │  Ready  │
│ LED: Dim     │ ◄────────────────── │         │
│   Orange     │    Trigger Release  │LED:     │
└──────┬───────┘                     │ Bright  │
       │ Move Press                  │ Orange  │
       ▼                             └────┬────┘
┌──────────────┐                          │
│ Admin Mode   │                          │ Game Start
│ LED: White   │                          ▼
└──────────────┘                     ┌─────────┐
                                     │ In Game │
                                     │ LED:    │
                                     │ Team    │
                                     │ Color   │
                                     └─────────┘
```

### Service Responsibilities

**Menu Service:**
- Monitor controller connection events
- Set lobby state colors (dim/bright orange)
- Handle admin mode feedback (white)
- Coordinate with controller manager for LED updates

**Game Coordinator:**
- Set team colors at game start
- Update colors during gameplay
- Handle death/victory feedback (already done)

**Controller Manager:**
- Monitor battery levels continuously
- Auto-trigger low battery warnings
- Execute LED color commands

## Tasks

### Task 1: Add Lobby State Feedback to Menu Service

**Files:** `services/menu/server.py`

- [ ] Add background task to monitor controller states
  - Subscribe to controller state stream
  - Track connected vs ready controllers
  - Update LED colors based on state

**Implementation:**
```python
async def _update_lobby_feedback(self):
    """Background task to update controller LED feedback in menu/lobby."""
    from proto import controller_manager_pb2, controller_manager_pb2_grpc

    # Connect to controller manager
    channel = grpc.aio.insecure_channel(self.controller_manager_addr)
    stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    try:
        # Subscribe to controller state stream
        stream_request = controller_manager_pb2.StreamRequest(update_frequency_hz=2)
        async for update in stub.StreamControllerStates(stream_request):
            if not self.menu_running:
                continue

            for controller in update.controllers:
                # Determine LED color based on state
                if controller.ready:
                    # Bright orange: Ready for game
                    color = controller_manager_pb2.RGB(r=255, g=140, b=0)
                else:
                    # Dim orange: Connected but not ready
                    color = controller_manager_pb2.RGB(r=128, g=70, b=0)

                # Set controller color
                await stub.SetControllerColor(
                    controller_manager_pb2.SetControllerColorRequest(
                        serial=controller.serial,
                        color=color,
                        duration_ms=0  # Persistent until changed
                    )
                )

    except Exception as e:
        logger.error(f"Lobby feedback error: {e}")
    finally:
        await channel.close()

# Start in StartMenu RPC
asyncio.create_task(self._update_lobby_feedback())
```

- [ ] Add connection event feedback
  - Flash green when controller first connects (200ms)
  - Then transition to dim orange

```python
# In controller connection handler
async def _on_controller_connected(self, serial: str):
    """Called when a new controller connects."""
    # Flash green to acknowledge connection
    await stub.SetControllerColor(
        controller_manager_pb2.SetControllerColorRequest(
            serial=serial,
            color=controller_manager_pb2.RGB(r=0, g=255, b=0),
            duration_ms=200
        )
    )

    # Then set dim orange (connected state)
    await asyncio.sleep(0.2)
    await stub.SetControllerColor(
        controller_manager_pb2.SetControllerColorRequest(
            serial=serial,
            color=controller_manager_pb2.RGB(r=128, g=70, b=0),
            duration_ms=0
        )
    )
```

- [ ] Update ready state detection
  - Currently menu doesn't track which controllers are ready
  - Add logic to monitor trigger button state
  - Update `ready_controller_count` when controllers become ready

```python
# Track ready state per controller
self.ready_controllers: set[str] = set()

# In button monitoring loop
if controller.trigger_pressed and serial not in self.ready_controllers:
    self.ready_controllers.add(serial)
    self.ready_controller_count = len(self.ready_controllers)
    logger.info(f"Controller {serial} is ready ({self.ready_controller_count} total)")

elif not controller.trigger_pressed and serial in self.ready_controllers:
    self.ready_controllers.remove(serial)
    self.ready_controller_count = len(self.ready_controllers)
    logger.info(f"Controller {serial} unready ({self.ready_controller_count} total)")
```

### Task 2: Add Admin Mode Visual Feedback

**Files:** `services/menu/server.py`

- [ ] Set white LED when entering admin mode
  - All controllers turn white when admin mode activates
  - Clear visual distinction from menu state

```python
async def _enter_admin_mode(self):
    """Enter admin mode - set all controllers to white."""
    # Set all controllers to white
    await self.controller_stub.SetControllerColor(
        controller_manager_pb2.SetControllerColorRequest(
            serial="",  # Empty = all controllers
            color=controller_manager_pb2.RGB(r=255, g=255, b=255),
            duration_ms=0
        )
    )

    self.in_admin_mode = True
    logger.info("Entered admin mode - controllers set to white")
```

- [ ] Restore lobby colors when exiting admin mode
  - Return to dim/bright orange based on ready state

```python
async def _exit_admin_mode(self):
    """Exit admin mode - restore lobby feedback."""
    self.in_admin_mode = False

    # Restore lobby colors for each controller
    # Will be handled by _update_lobby_feedback() task
    logger.info("Exited admin mode - restoring lobby colors")
```

### Task 3: Implement Team Color Assignment

**Files:** `services/game_coordinator/games/teams.py`, `random_teams.py`, `nonstop_joust.py`

- [ ] Define team color palette

```python
TEAM_COLORS = [
    controller_manager_pb2.RGB(r=255, g=0, b=0),    # Team 0: Red
    controller_manager_pb2.RGB(r=0, g=0, b=255),    # Team 1: Blue
    controller_manager_pb2.RGB(r=0, g=255, b=0),    # Team 2: Green
    controller_manager_pb2.RGB(r=255, g=255, b=0),  # Team 3: Yellow
    controller_manager_pb2.RGB(r=255, g=0, b=255),  # Team 4: Magenta
    controller_manager_pb2.RGB(r=0, g=255, b=255),  # Team 5: Cyan
]
```

- [ ] Set team colors at game start (before countdown)
  - All players see their team color
  - Helps players identify teammates

```python
async def _assign_team_colors(self):
    """Assign team colors to all players."""
    from proto import controller_manager_pb2, controller_manager_pb2_grpc

    channel = grpc.aio.insecure_channel(self.controller_manager_addr)
    stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    try:
        for serial, player in self.players.items():
            team_color = TEAM_COLORS[player.team % len(TEAM_COLORS)]

            await stub.SetControllerColor(
                controller_manager_pb2.SetControllerColorRequest(
                    serial=serial,
                    color=team_color,
                    duration_ms=0  # Persistent during game
                )
            )

            logger.info(f"Set {serial} to team {player.team} color")

    finally:
        await channel.close()

# Call before countdown
await self._assign_team_colors()
await self._countdown()
```

- [ ] Maintain team colors during gameplay
  - Keep team color as base color
  - Override temporarily for warnings/deaths
  - Restore team color after temporary effects

```python
# In death warning
async def _warn_player(self, serial: str):
    """Warn player about impending death - temporarily override team color."""
    # Flash orange warning
    await stub.SetControllerColor(
        controller_manager_pb2.SetControllerColorRequest(
            serial=serial,
            color=controller_manager_pb2.RGB(r=255, g=140, b=0),
            duration_ms=200
        )
    )

    # Restore team color after warning
    await asyncio.sleep(0.2)
    player = self.players[serial]
    team_color = TEAM_COLORS[player.team % len(TEAM_COLORS)]
    await stub.SetControllerColor(
        controller_manager_pb2.SetControllerColorRequest(
            serial=serial,
            color=team_color,
            duration_ms=0
        )
    )
```

- [ ] Add team formation announcement for Random Teams
  - Show team color for 3 seconds
  - Pulse effect to emphasize

```python
async def _announce_teams(self):
    """Announce team assignments with color feedback."""
    logger.info("Announcing team assignments...")

    # Set all controllers to their team colors with pulse
    for serial, player in self.players.items():
        team_color = TEAM_COLORS[player.team % len(TEAM_COLORS)]

        # Use pulse effect for emphasis
        await stub.PlayControllerEffect(
            controller_manager_pb2.PlayControllerEffectRequest(
                serial=serial,
                effect=controller_manager_pb2.EFFECT_PULSE,
                color=team_color,
                duration_ms=3000,
                speed=3  # Medium pulse speed
            )
        )

    await asyncio.sleep(3)
    logger.info("Team announcement complete")
```

### Task 4: Add Proactive Low Battery Warnings

**Files:** `services/controller_manager/server.py`

- [ ] Add background task to monitor battery levels
  - Check all controllers every 30 seconds
  - Warn at <20% battery (level 1 or 0)

```python
async def _monitor_battery_levels(self):
    """Background task to monitor and warn about low batteries."""
    while self.running:
        try:
            for serial, info in self.tracked_controllers.items():
                battery = info.get("battery", 0)

                if battery <= 1:  # Critical: 0 or 1 out of 5
                    # Trigger low battery warning
                    await self._warn_low_battery(serial, battery)

            await asyncio.sleep(30)  # Check every 30 seconds

        except Exception as e:
            logger.error(f"Battery monitoring error: {e}")

# Start in __init__
asyncio.create_task(self._monitor_battery_levels())
```

- [ ] Implement low battery warning feedback
  - Slow red pulse (overrides current color)
  - Repeat every 30 seconds until charged
  - Log warning for visibility

```python
async def _warn_low_battery(self, serial: str, battery_level: int):
    """Warn player about low battery."""
    logger.warning(f"Controller {serial} has low battery: {battery_level}/5")

    # Red pulse for 2 seconds (overrides current color)
    # Use low-level LED control to override
    move = self.tracked_controllers[serial].get("move")
    if move and PSMOVE_AVAILABLE:
        # Pulse red 3 times
        for _ in range(3):
            move.set_leds(255, 0, 0)
            move.update_leds()
            await asyncio.sleep(0.3)

            move.set_leds(100, 0, 0)
            move.update_leds()
            await asyncio.sleep(0.3)

        # Note: Current state will be restored by next state update
```

- [ ] Add Prometheus metric for battery warnings
  - Track when warnings are triggered
  - Monitor battery levels over time

```python
from services.controller_manager import metrics

# In _warn_low_battery
metrics.controller_low_battery_warnings_total.labels(serial=serial).inc()
```

### Task 5: Add Connection State Feedback

**Files:** `services/controller_manager/server.py`

- [ ] Add pairing mode feedback
  - Fast white pulse when in pairing mode
  - Helps identify which controller is being paired

```python
async def _pairing_feedback(self, serial: str):
    """Show pairing feedback - fast white pulse."""
    move = self.tracked_controllers[serial].get("move")
    if not move or not PSMOVE_AVAILABLE:
        return

    # Fast white pulse for 5 seconds
    for _ in range(10):
        move.set_leds(255, 255, 255)
        move.update_leds()
        await asyncio.sleep(0.25)

        move.set_leds(50, 50, 50)
        move.update_leds()
        await asyncio.sleep(0.25)
```

- [ ] Add reconnection feedback
  - Slow white pulse when reconnecting
  - Flash green when reconnection succeeds

```python
async def _on_reconnect(self, serial: str):
    """Called when controller reconnects."""
    logger.info(f"Controller {serial} reconnected")

    # Flash green to acknowledge reconnection
    move = self.tracked_controllers[serial].get("move")
    if move and PSMOVE_AVAILABLE:
        move.set_leds(0, 255, 0)
        move.update_leds()
        await asyncio.sleep(0.5)

    # Restore to lobby state (dim orange)
    # Will be handled by menu service feedback loop
```

### Task 6: Add FFA Team Color (White for Non-Team Modes)

**Files:** `services/game_coordinator/games/ffa.py`

- [ ] Set all players to white at game start
  - FFA has no teams, so all players are white
  - Provides consistent feedback

```python
async def _set_ffa_colors(self):
    """Set all players to white for FFA mode."""
    from proto import controller_manager_pb2, controller_manager_pb2_grpc

    channel = grpc.aio.insecure_channel(self.controller_manager_addr)
    stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    try:
        # Set all players to white
        await stub.SetControllerColor(
            controller_manager_pb2.SetControllerColorRequest(
                serial="",  # All controllers
                color=controller_manager_pb2.RGB(r=255, g=255, b=255),
                duration_ms=0
            )
        )
    finally:
        await channel.close()

# Call before countdown
await self._set_ffa_colors()
await self._countdown()
```

### Task 7: Add Game End Feedback

**Files:** `services/game_coordinator/games/*.py`

- [ ] Provide feedback when returning to menu
  - All non-winning controllers fade to dim orange
  - Winner keeps rainbow (already implemented)

```python
async def _end_game_feedback(self, winner_serial: str = None):
    """Provide feedback when game ends."""
    from proto import controller_manager_pb2, controller_manager_pb2_grpc

    channel = grpc.aio.insecure_channel(self.controller_manager_addr)
    stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    try:
        for serial in self.players.keys():
            if serial == winner_serial:
                # Winner gets rainbow (already set)
                continue

            # Non-winners fade to dim orange (lobby state)
            await stub.PlayControllerEffect(
                controller_manager_pb2.PlayControllerEffectRequest(
                    serial=serial,
                    effect=controller_manager_pb2.EFFECT_FADE_OUT,
                    color=controller_manager_pb2.RGB(r=128, g=70, b=0),
                    duration_ms=2000,
                    speed=5
                )
            )

    finally:
        await channel.close()
```

### Task 8: Update Documentation

**Files:** `docs/controller-feedback.md` (new), `README.md`

- [ ] Create controller feedback documentation
  - LED color reference (what each color means)
  - State machine diagram
  - Troubleshooting (LED stuck on one color, etc.)

**docs/controller-feedback.md:**
```markdown
# Controller LED Feedback Reference

## Lobby/Menu States

| Color | State | Description |
|-------|-------|-------------|
| Off | Disconnected | Controller is not connected |
| Dim Orange (128,70,0) | Connected | Controller detected, not ready |
| Bright Orange (255,140,0) | Ready | Holding trigger, ready to start |
| White | Admin Mode | Configuring settings |
| Slow Red Pulse | Low Battery | <20% battery, charge soon |

## Game States

| Color | State | Description |
|-------|-------|-------------|
| Red | Countdown: 3 | Game starting in 3 seconds |
| Yellow | Countdown: 2 | Game starting in 2 seconds |
| Green | Countdown: 1 | Game starting in 1 second |
| Team Color | In Game | Red/Blue/Green/Yellow by team |
| White | In Game (FFA) | Free-for-all, no teams |
| Orange Flash | Death Warning | Near death threshold |
| Red | Dead | Eliminated from game |
| Rainbow | Victory | You won! |

## Team Colors

| Team | Color | RGB |
|------|-------|-----|
| 0 | Red | (255, 0, 0) |
| 1 | Blue | (0, 0, 255) |
| 2 | Green | (0, 255, 0) |
| 3 | Yellow | (255, 255, 0) |
| 4 | Magenta | (255, 0, 255) |
| 5 | Cyan | (0, 255, 255) |

## Connection States

| Effect | State | Description |
|--------|-------|-------------|
| Fast White Pulse | Pairing | Bluetooth pairing mode |
| Slow White Pulse | Reconnecting | Trying to reconnect |
| Green Flash | Reconnected | Connection restored |

## Troubleshooting

**Controller stuck on dim orange:**
- Check if trigger is fully released
- Controller may be in sleep mode - press any button

**Controller doesn't change color:**
- Check Bluetooth connection
- Verify controller manager is running
- Check logs for errors

**Low battery warning won't stop:**
- Charge or replace batteries
- Warning repeats every 30 seconds until charged
```

- [ ] Update main README with feedback section

## Testing

### Manual Testing Checklist

- [ ] **Lobby State Feedback**
  - [ ] Connect controller → Verify dim orange
  - [ ] Press trigger → Verify bright orange
  - [ ] Release trigger → Verify dim orange
  - [ ] Disconnect → Verify LED turns off

- [ ] **Admin Mode Feedback**
  - [ ] Enter admin mode → Verify white
  - [ ] Exit admin mode → Verify returns to orange
  - [ ] Check battery in admin → Verify green/yellow/red

- [ ] **Team Colors**
  - [ ] Start Teams game → Verify red/blue team colors
  - [ ] Start Random Teams → Verify team formation colors pulse
  - [ ] During game → Verify team colors persist

- [ ] **Low Battery Warning**
  - [ ] Set battery to level 1 → Verify red pulse
  - [ ] Verify warning repeats every 30 seconds
  - [ ] Verify warning overrides other colors

- [ ] **Connection Feedback**
  - [ ] Pair new controller → Verify fast white pulse
  - [ ] Disconnect and reconnect → Verify green flash

- [ ] **FFA Colors**
  - [ ] Start FFA game → Verify all controllers white
  - [ ] Death warning → Verify orange flash, then white
  - [ ] Victory → Verify rainbow

### Integration Tests

- [ ] Add test for lobby state transitions
- [ ] Add test for team color assignment
- [ ] Add test for low battery warning
- [ ] Add test for admin mode colors

**Example test:**
```python
@pytest.mark.asyncio
async def test_lobby_state_feedback(docker_compose):
    """Test controller LED feedback in lobby."""
    # Get controller manager client
    host = docker_compose.get_service_host("mock-controller-manager", 50062)
    port = docker_compose.get_service_port("mock-controller-manager", 50062)
    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(channel)

    # Simulate controller connection
    connect_response = await mock_client.SimulateConnect(
        controller_manager_mock_pb2.ConnectRequest(serial="test_controller")
    )
    assert connect_response.success

    # Wait for lobby feedback to apply
    await asyncio.sleep(0.5)

    # Get controller state
    state_response = await mock_client.GetControllerState(
        controller_manager_mock_pb2.GetStateRequest(serial="test_controller")
    )

    # Verify dim orange (connected but not ready)
    assert state_response.color.r == 128
    assert state_response.color.g == 70
    assert state_response.color.b == 0

    await channel.close()
```

## Success Criteria

- ✅ Controllers show dim orange when connected to menu
- ✅ Controllers show bright orange when ready (trigger pressed)
- ✅ Admin mode shows white LED on all controllers
- ✅ Team games show team colors (red, blue, green, yellow)
- ✅ FFA shows white for all players
- ✅ Low battery triggers red pulse warning automatically
- ✅ Pairing shows fast white pulse
- ✅ Reconnection shows slow pulse then green flash
- ✅ All feedback documented in controller-feedback.md
- ✅ Manual testing checklist passes
- ✅ Integration tests pass

## Dependencies

- Phase 19 (Controller Feedback Implementation) - ✅ Complete (base LED/vibration APIs)
- Phase 21 (Menu Controller Integration) - ✅ Complete (button monitoring)
- Controller Manager SetControllerColor/PlayControllerEffect RPCs - ✅ Available

## Performance Impact

**Negligible:**
- LED updates: ~1-2 per controller per state change
- Battery monitoring: Every 30 seconds (background task)
- Lobby feedback: 2 Hz polling (very low overhead)
- No impact on game loop performance

## Notes

- LED feedback improves UX without changing gameplay
- Clear visual communication reduces confusion
- Proactive battery warnings prevent mid-game failures
- Team colors help players coordinate in team modes
- Matches original JoustMania user experience

## Future Enhancements

- **Customizable Colors**: Allow users to choose team colors
- **Brightness Control**: Adjust LED brightness for different environments
- **Color Blindness Mode**: Alternative color schemes for accessibility
- **LED Patterns**: More complex patterns (spiral, wave, etc.)
- **Audio Cues**: Combine LED feedback with sounds
- **Mobile App Control**: View/control LED colors from phone

## Related Phases

- **Phase 19**: Controller Feedback Implementation (in-game feedback)
- **Phase 21**: Menu Controller Integration (button monitoring)
- **Phase 30**: Controller Feedback Completion (planned - audio integration)
- **Phase 31**: Controller Effects Implementation (planned - advanced effects)
