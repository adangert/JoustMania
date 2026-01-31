# Game Modes Reference

All game modes in `services/game_coordinator/games/`.

## Solo/FFA Modes

### FFA (Free-For-All)
**File:** `ffa.py` | **Class:** `FFAGame`

Last player standing wins. All players compete individually.
- No teams (everyone on team=0)
- Unique colors per player
- Death is permanent

### Nonstop Joust
**File:** `nonstop_joust.py` | **Class:** `NonstopJoustGame`

Endless respawn with scoring. Compete for highest score.
- Respawn after 3 seconds
- 2 seconds spawn protection
- Time-limited (configurable via `time_limit_seconds`, 0=unlimited)
- Tracks kills, deaths, streaks

**Config:** `NonstopConfig { time_limit_seconds }`

## Team Modes

### Teams (Simple)
**File:** `teams.py` | **Class:** `SimpleTeamsGame`

Teams compete, last team standing wins.
- Round-robin team assignment
- Team colors assigned at start

**Config:** `TeamsConfig { num_teams, random_assignment }`

### Random Teams
**File:** `random_teams.py` | **Class:** `RandomTeamsGame`

Like Teams but with random assignment.
- 5 second team formation phase
- Colors pulsed during formation

**Config:** `TeamsConfig { num_teams, random_assignment }`

### Swapper
**File:** `swapper.py` | **Class:** `SwapperGame`

Switch teams when you die instead of elimination.
- Always 2 teams
- 2 second grace period after swap
- Ends when all on same team
- Last swapper excluded from winners

## Hidden Role Modes

### Werewolf
**File:** `werewolf.py` | **Class:** `WerewolfGame`

~44% are secret werewolves, revealed after configurable time.
- All start yellow (human color)
- Werewolves get rumble signal during countdown
- Werewolves turn blue at reveal
- Werewolves have higher death thresholds

**Config:** `WerewolfConfig { reveal_time_seconds }` (default: 35s)

### Traitor
**File:** `traitor.py` | **Class:** `TraitorGame`

Team game with secret traitors.
- Traitor count scales with players (1-3+)
- Traitors appear as their team but win with enemy
- Traitors get rumble signal

**Config:** `TraitorConfig { num_teams }`

### Zombie
**File:** `zombie.py` | **Class:** `ZombieGame`

Humans vs Zombies. Killed humans become zombies.
- Starts with 2 zombies
- Zombies respawn after 2-10 seconds
- Zombies have higher thresholds (harder to kill)
- Time-limited (~3-7 min based on player count)
- Humans win if time expires

## Tournament Modes

### Fight Club
**File:** `fight_club.py` | **Class:** `FightClubGame`

1v1 arena with queue system.
- 22 second rounds, configurable invincibility
- Defender (red) vs Challenger (green)
- Winner stays, loser goes to back of queue
- Configurable min rounds before game can end

**Config:** `FightClubConfig { invincibility_seconds, min_rounds }`

### Tournament
**File:** `tournament.py` | **Class:** `TournamentGame`

Single elimination bracket.
- 22 second matches, configurable invincibility
- Bracket with byes for non-power-of-2
- Red vs Blue, winner turns green
- Single champion wins

**Config:** `TournamentConfig { invincibility_seconds }`

## Modifying Game Modes

### Adding a New Mode

1. Create `services/game_coordinator/games/my_mode.py`
2. Extend `BaseGameMode` or `TeamsGameBase`
3. Register in `services/game_coordinator/games/__init__.py`
4. Add to `lib/types.py` `Games` enum
5. (Optional) Add config message to `proto/game_coordinator.proto`
6. Update `GameFactory._extract_mode_config()` if custom config needed
7. Update `MenuServicer._build_game_config()` to build the config

### Key Methods to Override

```python
class MyGame(BaseGameMode):
    def get_game_name(self) -> str:
        return "MyMode"

    async def _kill_player_impl(self, serial, accel_mag):
        # Custom death handling

    def _check_win_condition(self) -> bool:
        # Custom win logic

    def _get_death_thresholds(self):
        # Custom sensitivity thresholds
```

### Threshold Tuning

Thresholds in `base.py` (index 0-4 = ULTRA_SLOW to ULTRA_FAST):
```python
SLOW_WARNING = [1.2, 1.3, 1.6, 2.0, 2.5]  # Music slow
SLOW_MAX = [1.3, 1.5, 1.8, 2.5, 3.2]      # Death threshold
FAST_WARNING = [1.4, 1.5, 2.0, 2.8, 3.2]  # Music fast
FAST_MAX = [1.6, 1.8, 2.8, 3.2, 3.5]      # Death threshold
```

Zombie/Werewolf override in their files with higher thresholds.
