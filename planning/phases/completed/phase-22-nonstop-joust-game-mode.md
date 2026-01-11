# Phase 22: Nonstop Joust Game Mode

**Status:** ✅ COMPLETE
**Date Completed:** 2026-01-10
**Commit:** 180f4ad
**Priority:** MEDIUM

## Goal
Add endless respawn game mode for continuous action gameplay

## Motivation
- Current game modes end when players die
- Players want an action-packed mode without downtime
- Great for parties - no waiting between rounds
- Enables kill-based scoring and leaderboards

## Game Design

**Core Mechanics:**
- Players respawn 3 seconds after death
- Game never ends naturally (time-based or manual stop)
- Score tracking: kills, deaths, kill streaks
- Optional time limit (5min, 10min, 15min, unlimited)
- Winner: highest score when time expires OR admin stops game

**Respawn System:**
- Death: Same feedback as FFA (red LED + vibration)
- Respawn countdown (3s): Gray → Yellow → Green LED colors
- Spawn protection: 2 seconds invulnerability after respawn
  - White pulsing glow during protection
  - Cannot die during protection
  - Can kill others (but discouraged by game design)
- Respawn location: Random (prevent spawn camping)

**Scoring:**
- +1 point per kill
- Track deaths (for K/D ratio)
- Track longest kill streak
- Bonus points for kill streaks (3+ kills without dying)
- Leaderboard updated in real-time

**Victory Conditions:**
- Time limit expires → highest score wins
- Admin manually stops game → highest score wins
- Tie-breaker: fewest deaths, then longest kill streak

## Tasks Completed

- [x] Create game file structure
  - [x] Create `services/game_coordinator/games/nonstop_joust.py` (689 lines)
  - [x] NonstopJoustGame class based on FFA structure
  - [x] Game state: IDLE → STARTING → RUNNING → ENDING → ENDED

- [x] Implement respawn system
  - [x] Track dead players with respawn timers (3.0 seconds)
  - [x] Respawn countdown with LED colors (Gray → Yellow → Green)
  - [x] Spawn protection (2s invulnerability, white LED)
  - [ ] Random respawn position logic (not needed - accelerometer based)

- [x] Implement scoring system
  - [x] Player stats: deaths, score (simplified from original plan)
  - [x] Score formula: 100 - (deaths × 10), minimum 0
  - [ ] Kill tracking (not applicable - no direct kill attribution in accelerometer game)
  - [ ] Streak bonuses (future enhancement)
  - [x] Score calculated at game end

- [x] Implement victory conditions
  - [x] Optional time limit (nonstop_time_limit setting, 0 = unlimited)
  - [x] Manual stop support (force_end/game stop)
  - [x] Determine winner by highest score
  - [x] Tie-breaking: fewest deaths

- [x] Controller feedback
  - [x] Respawn countdown colors with span events
  - [x] Spawn protection white LED (pulse effect future enhancement)
  - [x] Death warning (orange flash + 100 intensity vibration)
  - [x] Death notification (red LED + 255 intensity vibration)
  - [x] Victory (rainbow effect on winner, 3s)

- [x] Integration
  - [x] Add "NonstopJoust" to Game Coordinator game registry
  - [x] Add to Menu service game list (completed in Phase 21)
  - [x] Settings support: nonstop_time_limit
  - [ ] Test with multiple players (requires hardware)

- [x] OpenTelemetry Instrumentation
  - [x] Comprehensive span attributes (game settings, duration, stats)
  - [x] Periodic progress events (every 30s)
  - [x] Player lifecycle spans
  - [x] Game events (death, respawn, warning, victory)

- [ ] Optional enhancements (future phases)
  - [ ] Power-ups (speed boost, shield, double damage)
  - [ ] Zone control (king of the hill variant)
  - [ ] Team mode (Team Nonstop Joust)

## Implementation Details

```python
# services/game_coordinator/games/nonstop_joust.py

@dataclass
class NonstopPlayer(Player):
    """Extended player with respawn and scoring."""
    kills: int = 0
    deaths: int = 0
    current_streak: int = 0
    best_streak: int = 0
    score: int = 0

    # Respawn state
    respawn_timer: float = 0.0  # Time until respawn
    spawn_protected: bool = False
    spawn_protection_end: float = 0.0

class NonstopJoustGame:
    """Endless respawn game mode."""

    async def _game_loop(self):
        """Main game loop with respawn handling."""
        while self.running:
            # Process controller states
            async for state_update in controller_stream:
                for controller_state in state_update.controllers:
                    await self._process_controller_state(controller_state)

                # Update respawn timers
                await self._update_respawn_timers()

                # Check time limit
                if self._check_time_limit():
                    break

    async def _kill_player(self, serial: str, accel_mag: float):
        """Kill player and start respawn timer."""
        player = self.players[serial]
        player.alive = False
        player.deaths += 1
        player.current_streak = 0
        player.respawn_timer = 3.0  # 3 second respawn

        # Award kill to nearest player? Or track separately
        # (Implementation detail - may need kill attribution)

        # Standard death feedback
        await self._send_death_feedback(serial)

        # Publish death event
        self.event_publisher("player_death", {
            "serial": serial,
            "kills": player.kills,
            "deaths": player.deaths
        })

    async def _update_respawn_timers(self):
        """Update respawn timers and respawn players."""
        current_time = time.time()

        for serial, player in self.players.items():
            if not player.alive and player.respawn_timer > 0:
                player.respawn_timer -= (1.0 / UPDATE_FREQUENCY)

                # Show respawn countdown colors
                await self._show_respawn_countdown(serial, player.respawn_timer)

                # Respawn when timer reaches 0
                if player.respawn_timer <= 0:
                    await self._respawn_player(serial)

            # Check spawn protection expiration
            if player.spawn_protected and current_time >= player.spawn_protection_end:
                player.spawn_protected = False
                # Return to normal color
                await self._set_normal_color(serial)

    async def _respawn_player(self, serial: str):
        """Respawn a dead player."""
        player = self.players[serial]
        player.alive = True
        player.spawn_protected = True
        player.spawn_protection_end = time.time() + 2.0  # 2s protection

        # White pulse effect during protection
        await self._show_spawn_protection(serial)

        span.add_event("player_respawned", {
            "serial": serial,
            "kills": player.kills,
            "deaths": player.deaths
        })

        self.event_publisher("player_respawned", {
            "serial": serial
        })
```

## Expected Improvements
- Continuous action gameplay without downtime
- Kill-based competition with leaderboards
- Great for parties and quick play sessions
- Foundation for future competitive modes

## Raspberry Pi Impact
- Same performance as FFA mode (~60 FPS)
- Respawn timers add minimal overhead (<1ms per player)
- Score tracking negligible CPU impact

## Success Criteria
- Players respawn 3 seconds after death
- Spawn protection prevents immediate re-death
- Time limit works correctly (or unlimited mode)
- Winner determined by highest score
- Controller feedback works (death, respawn, victory)
