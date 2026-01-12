# Phase 52: Flag-Based Gameplay Adjustments

**Status**: 📋 PLANNED
**Priority**: High
**Estimated Effort**: 3-5 days
**Dependencies**: Phase 49 (Profiles), Phase 50 (Mode Tracking), Phase 51 (Flagd)
**Blocks**: None (enables dynamic gameplay tuning)

---

## Overview

Integrate flagd flag evaluation into the game loop to enable dynamic gameplay adjustments based on player performance. Instead of building a custom "reward/punishment engine", use flagd's targeting rules with player context to determine adjustments.

**Goals:**
- Evaluate flags with player context (win_rate, warnings_per_game, K/D, battery)
- Apply flag-returned adjustments to gameplay parameters
- Support per-player, per-mode, and per-game adjustments
- Enable A/B testing of reward strategies
- No hardcoded reward logic - everything via flags

---

## Why This Phase Matters

**Key insight:** Flagd's JSONLogic targeting can handle all reward/punishment logic without custom Python code.

**Instead of:**
```python
class RewardPunishmentEngine:
    def evaluate_rules(self, profile):
        if profile.ffa_wins / profile.ffa_total_games > 0.5:
            return RewardAction(death_threshold_delta=0.1)
```

**We can use:**
```json
{
  "death_threshold_adjustment": {
    "variants": {
      "reward_winner": 0.1,
      "neutral": 0.0,
      "punish_warnings": -0.1
    },
    "targeting": [
      {
        "if": [
          {">": [{"var": "win_rate"}, 0.5]},
          "reward_winner",
          {"if": [
            {">": [{"var": "warnings_per_game"}, 10]},
            "punish_warnings",
            "neutral"
          ]}
        ]
      }
    ]
  }
}
```

**Benefits:**
- Change reward logic via Web UI, not code deploys
- A/B test different reward strategies
- Per-player targeting for experiments
- Simpler codebase (no custom engine)

---

## Architecture

### Flag Evaluation Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Game Coordinator (BaseGameMode)                            │
│                                                              │
│  _initialize_players_impl():                                │
│    For each player:                                         │
│      1. Load PlayerProfile from Redis                       │
│      2. Calculate context (win_rate, kd_ratio, etc.)        │
│      3. Evaluate flags with context                         │
│      4. Apply adjustments to player parameters              │
│                                                              │
│  Context passed to flagd:                                   │
│    - serial: "00:06:F7:12:34:56"                            │
│    - game_mode: "FFA"                                       │
│    - win_rate: 0.65                                         │
│    - warnings_per_game: 3.2                                 │
│    - kd_ratio: 2.1                                          │
│    - battery: 4.2                                           │
│    - connection_stability: 0.95                             │
│    - performance_score: 88.0                                │
│    - reward_tier: "GOOD"                                    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      │ gRPC EvaluateFlag(context)
                      ▼
            ┌─────────────────┐
            │  flagd          │
            │                 │
            │  Evaluates      │
            │  targeting      │
            │  rules with     │
            │  JSONLogic      │
            └────────┬────────┘
                     │
                     │ Returns variant value
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Game Coordinator                                           │
│                                                              │
│  adjustment = 0.1  (from flag)                              │
│  player.death_threshold += adjustment                       │
│  player.feedback_intensity *= 1.2                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Flag Definitions for Gameplay Adjustments

### 1. Death Threshold Adjustment (FFA)

**Purpose:** Reward winners with easier death threshold, punish excessive warnings with stricter threshold.

```json
{
  "ffa_death_threshold_adjustment": {
    "state": "ENABLED",
    "variants": {
      "reward_winner": 0.1,
      "reward_good": 0.05,
      "neutral": 0.0,
      "punish_warnings": -0.05,
      "punish_excessive": -0.1
    },
    "defaultVariant": "neutral",
    "targeting": [
      {
        "if": [
          {">": [{"var": "win_rate"}, 0.6]},
          "reward_winner",
          {
            "if": [
              {">": [{"var": "win_rate"}, 0.4]},
              "reward_good",
              {
                "if": [
                  {">": [{"var": "warnings_per_game"}, 10]},
                  "punish_excessive",
                  {
                    "if": [
                      {">": [{"var": "warnings_per_game"}, 5]},
                      "punish_warnings",
                      "neutral"
                    ]
                  }
                ]
              }
            ]
          }
        ]
      }
    ]
  }
}
```

### 2. Feedback Intensity Multiplier (All Modes)

**Purpose:** Stronger feedback for players with good battery, weaker for low battery.

```json
{
  "feedback_intensity_multiplier": {
    "state": "ENABLED",
    "variants": {
      "strong": 1.3,
      "normal": 1.0,
      "weak": 0.7
    },
    "defaultVariant": "normal",
    "targeting": [
      {
        "if": [
          {">": [{"var": "battery"}, 4.0]},
          "strong",
          {
            "if": [
              {"<": [{"var": "battery"}, 2.0]},
              "weak",
              "normal"
            ]
          }
        ]
      }
    ]
  }
}
```

### 3. Nonstop Death Threshold (K/D Ratio)

**Purpose:** Reward high K/D players with easier threshold (god mode effect).

```json
{
  "nonstop_death_threshold_adjustment": {
    "state": "ENABLED",
    "variants": {
      "god_mode": 0.15,
      "strong": 0.1,
      "neutral": 0.0,
      "weak": -0.05
    },
    "defaultVariant": "neutral",
    "targeting": [
      {
        "if": [
          {">": [{"var": "kd_ratio"}, 2.5]},
          "god_mode",
          {
            "if": [
              {">": [{"var": "kd_ratio"}, 1.5]},
              "strong",
              {
                "if": [
                  {"<": [{"var": "kd_ratio"}, 0.5]},
                  "weak",
                  "neutral"
                ]
              }
            ]
          }
        ]
      }
    ]
  }
}
```

### 4. Nonstop Respawn Delay (Deaths Per Minute)

**Purpose:** Punish excessive deaths with longer respawn delay.

```json
{
  "nonstop_respawn_delay_adjustment": {
    "state": "ENABLED",
    "variants": {
      "fast": -0.5,
      "normal": 0.0,
      "slow": 0.5,
      "very_slow": 1.0
    },
    "defaultVariant": "normal",
    "targeting": [
      {
        "if": [
          {">": [{"var": "deaths_per_minute"}, 3.0]},
          "very_slow",
          {
            "if": [
              {">": [{"var": "deaths_per_minute"}, 2.0]},
              "slow",
              {
                "if": [
                  {"<": [{"var": "deaths_per_minute"}, 0.5]},
                  "fast",
                  "normal"
                ]
              }
            ]
          }
        ]
      }
    ]
  }
}
```

### 5. Team Death Threshold (Team Performance)

**Purpose:** Reward winning teams, punish losing teams.

```json
{
  "team_death_threshold_adjustment": {
    "state": "ENABLED",
    "variants": {
      "winning_streak": 0.1,
      "neutral": 0.0,
      "losing_streak": -0.05
    },
    "defaultVariant": "neutral",
    "targeting": [
      {
        "if": [
          {">=": [{"var": "team_wins_last_3"}, 2]},
          "winning_streak",
          {
            "if": [
              {">=": [{"var": "team_losses_last_3"}, 2]},
              "losing_streak",
              "neutral"
            ]
          }
        ]
      }
    ]
  }
}
```

### 6. Visual Reward Flag (FFA Winners)

**Purpose:** Apply visual effects for high performers.

```json
{
  "visual_reward_effect": {
    "state": "ENABLED",
    "variants": {
      "gold_tint": "gold_tint",
      "rainbow": "rainbow",
      "pulsing": "pulsing",
      "none": "none"
    },
    "defaultVariant": "none",
    "targeting": [
      {
        "if": [
          {">=": [{"var": "performance_score"}, 90]},
          "gold_tint",
          {
            "if": [
              {">=": [{"var": "performance_score"}, 80]},
              "pulsing",
              "none"
            ]
          }
        ]
      }
    ]
  }
}
```

---

## Implementation Tasks

### Task 1: Add Flag Evaluation Helper to BaseGameMode

**File**: `services/game_coordinator/games/base.py`

**Method: `_evaluate_player_adjustments()`**

```python
async def _evaluate_player_adjustments(
    self,
    player: EnhancedPlayer
) -> dict[str, Any]:
    """
    Evaluate flags for player-specific adjustments.

    Args:
        player: Player with loaded profile

    Returns:
        Dictionary of adjustments to apply
    """

    # Calculate context from profile
    context = {
        "serial": player.serial,
        "game_mode": self.get_game_name(),
        "win_rate": player.profile.calculate_win_rate(),
        "warnings_per_game": player.profile.calculate_warnings_per_game(),
        "kd_ratio": player.profile.nonstop_kd_ratio,
        "battery": player.profile.average_battery_level,
        "connection_stability": player.profile.connection_stability_score,
        "performance_score": player.profile.performance_score,
        "reward_tier": player.profile.reward_tier,
    }

    # Add mode-specific context
    if self.get_game_name() == "FFA":
        context["ffa_wins"] = player.profile.ffa_wins
        context["ffa_total_games"] = player.profile.ffa_total_games

    elif self.get_game_name() == "Nonstop":
        context["deaths_per_minute"] = player.profile.calculate_deaths_per_minute()
        context["current_streak"] = getattr(player, "current_streak", 0)

    elif self.get_game_name() in ["Teams", "RandomTeams", "Zombies"]:
        context["team_num"] = player.team_num
        context["team_wins_last_3"] = player.profile.calculate_team_wins_last_3()
        context["team_losses_last_3"] = player.profile.calculate_team_losses_last_3()

    # Evaluate flags
    adjustments = {}

    # Death threshold adjustment
    threshold_flag = f"{self.get_game_name().lower()}_death_threshold_adjustment"
    adjustments["death_threshold_delta"] = self.flag_client.get_number_value(
        threshold_flag,
        default=0.0,
        evaluation_context=context
    )

    # Feedback intensity multiplier
    adjustments["feedback_intensity_multiplier"] = self.flag_client.get_number_value(
        "feedback_intensity_multiplier",
        default=1.0,
        evaluation_context=context
    )

    # Visual effects
    adjustments["visual_effect"] = self.flag_client.get_string_value(
        "visual_reward_effect",
        default="none",
        evaluation_context=context
    )

    # Nonstop-specific: respawn delay
    if self.get_game_name() == "Nonstop":
        adjustments["respawn_delay_delta"] = self.flag_client.get_number_value(
            "nonstop_respawn_delay_adjustment",
            default=0.0,
            evaluation_context=context
        )

    return adjustments
```

### Task 2: Apply Adjustments in Game Lifecycle

**In `_initialize_players_impl()`:**

```python
async def _initialize_players_impl(
    self,
    controllers: list[ControllerInfo]
) -> None:
    """Initialize players with profile loading and adjustments."""

    for controller in controllers:
        # Load profile
        profile = await self.profile_manager.get_or_create_profile(
            controller.serial,
            self.session_id
        )

        # Create player
        player = EnhancedPlayer(
            serial=controller.serial,
            profile=profile,
            current_battery=controller.battery
        )

        # Evaluate adjustments via flags
        adjustments = await self._evaluate_player_adjustments(player)

        # Apply adjustments
        player.death_threshold += adjustments.get("death_threshold_delta", 0.0)
        player.feedback_intensity *= adjustments.get("feedback_intensity_multiplier", 1.0)
        player.visual_effect = adjustments.get("visual_effect", "none")

        if "respawn_delay_delta" in adjustments:
            player.respawn_delay += adjustments["respawn_delay_delta"]

        # Log adjustments
        if any(v != 0 for v in [
            adjustments.get("death_threshold_delta", 0),
            adjustments.get("feedback_intensity_multiplier", 1.0) - 1.0
        ]):
            logger.info(
                f"Applied adjustments to {controller.serial}: "
                f"threshold_delta={adjustments['death_threshold_delta']:.2f}, "
                f"feedback_multiplier={adjustments['feedback_intensity_multiplier']:.2f}, "
                f"visual={adjustments['visual_effect']}"
            )

        self.players[controller.serial] = player
```

### Task 3: Add Metrics for Adjustments

**File**: `services/game_coordinator/metrics.py`

```python
# Adjustment tracking
player_death_threshold_adjustment = Gauge(
    'player_death_threshold_adjustment',
    'Death threshold adjustment per player',
    ['serial', 'game_mode']
)

player_feedback_intensity_multiplier = Gauge(
    'player_feedback_intensity_multiplier',
    'Feedback intensity multiplier per player',
    ['serial', 'game_mode']
)

adjustments_applied_total = Counter(
    'adjustments_applied_total',
    'Total gameplay adjustments applied',
    ['adjustment_type', 'game_mode']
)
```

**Update metrics in `_evaluate_player_adjustments()`:**

```python
# After evaluating adjustments
player_death_threshold_adjustment.labels(
    serial=player.serial,
    game_mode=self.get_game_name()
).set(adjustments["death_threshold_delta"])

player_feedback_intensity_multiplier.labels(
    serial=player.serial,
    game_mode=self.get_game_name()
).set(adjustments["feedback_intensity_multiplier"])

if adjustments["death_threshold_delta"] != 0:
    adjustments_applied_total.labels(
        adjustment_type="death_threshold",
        game_mode=self.get_game_name()
    ).inc()
```

### Task 4: Add PlayerProfile Calculation Methods

**File**: `services/game_coordinator/models/player.py`

Add helper methods to PlayerProfile:

```python
@dataclass
class PlayerProfile:
    # ... existing fields ...

    def calculate_win_rate(self) -> float:
        """Calculate overall win rate across all modes."""
        total_games = self.ffa_total_games + self.nonstop_total_games + self.team_total_games
        total_wins = self.ffa_wins + self.team_wins

        if total_games == 0:
            return 0.0

        return total_wins / total_games

    def calculate_warnings_per_game(self) -> float:
        """Calculate average warnings per game (FFA only)."""
        if self.ffa_total_games == 0:
            return 0.0

        return self.ffa_warnings / self.ffa_total_games

    def calculate_deaths_per_minute(self) -> float:
        """Calculate deaths per minute (Nonstop only)."""
        # This requires tracking total playtime in Nonstop
        # For now, estimate based on typical game duration (120s)
        if self.nonstop_total_games == 0:
            return 0.0

        total_minutes = (self.nonstop_total_games * 120) / 60
        return self.nonstop_deaths / max(total_minutes, 0.1)

    def calculate_team_wins_last_3(self) -> int:
        """Calculate team wins in last 3 team games."""
        # Requires round history analysis
        # Placeholder for now
        return 0

    def calculate_team_losses_last_3(self) -> int:
        """Calculate team losses in last 3 team games."""
        # Requires round history analysis
        # Placeholder for now
        return 0
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/unit/games/test_flag_adjustments.py`

```python
import pytest
from unittest.mock import Mock, AsyncMock

from services.game_coordinator.games.base import BaseGameMode
from services.game_coordinator.models.player import PlayerProfile, EnhancedPlayer


@pytest.mark.asyncio
async def test_evaluate_player_adjustments_winner():
    """Test adjustments for high win rate player."""

    game = BaseGameMode(game_id="test", controllers=[])

    # Mock flag client
    game.flag_client = Mock()
    game.flag_client.get_number_value = Mock(side_effect=lambda flag, default, **ctx: {
        "ffa_death_threshold_adjustment": 0.1,  # Reward
        "feedback_intensity_multiplier": 1.2
    }.get(flag, default))
    game.flag_client.get_string_value = Mock(return_value="gold_tint")

    # Player with high win rate
    profile = PlayerProfile(
        serial="00:06:F7:12:34:56",
        ffa_total_games=20,
        ffa_wins=15,  # 75% win rate
        ffa_warnings=10,
        performance_score=92.0
    )

    player = EnhancedPlayer(serial=profile.serial, profile=profile)

    # Evaluate
    adjustments = await game._evaluate_player_adjustments(player)

    # Assertions
    assert adjustments["death_threshold_delta"] == 0.1
    assert adjustments["feedback_intensity_multiplier"] == 1.2
    assert adjustments["visual_effect"] == "gold_tint"


@pytest.mark.asyncio
async def test_evaluate_player_adjustments_excessive_warnings():
    """Test punishment for excessive warnings."""

    game = BaseGameMode(game_id="test", controllers=[])

    # Mock flag client returning punishment
    game.flag_client = Mock()
    game.flag_client.get_number_value = Mock(side_effect=lambda flag, default, **ctx: {
        "ffa_death_threshold_adjustment": -0.1,  # Punish
        "feedback_intensity_multiplier": 0.8
    }.get(flag, default))
    game.flag_client.get_string_value = Mock(return_value="none")

    # Player with excessive warnings
    profile = PlayerProfile(
        serial="00:06:F7:AB:CD:EF",
        ffa_total_games=10,
        ffa_wins=2,
        ffa_warnings=120,  # 12 warnings per game
        performance_score=35.0
    )

    player = EnhancedPlayer(serial=profile.serial, profile=profile)

    # Evaluate
    adjustments = await game._evaluate_player_adjustments(player)

    # Assertions
    assert adjustments["death_threshold_delta"] == -0.1
    assert adjustments["feedback_intensity_multiplier"] == 0.8
```

### Integration Tests

**File**: `tests/integration/test_flag_adjustments_integration.py`

```python
@pytest.mark.asyncio
async def test_flag_adjustments_applied_in_game():
    """Test adjustments are applied during actual game."""

    # Setup flagd with test flags
    # ...

    # Create player with profile
    profile = PlayerProfile(
        serial="00:06:F7:12:34:56",
        ffa_total_games=10,
        ffa_wins=8,  # 80% win rate
        ffa_warnings=5
    )

    await profile_manager.update_profile(profile)

    # Start game
    game = FFAGame(game_id="test", controllers=[controller])
    await game.initialize_game()

    # Check adjustments applied
    player = game.players[controller.serial]
    assert player.death_threshold > BASE_DEATH_THRESHOLD  # Rewarded
    assert player.visual_effect in ["gold_tint", "pulsing"]
```

### Manual Testing

**Test 1: Winner Reward (FFA)**
- [ ] Create player profile with 70% win rate
- [ ] Start FFA game
- [ ] Check logs: "Applied adjustments to XX:XX:XX: threshold_delta=0.10"
- [ ] Verify death threshold increased in gameplay
- [ ] Check Grafana: `player_death_threshold_adjustment{serial="XX:XX:XX"} = 0.1`

**Test 2: Warning Punishment (FFA)**
- [ ] Create player profile with 15 warnings per game
- [ ] Start FFA game
- [ ] Check logs: "Applied adjustments to XX:XX:XX: threshold_delta=-0.10"
- [ ] Verify death threshold decreased (harder to survive)
- [ ] Check Grafana: `adjustments_applied_total{adjustment_type="death_threshold"}`

**Test 3: K/D Reward (Nonstop)**
- [ ] Create player profile with K/D ratio 3.0
- [ ] Start Nonstop game
- [ ] Check logs: "Applied adjustments: threshold_delta=0.15" (god mode)
- [ ] Verify player is harder to kill
- [ ] Visual effect should be applied

**Test 4: Battery-Based Feedback**
- [ ] Create player with battery 4.5
- [ ] Start any game
- [ ] Check logs: "feedback_multiplier=1.30"
- [ ] Verify stronger vibration/feedback during gameplay

**Test 5: Flag Update During Demo**
- [ ] Start game with default adjustments
- [ ] Via Web UI, change `ffa_death_threshold_adjustment` targeting
- [ ] Wait 10 seconds (flagd sync)
- [ ] Start new game
- [ ] Verify new adjustments applied

---

## Files to Create

```
services/game_coordinator/
└── games/
    └── base.py (modify - add _evaluate_player_adjustments)

services/game_coordinator/models/
└── player.py (modify - add calculation methods)

services/game_coordinator/
└── metrics.py (modify - add adjustment metrics)
```

---

## Files to Modify

- `services/game_coordinator/games/base.py` - Add flag evaluation and adjustment application
- `services/game_coordinator/games/ffa.py` - FFA-specific context
- `services/game_coordinator/games/nonstop_joust.py` - Nonstop-specific context
- `services/game_coordinator/games/teams.py` - Team-specific context
- `services/game_coordinator/models/player.py` - Add calculation methods
- `services/game_coordinator/metrics.py` - Add adjustment metrics

---

## Flag Definitions to Create (Phase 53 - Web UI)

During Phase 53, these flag definitions will be created in the Web UI:

- `ffa_death_threshold_adjustment`
- `feedback_intensity_multiplier`
- `nonstop_death_threshold_adjustment`
- `nonstop_respawn_delay_adjustment`
- `team_death_threshold_adjustment`
- `visual_reward_effect`

---

## Success Criteria

- [ ] `_evaluate_player_adjustments()` method implemented
- [ ] Flag evaluation integrated into `_initialize_players_impl()`
- [ ] Adjustments applied to player parameters
- [ ] Metrics track adjustments per player
- [ ] FFA rewards winners with +0.1 threshold (when flag enabled)
- [ ] FFA punishes warnings with -0.1 threshold (when flag enabled)
- [ ] Nonstop rewards high K/D with +0.15 threshold
- [ ] Battery affects feedback intensity (1.3x for good, 0.7x for low)
- [ ] Visual effects applied based on performance score
- [ ] No custom rule engine code (all via flags)
- [ ] Unit tests pass (>85% coverage)
- [ ] Integration tests pass
- [ ] Flag evaluation <5ms (p95)
- [ ] No game loop impact (<1ms overhead)

---

## Migration from Old "Engine" Approach

**What we're NOT building:**
- ❌ RewardPunishmentEngine class
- ❌ RewardPunishmentRule dataclass
- ❌ RuleEvaluator with custom logic
- ❌ ActionApplier classes
- ❌ Hardcoded Python rule definitions

**What we ARE building:**
- ✅ Simple flag evaluation with player context
- ✅ Adjustment application in game loop
- ✅ Metrics for observability
- ✅ All logic in flagd targeting rules (Web UI)

**Lines of code comparison:**
- Old approach (custom engine): ~900 lines
- New approach (flag evaluation): ~200 lines

---

## Next Phase

**Phase 53: Web UI Enhancements** will:
- Create flag management interface
- Define flag targeting rules in UI
- Allow editing adjustment thresholds
- Visualize player profiles and adjustments
- Enable A/B testing of reward strategies

**Dependencies**: Requires Phase 51 (Flagd) and Phase 52 (this phase) complete.

---

**End of Phase 52**
