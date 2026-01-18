# Per-Player OpenTelemetry Tracing

## Overview

All game modes now include **per-player lifecycle spans** with hierarchical structure for team-based games. This provides granular visibility into individual player behavior and team dynamics throughout the game.

## Architecture

### FFA Mode (Flat Structure)

```
ffa_run (root span)
├── ffa_load_settings
├── ffa_initialize_players
├── ffa_countdown
├── ffa_game_loop (parent span)
│   ├── player_controller_0_lifecycle
│   │   ├── player_warning (event)
│   │   ├── player_warning (event)
│   │   └── player_death (event, ends span)
│   ├── player_controller_1_lifecycle
│   │   └── player_death (event, ends span)
│   └── player_controller_2_lifecycle (winner)
│       └── player_survived (event, ends span at game end)
└── ffa_end_game
```

### Team Modes (Hierarchical Structure)

```
teams_run (root span)
├── teams_game_loop (parent span)
│   ├── team_0_Pink_lifecycle (team span)
│   │   ├── player_controller_0_lifecycle (player span)
│   │   │   └── player_survived (event)
│   │   └── player_controller_2_lifecycle (player span)
│   │       └── player_survived (event)
│   └── team_1_Magenta_lifecycle (team span)
│       ├── player_controller_1_lifecycle (player span)
│       │   ├── player_warning (event)
│       │   ├── player_warning (event)
│       │   └── player_death (event, ends span)
│       └── player_controller_3_lifecycle (player span)
│           └── player_death (event, ends span, team eliminated)
└── teams_end_game
```

## Span Lifecycle

### Player Spans

**Started:** At the beginning of `_game_loop()` after controller streaming begins

**Attributes:**
- `player.serial` - Controller serial number
- `player.team` - Team number (0 for FFA)
- `player.team_name` - Team name (Teams/RandomTeams only)
- `player.color` - RGB color tuple
- `game.mode` - Game mode (FFA, Teams, RandomTeams)

**Events:**
- `player_warning` - Triggered when acceleration exceeds warning threshold
  - Attributes: `accel_magnitude`, `threshold`, `team`
- `player_death` - Triggered when player dies
  - Attributes: `accel_magnitude`, `threshold`, `alive_count`, `team_eliminated` (team games)
- `player_survived` - Triggered when player survives to game end
  - Attributes: `game_duration`, `winner`, `team`

**Ended:**
- When player dies (in `_kill_player()`)
- When game ends (in `_end_game()` for survivors)

### Team Spans (Teams/RandomTeams only)

**Started:** At the beginning of `_game_loop()` before player spans

**Attributes:**
- `team.number` - Team number (0-7)
- `team.name` - Team name (Pink, Magenta, Orange, Yellow, Green, Turquoise, Blue, Purple)
- `team.color` - RGB color tuple
- `game.mode` - Game mode (Teams or RandomTeams)

**Events:**
- `team_eliminated` - Triggered when last player on team dies
  - Attributes: `last_player`, `alive_teams_count`
- `team_victory` - Triggered when team wins
  - Attributes: `game_duration`, `winner=true`
- `team_survived` - Triggered when team survives but doesn't win (multi-team edge case)
  - Attributes: `game_duration`, `winner=false`

**Ended:**
- When team is eliminated (all players dead)
- When game ends (in `_end_game()`)

## Context Propagation

### FFA Mode

Player spans are direct children of the `ffa_game_loop` span:

```python
# In _game_loop()
for serial, player in self.players.items():
    player_span = tracer.start_span(
        f"player_{serial}_lifecycle",
        attributes={...}
    )
    player.span = player_span
```

### Team Modes

Player spans are children of their team span using OpenTelemetry context:

```python
# In _game_loop()
# 1. Start team spans (children of game_loop)
for team_num, team in self.teams.items():
    team_span = tracer.start_span(...)
    team.span = team_span

# 2. Start player spans (children of team span)
for serial, player in self.players.items():
    team = self.teams[player.team]

    # Set context to make player span a child of team span
    from opentelemetry import context
    ctx = trace.set_span_in_context(team.span)

    player_span = tracer.start_span(
        f"player_{serial}_lifecycle",
        context=ctx,  # Parent is team span
        attributes={...}
    )
    player.span = player_span
```

## Querying in Jaeger

### Find all warnings for a specific player

```
service.name="game_coordinator"
  AND game.mode="Teams"
  AND player.serial="mock_controller_1"
```

Then look for `player_warning` events in the player's lifecycle span.

### Find all team eliminations

```
service.name="game_coordinator"
  AND team.eliminated=true
```

Or look for `team_eliminated` events in team lifecycle spans.

### Find games where a specific team won

```
service.name="game_coordinator"
  AND team.name="Pink"
  AND winner=true
```

### Analyze player performance

Filter by `player.serial` and look at:
- Number of `player_warning` events (how close to death)
- `player_death` event attributes (acceleration that killed them)
- `player_survived` event (if they won)

## Benefits

### Enhanced Observability

1. **Per-Player Insights:**
   - See exactly when each player triggered warnings
   - Track acceleration patterns leading to death
   - Identify which players are most/least careful

2. **Team Dynamics:**
   - Visualize team elimination order
   - See which teams lasted longest
   - Track team-level statistics

3. **Game Balance:**
   - Analyze death distribution across teams
   - Identify if team assignments are fair
   - Spot patterns in random team generation

4. **Performance Analysis:**
   - Measure game duration per player
   - Track warning-to-death ratios
   - Identify optimal sensitivity thresholds

### Debugging

1. **Death Detection Issues:**
   - See exact acceleration values at death
   - Compare against thresholds
   - Identify false positives/negatives

2. **Team Assignment Issues:**
   - Verify players are on correct teams
   - Trace team color assignments
   - Debug random assignment algorithms

3. **Event Ordering:**
   - Verify countdown → game start → deaths → winner
   - Ensure events fire in correct sequence
   - Spot race conditions

## Implementation Details

### Player Dataclass

```python
@dataclass
class Player:
    serial: str
    team: int
    alive: bool = True
    color: tuple = (255, 255, 255)
    last_accel_mag: float = 0.0
    span: Optional[trace.Span] = None  # NEW: Player lifecycle span
```

### Team Dataclass (Teams/RandomTeams)

```python
@dataclass
class Team:
    team_num: int
    name: str
    color: tuple
    span: Optional[trace.Span] = None  # NEW: Team lifecycle span
```

### Warning Detection

```python
async def _warn_player(self, serial: str, accel_mag: float):
    player = self.players.get(serial)
    if not player or not player.alive:
        return

    # Add warning event to player's lifecycle span
    if player.span:
        player.span.add_event(
            "player_warning",
            attributes={
                "accel_magnitude": accel_mag,
                "sensitivity": self.sensitivity.name,
                "team": player.team
            }
        )
```

### Death Handling

```python
async def _kill_player(self, serial: str, accel_mag: float):
    # ... death logic ...

    # Add death event to player's lifecycle span and end it
    if player.span:
        player.span.add_event(
            "player_death",
            attributes={
                "accel_magnitude": accel_mag,
                "sensitivity": self.sensitivity.name,
                "alive_count": alive_count,
                "team_eliminated": team_eliminated  # Teams only
            }
        )
        player.span.set_status(Status(StatusCode.OK, "Player died"))
        player.span.end()

    # If team eliminated, end team span (Teams only)
    if team_eliminated and team.span:
        team.span.add_event(
            "team_eliminated",
            attributes={"last_player": serial, "alive_teams_count": len(alive_teams)}
        )
        team.span.set_status(Status(StatusCode.OK, "Team eliminated"))
        team.span.end()
```

### Survival Handling

```python
async def _end_game(self):
    # Determine winning team (for team modes)
    alive_teams = self._get_alive_teams()
    winning_team_num = list(alive_teams)[0] if len(alive_teams) == 1 else None

    # End spans for surviving players
    for serial, player in self.players.items():
        if player.span and player.alive:
            is_winner = winning_team_num is not None and player.team == winning_team_num
            player.span.add_event(
                "player_survived",
                attributes={
                    "game_duration": time.time() - self.start_time,
                    "winner": is_winner,
                    "team": player.team
                }
            )
            player.span.set_status(Status(StatusCode.OK, "Player survived"))
            player.span.end()

    # End spans for surviving teams (Teams only)
    for team_num, team in self.teams.items():
        if team.span and team_num in alive_teams:
            is_winning_team = winning_team_num is not None and team_num == winning_team_num
            team.span.add_event(
                "team_victory" if is_winning_team else "team_survived",
                attributes={
                    "game_duration": time.time() - self.start_time,
                    "winner": is_winning_team
                }
            )
            team.span.set_status(Status(StatusCode.OK, "Team won" if is_winning_team else "Team survived"))
            team.span.end()
```

## Testing

All existing integration tests continue to work without modification. The per-player spans are created and ended automatically during game execution.

To verify spans are created correctly:

1. Run integration tests with OpenTelemetry collector
2. View traces in Jaeger UI
3. Look for player lifecycle spans nested under game_loop
4. Verify team → player hierarchy in team games
5. Check that span events contain expected attributes

## Future Enhancements

1. **Performance Metrics:**
   - Track average warning count per game
   - Measure time-to-death distributions
   - Analyze survival rates by team/position

2. **Advanced Analytics:**
   - Player skill ratings based on survival time
   - Team composition impact on win rate
   - Sensitivity tuning based on span data

3. **Real-time Monitoring:**
   - Alert on unusual death patterns
   - Track player rage-quit indicators
   - Monitor controller hardware issues

4. **Game Balance:**
   - Identify overpowered team positions
   - Detect unfair team assignments
   - Optimize starting positions

## Related Files

- `services/game_coordinator/games/ffa.py` - FFA implementation
- `services/game_coordinator/games/teams.py` - Teams implementation
- `services/game_coordinator/games/random_teams.py` - Random Teams implementation
- `services/game_coordinator/test_ffa_integration.py` - FFA tests
- `services/game_coordinator/test_teams_integration.py` - Teams tests
- `services/game_coordinator/test_random_teams_integration.py` - Random Teams tests
