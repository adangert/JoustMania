# Menu Process - Design Document

**Date:** 2026-01-10
**Purpose:** Extract menu loop into dedicated process
**Status:** Design Proposal (Phase 5 of Microservices Architecture)

---

## Problem Statement

`piparty.py` currently handles the menu loop directly:
- Menu display and controller tracking
- Game mode selection
- Admin controls
- Game start detection
- Audio playback

This makes piparty.py a large monolith (~3000 lines) mixing:
- Process orchestration (starting/stopping services)
- Menu UI logic (controller colors, team selection)
- Audio management
- Web UI integration

---

## Proposed Solution

Create a **Menu Process** that runs the menu loop as a separate microservice.

### Architecture

**MenuProcess as Separate Process**
- Runs as independent process
- Handles menu UI and controller display
- Detects game start triggers
- Communicates with other services via IPC
- Sends events to orchestrator (piparty.py)

**piparty.py becomes Pure Orchestrator**
- Starts all processes (via ProcessSupervisor)
- Routes commands between processes
- Minimal logic, just coordination
- Much smaller and maintainable

---

## Menu Process Responsibilities

### Menu Loop
- Run menu display loop at 60 FPS
- Update controller colors based on game mode
- Handle team selection (color cycling)
- Display battery status
- Play menu music

### Controller Interaction
- Read controller state (buttons, battery)
- Detect game mode changes
- Handle admin controls
- Track ready/not-ready status

### Game Start Detection
- Monitor for start triggers (all ready, admin force start)
- Send game_requested event to orchestrator
- Wait for game to finish, return to menu

### Admin Controls
- Sensitivity adjustment
- Game mode selection
- Force start
- Random mode

---

## Proposed Architecture

### Process Structure

```
piparty.py (Orchestrator)
   │
   ├─→ ProcessSupervisor
   │   ├─→ Settings
   │   ├─→ ControllerManager
   │   ├─→ GameCoordinator
   │   └─→ Menu  (NEW)
   │
   └─→ Event Loop
       ├─→ Listen for menu events (game_requested)
       ├─→ Route to GameCoordinator
       └─→ Return control to Menu when game ends
```

### Class Design

```python
class MenuProcess(Process):
    """
    Menu UI process.

    Responsibilities:
    - Run menu loop
    - Display controller colors
    - Handle game mode selection
    - Detect game start triggers
    - Send events to orchestrator
    """

    def __init__(self, command_queue, response_queue, event_queue,
                 controller_cmd_queue, controller_resp_queue,
                 settings_cmd_queue, settings_resp_queue,
                 menu_flag, ns):
        """Initialize Menu process."""

    def run(self):
        """Main process loop."""

    # Menu Loop
    def menu_loop(self):
        """Main menu loop (60 FPS)."""

    def update_controller_display(self):
        """Update controller colors based on game mode."""

    def check_game_start(self):
        """Check if game should start."""

    # Game Mode
    def handle_mode_change(self):
        """Handle game mode selection."""

    def cycle_team(self, controller_serial):
        """Cycle controller team color."""

    # Admin Controls
    def handle_admin_controls(self):
        """Process admin button combinations."""

    def adjust_sensitivity(self, delta):
        """Adjust controller sensitivity."""

    # Events
    def send_game_requested_event(self, game_mode, force_all):
        """Signal orchestrator that game should start."""

    # IPC Handlers
    def handle_start_menu(self, params):
        """Handle start_menu command."""

    def handle_stop_menu(self, params):
        """Handle stop_menu command."""
```

---

## IPC Protocol

### Command/Response (Orchestrator → Menu)

**Commands:**
1. `start_menu` - Start menu loop
2. `stop_menu` - Stop menu loop
3. `get_menu_status` - Query menu state
4. `shutdown` - Graceful shutdown

**Example:**
```python
# Orchestrator sends start_menu
command = {
    'command': 'start_menu',
    'params': {},
    'request_id': 'uuid-1234',
    'timestamp': 1234567890.123
}

# Menu responds
response = {
    'status': 'success',
    'data': {
        'menu_running': True
    },
    'request_id': 'uuid-1234',
    'timestamp': 1234567890.456
}
```

### Events (Menu → Orchestrator)

**Events:**
1. `menu_started` - Menu loop started
2. `game_requested` - User wants to start game
3. `menu_stopped` - Menu loop stopped
4. `menu_error` - Menu error occurred

**Example:**
```python
# Menu sends game_requested event
event = {
    'event': 'game_requested',
    'data': {
        'game_mode': 'JoustFFA',
        'random_mode': False,
        'force_all': False,
        'ready_controllers': ['serial1', 'serial2', 'serial3']
    },
    'timestamp': 1234567890.789
}
```

---

## Key Features

### 1. Menu Loop

```python
def menu_loop(self):
    """
    Main menu loop.

    Runs at 60 FPS, updates controller display and checks for game start.
    """
    logger.info("Menu loop started")

    # Load menu music
    self.play_menu_music()

    while self.menu_running:
        # Update controller display
        self.update_controller_display()

        # Check for game mode changes
        self.handle_mode_changes()

        # Check for admin controls
        self.handle_admin_controls()

        # Check if game should start
        if self.check_game_start():
            self.send_game_requested_event()
            # Wait for game to finish
            self.wait_for_game_end()

        # 60 FPS
        time.sleep(1/60)

    logger.info("Menu loop stopped")
```

### 2. Controller Display

```python
def update_controller_display(self):
    """
    Update controller LED colors based on game mode and readiness.

    Uses ControllerManager to get controller states.
    """
    # Get controllers from ControllerManager
    response = self.send_controller_command('get_controllers')
    controllers = response['data']['controllers']

    for serial, state in controllers.items():
        # Determine color based on game mode
        if self.game_mode == Games.JoustFFA:
            # Show readiness (green = ready, red = not ready)
            color = self.get_ready_color(state)
        elif self.game_mode == Games.JoustTeams:
            # Show team color
            color = self.get_team_color(state)
        # ... other modes

        # Send color update to ControllerManager
        self.send_controller_command('set_color', {
            'serial': serial,
            'color': color
        })
```

### 3. Game Start Detection

```python
def check_game_start(self):
    """
    Check if game should start.

    Returns True if:
    - All controllers are ready (SELECT pressed)
    - OR admin force start triggered
    """
    # Get ready controllers
    response = self.send_controller_command('get_ready_controllers')
    ready_controllers = response['data']['controllers']

    # Check if all alive controllers are ready
    all_ready = len(ready_controllers) > 0
    for serial in self.get_alive_controllers():
        if serial not in ready_controllers:
            all_ready = False
            break

    # Or admin force start
    admin_force = self.check_admin_force_start()

    return all_ready or admin_force
```

---

## Integration with Orchestrator (piparty.py)

### Modified piparty.py

```python
class Orchestrator:
    """
    Process orchestrator.

    Responsibilities:
    - Start all processes via ProcessSupervisor
    - Route events between processes
    - Minimal logic, just coordination
    """

    def __init__(self):
        # Create supervisor
        self.supervisor = ProcessSupervisor()

        # Register all processes
        self.supervisor.register_process_factory('Settings', self._create_settings)
        self.supervisor.register_process_factory('ControllerManager', self._create_controller_manager)
        self.supervisor.register_process_factory('GameCoordinator', self._create_game_coordinator)
        self.supervisor.register_process_factory('Menu', self._create_menu)  # NEW

        # Start all processes
        self.supervisor.start_all_processes()

        # Start event loop
        self.event_loop()

    def event_loop(self):
        """
        Main orchestrator event loop.

        Listen for events from processes and route accordingly.
        """
        while True:
            # Check for menu events
            self.check_menu_events()

            # Check for game events
            self.check_game_events()

            # Check for settings events
            self.check_settings_events()

            time.sleep(0.01)

    def check_menu_events(self):
        """Handle events from Menu process."""
        while not self.menu_event_queue.empty():
            event = self.menu_event_queue.get_nowait()

            if event['event'] == 'game_requested':
                # Start game via GameCoordinator
                self.start_game(event['data'])

    def start_game(self, game_data):
        """Start game via GameCoordinator."""
        # Stop menu
        self.send_menu_command('stop_menu')

        # Start game
        response = self.send_game_command('start_game', game_data)

        # Wait for game to end (handled by game_events)

    def handle_game_ended(self):
        """Handle game ended event."""
        # Restart menu
        self.send_menu_command('start_menu')
```

---

## Benefits

### 1. Separation of Concerns
- ✅ Menu logic isolated in separate process
- ✅ piparty.py is pure orchestrator (~200 lines vs ~3000)
- ✅ Clear boundaries

### 2. Independent Development
- ✅ Menu can be developed/tested separately
- ✅ Can swap menu implementations
- ✅ Easier to add new menu features

### 3. Fault Isolation
- ✅ Menu crashes don't crash orchestrator
- ✅ Can restart Menu independently
- ✅ Better error handling

### 4. Observability
- ✅ Menu-level metrics (FPS, controller count)
- ✅ Process-level monitoring
- ✅ Clear event flow

---

## Implementation Challenges

### Challenge 1: Shared State

**Problem:** Menu needs access to controller state, settings, etc.

**Solution:** Query via IPC:
- ControllerManager for controller states
- Settings for current settings
- No shared memory except via IPC

### Challenge 2: Music Management

**Problem:** Menu plays music, so does GameCoordinator.

**Solution:** Each process manages its own music:
- Menu loads and plays menu music
- GameCoordinator loads and plays game music
- No conflicts (different processes)

### Challenge 3: Startup Order

**Problem:** Menu depends on ControllerManager and Settings.

**Solution:** ProcessSupervisor handles dependencies:
```python
PROCESS_REGISTRY = {
    'Menu': {
        'dependencies': ['Settings', 'ControllerManager'],
        ...
    }
}
```

---

## Migration Strategy

### Step 1: Create MenuProcess
- Implement MenuProcess in `services/menu/`
- Extract menu_loop() logic
- Add IPC handlers
- Test independently

### Step 2: Refactor piparty.py
- Remove menu loop code
- Add Menu process startup
- Add event routing
- Keep legacy code behind feature flag

### Step 3: Feature Flag
```python
self.use_menu_process = True  # Feature flag
```
- If enabled, use MenuProcess
- If disabled, use legacy menu_loop()
- Test both paths

### Step 4: Cut Over
- Make MenuProcess default
- Remove legacy menu_loop() from piparty.py
- Final testing

---

## Testing Strategy

### Unit Tests
- MenuProcess startup/shutdown
- Controller display logic
- Game start detection
- Event emission

### Integration Tests
- Menu ↔ ControllerManager communication
- Menu ↔ GameCoordinator handoff
- Menu ↔ Settings synchronization

### Manual Tests
- Start menu, see controller colors
- Select game mode
- Start game
- Game ends, return to menu

---

## Success Criteria

### Implementation
- [ ] MenuProcess class created
- [ ] Menu loop extracted
- [ ] IPC communication working
- [ ] Events sent to orchestrator
- [ ] Integration with ProcessSupervisor

### Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing complete
- [ ] Game start/end cycle works

### Refactoring
- [ ] piparty.py reduced to orchestrator (~200 lines)
- [ ] Legacy code removed
- [ ] Clean separation

---

## Expected Impact

**piparty.py Before:**
- ~3000 lines
- Menu loop
- Game start logic
- Controller tracking
- Audio management
- Process management

**piparty.py After:**
- ~200 lines
- Process orchestration
- Event routing
- Minimal logic

**Reduction:** ~93% code reduction in main file!

---

## Next Steps

1. Create `services/menu/` directory
2. Implement MenuProcess class
3. Extract menu_loop() from piparty.py
4. Add IPC handlers
5. Integrate with ProcessSupervisor
6. Test menu loop independently
7. Test full system integration

---

## Approval

**Design by:** Claude Sonnet 4.5
**Date:** 2026-01-10
**Status:** Ready for Implementation

Once approved, we can proceed with implementation.
