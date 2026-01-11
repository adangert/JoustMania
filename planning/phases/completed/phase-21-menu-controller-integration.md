# Phase 21: Menu Controller Integration

**Status:** ✅ COMPLETE
**Date Completed:** 2026-01-10
**Commit:** ba1cda3
**Priority:** HIGH

## Goal
Restore physical controller button navigation in menu

## Motivation
- Menu service has `ProcessInput` RPC but no controller button monitoring
- Physical controller buttons don't work for menu navigation
- Players can only use WebUI to select games - defeats purpose of controller-based game
- Essential UX feature missing from refactored architecture

## Current Gap
- Controller Manager streams button states (`trigger_pressed`, `move_pressed`)
- Menu service accepts button events via `ProcessInput` RPC
- **Missing:** Service to monitor button states and call `ProcessInput`
- WebUI can trigger games, but physical controllers cannot

## Implementation Approach
Add background task to Menu service to monitor controller buttons

## Tasks

- [x] Add background async task to Menu service
  - [x] Create `_button_monitor_loop()` method
  - [x] Stream controller states from Controller Manager
  - [x] Track previous button states per controller
  - [x] Detect button press transitions (False → True)
  - [x] Call internal menu logic (publish events directly)

- [x] Implement button detection logic
  - [x] SELECT button (MOVE): Cycle through games
  - [x] TRIGGER button: Start selected game
  - [x] Debouncing: 200ms minimum between same button presses
  - [ ] PlayStation button: Remove controller (Phase 23)
  - [ ] Admin mode: All 4 buttons for settings (Phase 23)

- [x] Add game mode to list
  - [x] Add "NonstopJoust" to game list (prep for Phase 22)
  - [x] Update hardcoded games arrays (ProcessInput + button handler)

- [ ] Testing
  - [ ] Verify button presses cycle through games (requires hardware)
  - [ ] Verify trigger starts game (requires hardware)
  - [ ] Test with multiple controllers (requires hardware)
  - [ ] Verify debouncing works (requires hardware)

## Implementation Details

```python
# In services/menu/server.py MenuServicer.__init__()
self.button_monitor_task = None
self.controller_button_states = {}  # {serial: {trigger: bool, move: bool}}
self.last_button_press_time = {}    # {serial: {button: timestamp}}

async def _button_monitor_loop(self):
    """Monitor controller buttons and trigger menu actions."""
    try:
        # Connect to Controller Manager
        channel = grpc.aio.insecure_channel('controller-manager:50052')
        stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

        # Stream controller states
        stream_request = controller_manager_pb2.StreamRequest(update_frequency_hz=30)
        async for update in stub.StreamControllerStates(stream_request):
            for controller in update.controllers:
                await self._process_button_state(controller)
    except Exception as e:
        logger.error(f"Button monitor error: {e}")

async def _process_button_state(self, controller):
    """Detect button press transitions and trigger menu actions."""
    serial = controller.serial
    current_time = time.time()

    # Initialize state tracking
    if serial not in self.controller_button_states:
        self.controller_button_states[serial] = {
            'trigger': False, 'move': False
        }
        self.last_button_press_time[serial] = {}

    prev_state = self.controller_button_states[serial]

    # Detect trigger press (False → True)
    if controller.trigger_pressed and not prev_state['trigger']:
        if self._should_process_button(serial, 'trigger', current_time):
            await self._handle_trigger_press(serial)

    # Detect move press (False → True) - used as SELECT
    if controller.move_pressed and not prev_state['move']:
        if self._should_process_button(serial, 'move', current_time):
            await self._handle_select_press(serial)

    # Update state
    prev_state['trigger'] = controller.trigger_pressed
    prev_state['move'] = controller.move_pressed

def _should_process_button(self, serial, button, current_time):
    """Check if button press should be processed (debouncing)."""
    last_press = self.last_button_press_time[serial].get(button, 0)
    if current_time - last_press < 0.2:  # 200ms debounce
        return False
    self.last_button_press_time[serial][button] = current_time
    return True

async def _handle_trigger_press(self, serial):
    """Handle trigger button press - start game."""
    self.state = menu_pb2.MenuState.GAME_STARTING
    self._publish_event("game_requested", {
        "game_name": self.current_selection,
        "source": "controller",
        "serial": serial
    })
    logger.info(f"Game requested via controller {serial}: {self.current_selection}")

async def _handle_select_press(self, serial):
    """Handle select button press - cycle games."""
    games = ["JoustFFA", "JoustTeams", "Tournament", "Werewolf", "NonstopJoust"]
    current_index = games.index(self.current_selection) if self.current_selection in games else 0
    self.current_selection = games[(current_index + 1) % len(games)]
    self._publish_event("selection_changed", {
        "game_name": self.current_selection,
        "source": "controller",
        "serial": serial
    })
    logger.info(f"Selection changed via controller {serial}: {self.current_selection}")
```

## Expected Improvements

- Physical controller buttons work for menu navigation
- Players can select and start games without WebUI
- Complete standalone controller-based UX
- Foundation for Phase 22 (NonstopJoust in game list)

## Raspberry Pi Impact

- Minimal CPU overhead (~1-2% for 30Hz button monitoring)
- No latency impact on gameplay
- Button monitoring runs independently from game loop

## Success Criteria

- Physical SELECT button cycles through games
- Physical TRIGGER button starts selected game
- Debouncing prevents duplicate inputs
- Works with multiple controllers
- WebUI game selection still works
