# Phase 50: Game Mode-Specific Tracking

**Status**: 📋 PLANNED
**Priority**: High
**Estimated Effort**: 1 week
**Dependencies**: Phase 49 (Redis & Player Profiles)
**Blocks**: Phase 51 (Reward/Punishment Engine)

---

## Overview

Extend player profile tracking with game mode-specific metrics. Different game modes have different dynamics and meaningful metrics that should be tracked separately.

**Goals:**
- Track FFA-specific stats (survival time, placement distribution)
- Track Nonstop-specific stats (K/D ratio, kill streaks, deaths per minute)
- Track Team-specific stats (team coordination, role preference)
- Improve round result data with mode-specific fields
- Add mode-specific Prometheus metrics

---

## Why This Phase Matters

**Current limitation (Phase 49):** All games increment the same counters (`ffa_total_games`, `ffa_warnings`), even for non-FFA modes. No mode-specific performance tracking.

**After this phase:**
- Each game mode tracks its own relevant metrics
- Nonstop Joust tracks kills, deaths, K/D ratio
- Team modes track team performance and coordination
- FFA tracks survival time and placement history
- Better data for reward/punishment decisions (Phase 51)

---

## Game Mode Metrics

### FFA (Free-For-All)

**Focus:** Individual performance, survival skills

**Metrics to track:**
- `ffa_total_games` - Total FFA games played
- `ffa_wins` - Total FFA wins
- `ffa_warnings` - Cumulative warnings in FFA
- `ffa_avg_survival_time` - Average survival time in seconds
- `ffa_placement_history` - Last 10 placements (for trend analysis)

**Round result fields:**
- `survival_time` - How long player survived
- `placement` - 1st, 2nd, 3rd, etc.

### Nonstop Joust

**Focus:** Combat effectiveness, aggression, K/D ratio

**Metrics to track:**
- `nonstop_total_games` - Total Nonstop games played
- `nonstop_kills` - Total kills
- `nonstop_deaths` - Total deaths
- `nonstop_best_streak` - Best kill streak ever
- `nonstop_kd_ratio` - Calculated: kills / max(deaths, 1)
- `nonstop_avg_deaths_per_minute` - Deaths per minute average

**Round result fields:**
- `kills` - Kills this round
- `deaths` - Deaths this round
- `best_streak_this_round` - Best kill streak this round
- `deaths_per_minute` - Calculated from deaths and round duration

### Team Modes (Teams, Random Teams, Zombies)

**Focus:** Team performance, coordination

**Metrics to track:**
- `team_total_games` - Total team games played
- `team_wins` - Total team wins
- `team_preferred_role` - "aggressive", "defensive", "balanced"
- `team_coordination_score` - 0-100 score for teamwork
- `team_simultaneous_kills` - Times team got multiple kills at once

**Round result fields:**
- `team_num` - Which team player was on
- `team_won` - Whether player's team won
- `team_eliminations` - How many enemies eliminated
- `coordination_events` - Simultaneous kills, assists

---

## Data Model Changes

### Extended PlayerProfile

```python
@dataclass
class PlayerProfile:
    """Persistent player profile (Phase 49 + Phase 50 extensions)."""

    serial: str
    first_seen: float
    last_seen: float
    session_id: str

    # FFA stats (Phase 50 - enhanced)
    ffa_total_games: int = 0
    ffa_wins: int = 0
    ffa_warnings: int = 0
    ffa_avg_survival_time: float = 0.0
    ffa_placement_history: list[int] = field(default_factory=list)  # Last 10 placements

    # Nonstop stats (Phase 50 - NEW)
    nonstop_total_games: int = 0
    nonstop_kills: int = 0
    nonstop_deaths: int = 0
    nonstop_best_streak: int = 0
    nonstop_kd_ratio: float = 0.0  # Calculated field
    nonstop_avg_deaths_per_minute: float = 0.0

    # Team stats (Phase 50 - enhanced)
    team_total_games: int = 0
    team_wins: int = 0
    team_preferred_role: str = "balanced"  # aggressive, defensive, balanced
    team_coordination_score: float = 50.0  # 0-100
    team_simultaneous_kills: int = 0

    # Hardware/connection (unchanged from Phase 49)
    average_battery_level: float = 5.0
    connection_stability_score: float = 1.0
    total_disconnects: int = 0

    # Performance score (unchanged from Phase 49)
    performance_score: float = 100.0
    reward_tier: str = "NEUTRAL"

    # Config overrides (for Phase 51)
    config_overrides: dict[str, Any] = field(default_factory=dict)

    def calculate_nonstop_kd_ratio(self) -> float:
        """Calculate K/D ratio for Nonstop mode."""
        if self.nonstop_deaths == 0:
            return float(self.nonstop_kills)
        return self.nonstop_kills / self.nonstop_deaths

    def update_ffa_placement(self, placement: int) -> None:
        """Add placement to history (keep last 10)."""
        self.ffa_placement_history.append(placement)
        if len(self.ffa_placement_history) > 10:
            self.ffa_placement_history.pop(0)

    def determine_team_role(self) -> str:
        """Determine player's team role based on stats."""
        # Simple heuristic - will improve in Phase 51
        if self.team_total_games < 3:
            return "balanced"

        # Placeholder logic - Phase 51 will improve this
        if self.team_simultaneous_kills > self.team_total_games:
            return "aggressive"
        else:
            return "defensive"
```

### Enhanced RoundResult

```python
@dataclass
class RoundResult:
    """Round result with mode-specific fields (Phase 49 + Phase 50)."""

    # Universal fields (Phase 49)
    round_id: str
    game_mode: str
    timestamp: float
    placement: int
    won: bool
    warnings: int

    # FFA-specific (Phase 50)
    survival_time: Optional[float] = None  # Seconds survived

    # Nonstop-specific (Phase 50)
    kills: Optional[int] = None
    deaths: Optional[int] = None
    best_streak_this_round: Optional[int] = None
    deaths_per_minute: Optional[float] = None

    # Team-specific (Phase 50)
    team_num: Optional[int] = None
    team_won: Optional[bool] = None
    team_eliminations: Optional[int] = None
    coordination_events: Optional[int] = None

    # Context (unchanged)
    total_players: int
    round_duration: float
    sensitivity_mode: str
    update_frequency_hz: int
```

---

## Implementation Tasks

### Task 1: Update FFA Mode

**File**: `services/game_coordinator/games/ffa.py`

**Changes:**

1. Track survival time per player:
```python
class FFAGame(BaseGameMode):

    def __init__(self, ...):
        super().__init__(...)
        self.player_death_times = {}  # serial -> timestamp

    async def _kill_player_impl(self, serial: str, accel_mag: float):
        """FFA-specific death handling with survival tracking."""

        player = self.players.get(serial)
        if not player or not player.alive:
            return

        # Record death time
        death_time = time.time()
        self.player_death_times[serial] = death_time

        # Calculate survival time
        if self.start_time:
            survival_time = death_time - self.start_time
        else:
            survival_time = 0.0

        logger.info(f"Player {serial} died after {survival_time:.1f}s")

        # Mark as dead
        player.alive = False

        # ... existing death handling (rainbow effect, etc.)
```

2. Calculate placement correctly:
```python
def _calculate_placement(self, serial: str) -> int:
    """
    Calculate FFA placement based on elimination order.

    1st = Last player standing
    2nd = Second-to-last eliminated
    etc.
    """

    if serial not in self.player_death_times:
        # Still alive - winner
        return 1

    # Sort by death time (earliest death = worst placement)
    death_times = sorted(
        self.player_death_times.items(),
        key=lambda x: x[1]
    )

    # Find player's position in death order
    for i, (player_serial, _) in enumerate(death_times):
        if player_serial == serial:
            # Position in death order + 1 (since winner is not in death_times)
            return len(self.players) - i

    return len(self.players)  # Fallback
```

3. Update round result in `_end_game_impl()`:
```python
async def _end_game_impl(self):
    """Enhanced with FFA-specific stats."""

    winner_serial = self._determine_winner()

    for serial, player in self.players.items():
        # Calculate survival time
        if serial in self.player_death_times:
            survival_time = self.player_death_times[serial] - self.start_time
        else:
            # Winner - survived entire round
            survival_time = time.time() - self.start_time

        placement = self._calculate_placement(serial)

        result = RoundResult(
            round_id=self.game_id,
            game_mode="FFA",
            timestamp=time.time(),
            placement=placement,
            won=(serial == winner_serial),
            warnings=player.warnings_this_round,
            survival_time=survival_time,  # FFA-specific
            total_players=len(self.players),
            round_duration=time.time() - self.start_time,
            sensitivity_mode=self.sensitivity.name,
            update_frequency_hz=get_config_manager().get_config().update_frequency_hz,
        )

        # Save to history
        await self.profile_manager.add_round_result(serial, result)

        # Update FFA-specific profile stats
        player.profile.ffa_total_games += 1
        if result.won:
            player.profile.ffa_wins += 1

        # Update average survival time
        old_avg = player.profile.ffa_avg_survival_time
        total_games = player.profile.ffa_total_games
        player.profile.ffa_avg_survival_time = (
            (old_avg * (total_games - 1) + survival_time) / total_games
        )

        # Update placement history
        player.profile.update_ffa_placement(placement)

        # Recalculate performance score
        player.profile.performance_score = await self.profile_manager.calculate_performance_score(serial)

        await self.profile_manager.update_profile(player.profile)

        logger.info(
            f"FFA result for {serial}: "
            f"placement={placement}, survived={survival_time:.1f}s, "
            f"avg_survival={player.profile.ffa_avg_survival_time:.1f}s"
        )
```

### Task 2: Update Nonstop Joust Mode

**File**: `services/game_coordinator/games/nonstop_joust.py`

**Changes:**

1. Track kills and streaks:
```python
@dataclass
class NonstopPlayer(Player):
    """Nonstop-specific player state."""

    # Round-specific counters
    kills_this_round: int = 0
    deaths_this_round: int = 0
    current_streak: int = 0
    best_streak_this_round: int = 0

    # Profile reference (from Phase 49)
    profile: PlayerProfile = None
```

2. Update kill tracking:
```python
async def _handle_kill(self, killer_serial: str, victim_serial: str):
    """Track kill for killer."""

    killer = self.players.get(killer_serial)
    if not killer:
        return

    # Increment kill count
    killer.kills_this_round += 1
    killer.current_streak += 1

    # Update best streak
    if killer.current_streak > killer.best_streak_this_round:
        killer.best_streak_this_round = killer.current_streak

    logger.info(
        f"Player {killer_serial} killed {victim_serial}: "
        f"kills={killer.kills_this_round}, streak={killer.current_streak}"
    )

    # Emit metric
    from services.game_coordinator import metrics
    metrics.nonstop_kills_total.labels(serial=killer_serial).inc()
```

3. Update death tracking:
```python
async def _kill_player_impl(self, serial: str, accel_mag: float):
    """Nonstop-specific death handling."""

    player = self.players.get(serial)
    if not player or not player.alive:
        return

    # Increment death count
    player.deaths_this_round += 1

    # Reset streak
    player.current_streak = 0

    # Mark as dead (will respawn after timer)
    player.alive = False
    player.respawn_timer = self.RESPAWN_DURATION

    logger.info(f"Player {serial} died: deaths={player.deaths_this_round}")

    # Emit metric
    from services.game_coordinator import metrics
    metrics.nonstop_deaths_total.labels(serial=serial).inc()

    # ... existing respawn logic ...
```

4. Calculate K/D and deaths per minute in `_end_game_impl()`:
```python
async def _end_game_impl(self):
    """Enhanced with Nonstop-specific stats."""

    round_duration = time.time() - self.start_time
    duration_minutes = round_duration / 60.0

    for serial, player in self.players.items():
        # Calculate deaths per minute
        deaths_per_minute = player.deaths_this_round / max(duration_minutes, 0.1)

        result = RoundResult(
            round_id=self.game_id,
            game_mode="Nonstop",
            timestamp=time.time(),
            placement=self._calculate_placement_by_score(serial),
            won=(serial == self._determine_winner()),
            warnings=player.warnings_this_round,
            kills=player.kills_this_round,  # Nonstop-specific
            deaths=player.deaths_this_round,  # Nonstop-specific
            best_streak_this_round=player.best_streak_this_round,  # Nonstop-specific
            deaths_per_minute=deaths_per_minute,  # Nonstop-specific
            total_players=len(self.players),
            round_duration=round_duration,
            sensitivity_mode=self.sensitivity.name,
            update_frequency_hz=get_config_manager().get_config().update_frequency_hz,
        )

        # Save to history
        await self.profile_manager.add_round_result(serial, result)

        # Update Nonstop-specific profile stats
        player.profile.nonstop_total_games += 1
        player.profile.nonstop_kills += player.kills_this_round
        player.profile.nonstop_deaths += player.deaths_this_round

        # Update best streak
        if player.best_streak_this_round > player.profile.nonstop_best_streak:
            player.profile.nonstop_best_streak = player.best_streak_this_round

        # Update K/D ratio
        player.profile.nonstop_kd_ratio = player.profile.calculate_nonstop_kd_ratio()

        # Update avg deaths per minute
        old_avg = player.profile.nonstop_avg_deaths_per_minute
        total_games = player.profile.nonstop_total_games
        player.profile.nonstop_avg_deaths_per_minute = (
            (old_avg * (total_games - 1) + deaths_per_minute) / total_games
        )

        await self.profile_manager.update_profile(player.profile)

        logger.info(
            f"Nonstop result for {serial}: "
            f"K/D={player.kills_this_round}/{player.deaths_this_round}, "
            f"lifetime K/D={player.profile.nonstop_kd_ratio:.2f}, "
            f"streak={player.best_streak_this_round}"
        )
```

### Task 3: Update Team Modes

**File**: `services/game_coordinator/games/teams_base.py`

**Changes:**

1. Track team coordination events:
```python
class TeamsBase(BaseGameMode):

    def __init__(self, ...):
        super().__init__(...)
        self.last_kill_times = {}  # team_num -> timestamp
        self.simultaneous_kill_window = 2.0  # seconds

    async def _check_simultaneous_kills(self, team_num: int):
        """Check if multiple team members got kills simultaneously."""

        current_time = time.time()

        # Record this kill time
        if team_num not in self.last_kill_times:
            self.last_kill_times[team_num] = []

        self.last_kill_times[team_num].append(current_time)

        # Remove old kills (outside window)
        self.last_kill_times[team_num] = [
            t for t in self.last_kill_times[team_num]
            if current_time - t < self.simultaneous_kill_window
        ]

        # Check if multiple kills in window
        if len(self.last_kill_times[team_num]) >= 2:
            logger.info(f"Team {team_num} coordination event: {len(self.last_kill_times[team_num])} simultaneous kills")
            return len(self.last_kill_times[team_num])

        return 0
```

2. Update round results with team stats:
```python
async def _end_game_impl(self):
    """Enhanced with team-specific stats."""

    winning_team = self._determine_winning_team()

    for serial, player in self.players.items():
        team_won = (player.team == winning_team)

        # Count team eliminations (enemies killed by team)
        team_eliminations = self._count_team_eliminations(player.team)

        # Count coordination events
        coordination_events = len(self.last_kill_times.get(player.team, []))

        result = RoundResult(
            round_id=self.game_id,
            game_mode=self.get_game_name(),
            timestamp=time.time(),
            placement=1 if team_won else 2,
            won=team_won,
            warnings=player.warnings_this_round,
            team_num=player.team,  # Team-specific
            team_won=team_won,  # Team-specific
            team_eliminations=team_eliminations,  # Team-specific
            coordination_events=coordination_events,  # Team-specific
            total_players=len(self.players),
            round_duration=time.time() - self.start_time,
            sensitivity_mode=self.sensitivity.name,
            update_frequency_hz=get_config_manager().get_config().update_frequency_hz,
        )

        # Save to history
        await self.profile_manager.add_round_result(serial, result)

        # Update team-specific profile stats
        player.profile.team_total_games += 1
        if team_won:
            player.profile.team_wins += 1

        if coordination_events > 0:
            player.profile.team_simultaneous_kills += coordination_events

        # Update coordination score (simple formula - will improve in Phase 51)
        if player.profile.team_total_games > 0:
            win_rate = player.profile.team_wins / player.profile.team_total_games
            player.profile.team_coordination_score = win_rate * 100.0

        # Determine role preference
        player.profile.team_preferred_role = player.profile.determine_team_role()

        await self.profile_manager.update_profile(player.profile)

        logger.info(
            f"Team result for {serial}: "
            f"team={player.team}, won={team_won}, "
            f"coordination_score={player.profile.team_coordination_score:.1f}"
        )
```

### Task 4: Add Mode-Specific Metrics

**File**: `services/game_coordinator/metrics.py`

```python
# FFA-specific metrics
ffa_survival_time_seconds = Histogram(
    'ffa_survival_time_seconds',
    'Survival time in FFA mode',
    ['serial'],
    buckets=[10, 30, 60, 90, 120, 180, 300]
)

ffa_placement = Histogram(
    'ffa_placement',
    'FFA placement distribution',
    ['serial'],
    buckets=[1, 2, 3, 4, 5, 10, 15, 20, 25]
)

# Nonstop-specific metrics
nonstop_kills_total = Counter(
    'nonstop_kills_total',
    'Total kills in Nonstop mode',
    ['serial']
)

nonstop_deaths_total = Counter(
    'nonstop_deaths_total',
    'Total deaths in Nonstop mode',
    ['serial']
)

nonstop_kd_ratio = Gauge(
    'nonstop_kd_ratio',
    'Kill/Death ratio in Nonstop mode',
    ['serial']
)

nonstop_streak_length = Histogram(
    'nonstop_streak_length',
    'Kill streak distribution',
    ['serial'],
    buckets=[1, 2, 3, 5, 7, 10, 15, 20]
)

nonstop_deaths_per_minute = Gauge(
    'nonstop_deaths_per_minute',
    'Deaths per minute in Nonstop mode',
    ['serial']
)

# Team-specific metrics
team_wins_total = Counter(
    'team_wins_total',
    'Total team wins',
    ['team_num', 'game_mode']
)

team_coordination_score = Gauge(
    'team_coordination_score',
    'Team coordination score (0-100)',
    ['team_num']
)

team_simultaneous_kills_total = Counter(
    'team_simultaneous_kills_total',
    'Simultaneous team kills',
    ['team_num']
)

player_team_role = Gauge(
    'player_team_role',
    'Player team role (0=defensive, 1=balanced, 2=aggressive)',
    ['serial']
)
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/unit/games/test_ffa_tracking.py`
```python
def test_ffa_survival_time_calculation():
    """Test FFA survival time tracking."""
    # Create game, start, kill players at different times
    # Verify survival times calculated correctly

def test_ffa_placement_calculation():
    """Test FFA placement based on elimination order."""
    # Kill players in specific order
    # Verify placement: 1st=survivor, 2nd=last killed, etc.
```

**File**: `tests/unit/games/test_nonstop_tracking.py`
```python
def test_nonstop_kill_streak_tracking():
    """Test kill streak tracking."""
    # Record multiple kills without death
    # Verify streak increments
    # Record death
    # Verify streak resets

def test_nonstop_kd_ratio_calculation():
    """Test K/D ratio calculation."""
    # 10 kills, 5 deaths → K/D = 2.0
    # 5 kills, 0 deaths → K/D = 5.0
```

**File**: `tests/unit/games/test_team_tracking.py`
```python
def test_team_simultaneous_kills():
    """Test simultaneous kill detection."""
    # Record 2 kills within 2 seconds
    # Verify coordination event counted
    # Record kill 3 seconds later
    # Verify no coordination event
```

### Integration Tests

**File**: `tests/integration/test_game_mode_tracking.py`

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_ffa_complete_tracking():
    """Test complete FFA game with profile updates."""

    game = FFAGame(...)
    await game.run()

    # Verify winner has survival_time = full round
    winner_serial = game._determine_winner()
    history = await game.profile_manager.get_round_history(winner_serial, 1)

    assert history[0].game_mode == "FFA"
    assert history[0].placement == 1
    assert history[0].survival_time > 100  # Survived entire round


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nonstop_kd_tracking():
    """Test Nonstop K/D ratio updates."""

    game = NonstopJoustGame(...)
    await game.run()

    # Check K/D ratios calculated
    for serial, player in game.players.items():
        profile = player.profile
        expected_kd = profile.nonstop_kills / max(profile.nonstop_deaths, 1)
        assert abs(profile.nonstop_kd_ratio - expected_kd) < 0.01
```

### Manual Testing Checklist

**FFA Mode:**
- [ ] Play FFA game
- [ ] Check survival times logged correctly
- [ ] Verify placement: winner=1st, last killed=2nd, etc.
- [ ] Check `ffa_avg_survival_time` updated in profile
- [ ] Verify metrics: `ffa_survival_time_seconds`, `ffa_placement`

**Nonstop Mode:**
- [ ] Play Nonstop game
- [ ] Get kill streak of 5+
- [ ] Verify `best_streak_this_round` recorded
- [ ] Check K/D ratio calculated correctly
- [ ] Verify metrics: `nonstop_kd_ratio`, `nonstop_streak_length`

**Team Mode:**
- [ ] Play Teams game
- [ ] Coordinate kills within 2 seconds
- [ ] Verify coordination events counted
- [ ] Check winning team updates team_wins
- [ ] Verify metrics: `team_coordination_score`, `team_simultaneous_kills_total`

---

## Files to Modify

- `services/game_coordinator/games/ffa.py` - Add survival tracking, placement calculation
- `services/game_coordinator/games/nonstop_joust.py` - Add K/D tracking, streak tracking
- `services/game_coordinator/games/teams_base.py` - Add coordination tracking
- `services/game_coordinator/models/player.py` - Extend PlayerProfile with mode stats
- `services/game_coordinator/metrics.py` - Add mode-specific metrics
- `services/game_coordinator/storage/player_profiles.py` - Update save/load for new fields

---

## Success Criteria

- [ ] FFA tracks survival time per player
- [ ] FFA calculates placement correctly (1st=survivor, etc.)
- [ ] Nonstop tracks kills, deaths, K/D ratio
- [ ] Nonstop tracks kill streaks correctly
- [ ] Team modes track coordination events
- [ ] All mode-specific stats save to Redis
- [ ] Mode-specific metrics visible in Grafana
- [ ] Round results include mode-specific fields
- [ ] Profile average calculations work correctly
- [ ] Unit tests pass (>85% coverage)
- [ ] Integration tests pass
- [ ] No performance regression

---

## Next Phase

**Phase 51: Reward/Punishment Engine** will use these mode-specific stats to:
- Reward high K/D players in Nonstop with enhanced feedback
- Reward consistent FFA winners with easier thresholds
- Reward coordinated team play with visual effects
- Punish poor performers appropriately per mode

**Dependencies**: Requires Phase 50 to track the stats that reward/punishment decisions are based on.

---

**End of Phase 50**
