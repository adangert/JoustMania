# Phase 49: Redis Storage & Player Profiles

**Status**: 📋 PLANNED
**Priority**: High (Foundational)
**Estimated Effort**: 1 week
**Dependencies**: None
**Blocks**: Phase 50, 51, 52

---

## Overview

Implement persistent player profile storage using Redis to track player performance across game sessions. This is the foundation for the reward/punishment system and experimentation framework.

**Goals:**
- Add Redis for persistent storage
- Implement PlayerProfile data model
- Create PlayerProfileManager for CRUD operations
- Track cumulative stats per game mode
- Integrate profile loading/saving into game lifecycle

---

## Why This Phase Matters

**Current limitation:** Player stats (warnings, wins, performance) are lost after each game. No way to track trends or reward consistent performance.

**After this phase:**
- Player profiles persist across sessions
- Cumulative warnings tracked per game mode
- Round history stored (last 100 rounds per player)
- Battery and connection quality tracked over time
- Foundation for reward/punishment decisions

---

## Data Models

### PlayerProfile

```python
@dataclass
class PlayerProfile:
    """Persistent player profile across games/rounds."""

    serial: str
    first_seen: float
    last_seen: float
    session_id: str

    # FFA stats
    ffa_total_games: int = 0
    ffa_wins: int = 0
    ffa_warnings: int = 0
    ffa_avg_survival_time: float = 0.0

    # Nonstop stats
    nonstop_total_games: int = 0
    nonstop_kills: int = 0
    nonstop_deaths: int = 0
    nonstop_best_streak: int = 0

    # Team stats
    team_total_games: int = 0
    team_wins: int = 0

    # Hardware/connection
    average_battery_level: float = 5.0
    connection_stability_score: float = 1.0
    total_disconnects: int = 0

    # Performance score (0-100)
    performance_score: float = 100.0
    reward_tier: str = "NEUTRAL"
```

### RoundResult

```python
@dataclass
class RoundResult:
    """Result of a single game round."""

    round_id: str
    game_mode: str
    timestamp: float
    placement: int
    won: bool
    warnings: int

    # Mode-specific (optional)
    deaths: Optional[int] = None
    kills: Optional[int] = None
    team_num: Optional[int] = None
    survival_time: Optional[float] = None

    # Context
    total_players: int
    round_duration: float
    sensitivity_mode: str
    update_frequency_hz: int
```

---

## Redis Schema

### Key Patterns

```
player:{serial}:profile          → PlayerProfile JSON (hash)
player:{serial}:history          → List of RoundResult JSONs (list, max 100)
session:{session_id}:players     → Set of active player serials (set)
stats:total_profiles             → Count of total profiles (string)
```

### TTL Strategy

- **Profiles**: No TTL (persist indefinitely)
- **History**: No TTL, but limit to 100 most recent rounds per player
- **Session sets**: TTL 1 hour (cleanup after games end)

---

## Implementation Tasks

### Task 1: Redis Client Wrapper

**File**: `services/game_coordinator/storage/redis_client.py`

**Methods:**
- `connect()` - Connect to Redis
- `get_hash(key)` - Get hash value
- `set_hash(key, data)` - Set hash value
- `get_list(key, start, end)` - Get list range
- `push_list(key, value, max_length)` - Push to list (FIFO)
- `add_to_set(key, *values)` - Add to set
- `get_set(key)` - Get set members

### Task 2: PlayerProfileManager

**File**: `services/game_coordinator/storage/player_profiles.py`

**Methods:**
- `get_or_create_profile(serial, session_id)` - Load or create profile
- `update_profile(profile)` - Save profile to Redis
- `add_round_result(serial, result)` - Add round to history
- `get_round_history(serial, limit)` - Get recent rounds
- `calculate_performance_score(serial)` - Compute 0-100 score
- `get_all_active_profiles(session_id)` - Get session profiles
- `add_to_session(session_id, serial)` - Track active session

**Performance Score Formula:**
```
score = 100.0
score -= (total_warnings / 5.0)           # -1 per 5 warnings
score += (total_wins * 2.0)                # +2 per win
score -= (total_disconnects * 3.0)        # -3 per disconnect
score += 5.0 if battery > 4.0 else 0      # +5 for good battery
score -= 10.0 if battery < 2.0 else 0     # -10 for poor battery
score -= 5.0 if connection < 0.7 else 0   # -5 for poor connection
return max(0.0, min(100.0, score))
```

### Task 3: Integrate into BaseGameMode

**File**: `services/game_coordinator/games/base.py`

**Changes:**

1. Add profile manager in `__init__()`:
```python
self.profile_manager = PlayerProfileManager()
self.session_id = f"{self.game_id}_session"
```

2. Load profiles in `_initialize_players_impl()`:
```python
for controller in controllers:
    profile = await self.profile_manager.get_or_create_profile(
        controller.serial, self.session_id
    )
    player = EnhancedPlayer(
        serial=controller.serial,
        profile=profile,
        current_battery=controller.battery
    )
    self.players[controller.serial] = player
```

3. Track warnings cumulatively in `_warn_player()`:
```python
player.warnings_this_round += 1
player.profile.ffa_warnings += 1  # Cumulative
```

4. Save round results in `_end_game_impl()`:
```python
for serial, player in self.players.items():
    result = RoundResult(
        round_id=self.game_id,
        game_mode=self.get_game_name(),
        won=(serial == winner_serial),
        warnings=player.warnings_this_round,
        # ... other fields
    )
    await self.profile_manager.add_round_result(serial, result)

    player.profile.ffa_total_games += 1
    if result.won:
        player.profile.ffa_wins += 1

    player.profile.performance_score = await self.profile_manager.calculate_performance_score(serial)
    await self.profile_manager.update_profile(player.profile)
```

### Task 4: Add Prometheus Metrics

**File**: `services/game_coordinator/metrics.py`

**New metrics:**
```python
player_warnings_total = Counter(
    'player_warnings_total',
    'Total warnings per player',
    ['serial', 'game_mode']
)

player_wins_total = Counter(
    'player_wins_total',
    'Total wins per player',
    ['serial', 'game_mode']
)

player_performance_score = Gauge(
    'player_performance_score',
    'Performance score (0-100) per player',
    ['serial']
)

player_battery_level = Gauge(
    'player_battery_level',
    'Current battery level per player',
    ['serial']
)

player_connection_stability = Gauge(
    'player_connection_stability',
    'Connection stability score (0-1) per player',
    ['serial']
)

profiles_loaded_total = Counter(
    'profiles_loaded_total',
    'Total player profiles loaded from Redis'
)

profiles_created_total = Counter(
    'profiles_created_total',
    'Total new player profiles created'
)

profile_load_duration_seconds = Histogram(
    'profile_load_duration_seconds',
    'Time to load player profile from Redis',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1]
)
```

---

## Testing Strategy

### Unit Tests

**Files:**
- `tests/unit/storage/test_redis_client.py` - Redis wrapper
- `tests/unit/storage/test_player_profiles.py` - ProfileManager
- `tests/unit/models/test_player.py` - Data models

**Key tests:**
- Redis connection
- Profile creation and loading
- Round result storage
- Performance score calculation
- History retrieval with limits

### Integration Tests

**File**: `tests/integration/test_player_profiles_integration.py`

**Test scenarios:**
1. Full profile lifecycle (create, update, save, load)
2. Multiple round results accumulation
3. Performance score changes over multiple games
4. Profile persistence across service restarts

### Manual Testing Checklist

**Test 1: New Player Profile Creation**
- [ ] Start FFA game with 4 players
- [ ] Check logs for "Created new profile" messages
- [ ] Verify 4 profiles in Redis: `redis-cli KEYS "player:*:profile"`

**Test 2: Profile Loading on Second Game**
- [ ] Start another FFA game with same players
- [ ] Check logs for "Loaded profile" messages
- [ ] Verify `ffa_total_games` incremented: `redis-cli HGET player:XX:XX:XX:profile ffa_total_games`

**Test 3: Warning Tracking**
- [ ] Trigger warnings during gameplay
- [ ] Verify cumulative count: `redis-cli HGET player:XX:XX:XX:profile ffa_warnings`

**Test 4: Round History**
- [ ] Play 3 games
- [ ] Check history: `redis-cli LRANGE player:XX:XX:XX:history 0 -1`
- [ ] Verify 3 entries

**Test 5: Performance Score**
- [ ] Win 3 games in a row
- [ ] Check score: `redis-cli HGET player:XX:XX:XX:profile performance_score`
- [ ] Expect score > 100 (wins bonus)

**Test 6: Metrics in Grafana**
- [ ] Query `player_warnings_total`
- [ ] Query `player_performance_score`
- [ ] Verify per-player data visible

---

## Files to Create

```
services/game_coordinator/
├── storage/
│   ├── __init__.py
│   ├── redis_client.py          # Redis wrapper
│   └── player_profiles.py       # ProfileManager
└── models/
    ├── __init__.py
    └── player.py                 # PlayerProfile, RoundResult, EnhancedPlayer

tests/
├── unit/
│   ├── storage/
│   │   ├── test_redis_client.py
│   │   └── test_player_profiles.py
│   └── models/
│       └── test_player.py
└── integration/
    ├── test_player_profiles_integration.py
    └── test_game_with_profiles.py
```

## Files to Modify

- `services/game_coordinator/games/base.py` - Integrate profile loading/saving
- `services/game_coordinator/metrics.py` - Add player metrics
- `pyproject.toml` - Add redis dependency

---

## Dependencies

### Python Packages

```toml
[tool.poetry.dependencies]
redis = "^5.0.0"
```

### Docker Services

Redis already exists in `docker-compose.yml` - no changes needed.

---

## Success Criteria

- [ ] Redis client connects successfully
- [ ] New profiles created for first-time players
- [ ] Existing profiles loaded correctly
- [ ] Warnings tracked cumulatively
- [ ] Round history saved (up to 100 rounds per player)
- [ ] Performance scores calculated correctly
- [ ] Profiles persist across game restarts
- [ ] Metrics emitted to Prometheus
- [ ] Unit tests pass (>85% coverage)
- [ ] Integration tests pass
- [ ] Profile load <10ms (p95)
- [ ] Profile save <20ms (p95)
- [ ] No game loop impact (<1ms overhead)

---

## Next Phase

**Phase 50: Game Mode-Specific Tracking** will build on this foundation to add:
- Mode-specific stats (FFA survival time, Nonstop K/D, Team coordination)
- Improved placement calculation per game mode
- Mode-specific metrics

**Dependencies**: Requires Phase 49 to be complete and stable.

---

**End of Phase 49**
