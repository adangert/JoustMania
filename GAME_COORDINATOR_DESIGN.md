# GameCoordinator Process - Design Document

**Date:** 2026-01-09
**Purpose:** Extract game coordination logic into dedicated process
**Status:** Design Proposal (Phase 2 of Microservices Architecture)

---

## Problem Statement

`piparty.py` currently handles game coordination directly in the `start_game()` method (~200 lines), which:
- Initializes games
- Manages game lifecycle
- Coordinates controller state during games
- Handles post-game cleanup

This violates separation of concerns and makes the Menu process do too much.

---

## Proposed Solution

Create a **GameCoordinator** process that encapsulates all game-related operations.

### Architecture Option

**GameCoordinator as Separate Process (Recommended)**
- Runs as independent process
- Communicates with Menu via IPC
- Manages game lifecycle independently
- Better isolation and monitoring

---

## GameCoordinator Responsibilities

### What to Extract from piparty.py

**Game Lifecycle:**
- `start_game()` - Initialize and start game
- Game mode selection (including random mode)
- Game instance creation and execution
- Game end detection
- Post-game cleanup

**Game State Management:**
- Current game mode
- Game moves (controllers in current game)
- Teams assignment
- Random mode selection history

**Game Queries:**
- `get_ready_moves()` - Get controllers ready for game
- `get_game_moves()` - Get current game controllers
- `get_game_teams()` - Get team assignments

**Post-Game Logic:**
- `retrack_removed_controllers()` - Restart controllers after game
- `reset_controller_game_state()` - Reset state
- Return to menu mode

### What Stays in Menu

**Menu Logic:**
- Menu loop
- Controller color display
- Admin controls
- Game trigger detection (just signals GameCoordinator)

---

## Proposed Architecture

### Process Structure

```
Menu Process (piparty.py)
   │
   │ IPC: start_game command
   ↓
GameCoordinator Process
   │
   ├─→ Get ready controllers from ControllerManager
   ├─→ Select game mode
   ├─→ Initialize game instance
   ├─→ Run game (blocking)
   ├─→ Detect end
   ├─→ Cleanup
   └─→ Signal Menu: game_ended event
```

### Class Design

```python
class GameCoordinatorProcess(Process):
    """
    Coordinates game initialization, execution, and cleanup.

    Responsibilities:
    - Initialize game instances
    - Monitor game state
    - Detect end conditions
    - Coordinate with ControllerManager
    - Signal game events to Menu
    """

    def __init__(self, command_queue, response_queue, event_queue,
                 controller_cmd_queue, controller_resp_queue,
                 menu_flag, restart_flag, music_speed, red_on_kill,
                 show_team_colors, revive, controller_game_mode, ns):
        """Initialize GameCoordinator with IPC queues and shared flags."""

    def run(self):
        """Main process loop."""

    # Game Lifecycle
    def start_game(self, game_mode, random_mode=False):
        """Initialize and start a game."""

    def run_game(self, game_instance):
        """Execute game instance (blocking)."""

    def end_game(self):
        """Handle game end logic."""

    def cleanup_game(self):
        """Post-game cleanup."""

    # Game Selection
    def select_game_mode(self, random_mode=False):
        """Select game mode (random or specific)."""

    def get_random_game_mode(self, available_modes):
        """Select random game mode avoiding repeats."""

    # Controller Queries (via ControllerManager)
    def get_ready_controllers(self, force_all=False):
        """Get controllers ready for game via ControllerManager IPC."""

    def get_game_teams(self):
        """Get team assignments for game."""

    # Game Instance Creation
    def create_game_instance(self, game_mode, moves, teams):
        """Instantiate appropriate game class."""

    # IPC Command Handlers
    def handle_start_game(self, params):
        """Handle start_game IPC command from Menu."""

    def handle_get_game_status(self):
        """Handle get_game_status IPC query."""
```

---

## IPC Protocol

### Command/Response (Menu → GameCoordinator)

**Commands:**
1. `start_game` - Start a new game
2. `get_game_status` - Query current game state
3. `force_end_game` - Force game to end
4. `shutdown` - Graceful shutdown

**Example:**
```python
# Menu sends start_game command
command = {
    'command': 'start_game',
    'params': {
        'game_mode': 'JoustFFA',  # or None for current mode
        'random_mode': False,
        'force_all': False
    },
    'request_id': 'uuid-1234',
    'timestamp': 1234567890.123
}

# GameCoordinator responds
response = {
    'status': 'success',  # or 'error'
    'data': {
        'game_started': True,
        'game_mode': 'JoustFFA',
        'player_count': 4
    },
    'request_id': 'uuid-1234',
    'timestamp': 1234567890.456
}
```

### Events (GameCoordinator → Menu)

**Events:**
1. `game_started` - Game has started
2. `game_ended` - Game has ended
3. `game_error` - Game error occurred

**Example:**
```python
# GameCoordinator sends game_ended event
event = {
    'event': 'game_ended',
    'data': {
        'game_mode': 'JoustFFA',
        'winner': 'serial123',  # or None
        'duration_seconds': 120
    },
    'timestamp': 1234567890.789
}
```

### Communication with ControllerManager

GameCoordinator needs to query ControllerManager for:
- Ready controllers
- Controller states
- Reset controller states

```python
# GameCoordinator → ControllerManager
response = send_command(
    controller_cmd_queue,
    controller_resp_queue,
    'get_ready_controllers',
    {'force_all': False}
)
ready_controllers = response['data']['controllers']
```

---

## Key Features

### 1. Game Mode Selection

```python
def select_game_mode(self, random_mode=False, requested_mode=None):
    """
    Select game mode for next game.

    If random_mode:
        - Choose from random_modes setting
        - Avoid recently played modes
        - Respect minimum player requirements
    Else:
        - Use requested_mode or current mode
    """
    if random_mode:
        good_modes = self._filter_random_modes()
        selected = self._pick_random_avoiding_repeats(good_modes)
        self.random_history.append(selected)
        return selected
    else:
        return requested_mode or self.current_game_mode
```

### 2. Game Instance Creation

```python
def create_game_instance(self, game_mode, moves, teams):
    """
    Instantiate the appropriate game class.

    Each game mode has its own class (joust_ffa.Joust, traitor.Joust, etc.)
    All share common constructor signature.
    """
    music = self._select_music(game_mode)

    if game_mode == Games.JoustFFA:
        return joust_ffa.Joust(
            moves=moves,
            command_queue=self.command_queue,
            ns=self.ns,
            red_on_kill=self.red_on_kill,
            music=music,
            teams=teams,
            game_mode=game_mode,
            controller_teams=self.controller_teams,
            controller_colors=self.controller_colors,
            dead_moves=self.dead_moves,
            invincible_moves=self.invincible_moves,
            force_move_colors=self.force_color,
            music_speed=self.music_speed,
            show_team_colors=self.show_team_colors,
            restart=self.restart,
            revive=self.revive
        )
    # ... similar for other game modes
```

### 3. Game Execution

```python
def run_game(self, game_instance):
    """
    Execute game (blocking).

    Game instances handle their own game loop.
    This method blocks until game ends.
    """
    # Game constructor runs the game
    # Most game classes start their loop in __init__
    # When constructor returns, game has ended

    # Game instances will set menu.value = 1 and restart.value = 0
    # when they're done, which signals end
```

### 4. Post-Game Cleanup

```python
def cleanup_game(self):
    """
    Cleanup after game ends.

    - Reset controller game state
    - Reload music
    - Reset admin mode
    - Retrack removed controllers
    """
    # Reset game state
    response = send_command(
        self.controller_cmd_queue,
        self.controller_resp_queue,
        'reset_state'
    )

    # Reload music
    self.choose_new_music()

    # Reset other state
    self.admin_move = None
    self.random_added = []

    # Signal Menu that game ended
    self.event_queue.put({
        'event': 'game_ended',
        'timestamp': time.time()
    })
```

---

## State Management

### Shared Memory (from ControllerManager)

GameCoordinator needs access to controller state shared memory:

```python
# These come from ControllerManager via queries
self.controller_teams = {}     # Via ControllerManager
self.controller_colors = {}    # Via ControllerManager
self.dead_moves = {}           # Via ControllerManager
self.invincible_moves = {}     # Via ControllerManager
self.force_color = {}          # Via ControllerManager
self.game_opts = {}            # Via ControllerManager
```

### Shared Flags

```python
self.menu = Value('i', 1)                    # Menu/game mode flag
self.restart = Value('i', 0)                 # Restart flag
self.music_speed = Value('d', 0)             # Music speed
self.red_on_kill = Value('i', 0)             # Red on kill
self.show_team_colors = Value('i', 0)        # Team colors
self.revive = Value('b', False)              # Revive enabled
self.controller_game_mode = Value('i', 1)    # Game mode
```

### GameCoordinator-Owned State

```python
self.current_game_mode = Games.JoustFFA
self.old_game_mode = Games.JoustFFA
self.random_history = []         # History for random mode
self.current_game_instance = None
self.game_in_progress = False
```

---

## Integration with Menu

### Menu Triggers Game

```python
# piparty.py Menu.check_start_game()
def check_start_game(self):
    # Detect start trigger from controllers or webui
    if start_triggered:
        # Send start_game command to GameCoordinator
        response = self.send_game_command('start_game', {
            'random_mode': self.game_mode == Games.Random,
            'force_all': self.ns.settings['force_all_start']
        })

        if response['status'] == 'success':
            logger.info("Game started successfully")
```

### Menu Receives Game End Event

```python
# piparty.py Menu.game_loop()
def game_loop(self):
    while True:
        # ... menu logic

        # Check for game events (non-blocking)
        self.check_game_events()

def check_game_events(self):
    """Check for events from GameCoordinator."""
    try:
        while not self.game_event_queue.empty():
            event = self.game_event_queue.get_nowait()

            if event['event'] == 'game_ended':
                logger.info("Game ended, returning to menu")
                self.play_menu_music = True
            elif event['event'] == 'game_error':
                logger.error(f"Game error: {event.get('error')}")
    except:
        pass
```

---

## Benefits

### 1. Separation of Concerns
- ✅ Game logic isolated in separate process
- ✅ Menu focuses on UI and triggers
- ✅ Clear boundaries

### 2. Independent Monitoring
- ✅ GameCoordinator can be observed separately
- ✅ Game-level metrics (duration, players, mode)
- ✅ Process-level metrics (CPU, memory)

### 3. Fault Isolation
- ✅ Game crashes don't crash menu
- ✅ Can restart GameCoordinator independently
- ✅ Menu remains responsive

### 4. Easier Testing
- ✅ Can test game coordination without menu
- ✅ Mock IPC interfaces
- ✅ Isolated game logic

---

## Implementation Challenges

### Challenge 1: Game Constructors Block

**Problem:** Most game classes start their game loop in `__init__()`, which blocks.

**Solution:** GameCoordinator's `run_game()` method should expect blocking and run in the main process loop. While game runs, GameCoordinator is blocked (which is fine - it's dedicated to that game).

### Challenge 2: Shared Memory Access

**Problem:** Games need direct access to controller shared memory (controller_teams, dead_moves, etc.).

**Solution:** GameCoordinator has references to these shared memory objects and passes them to game constructors. ControllerManager creates them, GameCoordinator uses them.

### Challenge 3: Music Management

**Problem:** Games control music directly, but Menu also needs music.

**Solution:** Move music loading to GameCoordinator. Menu and GameCoordinator each manage their own music instances.

---

## Migration Strategy

### Step 1: Create GameCoordinator Alongside (No Breaking Changes)
- Create `game_coordinator.py` with full implementation
- Keep existing `start_game()` in piparty.py
- Test GameCoordinator independently

### Step 2: Dual Mode (Feature Flag)
```python
self.use_game_coordinator_process = True  # Feature flag
```
- If enabled, use GameCoordinator
- If disabled, use legacy `start_game()`
- Test both paths work

### Step 3: Cut Over
- Make GameCoordinator the default
- Remove old `start_game()` from piparty.py

### Step 4: Cleanup
- Remove feature flag
- Final testing
- Documentation

---

## Testing Strategy

### Unit Tests
- Game mode selection logic
- Random mode avoidance
- IPC message handling

### Integration Tests
- Start game via IPC
- Game execution
- End game detection
- Event delivery to Menu

### Manual Tests
- Play each game mode through GameCoordinator
- Test random mode
- Test minimum players enforcement
- Test force start

---

## Timeline Estimate

- **Design & Review:** 1 hour (this document) ✅
- **Implementation:** 6-8 hours
  - Core GameCoordinator class: 2 hours
  - Game instance creation: 2 hours
  - IPC handlers: 1 hour
  - Integration with Menu: 2 hours
  - Music management: 1 hour
- **Testing & Validation:** 3-4 hours
- **Total:** 1-1.5 days of focused work

---

## Success Criteria

### Implementation
- [ ] GameCoordinator process starts successfully
- [ ] IPC communication works (commands + events)
- [ ] All game modes can be started
- [ ] Games execute correctly
- [ ] Post-game cleanup works
- [ ] Return to menu seamless

### Testing
- [ ] Integration test for IPC
- [ ] Test each game mode
- [ ] Test random mode
- [ ] Test error handling

### Documentation
- [ ] GameCoordinator API documented
- [ ] Integration guide
- [ ] Architecture diagrams
- [ ] Migration guide

---

## Next Steps

**For Implementation:**
1. Review and approve this design
2. Create `game_coordinator.py` skeleton
3. Implement GameCoordinatorProcess class
4. Implement game lifecycle methods
5. Integrate with Menu via IPC
6. Test incrementally

**For Discussion:**
- Should GameCoordinator also manage shared memory objects, or just reference them?
- How to handle music - separate Audio Manager process or keep in GameCoordinator?
- Should we add game state queries (get_current_players, get_game_progress)?

---

## Open Questions

**Q: How does GameCoordinator access controller shared memory?**
A: ControllerManager creates and owns the shared memory. GameCoordinator receives references via IPC or at startup. Games receive direct references when instantiated.

**Q: What happens if Menu process dies while game is running?**
A: GameCoordinator continues running game. When game ends, it tries to send event to Menu but gets no response. Could implement timeout and graceful shutdown.

**Q: Should GameCoordinator be a long-running process or one-per-game?**
A: Long-running. Start once at system startup, handle multiple games via IPC commands.

**Q: How to handle game-specific music?**
A: GameCoordinator loads and manages game music. Menu manages menu music. Audio Manager process (Phase 3+) could centralize this later.

---

## Approval

**Design by:** Claude Sonnet 4.5
**Date:** 2026-01-09
**Status:** Awaiting Review

Once approved, we can proceed with implementation.
