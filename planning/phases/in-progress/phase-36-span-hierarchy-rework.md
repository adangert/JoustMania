# Phase 36: OpenTelemetry Span Hierarchy Rework

**Status:** Planned
**Priority:** HIGH
**Estimated Effort:** Medium (1-2 days)

## Goal

Restructure OpenTelemetry spans in the Game Coordinator to create a proper hierarchical trace structure with one parent game session span and child spans for each game phase. This will provide clear visibility into time spent in initialization, countdown, gameplay, and teardown phases.

## Motivation

**Current Problems:**
1. **No parent game span**: `StartGame`, `game_loop`, and `ForceEndGame` RPCs create independent, disconnected spans
2. **Fragmented traces**: Game lifecycle phases (load_settings, initialize_players, countdown, game_loop, end_game) are independent spans instead of children of a parent
3. **Excessive span creation**: High-frequency operations like `kill_player` create individual spans instead of events
4. **Poor tracing UX**: Difficult to see overall game duration and phase breakdown in Jaeger

**Benefits of Hierarchical Structure:**
- **Single game view**: One parent span covering entire game lifecycle from start to end
- **Phase timing**: Clear breakdown of time spent in initialization, countdown, gameplay, teardown
- **Team/player hierarchy**: Parent spans for teams (in team modes) with child spans per player
- **Reduced overhead**: Convert high-frequency operations from spans to events (~30% fewer spans)
- **Better debugging**: Easy to identify which phase is slow or failing

## Current Span Structure

### Server-Level (services/game_coordinator/server.py)
```
StartGame (RPC) - Independent span
  └─> game_loop - Independent span (created in _run_game_loop_async)
ForceEndGame (RPC) - Independent span
```

**Problem**: No connection between these spans. Can't see full game duration.

### Game Mode Level (e.g., ffa.py, teams.py)
```
ffa_run - Parent span (but disconnected from server RPCs)
  ffa_load_settings - Independent span
  ffa_initialize_players - Independent span
  ffa_countdown - Independent span
  ffa_game_loop - Independent span
    player_X_lifecycle - Child span (GOOD)
      └─> death_warning - Event (GOOD)
  ffa_kill_player - Independent span (SHOULD BE EVENT)
  ffa_end_game - Independent span
```

**Problems**:
- Game mode spans are disconnected from server RPC spans
- `kill_player` creates unnecessary spans instead of events
- No single parent covering all phases

## Proposed Span Hierarchy

### Top-Level Structure
```
game_session (parent span covering entire lifecycle)
├─> initialization_phase (child span)
│   ├─> load_settings (child span)
│   └─> initialize_players (child span)
├─> countdown_phase (child span)
├─> gameplay_phase (child span)
│   ├─> [FFA Mode] player_X_lifecycle (child spans)
│   │   ├─> death_warning (event)
│   │   ├─> player_death (event)
│   │   └─> ... (other events)
│   └─> [Team Mode] team_X_lifecycle (child spans)
│       ├─> player_Y_lifecycle (child spans of team)
│       │   ├─> death_warning (event)
│       │   ├─> player_death (event)
│       │   └─> ... (other events)
│       └─> ... (other players in team)
└─> teardown_phase (child span)
    └─> end_game (child span)
```

### Span vs Event Decision Matrix

| Operation | Current | Proposed | Reason |
|-----------|---------|----------|--------|
| Game session | ❌ None | ✅ Span | Top-level parent for entire game |
| Initialization | ✅ Span | ✅ Span | Distinct phase with multiple steps |
| Countdown | ✅ Span | ✅ Span | Distinct phase with timing |
| Game loop | ✅ Span | ✅ Span (renamed to gameplay_phase) | Main game phase |
| Teardown | ✅ Span | ✅ Span | Distinct phase for cleanup |
| Team lifecycle | ✅ Span | ✅ Span | Parent for team players (team modes) |
| Player lifecycle | ✅ Span | ✅ Span | Covers player's full game participation |
| Kill player | ⚠️ Span | ✅ Event | High-frequency, short-lived |
| Warn player | ✅ Event | ✅ Event | High-frequency, already correct |
| Respawn player | ⚠️ Span | ✅ Event | High-frequency (Nonstop Joust) |

## Implementation Tasks

### Task 1: Create Parent Game Session Span
**Files**: `services/game_coordinator/server.py`

- [ ] Modify `StartGame` RPC to create `game_session` span
- [ ] Pass game_session span context to `_run_game_loop_async`
- [ ] Store span context in `self.current_game_context`
- [ ] End `game_session` span in `ForceEndGame` or when game naturally ends
- [ ] Add attributes: `game.mode`, `game.id`, `player_count`

**Example**:
```python
async def StartGame(self, request, context):
    """Start a new game."""
    # Create parent game session span
    with tracer.start_as_current_span("game_session") as game_span:
        game_span.set_attribute("game.mode", request.game_mode)
        game_span.set_attribute("game.id", self.current_game_id)

        # Store context for later access
        self.current_game_context = trace.set_span_in_context(game_span)

        # Start game (initialization, countdown, gameplay, teardown happen as children)
        # ...
```

### Task 2: Convert Game Mode Spans to Child Spans
**Files**: `services/game_coordinator/games/{ffa,teams,random_teams,nonstop_joust}.py`

- [ ] Accept parent `game_context` parameter in `run()` method
- [ ] Create child spans using parent context:
  - `initialization_phase` (wraps load_settings + initialize_players)
  - `countdown_phase` (wraps countdown)
  - `gameplay_phase` (wraps game_loop)
  - `teardown_phase` (wraps end_game)
- [ ] Remove the outer `{mode}_run` span (replaced by game_session)

**Example for FFA**:
```python
async def run(self, game_context=None):
    """Run the FFA game with proper span hierarchy."""

    # Initialization phase
    init_ctx = game_context or trace.get_current_span().get_span_context()
    with tracer.start_as_current_span("initialization_phase", context=init_ctx) as init_span:
        await self._load_settings()
        await self._initialize_players()

    # Countdown phase
    with tracer.start_as_current_span("countdown_phase", context=init_ctx) as countdown_span:
        await self._countdown()

    # Gameplay phase
    with tracer.start_as_current_span("gameplay_phase", context=init_ctx) as gameplay_span:
        await self._game_loop()

    # Teardown phase
    with tracer.start_as_current_span("teardown_phase", context=init_ctx) as teardown_span:
        await self._end_game()
```

### Task 3: Convert Kill/Respawn Operations to Events
**Files**: `services/game_coordinator/games/{ffa,teams,random_teams,nonstop_joust}.py`

- [ ] Remove `with tracer.start_as_current_span("xxx_kill_player")` wrapper
- [ ] Add `player_death` event to player's lifecycle span instead
- [ ] Remove `with tracer.start_as_current_span("nonstop_respawn_player")` wrapper
- [ ] Add `player_respawn` event to player's lifecycle span instead
- [ ] Keep the actual kill/respawn logic unchanged

**Example**:
```python
async def _kill_player(self, serial: str, accel_mag: float):
    """Kill a player (converted from span to event)."""
    player = self.players.get(serial)
    if not player or not player.alive:
        return

    player.alive = False

    # Add death event to player's lifecycle span
    if player.span:
        player.span.add_event(
            "player_death",
            attributes={
                "accel_magnitude": accel_mag,
                "threshold": self.sensitivity.value[1],
                "alive_count": len([p for p in self.players.values() if p.alive])
            }
        )

    # Rest of kill logic...
```

### Task 4: Remove Redundant Individual Spans
**Files**: `services/game_coordinator/games/{ffa,teams,random_teams,nonstop_joust}.py`

- [ ] Remove individual `load_settings` spans (covered by initialization_phase)
- [ ] Remove individual `initialize_players` spans (covered by initialization_phase)
- [ ] Remove individual `countdown` spans (covered by countdown_phase)
- [ ] Remove individual `game_loop` spans (covered by gameplay_phase)
- [ ] Remove individual `end_game` spans (covered by teardown_phase)
- [ ] Keep only the parent phase spans

**Note**: Individual operations can still log, but don't need separate spans.

### Task 5: Update All Game Modes
**Files**: Apply changes to all game modes

- [ ] **FFA** (`services/game_coordinator/games/ffa.py`)
  - Update span hierarchy
  - Convert kill_player to event

- [ ] **Teams** (`services/game_coordinator/games/teams.py`)
  - Update span hierarchy
  - Convert kill_player to event
  - Keep team/player hierarchy (already good)

- [ ] **Random Teams** (`services/game_coordinator/games/random_teams.py`)
  - Update span hierarchy
  - Convert kill_player to event
  - Keep team/player hierarchy

- [ ] **Nonstop Joust** (`services/game_coordinator/games/nonstop_joust.py`)
  - Update span hierarchy
  - Convert kill_player to event
  - Convert respawn_player to event

### Task 6: Update ForceEndGame
**Files**: `services/game_coordinator/server.py`

- [ ] Access stored `self.current_game_context`
- [ ] Add event to game_session span: `game_force_ended`
- [ ] Ensure game_session span ends gracefully
- [ ] Clear `self.current_game_context`

### Task 7: Testing and Validation
**Tools**: Jaeger UI (http://localhost:16686)

- [ ] Start each game mode and verify span hierarchy in Jaeger
- [ ] Confirm single parent `game_session` span appears
- [ ] Verify child spans: initialization, countdown, gameplay, teardown
- [ ] Check team/player hierarchy in team modes
- [ ] Confirm kill/respawn are events, not spans
- [ ] Verify span count reduction (~30% fewer spans)
- [ ] Test ForceEndGame and verify game_session span ends

## Success Criteria

- ✅ **Single game view**: One `game_session` span covers entire game lifecycle
- ✅ **Phase visibility**: Clear child spans for initialization, countdown, gameplay, teardown
- ✅ **Team hierarchy**: Team modes show team parent spans with player child spans
- ✅ **Event conversion**: kill_player and respawn_player are events, not spans
- ✅ **Jaeger clarity**: Traces are easy to navigate and understand in Jaeger UI
- ✅ **Span reduction**: ~30% fewer spans created per game
- ✅ **All modes updated**: FFA, Teams, RandomTeams, NonstopJoust all use new hierarchy

## Performance Impact

**Before**:
- ~50-100 spans per game (depending on mode and duration)
- Independent spans make trace navigation difficult

**After**:
- ~35-70 spans per game (~30% reduction)
- Single parent span makes trace navigation trivial
- Reduced OpenTelemetry overhead (~5-10% CPU in game loop)

## Dependencies

- Phase 8c (OpenTelemetry Integration) - ✅ Complete
- Phase 27 (OpenTelemetry Optimization) - 🚀 Planned (can be done in parallel)

## Notes

- This is primarily a refactoring task - no new functionality
- Existing logs and metrics remain unchanged
- Player lifecycle spans already work well, keeping them
- Team hierarchy (teams.py) already correct, just needs parent game_session
- Focus on clarity and hierarchy, not changing game logic

## Related Files

**Primary**:
- `services/game_coordinator/server.py` (lines 190-270, 429-450)
- `services/game_coordinator/games/ffa.py` (all span creation)
- `services/game_coordinator/games/teams.py` (all span creation)
- `services/game_coordinator/games/random_teams.py` (all span creation)
- `services/game_coordinator/games/nonstop_joust.py` (all span creation)

**Reference**:
- OpenTelemetry Context API documentation
- Jaeger UI for validation
