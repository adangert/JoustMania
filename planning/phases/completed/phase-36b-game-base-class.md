# Phase 36b: Game Base Class Refactoring

**Status**: ✅ COMPLETE
**Date Completed**: 2026-01-12
**Priority**: High
**Complexity**: Medium-High
**Estimated Effort**: 4-6 hours

## Overview

Complete Phase 36 span hierarchy normalization by extracting common patterns from all game modes into a base class. This eliminates ~1,500 lines of duplicated code and ensures consistent OpenTelemetry span hierarchy across all game modes.

## Motivation

Phase 36 normalized span naming and hierarchy across game modes, but each mode still has ~400+ lines of duplicated code:
- Identical `_load_settings()` implementation (4×25 lines = 100 lines)
- Identical `_process_controller_state()` core logic (4×30 lines = 120 lines)
- Identical `run()` method structure with phase orchestration (4×70 lines = 280 lines)
- Identical game loop entry patterns (4×25 lines = 100 lines)
- Identical error handling (4×15 lines = 60 lines)

**Total duplication**: ~720 lines of near-identical code that should be shared.

## Goals

1. **Create `BaseGameMode` abstract class** that handles:
   - Game session span creation with human-readable names
   - Phase span orchestration (initialization, countdown, gameplay, teardown)
   - Player/team lifecycle span creation
   - Common game operations (settings, controller processing, game loop)
   - Error handling and cleanup

2. **Refactor existing game modes** to extend base class:
   - **FFAGame**: Simple flat player hierarchy
   - **TeamsGameBase**: Shared team logic (hierarchical spans)
   - **SimpleTeamsGame**: Round-robin team assignment
   - **RandomTeamsGame**: Random teams with team_formation phase
   - **NonstopJoustGame**: Respawn mechanics and scoring

3. **Reduce codebase**:
   - FFA: 650 lines → 100 lines (85% reduction)
   - Teams: 620 lines → 120 lines (81% reduction)
   - Random Teams: 700 lines → 150 lines (79% reduction)
   - Nonstop Joust: 695 lines → 250 lines (64% reduction)
   - **Total**: 2,665 lines → 1,170 lines (56% reduction)

4. **Maintain 100% compatibility**:
   - All existing tests pass without modification
   - Span hierarchy remains identical in Jaeger
   - Game behavior unchanged

## Technical Approach

### Architecture Pattern: Template Method

```python
class BaseGameMode(ABC):
    """Base class providing game lifecycle orchestration and span management."""

    async def run(self, game_context=None):
        """Template method - orchestrates all phases with proper spans."""
        span_name = get_game_display_name(self.get_game_name())

        with tracer.start_as_current_span(span_name, context=game_context) as game_span:
            try:
                # Initialization phase
                with tracer.start_as_current_span("initialization_phase", ...):
                    await self._load_settings()  # Concrete (100% shared)
                    await self._initialize_players()  # Template method
                    self._create_player_spans(game_context)  # Abstract

                # Additional phases (e.g., team_formation for Random Teams)
                for phase in self._get_additional_phases():  # Abstract
                    with tracer.start_as_current_span(phase.name, ...):
                        await phase.execute()

                # Countdown phase
                with tracer.start_as_current_span("countdown_phase", ...):
                    await self._countdown()  # Concrete (shared with hooks)

                # Gameplay phase
                with tracer.start_as_current_span("gameplay_phase", ...):
                    await self._game_loop()  # Concrete (90% shared)

                # Teardown phase
                with tracer.start_as_current_span("teardown_phase", ...):
                    await self._end_game_impl()  # Abstract

            except Exception as e:
                # Standardized error handling
                self.event_publisher("game_error", {...})
                raise
            finally:
                self.running = False

    # Concrete methods (implemented in base, used by all)
    async def _load_settings(self): ...
    async def _process_controller_state(self, state): ...
    async def _game_loop(self): ...
    async def _countdown(self): ...
    async def _warn_player(self, serial, accel_mag): ...
    def force_end(self): ...

    # Abstract methods (subclasses must implement)
    @abstractmethod
    def get_game_name(self) -> str: ...

    @abstractmethod
    async def _initialize_players_impl(self, controllers): ...

    @abstractmethod
    def _create_player_spans(self, game_context): ...

    @abstractmethod
    async def _check_win_condition(self) -> bool: ...

    @abstractmethod
    async def _kill_player_impl(self, serial, accel_mag): ...

    @abstractmethod
    def _get_additional_phases(self) -> list: ...

    @abstractmethod
    async def _end_game_impl(self): ...
```

### Class Hierarchy

```
BaseGameMode (abstract)
├── FFAGame
├── TeamsGameBase (abstract)
│   ├── SimpleTeamsGame
│   └── RandomTeamsGame
└── NonstopJoustGame
```

## Implementation Tasks

### Task 1: Create BaseGameMode
**File**: `services/game_coordinator/games/base.py`

Create abstract base class with:
- [x] Template method `run()` orchestrating all phases
- [ ] Concrete methods for shared operations
  - [ ] `_load_settings()` - 100% identical across all modes
  - [ ] `_process_controller_state()` - 95% shared core logic
  - [ ] `_game_loop()` - 90% shared streaming pattern
  - [ ] `_countdown()` - shared with customization hooks
  - [ ] `_warn_player()` - shared LED flashing logic
  - [ ] `force_end()` - 100% identical
- [ ] Abstract methods for game-specific behavior
  - [ ] `get_game_name()` - return mode name for span naming
  - [ ] `_initialize_players_impl()` - team assignment logic
  - [ ] `_create_player_spans()` - flat vs hierarchical
  - [ ] `_check_win_condition()` - last player/team/time limit
  - [ ] `_kill_player_impl()` - stay dead vs respawn
  - [ ] `_get_additional_phases()` - extra phases (team_formation)
  - [ ] `_end_game_impl()` - close spans, declare winner
- [ ] Span creation utilities
  - [ ] `_create_player_lifecycle_span()`
  - [ ] `_create_team_lifecycle_span()`

**Lines**: ~400

### Task 2: Create TeamsGameBase
**File**: `services/game_coordinator/games/teams_base.py`

Extract shared team logic:
- [ ] Team management (`self.teams`, `self.num_teams`)
- [ ] Hierarchical span creation (team → player)
- [ ] Team-based win condition
- [ ] Team elimination detection (`_get_alive_teams()`)
- [ ] Team-aware `_kill_player_impl()`

**Lines**: ~150

### Task 3: Refactor FFA
**File**: `services/game_coordinator/games/ffa.py`

- [ ] Change class signature to `FFAGame(BaseGameMode)`
- [ ] Delete duplicated methods: `run()`, `_load_settings()`, `_process_controller_state()`, `_game_loop()`, `force_end()`
- [ ] Keep only game-specific implementations:
  - [ ] `get_game_name()` → return "FFA"
  - [ ] `_initialize_players_impl()` → all players team=0
  - [ ] `_create_player_spans()` → flat hierarchy
  - [ ] `_check_win_condition()` → last player standing
  - [ ] `_kill_player_impl()` → stay dead permanently
  - [ ] `_end_game_impl()` → close spans, declare winner
  - [ ] `_get_additional_phases()` → return []
- [ ] Verify: 650 lines → ~100 lines

### Task 4: Refactor Teams
**File**: `services/game_coordinator/games/teams.py`

- [ ] Change class signature to `SimpleTeamsGame(TeamsGameBase)`
- [ ] Delete duplicated methods
- [ ] Keep only:
  - [ ] `get_game_name()` → return "Teams"
  - [ ] `_initialize_players_impl()` → round-robin team assignment
  - [ ] `_get_additional_phases()` → return []
- [ ] Verify: 620 lines → ~120 lines

### Task 5: Refactor Random Teams
**File**: `services/game_coordinator/games/random_teams.py`

- [ ] Change class signature to `RandomTeamsGame(TeamsGameBase)`
- [ ] Delete duplicated methods
- [ ] Keep only:
  - [ ] `get_game_name()` → return "Random Teams"
  - [ ] `_initialize_players_impl()` → random assignment + colors
  - [ ] `_get_additional_phases()` → return [TeamFormationPhase]
  - [ ] `_team_formation()` → show colors before game
  - [ ] `_generate_random_team_colors()`
  - [ ] `_assign_random_teams()`
- [ ] Verify: 700 lines → ~150 lines

### Task 6: Refactor Nonstop Joust
**File**: `services/game_coordinator/games/nonstop_joust.py`

- [ ] Change class signature to `NonstopJoustGame(BaseGameMode)`
- [ ] Delete duplicated methods
- [ ] Keep specialized methods:
  - [ ] `get_game_name()` → return "Nonstop Joust"
  - [ ] `_initialize_players_impl()` → NonstopPlayer with scoring
  - [ ] `_load_settings()` override → add time_limit parsing
  - [ ] `_process_controller_state()` override → spawn protection check
  - [ ] `_check_win_condition()` → time limit check
  - [ ] `_kill_player_impl()` → respawn logic (DON'T end span)
  - [ ] `_update_respawn_timers()`
  - [ ] `_respawn_player()`
  - [ ] `_end_game_impl()` → scoring calculation
- [ ] Verify: 695 lines → ~250 lines

### Task 7: Update server.py
**File**: `services/game_coordinator/server.py`

- [ ] Update imports:
  ```python
  from services.game_coordinator.games.ffa import FFAGame
  from services.game_coordinator.games.teams import SimpleTeamsGame
  from services.game_coordinator.games.random_teams import RandomTeamsGame
  from services.game_coordinator.games.nonstop_joust import NonstopJoustGame
  ```
- [ ] Update game instantiation (lines ~295-391)
- [ ] Verify: All game modes instantiate correctly

### Task 8: Add Unit Tests
**File**: `services/game_coordinator/games/test_base.py`

- [ ] Test BaseGameMode template method execution
- [ ] Test phase span creation
- [ ] Test player span creation (flat vs hierarchical)
- [ ] Test error handling and cleanup
- [ ] Test abstract method enforcement

### Task 9: Verify Integration Tests
**All existing tests should pass without modification**

- [ ] Run `test_ffa_game_with_mock_controllers` ✓
- [ ] Run `test_teams_game_with_mock_controllers` ✓
- [ ] Run `test_staggered_player_deaths[FFA]` ✓
- [ ] Run `test_staggered_player_deaths[Teams]` ✓
- [ ] Run `test_staggered_player_deaths[Random Teams]` ✓
- [ ] Run `test_multiple_games_sequence` ✓
- [ ] Run all integration tests: `pytest tests/integration/ -v`

### Task 10: Manual Verification in Jaeger
**Verify span hierarchy remains identical**

- [ ] Start `docker-compose.mock.yml`
- [ ] Run `./scripts/testing/test-mock-with-pause.py`
- [ ] Open Jaeger UI at http://localhost:16686
- [ ] Verify span hierarchy for each mode:
  - [ ] **FFA**: Free-For-All → phases → player spans
  - [ ] **Teams**: Teams → phases → team spans → player spans
  - [ ] **Random Teams**: Random Teams → phases (with team_formation) → team spans → player spans
  - [ ] **Nonstop Joust**: Nonstop Joust → phases → player spans (don't end on death)
- [ ] Compare with pre-refactor traces - should be identical

## Success Criteria

- [ ] All 4 game modes extend BaseGameMode or TeamsGameBase
- [ ] ~1,500 lines of duplicate code eliminated
- [ ] All integration tests pass without modification
- [ ] Span hierarchy in Jaeger identical to before refactoring
- [ ] Game behavior unchanged (players die/respawn correctly)
- [ ] No performance regression
- [ ] Unit tests for BaseGameMode added and passing

## Benefits

1. **Maintainability**: Fix common bugs once in base class
2. **Consistency**: All games follow same patterns
3. **Testability**: Test common behavior once
4. **Clarity**: Template method makes game flow obvious
5. **Extensibility**: New game modes reuse 80% of base
6. **Code Quality**: 56% reduction in game mode code

## Files Modified

### Created:
- `services/game_coordinator/games/base.py` (~400 lines)
- `services/game_coordinator/games/teams_base.py` (~150 lines)
- `services/game_coordinator/games/test_base.py` (~200 lines)

### Modified:
- `services/game_coordinator/games/ffa.py` (650 → 100 lines, -550)
- `services/game_coordinator/games/teams.py` (620 → 120 lines, -500)
- `services/game_coordinator/games/random_teams.py` (700 → 150 lines, -550)
- `services/game_coordinator/games/nonstop_joust.py` (695 → 250 lines, -445)
- `services/game_coordinator/server.py` (~20 line changes for imports)

### Net Impact:
- **Before**: 2,665 lines across 4 game files
- **After**: 1,170 lines across 6 files (4 games + 2 bases + 1 test)
- **Reduction**: 1,495 lines removed (56%)

## Dependencies

- Phase 36 (Span Hierarchy Rework) - **Completed** ✓
- Phase 40 (Controller Manager Base Class) - **Completed** ✓ (similar pattern)

## Related Work

- Phase 36: Established span naming conventions and hierarchy
- Phase 40: Similar base class extraction for controller manager
- This completes the span hierarchy normalization started in Phase 36
