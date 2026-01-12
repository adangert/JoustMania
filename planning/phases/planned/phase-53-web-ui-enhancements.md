# Phase 53: Web UI Enhancements

**Status**: 📋 PLANNED
**Priority**: Medium
**Estimated Effort**: 1-2 weeks
**Dependencies**: Phase 49 (Profiles), Phase 52 (Flagd)
**Blocks**: None (enables easier experimentation)

---

## Overview

Build comprehensive web UI for flag management, player profile viewing, and experiment monitoring. The web UI becomes the source of truth for flagd configuration via HTTP sync endpoint.

**Goals:**
- Create flag management interface (view, edit, toggle flags)
- Implement `/api/flags/config` endpoint for flagd HTTP sync
- Build player profile viewer with stats and history
- Create experiment dashboard with real-time metrics
- Add real-time updates via WebSockets (optional)

---

## Why This Phase Matters

**Current limitation:** Flags managed via JSON file editing. No visibility into player profiles. No experiment tracking UI.

**After this phase:**
- Non-technical users can manage flags via UI
- Toggle experiments on/off with single click
- View player stats, performance scores, reward tiers
- Monitor active experiments with live metrics
- Change configs during demos without SSH/file editing

---

## Architecture

### Component Overview

```
┌──────────────────────────────────────────────────────┐
│  React Frontend (web-ui/src/)                        │
│  ┌────────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │ Flag Mgmt      │  │ Player       │  │ Exp      │ │
│  │ /flags         │  │ Profiles     │  │ Dashboard│ │
│  │                │  │ /players     │  │ /exps    │ │
│  └────────────────┘  └──────────────┘  └──────────┘ │
└─────────────────────────┬────────────────────────────┘
                          │ HTTP API
                          ▼
┌──────────────────────────────────────────────────────┐
│  Flask Backend (web-ui/api/)                         │
│  ┌────────────────────────────────────────────────┐  │
│  │  Endpoints:                                    │  │
│  │  GET  /api/flags/config  → flagd JSON         │  │
│  │  POST /api/flags/update  → update flags       │  │
│  │  GET  /api/players       → list profiles      │  │
│  │  GET  /api/players/:id   → profile details    │  │
│  │  GET  /api/experiments   → experiment list    │  │
│  └────────────────────────────────────────────────┘  │
└───────────────┬──────────────────────────────────────┘
                │
    ┌───────────┼───────────┐
    │           │           │
    ▼           ▼           ▼
┌────────┐  ┌────────┐  ┌────────────┐
│ flagd  │  │ Redis  │  │ Prometheus │
│ (sync) │  │ (data) │  │ (metrics)  │
└────────┘  └────────┘  └────────────┘
```

---

## Feature Breakdown

### 1. Flag Management Page (`/flags`)

**Features:**
- List all flags with current values
- Group by category (Performance, Gameplay, Experimental)
- Toggle boolean flags with switch component
- Edit number/string flags with input fields
- Add/edit targeting rules with visual rule builder
- Preview flag evaluation for different contexts
- Export/import flag configurations (JSON)
- Flag change history/audit log

**UI Components:**

```
┌─────────────────────────────────────────────────────┐
│ Flag Management                  [Import] [Export] │
├─────────────────────────────────────────────────────┤
│ [Search flags...]                                   │
│                                                     │
│ ┌── Performance Flags ──────────────────────────┐  │
│ │                                                │  │
│ │ update_frequency_hz          [30 ▼]  [Edit]   │  │
│ │ Game loop update frequency                     │  │
│ │ ├─ Variants: 15Hz, 30Hz, 60Hz                 │  │
│ │ └─ Targeting: controller_count > 20 → 30Hz    │  │
│ │    [+ Add Rule]                                │  │
│ │                                                │  │
│ │ adaptive_hz                  [OFF] [Toggle]    │  │
│ │ Enable dynamic Hz adjustment                   │  │
│ │                                                │  │
│ └────────────────────────────────────────────────┘  │
│                                                     │
│ ┌── Experimental Flags ─────────────────────────┐  │
│ │                                                │  │
│ │ streaming_mode         [bidirectional ▼]      │  │
│ │ Controller data streaming mode                 │  │
│ │ ├─ A/B Test: 50% control, 50% treatment       │  │
│ │ └─ [Configure Experiment]                      │  │
│ │                                                │  │
│ │ enable_adaptive_rewards    [ON] [Toggle]       │  │
│ │ Player reward/punishment system                │  │
│ │                                                │  │
│ └────────────────────────────────────────────────┘  │
│                                                     │
│ [Preview Evaluation]                               │
│ Context: game_mode=FFA, controller_count=25        │
│ Result: update_frequency_hz=30, streaming=bidir    │
└─────────────────────────────────────────────────────┘
```

### 2. Player Profiles Page (`/players`)

**Features:**
- List all players with key stats
- Search/filter by serial, performance score, reward tier
- Sort by wins, K/D ratio, warnings, etc.
- Click player to view detailed profile
- Performance charts (warnings over time, win rate trend)
- Round history timeline
- Current reward tier badge
- Active config adjustments/overrides
- Battery and connection health indicators

**List View:**

```
┌─────────────────────────────────────────────────────┐
│ Player Profiles                    [Search: ___]   │
├─────────────────────────────────────────────────────┤
│ Serial          Score   Tier      Wins  K/D  Btry  │
├─────────────────────────────────────────────────────┤
│ 00:06:F7:12:34  ⭐ 92   EXCELLENT   15   2.3  🔋🔋🔋🔋 │
│ 00:06:F7:56:78  💚 78   GOOD        8   1.5  🔋🔋🔋   │
│ 00:06:F7:AB:CD  ⚪ 55   NEUTRAL     3   0.9  🔋🔋     │
│ 00:06:F7:EF:01  ⚠️ 32   POOR        1   0.4  🔋      │
└─────────────────────────────────────────────────────┘
```

**Detail View:**

```
┌─────────────────────────────────────────────────────┐
│ ← Back to List      Player: 00:06:F7:12:34:56      │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Performance Score: 92/100  [██████████░] EXCELLENT │
│ Reward Tier: ⭐ EXCELLENT                           │
│                                                     │
│ ┌── Game Mode Stats ──────────────────────────────┐│
│ │ FFA:                                             ││
│ │   Total Games: 25    Wins: 15 (60%)             ││
│ │   Avg Survival: 125.3s                          ││
│ │   Warnings: 42 (1.7/game)                       ││
│ │                                                  ││
│ │ Nonstop:                                         ││
│ │   Total Games: 12    K/D: 2.3                   ││
│ │   Best Streak: 8     Kills: 45  Deaths: 19      ││
│ │                                                  ││
│ │ Teams:                                           ││
│ │   Total Games: 8     Wins: 5 (63%)              ││
│ │   Role: Aggressive                               ││
│ └──────────────────────────────────────────────────┘│
│                                                     │
│ ┌── Hardware ──────────────────────────────────────┐│
│ │ Battery: 🔋🔋🔋🔋 4.2/5.0 (avg)                    ││
│ │ Connection: 95% stable                           ││
│ │ Disconnects: 2 total                             ││
│ └──────────────────────────────────────────────────┘│
│                                                     │
│ ┌── Active Adjustments ────────────────────────────┐│
│ │ Death Threshold: +0.1 (reward for wins)          ││
│ │ Feedback Intensity: 120% (good battery)          ││
│ └──────────────────────────────────────────────────┘│
│                                                     │
│ ┌── Recent Round History ──────────────────────────┐│
│ │ 2026-01-12 15:30  FFA   1st/10  Survived 145.2s  ││
│ │ 2026-01-12 15:15  FFA   3rd/8   Survived 92.1s   ││
│ │ 2026-01-12 15:00  Nonstop Win  8K/3D  Streak: 5  ││
│ │ [View All History]                                ││
│ └──────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

### 3. Experiment Dashboard (`/experiments`)

**Features:**
- List active and completed experiments
- Real-time metrics comparison (control vs treatment)
- Statistical analysis (t-tests, confidence intervals)
- Start/stop experiments
- Clone experiments with modified parameters
- Export experiment results to CSV
- Grafana embed for live metrics

**Dashboard View:**

```
┌─────────────────────────────────────────────────────┐
│ Experiments                       [+ New Experiment]│
├─────────────────────────────────────────────────────┤
│                                                     │
│ ┌── Active Experiments ───────────────────────────┐│
│ │                                                  ││
│ │ 🟢 Streaming Mode Comparison                     ││
│ │    Started: 2026-01-12 10:00                     ││
│ │    Rounds: 15/30 completed                       ││
│ │    Groups: Control (unary) vs Treatment (bidir)  ││
│ │                                                  ││
│ │    Preliminary Results:                          ││
│ │    Latency: 30.2ms vs 22.1ms (-27%) ✅           ││
│ │    CPU: 22% vs 24% (+9%) ⚠️                      ││
│ │    [View Details] [Stop]                         ││
│ │                                                  ││
│ └──────────────────────────────────────────────────┘│
│                                                     │
│ ┌── Completed Experiments ────────────────────────┐│
│ │                                                  ││
│ │ Hz Optimization (25 controllers)                 ││
│ │ Completed: 2026-01-10                            ││
│ │ Winner: 30Hz (balanced)                          ││
│ │ [View Report]                                    ││
│ │                                                  ││
│ └──────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

**Experiment Detail View:**

```
┌─────────────────────────────────────────────────────┐
│ ← Back    Experiment: Streaming Mode Comparison    │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Status: 🟢 RUNNING     Rounds: 15/30 (50%)          │
│                                                     │
│ ┌── Configuration ─────────────────────────────────┐│
│ │ Control Group:    streaming_mode = "unary"       ││
│ │ Treatment Group:  streaming_mode = "bidirectional"││
│ │ Assignment:       Round-robin                     ││
│ │ Game Mode:        FFA (25 controllers)           ││
│ └──────────────────────────────────────────────────┘│
│                                                     │
│ ┌── Live Metrics ─────────────────────────────────┐│
│ │                                                  ││
│ │ Latency (ms):                                    ││
│ │   Control:    30.2 ± 4.1                        ││
│ │   Treatment:  22.1 ± 3.2  (-27%) ✅             ││
│ │   p-value:    0.002 (significant)                ││
│ │                                                  ││
│ │ CPU Usage (%):                                   ││
│ │   Control:    22.1 ± 2.3                        ││
│ │   Treatment:  23.8 ± 2.1  (+8%) ⚠️              ││
│ │   p-value:    0.12 (not significant)             ││
│ │                                                  ││
│ │ Bandwidth (KB/s):                                ││
│ │   Control:    22.4 ± 1.2                        ││
│ │   Treatment:  23.1 ± 1.5  (+3%)                 ││
│ │   p-value:    0.35 (not significant)             ││
│ │                                                  ││
│ │ [Refresh] [Export CSV] [Stop Experiment]         ││
│ └──────────────────────────────────────────────────┘│
│                                                     │
│ ┌── Grafana Dashboard ────────────────────────────┐│
│ │ [Embedded Grafana panel showing metrics]         ││
│ └──────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

---

## API Implementation

### Backend Endpoints

**File**: `web-ui/api/flags.py`

```python
"""Flag management API endpoints."""

import json
import logging
from flask import Blueprint, request, jsonify

from web-ui.api.storage import get_flag_store

logger = logging.getLogger(__name__)
bp = Blueprint('flags', __name__, url_prefix='/api/flags')


@bp.route('/config', methods=['GET'])
def get_flags_config():
    """
    Get flag configuration in flagd JSON format.

    This endpoint is polled by flagd every 10 seconds for HTTP sync.

    Returns:
        JSON flag configuration
    """

    try:
        flag_store = get_flag_store()
        config = flag_store.get_all_flags()

        # Format for flagd
        flagd_config = {
            "flags": config
        }

        logger.debug(f"Served flags config: {len(config)} flags")

        return jsonify(flagd_config), 200

    except Exception as e:
        logger.error(f"Error getting flags config: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route('/list', methods=['GET'])
def list_flags():
    """
    List all flags with metadata.

    Returns:
        List of flag definitions
    """

    try:
        flag_store = get_flag_store()
        flags = flag_store.get_all_flags()

        return jsonify({
            "flags": flags,
            "count": len(flags)
        }), 200

    except Exception as e:
        logger.error(f"Error listing flags: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route('/update', methods=['POST'])
def update_flag():
    """
    Update a flag value.

    Request body:
        {
          "flag_key": "update_frequency_hz",
          "value": 60,
          "variant": "high_performance"
        }

    Returns:
        Updated flag
    """

    try:
        data = request.get_json()

        flag_key = data.get('flag_key')
        value = data.get('value')
        variant = data.get('variant')

        if not flag_key:
            return jsonify({"error": "flag_key required"}), 400

        flag_store = get_flag_store()
        updated_flag = flag_store.update_flag(flag_key, value, variant)

        logger.info(f"Updated flag '{flag_key}': {value} ({variant})")

        return jsonify(updated_flag), 200

    except Exception as e:
        logger.error(f"Error updating flag: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route('/evaluate', methods=['POST'])
def evaluate_flag():
    """
    Preview flag evaluation with context.

    Request body:
        {
          "flag_key": "update_frequency_hz",
          "context": {
            "game_mode": "FFA",
            "controller_count": 25
          }
        }

    Returns:
        Evaluated value
    """

    try:
        data = request.get_json()

        flag_key = data.get('flag_key')
        context = data.get('context', {})

        if not flag_key:
            return jsonify({"error": "flag_key required"}), 400

        flag_store = get_flag_store()
        result = flag_store.evaluate_flag(flag_key, context)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error evaluating flag: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
```

**File**: `web-ui/api/players.py`

```python
"""Player profile API endpoints."""

import logging
from flask import Blueprint, request, jsonify

from services.game_coordinator.storage.player_profiles import PlayerProfileManager

logger = logging.getLogger(__name__)
bp = Blueprint('players', __name__, url_prefix='/api/players')


@bp.route('/', methods=['GET'])
def list_players():
    """
    List all player profiles.

    Query params:
        ?sort_by=performance_score
        &order=desc
        &limit=50

    Returns:
        List of player profiles
    """

    try:
        sort_by = request.args.get('sort_by', 'performance_score')
        order = request.args.get('order', 'desc')
        limit = int(request.args.get('limit', 50))

        profile_manager = PlayerProfileManager()
        profiles = await profile_manager.get_all_profiles(
            sort_by=sort_by,
            order=order,
            limit=limit
        )

        # Convert to dict
        profiles_data = [p.to_dict() for p in profiles]

        return jsonify({
            "players": profiles_data,
            "count": len(profiles_data)
        }), 200

    except Exception as e:
        logger.error(f"Error listing players: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route('/<serial>', methods=['GET'])
def get_player_profile(serial: str):
    """
    Get detailed player profile.

    Returns:
        Player profile with stats
    """

    try:
        profile_manager = PlayerProfileManager()
        profile = await profile_manager.get_or_create_profile(serial, "")

        # Get round history
        history = await profile_manager.get_round_history(serial, limit=10)

        return jsonify({
            "profile": profile.to_dict(),
            "history": [r.to_dict() for r in history]
        }), 200

    except Exception as e:
        logger.error(f"Error getting player profile: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route('/<serial>/history', methods=['GET'])
def get_player_history(serial: str):
    """
    Get player round history.

    Query params:
        ?limit=20
        &offset=0

    Returns:
        List of round results
    """

    try:
        limit = int(request.args.get('limit', 20))
        offset = int(request.args.get('offset', 0))

        profile_manager = PlayerProfileManager()
        history = await profile_manager.get_round_history(
            serial,
            limit=limit,
            offset=offset
        )

        return jsonify({
            "history": [r.to_dict() for r in history],
            "count": len(history)
        }), 200

    except Exception as e:
        logger.error(f"Error getting player history: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
```

**File**: `web-ui/api/experiments.py`

```python
"""Experiment API endpoints."""

import logging
from flask import Blueprint, request, jsonify

from services.game_coordinator.storage.experiments import ExperimentStore

logger = logging.getLogger(__name__)
bp = Blueprint('experiments', __name__, url_prefix='/api/experiments')


@bp.route('/', methods=['GET'])
def list_experiments():
    """
    List all experiments.

    Query params:
        ?status=active

    Returns:
        List of experiments
    """

    try:
        status = request.args.get('status', 'all')

        experiment_store = ExperimentStore()

        if status == 'active':
            experiments = await experiment_store.get_active_experiments()
        else:
            experiments = await experiment_store.get_all_experiments()

        return jsonify({
            "experiments": [e.to_dict() for e in experiments],
            "count": len(experiments)
        }), 200

    except Exception as e:
        logger.error(f"Error listing experiments: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route('/<experiment_id>', methods=['GET'])
def get_experiment(experiment_id: str):
    """
    Get experiment details with results.

    Returns:
        Experiment configuration and results
    """

    try:
        experiment_store = ExperimentStore()
        experiment = await experiment_store.get_experiment(experiment_id)
        results = await experiment_store.get_experiment_results(experiment_id)

        return jsonify({
            "experiment": experiment.to_dict(),
            "results": results
        }), 200

    except Exception as e:
        logger.error(f"Error getting experiment: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route('/', methods=['POST'])
def create_experiment():
    """
    Create new experiment.

    Request body:
        {
          "name": "Streaming Mode Comparison",
          "type": "streaming_mode",
          "control_group": {"streaming_mode": "unary"},
          "treatment_groups": [{"streaming_mode": "bidirectional"}],
          "max_rounds": 30
        }

    Returns:
        Created experiment
    """

    try:
        data = request.get_json()

        experiment_store = ExperimentStore()
        experiment = await experiment_store.create_experiment(data)

        logger.info(f"Created experiment: {experiment.experiment_id}")

        return jsonify(experiment.to_dict()), 201

    except Exception as e:
        logger.error(f"Error creating experiment: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
```

---

## Frontend Implementation

### React Components

**File**: `web-ui/src/pages/FlagManagement.tsx`

```typescript
import React, { useState, useEffect } from 'react';
import { getFlagsConfig, updateFlag } from '../api/flags';

interface Flag {
  key: string;
  type: 'boolean' | 'number' | 'string';
  value: any;
  variants: any[];
  defaultVariant: string;
  category: string;
}

export const FlagManagement: React.FC = () => {
  const [flags, setFlags] = useState<Flag[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    loadFlags();
  }, []);

  const loadFlags = async () => {
    try {
      const response = await getFlagsConfig();
      setFlags(response.flags);
    } catch (error) {
      console.error('Failed to load flags:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (flagKey: string, currentValue: boolean) => {
    try {
      await updateFlag(flagKey, !currentValue);
      await loadFlags(); // Reload
    } catch (error) {
      console.error('Failed to update flag:', error);
    }
  };

  const filteredFlags = flags.filter(f =>
    f.key.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="flag-management">
      <h1>Flag Management</h1>

      <input
        type="text"
        placeholder="Search flags..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
      />

      {/* Group flags by category */}
      {['Performance', 'Gameplay', 'Experimental'].map(category => (
        <div key={category} className="flag-category">
          <h2>{category} Flags</h2>

          {filteredFlags
            .filter(f => f.category === category)
            .map(flag => (
              <FlagItem
                key={flag.key}
                flag={flag}
                onToggle={handleToggle}
              />
            ))}
        </div>
      ))}
    </div>
  );
};
```

**File**: `web-ui/src/pages/PlayerProfiles.tsx`

```typescript
import React, { useState, useEffect } from 'react';
import { getPlayers, getPlayerProfile } from '../api/players';

interface PlayerProfile {
  serial: string;
  performance_score: float;
  reward_tier: string;
  ffa_wins: number;
  nonstop_kd_ratio: number;
  average_battery_level: number;
}

export const PlayerProfiles: React.FC = () => {
  const [players, setPlayers] = useState<PlayerProfile[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState<string | null>(null);

  useEffect(() => {
    loadPlayers();
  }, []);

  const loadPlayers = async () => {
    try {
      const response = await getPlayers();
      setPlayers(response.players);
    } catch (error) {
      console.error('Failed to load players:', error);
    }
  };

  const getTierBadge = (tier: string) => {
    const badges = {
      'EXCELLENT': '⭐',
      'GOOD': '💚',
      'NEUTRAL': '⚪',
      'POOR': '⚠️',
      'CRITICAL': '🔴'
    };
    return badges[tier] || '⚪';
  };

  return (
    <div className="player-profiles">
      <h1>Player Profiles</h1>

      <table className="players-table">
        <thead>
          <tr>
            <th>Serial</th>
            <th>Score</th>
            <th>Tier</th>
            <th>Wins</th>
            <th>K/D</th>
            <th>Battery</th>
          </tr>
        </thead>
        <tbody>
          {players.map(player => (
            <tr
              key={player.serial}
              onClick={() => setSelectedPlayer(player.serial)}
            >
              <td>{player.serial}</td>
              <td>{player.performance_score.toFixed(0)}/100</td>
              <td>{getTierBadge(player.reward_tier)} {player.reward_tier}</td>
              <td>{player.ffa_wins}</td>
              <td>{player.nonstop_kd_ratio.toFixed(2)}</td>
              <td>{'🔋'.repeat(Math.ceil(player.average_battery_level))}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {selectedPlayer && (
        <PlayerDetailModal
          serial={selectedPlayer}
          onClose={() => setSelectedPlayer(null)}
        />
      )}
    </div>
  );
};
```

---

## Testing Strategy

### Backend API Tests

**File**: `tests/api/test_flags_api.py`

```python
def test_get_flags_config():
    """Test GET /api/flags/config."""

    response = client.get('/api/flags/config')

    assert response.status_code == 200
    data = response.get_json()
    assert 'flags' in data
    assert 'update_frequency_hz' in data['flags']


def test_update_flag():
    """Test POST /api/flags/update."""

    response = client.post('/api/flags/update', json={
        'flag_key': 'update_frequency_hz',
        'value': 60,
        'variant': 'high_performance'
    })

    assert response.status_code == 200

    # Verify flagd will sync this change
    config_response = client.get('/api/flags/config')
    flags = config_response.get_json()['flags']
    assert flags['update_frequency_hz']['defaultVariant'] == 'high_performance'
```

### Frontend Tests

**File**: `web-ui/src/__tests__/FlagManagement.test.tsx`

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { FlagManagement } from '../pages/FlagManagement';

test('renders flag list', async () => {
  render(<FlagManagement />);

  // Wait for flags to load
  await screen.findByText('update_frequency_hz');

  // Check flag is visible
  expect(screen.getByText('update_frequency_hz')).toBeInTheDocument();
});

test('toggles boolean flag', async () => {
  render(<FlagManagement />);

  const toggle = await screen.findByTestId('flag-toggle-enable_audio');

  fireEvent.click(toggle);

  // Verify API called (mock)
  expect(mockUpdateFlag).toHaveBeenCalledWith('enable_audio', false);
});
```

### Manual Testing

**Test 1: Flag Update Propagation**
- [ ] Open Web UI at http://localhost:8080/flags
- [ ] Toggle `enable_adaptive_rewards` flag ON
- [ ] Wait 10 seconds (flagd sync interval)
- [ ] Start new game
- [ ] Verify rewards are applied
- [ ] Check logs: "enable_adaptive_rewards: true"

**Test 2: Player Profile Display**
- [ ] Navigate to /players
- [ ] Verify list shows all connected players
- [ ] Click a player
- [ ] Verify detail modal shows stats, history
- [ ] Check performance score, reward tier correct

**Test 3: Experiment Dashboard**
- [ ] Navigate to /experiments
- [ ] Start "Streaming Mode Comparison"
- [ ] Play 10 games
- [ ] Refresh dashboard
- [ ] Verify metrics update in real-time
- [ ] Check control vs treatment comparison

---

## Files to Create

```
web-ui/
├── api/
│   ├── flags.py               # Flag management endpoints
│   ├── players.py             # Player profile endpoints
│   ├── experiments.py         # Experiment endpoints
│   └── storage/
│       ├── flag_store.py      # Flag persistence
│       └── experiment_store.py
│
└── src/
    ├── pages/
    │   ├── FlagManagement.tsx
    │   ├── PlayerProfiles.tsx
    │   └── ExperimentDashboard.tsx
    ├── components/
    │   ├── FlagItem.tsx
    │   ├── PlayerCard.tsx
    │   └── ExperimentCard.tsx
    └── api/
        ├── flags.ts           # API client functions
        ├── players.ts
        └── experiments.ts
```

---

## Success Criteria

- [ ] Flag management UI loads and displays all flags
- [ ] Can toggle boolean flags with immediate effect
- [ ] Can edit number/string flags via input fields
- [ ] flagd syncs from `/api/flags/config` every 10s
- [ ] Player profile list displays all players
- [ ] Player detail view shows stats, history, adjustments
- [ ] Experiment dashboard lists active experiments
- [ ] Real-time metrics update in experiment view
- [ ] Flag changes propagate within 10 seconds
- [ ] API endpoints respond <100ms (p95)
- [ ] Frontend tests pass
- [ ] Backend API tests pass

---

## Next Phase

**Phase 54: Experimentation Framework** will:
- Create experiment runner automation
- Build analysis tools with statistical tests
- Write experiment templates
- Generate comparison reports
- Enable systematic A/B testing

---

**End of Phase 53**
