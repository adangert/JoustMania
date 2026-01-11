# Phase 23: Admin Mode & Advanced Controls

**Status:** 🎮 PLANNED
**Priority:** MEDIUM

## Goal
Add admin mode for on-the-fly game settings adjustment via controller

## Motivation
- Original JoustMania had admin mode (press all 4 front buttons)
- Allow event hosts to adjust settings without stopping game
- Change sensitivity, toggle instructions, check battery levels
- Essential for convention/party mode setup

## Original JoustMania Admin Mode Controls

From https://github.com/adangert/JoustMania README:

**Accessing Admin Mode:**
- Press all 4 front buttons simultaneously (X, O, Square, Triangle)
- Controller LED turns to admin mode color

**Admin Functions:**
- **X (Cross)**: Add/remove game from convention mode rotation
- **O (Circle)**: Change game sensitivity (slow/medium/fast)
- **Square**: Toggle instruction audio playback
- **Triangle**: Show battery level on all controllers
- **Middle Button**: Rotate through additional admin options
- **Start/Select**: Increase/decrease values (team count, etc.)
- **Trigger (hold 2s)**: Force start game with current players

**Additional Controls to Implement:**
- **PlayStation Button (hold)**: Turn off/remove controller from play

## Tasks

- [ ] Admin mode detection
  - [ ] Detect simultaneous press of 4 front buttons
  - [ ] Enter admin mode state
  - [ ] Show admin mode LED color (white or purple)
  - [ ] Exit admin mode on timeout or button

- [ ] Sensitivity adjustment
  - [ ] Circle button cycles through: SLOW → MEDIUM → FAST
  - [ ] Update Settings service sensitivity setting
  - [ ] Publish setting change event
  - [ ] Visual feedback on controller LED

- [ ] Battery display
  - [ ] Triangle button shows battery on all controllers
  - [ ] Color-coded battery levels (green/yellow/orange/red)
  - [ ] Display duration: 5 seconds
  - [ ] Return to previous color

- [ ] Instruction toggle
  - [ ] Square button toggles play_instructions setting
  - [ ] LED blink to confirm
  - [ ] Update Settings service

- [ ] Force start
  - [ ] Hold trigger for 2 seconds in menu
  - [ ] Start game with current ready controllers
  - [ ] Bypass minimum player count

- [ ] Controller removal
  - [ ] Hold PlayStation button for 2 seconds
  - [ ] Remove controller from game
  - [ ] Call Controller Manager RemoveController RPC

- [ ] Convention mode
  - [ ] X button adds/removes game from rotation
  - [ ] Visual indicator for included games
  - [ ] Settings persist across games

- [ ] Documentation
  - [ ] Update main README.md with controller button guide
  - [ ] Document all button controls (menu + admin mode)
  - [ ] Add visual diagram of controller buttons
  - [ ] Include troubleshooting section
  - [ ] Document admin mode access and functions

## Implementation Approach

```python
# In services/menu/server.py

class MenuServicer:
    def __init__(self):
        # Admin mode state
        self.admin_mode_active = False
        self.admin_mode_controller = None  # Serial of controller in admin mode

    async def _process_button_state(self, controller):
        """Detect button presses including admin mode."""
        serial = controller.serial

        # Check for admin mode entry (all 4 front buttons)
        if self._check_admin_mode_combo(controller):
            await self._enter_admin_mode(serial)
            return

        # Process admin mode commands if active
        if self.admin_mode_active and serial == self.admin_mode_controller:
            await self._process_admin_commands(controller)
            return

        # Normal menu button processing
        # ... existing code ...

    def _check_admin_mode_combo(self, controller) -> bool:
        """Check if all 4 front buttons pressed simultaneously."""
        # NOTE: Need to add cross/circle/square/triangle to proto first
        return (controller.cross_pressed and
                controller.circle_pressed and
                controller.square_pressed and
                controller.triangle_pressed)

    async def _enter_admin_mode(self, serial: str):
        """Enter admin mode."""
        self.admin_mode_active = True
        self.admin_mode_controller = serial

        # Set admin LED color (white or purple)
        from services.controller_manager import controller_manager_pb2
        color_request = controller_manager_pb2.SetControllerColorRequest(
            serial=serial,
            color=controller_manager_pb2.RGB(r=128, g=0, b=128),  # Purple
            duration_ms=0
        )
        await self.controller_client.SetControllerColor(color_request)

        logger.info(f"Admin mode entered by controller {serial}")

    async def _process_admin_commands(self, controller):
        """Process admin mode button presses."""
        # Circle: Change sensitivity
        if self._button_just_pressed(controller, 'circle'):
            await self._cycle_sensitivity()

        # Triangle: Show battery
        if self._button_just_pressed(controller, 'triangle'):
            await self._show_battery_levels()

        # Square: Toggle instructions
        if self._button_just_pressed(controller, 'square'):
            await self._toggle_instructions()

        # X: Toggle convention mode for current game
        if self._button_just_pressed(controller, 'cross'):
            await self._toggle_convention_mode()
```

## Proto Changes Required
- Add `cross_pressed`, `circle_pressed`, `square_pressed`, `triangle_pressed` to ControllerState
- Controller Manager must track these button states

## Expected Improvements
- Event hosts can adjust settings on-the-fly
- Battery monitoring without stopping game
- Quick sensitivity adjustments for different player skill levels
- Complete parity with original JoustMania admin features

## Raspberry Pi Impact
- Minimal overhead (only processes when admin mode active)
- Settings changes propagate through existing Settings service
- No gameplay impact

## Success Criteria
- Admin mode accessible via 4-button combo
- Sensitivity cycling works
- Battery display shows accurate levels
- Instruction toggle persists
- Force start works with current players
- PlayStation button removes controller
