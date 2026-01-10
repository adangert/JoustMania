# Controller Manager Architecture Design

**Date:** 2026-01-09
**Purpose:** Extract controller management from piparty.py into dedicated module
**Status:** Design Proposal

---

## Problem Statement

`piparty.py` currently handles too many responsibilities (1,242 lines):
- Controller pairing and discovery
- Controller process spawning and lifecycle
- Controller state management
- Menu orchestration
- Game coordination
- Settings management
- Web UI integration

This violates the Single Responsibility Principle and makes the code hard to maintain, test, and reason about.

---

## Proposed Solution

Create a **`ControllerManager`** class that encapsulates all controller-related operations.

### Two Architecture Options

#### Option 1: Manager Module (Recommended)
- Extract into `controller_manager.py` module
- Runs in main process (no additional process)
- Called by Menu class
- Simpler, lower risk

#### Option 2: Manager Process
- Runs as separate process
- Better isolation
- More complex IPC
- Higher risk, can be done later

**Recommendation:** Start with Option 1 (module), can migrate to Option 2 (process) later if needed.

---

## Controller Manager Responsibilities

### What to Extract from piparty.py

**Controller Lifecycle:**
- `check_for_new_moves()` - Discover new controllers
- `pair_usb_move()` - Pair USB controllers
- `pair_move()` - Spawn controller process
- `remove_controller()` - Stop and cleanup controller
- `stop_tracking_moves()` - Stop all controllers
- `retrack_removed_controllers()` - Restart controllers after game

**Controller State:**
- `tracked_moves` - Dict of active controller processes
- `controller_states` - Dict of ControllerState instances
- `menu_opts` - Per-controller menu options
- `game_opts` - Per-controller game options
- `force_color` - Per-controller color overrides
- `controller_teams` - Per-controller team assignments
- `controller_colors` - Per-controller color assignments
- `controller_sensitivity` - Per-controller sensitivity
- `dead_moves` - Per-controller alive/dead status
- `invincible_moves` - Per-controller invincibility
- `kill_controller_proc` - Per-controller kill flags
- `out_moves` - Per-controller output status

**Controller Queries:**
- `get_move_count()` - Count connected controllers
- `ready_move()` - Check if controller is ready for game
- `get_ready_moves()` - Get list of ready controllers
- `get_game_moves()` - Get controllers for current game

**Controller Configuration:**
- `reset_controller_game_state()` - Reset all controller states
- `check_charging_controller()` - Check for charging controllers

### What Stays in Menu Class

**Menu Logic:**
- Menu loop and game triggers
- Admin controls processing
- Game mode selection
- Start game logic

**Game Coordination:**
- `start_game()` - Initialize and start game
- `game_loop()` - Main game loop
- `check_end_game()` - End game logic

**Settings:**
- Settings loading/saving
- Web UI integration
- Audio management

---

## Proposed Architecture

### Module Structure

```
controller_manager.py
├── ControllerManager class
│   ├── Lifecycle management
│   ├── State management
│   ├── Process spawning
│   └── Query interface
│
piparty.py
├── Menu class (simplified)
│   ├── Menu loop
│   ├── Game coordination
│   ├── Settings management
│   └── Uses ControllerManager
```

### Class Design

```python
class ControllerManager:
    """
    Manages Move controller lifecycle, state, and processes.

    Responsibilities:
    - Discover and pair controllers
    - Spawn and manage controller processes
    - Track controller state
    - Provide query interface for menu/game logic
    """

    def __init__(self, menu_flag, restart_flag, dead_count, music_speed,
                 show_battery, show_team_colors, red_on_kill, revive,
                 use_state_based_tracking=True):
        """Initialize controller manager with shared flags."""

    # Lifecycle Management
    def check_for_new_moves(self) -> int:
        """Check for newly connected controllers."""

    def pair_usb_move(self, move) -> None:
        """Pair a USB-connected controller."""

    def pair_move(self, move, move_num) -> None:
        """Spawn tracking process for a controller."""

    def remove_controller(self, move_serial: str) -> None:
        """Stop and cleanup a controller."""

    def stop_all_controllers(self) -> None:
        """Stop all controller processes."""

    def retrack_removed_controllers(self, game_moves) -> None:
        """Restart controllers after game."""

    # State Management
    def get_controller_state(self, move_serial: str) -> ControllerState:
        """Get ControllerState for a controller."""

    def get_menu_opts(self, move_serial: str):
        """Get menu options for a controller."""

    def get_game_opts(self, move_serial: str):
        """Get game options for a controller."""

    def reset_all_state(self) -> None:
        """Reset all controller state for new game."""

    # Queries
    def get_move_count(self) -> int:
        """Count connected controllers."""

    def is_ready(self, move_serial: str) -> bool:
        """Check if controller is ready for game."""

    def get_ready_controllers(self, force_all: bool = False) -> list:
        """Get list of controllers ready for game."""

    def get_game_controllers(self) -> list:
        """Get list of controllers for current game."""

    def has_charging_controller(self) -> bool:
        """Check if any controller is charging."""

    # Configuration
    def set_game_mode(self, game_mode) -> None:
        """Set game mode for all controllers."""

    def set_sensitivity(self, sensitivity: int) -> None:
        """Set sensitivity for all controllers."""
```

### Usage in Menu Class

```python
class Menu:
    def __init__(self):
        # ... existing setup ...

        # Create controller manager
        self.controller_manager = ControllerManager(
            menu_flag=self.menu,
            restart_flag=self.restart,
            dead_count=self.dead_count,
            music_speed=self.music_speed,
            show_battery=self.show_battery,
            show_team_colors=self.show_team_colors,
            red_on_kill=self.red_on_kill,
            revive=self.revive,
            use_state_based_tracking=self.use_state_based_tracking
        )

    def game_loop(self):
        """Main menu loop."""
        while True:
            # Check for new controllers
            new_controllers = self.controller_manager.check_for_new_moves()

            # Pair new controllers
            for move_num in range(new_controllers):
                move = psmove.PSMove(move_num)
                self.controller_manager.pair_usb_move(move)
                self.controller_manager.pair_move(move, move_num)

            # ... menu logic ...

            # Check if ready to start game
            if self.check_start_conditions():
                ready_controllers = self.controller_manager.get_ready_controllers()
                self.start_game(ready_controllers)
```

---

## Benefits

### Code Organization
- ✅ **Single Responsibility** - Each class has one clear purpose
- ✅ **Reduced Complexity** - piparty.py goes from 1,242 → ~800 lines
- ✅ **Better Testability** - Can test ControllerManager independently
- ✅ **Clearer Interfaces** - Explicit API between menu and controller management

### Maintainability
- ✅ **Easier to Understand** - Controller logic in one place
- ✅ **Easier to Modify** - Changes to controller management don't affect menu logic
- ✅ **Easier to Debug** - Clear boundaries between components
- ✅ **Easier to Document** - Self-contained module

### Future Flexibility
- ✅ **Can Move to Separate Process** - If needed later for better isolation
- ✅ **Can Add Features** - E.g., controller health monitoring, auto-restart
- ✅ **Can Swap Implementations** - E.g., mock for testing
- ✅ **Better Observability** - Can add metrics/spans at manager level

---

## Implementation Plan

### Phase 1: Create ControllerManager Module ✅
1. Create `controller_manager.py`
2. Define `ControllerManager` class with interface
3. Add basic lifecycle methods (stub implementations)

### Phase 2: Extract Lifecycle Management ✅
1. Move `pair_move()` logic
2. Move `remove_controller()` logic
3. Move `check_for_new_moves()` logic
4. Move `stop_tracking_moves()` logic
5. Test controller pairing/removal

### Phase 3: Extract State Management ✅
1. Move state dictionaries to ControllerManager
2. Add getter/setter methods
3. Update Menu class to use manager methods
4. Test state management

### Phase 4: Extract Query Methods ✅
1. Move `get_ready_moves()` logic
2. Move `get_game_moves()` logic
3. Move `ready_move()` logic
4. Test query interface

### Phase 5: Integration and Testing ✅
1. Update Menu class to use ControllerManager
2. Remove extracted code from piparty.py
3. Run full test suite
4. Test with real controllers

### Phase 6: Documentation ✅
1. Document ControllerManager API
2. Update architecture docs
3. Add usage examples
4. Update IMPLEMENTATION_STATUS.md

---

## Migration Strategy

### Step 1: Create Alongside (No Breaking Changes)
- Create ControllerManager with full implementation
- Keep existing code in piparty.py
- Test ControllerManager independently

### Step 2: Dual Mode (Feature Flag)
- Add feature flag to use ControllerManager
- Test both paths work
- Verify no regressions

### Step 3: Cut Over
- Make ControllerManager the default
- Remove old code from piparty.py
- Clean up

### Step 4: Cleanup
- Remove feature flag
- Final testing
- Documentation

---

## Risk Assessment

### Low Risk ✅
- Controller lifecycle management (well-defined boundaries)
- State management (clear ownership)
- Query methods (read-only, easy to test)

### Medium Risk ⚠️
- Integration with existing Menu class (many touch points)
- Shared memory management (careful with multiprocessing)
- Process spawning (critical path)

### Mitigation Strategies
- ✅ **Extensive Testing** - Unit tests for ControllerManager
- ✅ **Feature Flag** - Can rollback if issues
- ✅ **Incremental Migration** - One component at a time
- ✅ **Keep Legacy Code** - Until ControllerManager proven

---

## Future Enhancements

Once ControllerManager is established:

### Controller Health Monitoring
```python
def get_controller_health(self, move_serial: str) -> dict:
    """
    Get health metrics for a controller.

    Returns:
        {
            'state_age_ms': 5.2,
            'update_frequency': 987,
            'battery_level': 80,
            'connection_quality': 'good'
        }
    """
```

### Auto-Restart on Failure
```python
def monitor_controllers(self):
    """
    Background monitor that auto-restarts failed controllers.
    """
```

### Controller Pooling
```python
def create_controller_pool(self, pool_size: int = 4):
    """
    Create shared worker pool for multiple controllers.
    Reduces from N processes to pool_size processes.
    """
```

### Manager as Separate Process
```python
class ControllerManagerProcess(Process):
    """
    Run ControllerManager in separate process.
    Provides better isolation and monitoring.
    """
```

---

## Alternatives Considered

### Alternative 1: Keep in piparty.py
**Pros:** No refactoring needed
**Cons:** Continues to violate SRP, hard to maintain
**Decision:** Rejected - technical debt too high

### Alternative 2: Extract to Multiple Small Modules
**Pros:** Even more granular
**Cons:** Over-engineering for current needs
**Decision:** Rejected - one ControllerManager is sufficient

### Alternative 3: Manager Process from Day 1
**Pros:** Better isolation
**Cons:** More complex, higher risk
**Decision:** Deferred - start with module, upgrade later if needed

---

## Success Criteria

### Code Quality
- [ ] piparty.py reduced to < 800 lines
- [ ] ControllerManager has clear, documented API
- [ ] All controller logic in one place
- [ ] No circular dependencies

### Functionality
- [ ] All controllers pair correctly
- [ ] All games work normally
- [ ] No regressions in controller behavior
- [ ] State management works correctly

### Testing
- [ ] Unit tests for ControllerManager (10+ tests)
- [ ] Integration tests with Menu class
- [ ] Real controller testing
- [ ] Performance unchanged or better

### Documentation
- [ ] ControllerManager API documented
- [ ] Usage examples provided
- [ ] Architecture diagrams updated
- [ ] Migration guide written

---

## Next Steps

**For Implementation:**
1. Review and approve this design
2. Create `controller_manager.py` skeleton
3. Implement ControllerManager class
4. Extract lifecycle methods first
5. Test incrementally

**For Discussion:**
- Should we do this now or after current state-based work stabilizes?
- Any concerns about the proposed API?
- Should we include any additional features in v1?

---

## Questions & Feedback

**Q: Should ControllerManager be a separate process?**
A: Not initially. Start with module in main process, can migrate to process later if isolation benefits outweigh complexity.

**Q: How does this interact with state-based tracking?**
A: ControllerManager owns ControllerState instances, tracks them alongside processes. Clean separation.

**Q: What about backward compatibility?**
A: Feature flag allows using old path. Remove once ControllerManager proven stable.

**Q: Performance impact?**
A: Should be neutral or slightly better (better organization, potential for optimizations).

---

## Timeline Estimate

- **Design & Review:** 1 hour (this document)
- **Implementation:** 4-6 hours
  - Phase 1-2: 2 hours (skeleton + lifecycle)
  - Phase 3-4: 2 hours (state + queries)
  - Phase 5: 1-2 hours (integration + testing)
  - Phase 6: 1 hour (documentation)
- **Testing & Validation:** 2-3 hours
- **Total:** 1 day of focused work

---

## Approval

**Design by:** Claude Sonnet 4.5
**Date:** 2026-01-09
**Status:** Awaiting Review

Once approved, we can proceed with implementation.
