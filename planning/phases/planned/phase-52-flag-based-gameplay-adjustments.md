# Phase 51: Reward/Punishment Engine

**Status**: 📋 PLANNED
**Priority**: High
**Estimated Effort**: 1 week
**Dependencies**: Phase 49 (Profiles), Phase 50 (Mode-Specific Tracking)
**Blocks**: Phase 53 (Web UI - needs reward data to display)

---

## Overview

Implement dynamic player parameter adjustment based on performance. Reward good performance with easier gameplay, punish poor performance with stricter rules. Game mode-specific rules ensure rewards/punishments match the dynamics of each mode.

**Goals:**
- Create RewardPunishmentEngine to evaluate and apply rules
- Define game mode-specific rule sets (FFA, Nonstop, Teams)
- Dynamically adjust thresholds, feedback intensity, and visual effects
- Track reward/punishment applications in metrics
- Store reward history in player profiles

---

## Why This Phase Matters

**Current limitation:** All players have identical gameplay parameters regardless of performance. No incentive for consistent good play, no help for struggling players.

**After this phase:**
- Consistent winners get easier thresholds (more forgiving)
- Excessive warnings trigger stricter thresholds (punishment)
- High K/D in Nonstop gets enhanced feedback (reward aggression)
- Winning teams get visual rewards (team pride)
- Performance adjustments visible in metrics and UI

---

## Reward/Punishment Strategy by Game Mode

### FFA (Free-For-All)

**Philosophy:** Reward individual skill and consistency

**Rewards:**
1. **Consistent winners** (win rate > 50%)
   - Action: +0.1 death threshold (easier)
   - Visual: Gold tint on LED

2. **Good battery management** (avg battery > 4.0)
   - Action: +20% feedback intensity (stronger vibration)

3. **Long survival times** (avg survival > 120s)
   - Action: +0.05 warn threshold (fewer nuisance warnings)

**Punishments:**
1. **Excessive warnings** (>10 warnings/round)
   - Action: -0.1 warn threshold (more sensitive warnings)
   - Feedback: -20% intensity (less feedback)

2. **Poor connection** (stability < 0.7)
   - Action: No adjustments (connection issue, not skill)

### Nonstop Joust

**Philosophy:** Reward aggression and combat effectiveness

**Rewards:**
1. **High K/D ratio** (K/D > 2.0)
   - Action: +30% vibration intensity on kills (satisfying feedback)
   - Visual: Rainbow flash on kill
   - Audio: Kill streak announcement at 5+ streak

2. **Kill streaks** (current streak >= 5)
   - Action: +0.15 death threshold (god mode feeling)
   - Visual: Pulsing gold LED
   - Audio: "Unstoppable!" announcement

3. **Low deaths per minute** (<1.5 DPM)
   - Action: +0.5s spawn protection (reward careful play)

**Punishments:**
1. **Excessive deaths** (>2 deaths/minute)
   - Action: -0.5s spawn protection (less invulnerability)
   - Respawn delay: +0.5s (longer wait)

2. **Very low K/D** (K/D < 0.3)
   - Action: +0.1 death threshold (make it easier)
   - Note: This is actually a "help" not punishment

### Team Modes

**Philosophy:** Reward teamwork and coordination

**Rewards:**
1. **Winning teams** (2+ wins in last 3 games)
   - Action: All team members +0.1 death threshold
   - Visual: Pulsing team color (synchronized)

2. **Team coordination** (2+ simultaneous kills)
   - Action: Team score bonus +50 points
   - Visual: All team LEDs flash in sync
   - Audio: "Teamwork!" announcement

3. **Consistent team player** (5+ team games, 60%+ win rate)
   - Action: +0.05 death threshold
   - Visual: Team color with gold tint

**Punishments:**
1. **Losing teams** (2+ losses in last 3 games)
   - Action: All team members -0.05 death threshold
   - Note: Can be earned back with wins (comeback bonus)

2. **Poor team coordination** (0 simultaneous kills in 5 games)
   - Action: Visual reminder (flash team color)
   - No mechanical punishment (encourage learning)

---

## Rule Engine Architecture

### Rule Definition Schema

```python
@dataclass
class RewardPunishmentRule:
    """Single reward/punishment rule."""

    rule_id: str
    name: str
    description: str
    game_modes: list[str]  # Which modes this applies to

    # Trigger
    trigger_type: str  # "performance_score", "win_rate", "kd_ratio", etc.
    threshold_value: float
    comparison: str  # "greater_than", "less_than", "equals"

    # Actions
    actions: list[RewardAction]

    # Frequency
    check_frequency: str  # "per_round", "per_game", "cumulative"
    cooldown_rounds: int = 0  # Minimum rounds between applications


@dataclass
class RewardAction:
    """Action to apply when rule triggers."""

    action_type: str  # "adjust_threshold", "modify_feedback", "visual", "audio"

    # Threshold adjustments
    death_threshold_delta: Optional[float] = None
    warn_threshold_delta: Optional[float] = None

    # Feedback adjustments
    feedback_intensity_multiplier: Optional[float] = None
    vibration_duration_multiplier: Optional[float] = None

    # Visual/audio
    color_override: Optional[tuple[int, int, int]] = None
    color_effect: Optional[str] = None  # "gold_tint", "pulsing", "rainbow"
    audio_clip: Optional[str] = None  # "streak", "teamwork", "comeback"
```

### Rule Sets

**File**: `services/game_coordinator/rewards/rules.py`

```python
"""Game mode-specific reward/punishment rules."""

FFA_RULES = [
    RewardPunishmentRule(
        rule_id="ffa_reward_winners",
        name="Reward Consistent Winners",
        description="Players with >50% win rate get easier thresholds",
        game_modes=["FFA"],
        trigger_type="win_rate",
        threshold_value=0.5,
        comparison="greater_than",
        actions=[
            RewardAction(
                action_type="adjust_threshold",
                death_threshold_delta=0.1,
                warn_threshold_delta=0.05,
            ),
            RewardAction(
                action_type="visual",
                color_effect="gold_tint",
            ),
        ],
        check_frequency="per_round",
        cooldown_rounds=0,
    ),

    RewardPunishmentRule(
        rule_id="ffa_punish_warnings",
        name="Punish Excessive Warnings",
        description="Players with >10 warnings/round get stricter thresholds",
        game_modes=["FFA"],
        trigger_type="warnings_per_round",
        threshold_value=10,
        comparison="greater_than",
        actions=[
            RewardAction(
                action_type="adjust_threshold",
                warn_threshold_delta=-0.05,
            ),
            RewardAction(
                action_type="modify_feedback",
                feedback_intensity_multiplier=0.8,
            ),
        ],
        check_frequency="per_round",
        cooldown_rounds=2,
    ),

    RewardPunishmentRule(
        rule_id="ffa_reward_battery",
        name="Reward Good Battery Management",
        description="Players maintaining battery >4 get enhanced feedback",
        game_modes=["FFA"],
        trigger_type="avg_battery",
        threshold_value=4.0,
        comparison="greater_than",
        actions=[
            RewardAction(
                action_type="modify_feedback",
                feedback_intensity_multiplier=1.2,
            ),
        ],
        check_frequency="cumulative",
        cooldown_rounds=0,
    ),
]

NONSTOP_RULES = [
    RewardPunishmentRule(
        rule_id="nonstop_reward_high_kd",
        name="Reward High K/D Ratio",
        description="Players with K/D > 2.0 get enhanced kill feedback",
        game_modes=["Nonstop"],
        trigger_type="kd_ratio",
        threshold_value=2.0,
        comparison="greater_than",
        actions=[
            RewardAction(
                action_type="modify_feedback",
                feedback_intensity_multiplier=1.3,
            ),
            RewardAction(
                action_type="visual",
                color_effect="rainbow_on_kill",
            ),
        ],
        check_frequency="cumulative",
        cooldown_rounds=0,
    ),

    RewardPunishmentRule(
        rule_id="nonstop_reward_streak",
        name="Reward Kill Streaks",
        description="5+ kill streak gives temporary god mode",
        game_modes=["Nonstop"],
        trigger_type="current_streak",
        threshold_value=5,
        comparison="greater_than_equal",
        actions=[
            RewardAction(
                action_type="adjust_threshold",
                death_threshold_delta=0.15,
            ),
            RewardAction(
                action_type="visual",
                color_effect="pulsing_gold",
            ),
            RewardAction(
                action_type="audio",
                audio_clip="unstoppable",
            ),
        ],
        check_frequency="per_game",
        cooldown_rounds=0,
    ),

    RewardPunishmentRule(
        rule_id="nonstop_punish_deaths",
        name="Punish Excessive Deaths",
        description="Players with >2 deaths/min get reduced spawn protection",
        game_modes=["Nonstop"],
        trigger_type="deaths_per_minute",
        threshold_value=2.0,
        comparison="greater_than",
        actions=[
            RewardAction(
                action_type="adjust_spawn",
                spawn_protection_delta=-0.5,  # -0.5 seconds
                respawn_delay_delta=0.5,  # +0.5 seconds
            ),
        ],
        check_frequency="per_round",
        cooldown_rounds=1,
    ),
]

TEAM_RULES = [
    RewardPunishmentRule(
        rule_id="team_reward_winners",
        name="Reward Winning Teams",
        description="Teams with 2+ wins in last 3 games get easier thresholds",
        game_modes=["Teams", "RandomTeams"],
        trigger_type="team_wins_last_3",
        threshold_value=2,
        comparison="greater_than_equal",
        actions=[
            RewardAction(
                action_type="adjust_threshold",
                death_threshold_delta=0.1,  # All team members
            ),
            RewardAction(
                action_type="visual",
                color_effect="pulsing_team_color",
            ),
        ],
        check_frequency="per_round",
        cooldown_rounds=0,
    ),

    RewardPunishmentRule(
        rule_id="team_reward_coordination",
        name="Reward Team Coordination",
        description="2+ simultaneous kills triggers team bonus",
        game_modes=["Teams", "RandomTeams"],
        trigger_type="simultaneous_kills",
        threshold_value=2,
        comparison="greater_than_equal",
        actions=[
            RewardAction(
                action_type="score_bonus",
                bonus_points=50,
            ),
            RewardAction(
                action_type="visual",
                color_effect="team_flash_sync",
            ),
            RewardAction(
                action_type="audio",
                audio_clip="teamwork",
            ),
        ],
        check_frequency="per_game",
        cooldown_rounds=0,
    ),

    RewardPunishmentRule(
        rule_id="team_punish_losers",
        name="Motivate Losing Teams",
        description="Teams with 2+ losses get slight handicap (encourages comeback)",
        game_modes=["Teams", "RandomTeams"],
        trigger_type="team_losses_last_3",
        threshold_value=2,
        comparison="greater_than_equal",
        actions=[
            RewardAction(
                action_type="adjust_threshold",
                death_threshold_delta=-0.05,  # Slight handicap
            ),
        ],
        check_frequency="per_round",
        cooldown_rounds=1,
    ),
]
```

### Engine Implementation

**File**: `services/game_coordinator/rewards/engine.py`

```python
"""Reward/punishment engine for dynamic gameplay adjustment."""

import logging
from typing import Optional

from services.game_coordinator.models.player import EnhancedPlayer, PlayerProfile
from services.game_coordinator.rewards.rules import FFA_RULES, NONSTOP_RULES, TEAM_RULES
from services.game_coordinator.storage.player_profiles import PlayerProfileManager

logger = logging.getLogger(__name__)


class RewardPunishmentEngine:
    """Evaluates and applies reward/punishment rules."""

    def __init__(self, profile_manager: PlayerProfileManager, game_mode: str):
        self.profile_manager = profile_manager
        self.game_mode = game_mode

        # Load rules for this game mode
        self.rules = self._load_rules_for_mode(game_mode)

        logger.info(f"Initialized reward engine for {game_mode} with {len(self.rules)} rules")

    def _load_rules_for_mode(self, game_mode: str) -> list:
        """Load rules applicable to this game mode."""

        all_rules = FFA_RULES + NONSTOP_RULES + TEAM_RULES

        # Filter by game mode
        applicable_rules = [
            rule for rule in all_rules
            if game_mode in rule.game_modes
        ]

        return applicable_rules

    async def evaluate_and_apply(
        self,
        player: EnhancedPlayer,
        context: str = "per_round"
    ) -> list[str]:
        """
        Evaluate all rules and apply matching rewards/punishments.

        Args:
            player: Player to evaluate
            context: When this is being called ("per_round", "per_game", etc.)

        Returns:
            List of rule IDs that were triggered
        """

        triggered_rules = []

        # Calculate metrics for evaluation
        metrics = self._calculate_metrics(player)

        logger.debug(f"Evaluating {player.serial}: {metrics}")

        # Evaluate each rule
        for rule in self.rules:
            # Check frequency matches
            if rule.check_frequency != context and context != "all":
                continue

            # Check if trigger condition is met
            if self._evaluate_trigger(rule, metrics):
                logger.info(
                    f"Rule '{rule.name}' triggered for {player.serial}: "
                    f"{rule.trigger_type}={metrics.get(rule.trigger_type):.2f} "
                    f"{rule.comparison} {rule.threshold_value}"
                )

                # Apply all actions
                for action in rule.actions:
                    await self._apply_action(player, action)

                triggered_rules.append(rule.rule_id)

                # Update reward tier
                self._update_reward_tier(player)

        return triggered_rules

    def _calculate_metrics(self, player: EnhancedPlayer) -> dict:
        """Calculate metrics from player profile for rule evaluation."""

        profile = player.profile

        metrics = {
            # FFA metrics
            "win_rate": profile.ffa_wins / max(profile.ffa_total_games, 1),
            "warnings_per_round": profile.ffa_warnings / max(profile.ffa_total_games, 1),
            "avg_survival_time": profile.ffa_avg_survival_time,

            # Nonstop metrics
            "kd_ratio": profile.nonstop_kd_ratio,
            "current_streak": getattr(player, 'current_streak', 0),
            "deaths_per_minute": profile.nonstop_avg_deaths_per_minute,

            # Team metrics
            "team_wins_last_3": self._count_recent_team_wins(profile, 3),
            "team_losses_last_3": self._count_recent_team_losses(profile, 3),
            "simultaneous_kills": profile.team_simultaneous_kills,

            # Hardware metrics
            "avg_battery": profile.average_battery_level,
            "connection_stability": profile.connection_stability_score,

            # Overall
            "performance_score": profile.performance_score,
        }

        return metrics

    def _evaluate_trigger(self, rule, metrics: dict) -> bool:
        """Check if rule trigger condition is met."""

        value = metrics.get(rule.trigger_type)
        if value is None:
            return False

        if rule.comparison == "greater_than":
            return value > rule.threshold_value
        elif rule.comparison == "less_than":
            return value < rule.threshold_value
        elif rule.comparison == "equals":
            return abs(value - rule.threshold_value) < 0.01
        elif rule.comparison == "greater_than_equal":
            return value >= rule.threshold_value
        elif rule.comparison == "less_than_equal":
            return value <= rule.threshold_value

        return False

    async def _apply_action(self, player: EnhancedPlayer, action):
        """Apply a single reward/punishment action."""

        if action.action_type == "adjust_threshold":
            # Adjust death/warning thresholds
            if action.death_threshold_delta:
                player.death_threshold_override = (
                    (player.death_threshold_override or 0.0) +
                    action.death_threshold_delta
                )

                # Emit metric
                from services.game_coordinator import metrics
                metrics.player_death_threshold.labels(serial=player.serial).set(
                    player.death_threshold_override
                )

                logger.debug(
                    f"Adjusted death threshold for {player.serial}: "
                    f"delta={action.death_threshold_delta:+.2f}, "
                    f"new={player.death_threshold_override:.2f}"
                )

            if action.warn_threshold_delta:
                player.warn_threshold_override = (
                    (player.warn_threshold_override or 0.0) +
                    action.warn_threshold_delta
                )

        elif action.action_type == "modify_feedback":
            # Adjust feedback intensity
            if action.feedback_intensity_multiplier:
                player.feedback_intensity_multiplier = action.feedback_intensity_multiplier

                # Emit metric
                from services.game_coordinator import metrics
                metrics.player_feedback_intensity.labels(serial=player.serial).set(
                    player.feedback_intensity_multiplier
                )

        elif action.action_type == "visual":
            # Apply visual effect (will be handled in game loop)
            player.visual_effect = action.color_effect
            if action.color_override:
                player.color = action.color_override

        elif action.action_type == "audio":
            # Trigger audio announcement (will be handled in game loop)
            player.audio_announcement = action.audio_clip

    def _update_reward_tier(self, player: EnhancedPlayer):
        """Update player's reward tier based on performance score."""

        score = player.profile.performance_score

        if score >= 90:
            tier = "EXCELLENT"
        elif score >= 75:
            tier = "GOOD"
        elif score >= 50:
            tier = "NEUTRAL"
        elif score >= 25:
            tier = "POOR"
        else:
            tier = "CRITICAL"

        if player.profile.reward_tier != tier:
            logger.info(f"Player {player.serial} tier changed: {player.profile.reward_tier} → {tier}")
            player.profile.reward_tier = tier

    def _count_recent_team_wins(self, profile: PlayerProfile, n: int) -> int:
        """Count team wins in last N games."""
        # Placeholder - will implement with round history in Phase 52
        return 0

    def _count_recent_team_losses(self, profile: PlayerProfile, n: int) -> int:
        """Count team losses in last N games."""
        # Placeholder - will implement with round history in Phase 52
        return 0
```

---

## Integration into Game Modes

**File**: `services/game_coordinator/games/base.py`

```python
from services.game_coordinator.rewards.engine import RewardPunishmentEngine

class BaseGameMode(ABC):

    def __init__(self, ...):
        # ... existing init ...

        # Phase 51: Reward/punishment engine
        self.reward_engine = RewardPunishmentEngine(
            self.profile_manager,
            self.get_game_name()
        )

    async def run(self, game_context=None):
        """Enhanced with reward/punishment application."""

        with tracer.start_as_current_span(span_name, context=game_context) as game_span:
            try:
                # ... initialization ...

                # Phase 51: Apply pre-game rewards/punishments
                for player in self.players.values():
                    triggered = await self.reward_engine.evaluate_and_apply(
                        player,
                        context="per_game"
                    )
                    if triggered:
                        logger.info(f"Pre-game adjustments for {player.serial}: {triggered}")

                # ... countdown, gameplay ...

                # Phase 51: Apply post-round rewards/punishments
                for player in self.players.values():
                    triggered = await self.reward_engine.evaluate_and_apply(
                        player,
                        context="per_round"
                    )
                    if triggered:
                        logger.info(f"Post-round adjustments for {player.serial}: {triggered}")

                # ... teardown ...

            finally:
                # ... cleanup ...
```

Apply threshold overrides in `_process_controller_state()`:

```python
async def _process_controller_state(self, gameplay_data):
    """Enhanced with per-player threshold overrides."""

    player = self.players.get(gameplay_data.serial)
    if not player or not player.alive:
        return

    # Calculate acceleration magnitude
    accel = gameplay_data.acceleration
    accel_mag = math.sqrt(accel.x**2 + accel.y**2 + accel.z**2)
    player.last_accel_mag = accel_mag

    # Get thresholds (with per-player overrides from Phase 51)
    base_warn, base_death = self.sensitivity.value

    warn_threshold = (
        player.warn_threshold_override
        if player.warn_threshold_override is not None
        else base_warn
    )

    death_threshold = (
        player.death_threshold_override
        if player.death_threshold_override is not None
        else base_death
    )

    # Check death
    if accel_mag > death_threshold:
        await self._kill_player(gameplay_data.serial, accel_mag)
    elif accel_mag > warn_threshold:
        await self._warn_player(gameplay_data.serial, accel_mag)
```

---

## New Metrics

**File**: `services/game_coordinator/metrics.py`

```python
# Reward/punishment metrics
player_death_threshold = Gauge(
    'player_death_threshold',
    'Current death threshold per player (after adjustments)',
    ['serial']
)

player_warn_threshold = Gauge(
    'player_warn_threshold',
    'Current warning threshold per player (after adjustments)',
    ['serial']
)

player_feedback_intensity = Gauge(
    'player_feedback_intensity',
    'Feedback intensity multiplier per player',
    ['serial']
)

player_reward_tier = Gauge(
    'player_reward_tier',
    'Player reward tier (0=CRITICAL, 1=POOR, 2=NEUTRAL, 3=GOOD, 4=EXCELLENT)',
    ['serial']
)

reward_rules_triggered_total = Counter(
    'reward_rules_triggered_total',
    'Total reward/punishment rules triggered',
    ['rule_id', 'game_mode']
)

reward_threshold_adjustments_total = Counter(
    'reward_threshold_adjustments_total',
    'Total threshold adjustments applied',
    ['serial', 'adjustment_type']  # 'death_easier', 'death_harder', 'warn_easier', 'warn_harder'
)
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/unit/rewards/test_engine.py`

```python
def test_ffa_winner_reward():
    """Test FFA winner gets threshold reward."""

    profile = create_mock_profile(
        ffa_total_games=10,
        ffa_wins=6  # 60% win rate
    )
    player = create_mock_player(profile=profile)

    engine = RewardPunishmentEngine(mock_manager, "FFA")
    triggered = await engine.evaluate_and_apply(player, "per_round")

    assert "ffa_reward_winners" in triggered
    assert player.death_threshold_override > 0  # Got easier


def test_nonstop_high_kd_reward():
    """Test Nonstop high K/D gets feedback boost."""

    profile = create_mock_profile(
        nonstop_kills=20,
        nonstop_deaths=8,  # K/D = 2.5
        nonstop_kd_ratio=2.5
    )
    player = create_mock_player(profile=profile)

    engine = RewardPunishmentEngine(mock_manager, "Nonstop")
    triggered = await engine.evaluate_and_apply(player, "cumulative")

    assert "nonstop_reward_high_kd" in triggered
    assert player.feedback_intensity_multiplier > 1.0  # Enhanced


def test_excessive_warnings_punishment():
    """Test excessive warnings trigger punishment."""

    profile = create_mock_profile(
        ffa_total_games=5,
        ffa_warnings=60  # 12 warnings/round
    )
    player = create_mock_player(profile=profile)

    engine = RewardPunishmentEngine(mock_manager, "FFA")
    triggered = await engine.evaluate_and_apply(player, "per_round")

    assert "ffa_punish_warnings" in triggered
    assert player.warn_threshold_override < 0  # Got stricter
```

### Integration Tests

**File**: `tests/integration/test_rewards_integration.py`

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_reward_application_in_game():
    """Test rewards actually affect gameplay."""

    # Create profile with good stats
    profile_manager = PlayerProfileManager()
    profile = await profile_manager.get_or_create_profile("winner_serial", "test")
    profile.ffa_wins = 8
    profile.ffa_total_games = 10
    await profile_manager.update_profile(profile)

    # Start game
    game = FFAGame(...)
    await game.run()

    # Check player got threshold adjustment
    player = game.players["winner_serial"]
    assert player.death_threshold_override > 0
    assert player.profile.reward_tier == "EXCELLENT"
```

### Manual Testing

**Test 1: FFA Winner Reward**
- [ ] Win 3 FFA games in a row
- [ ] Check logs for "Rule 'Reward Consistent Winners' triggered"
- [ ] Verify gold tint on LED
- [ ] Check death threshold increased (easier to survive)

**Test 2: Nonstop Kill Streak**
- [ ] Get 5+ kill streak in Nonstop
- [ ] Check logs for "Rule 'Reward Kill Streaks' triggered"
- [ ] Verify pulsing gold LED
- [ ] Hear "Unstoppable!" audio (if implemented)
- [ ] Verify death threshold +0.15 (god mode)

**Test 3: Team Coordination**
- [ ] Coordinate 2 simultaneous kills with teammate
- [ ] Check logs for "Rule 'Reward Team Coordination' triggered"
- [ ] Verify synchronized LED flash across team
- [ ] Check team score bonus applied

**Test 4: Metrics Verification**
- [ ] Query `player_death_threshold` in Grafana
- [ ] Verify adjusted thresholds per player
- [ ] Query `reward_rules_triggered_total`
- [ ] Verify rules are being evaluated

---

## Files to Create

```
services/game_coordinator/rewards/
├── __init__.py
├── engine.py          # RewardPunishmentEngine
└── rules.py           # FFA_RULES, NONSTOP_RULES, TEAM_RULES

tests/unit/rewards/
├── test_engine.py     # Engine unit tests
└── test_rules.py      # Rule evaluation tests

tests/integration/
└── test_rewards_integration.py
```

## Files to Modify

- `services/game_coordinator/games/base.py` - Integrate reward engine, apply overrides
- `services/game_coordinator/models/player.py` - Add override fields to EnhancedPlayer
- `services/game_coordinator/metrics.py` - Add reward metrics

---

## Success Criteria

- [ ] FFA winners get +0.1 death threshold
- [ ] Excessive warnings trigger -0.1 death threshold
- [ ] High K/D in Nonstop gets +30% feedback
- [ ] Kill streaks trigger god mode (+0.15 threshold)
- [ ] Winning teams get visual rewards
- [ ] Threshold adjustments visible in metrics
- [ ] Rules evaluated at correct frequency
- [ ] Per-player thresholds applied correctly
- [ ] Unit tests pass (>85% coverage)
- [ ] Integration tests pass
- [ ] Manual testing confirms visible effects

---

## Next Phase

**Phase 52: Flagd Integration** will enable:
- Runtime toggling of reward/punishment system
- A/B testing different rule sets
- Context-aware rule evaluation (e.g., different rules for 25-player games)
- Remote configuration of thresholds and rewards

**Phase 53: Web UI Enhancements** will:
- Display active rewards/punishments per player
- Show reward tier badges
- Visualize threshold adjustments
- Allow manual override of rules

---

**End of Phase 51**
