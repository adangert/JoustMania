# JoustMania Observability Quick Start Guide

**Phase 43: Performance Monitoring Tools**

This guide shows you how to use JoustMania's observability tools to monitor and optimize performance with 25 controllers.

---

## What's Available

### 1. Live Performance Dashboard
**File:** `tools/live_dashboard.py`

**What it shows:**
- Real-time Hz and latency
- CPU usage
- Controller count
- Per-USB-hub breakdown
- ASCII graphs of metrics over time
- Health status assessment

**Usage:**
```bash
python3 tools/live_dashboard.py --hz 30 --duration 300
```

**When to use:**
- During gameplay to see real-time performance
- For talk demos (audience-friendly visualization)
- To validate configuration changes

---

### 2. Multi-Hub Performance Monitor
**File:** `tools/monitor_multi_hub_performance.py`

**What it shows:**
- Per-hub controller count
- Per-hub latency statistics
- Disconnect detection
- Latency spikes (>100ms gaps)
- Health assessment (EXCELLENT/GOOD/FAIR/POOR)
- Detailed recommendations

**Usage:**
```bash
python3 tools/monitor_multi_hub_performance.py
```

**When to use:**
- Validating USB hub setup
- Diagnosing disconnection issues
- Comparing powered vs unpowered hubs
- Before large-scale events (25+ controllers)

---

### 3. Prometheus Metrics
**Integration:** Already built into game coordinator

**New metrics (Phase 43):**
- `game_configured_update_frequency_hz` - Configured game loop Hz
- `game_actual_update_frequency_hz` - Measured actual Hz
- `game_loop_latency_ms` - Game loop iteration time
- `game_loop_iterations_total` - Total iterations counter
- `config_changes_total` - Configuration change counter

**Access:**
```bash
# Metrics endpoint
curl http://localhost:9090/metrics | grep game_

# Or view in Grafana
open http://localhost:3000
```

**When to use:**
- Long-term performance tracking
- Grafana dashboards for talks
- Historical trend analysis
- Alerting on anomalies

---

## Quick Start: Testing with 25 Controllers

### Step 1: Setup

```bash
# Terminal 1: Start JoustMania services
cd /home/simon/JoustMania
docker-compose up

# Terminal 2: Start live dashboard
python3 tools/live_dashboard.py --hz 30

# Terminal 3: Game coordinator logs
docker logs -f joustmania-game-coordinator
```

### Step 2: Connect Controllers

1. Connect 25 controllers across 2 unpowered USB hubs
   - Hub 1 (USB Port 1): 15 controllers (3 dongles)
   - Hub 2 (USB Port 2): 10 controllers (2 dongles)

2. Wait for all controllers to pair (green LED flash)

3. Mark controllers ready (trigger button press)

### Step 3: Start Game

Via menu or gRPC:
```bash
# Start FFA game with 25 players
grpcurl -plaintext -d '{"game_mode": "FFA", "force_start": true}' \
    localhost:50053 joustmania.game_coordinator.GameCoordinatorService/StartGame
```

### Step 4: Monitor Performance

Watch the live dashboard:
```
🎮 JOUSTMANIA LIVE PERFORMANCE DASHBOARD
========================================
📊 CURRENT PERFORMANCE
  Frequency:    30.2 Hz
  Latency:      32.8 ms
  Controllers:   25
  CPU Usage:    22.3%
  Bandwidth:    22.4 KB/s

🔌 USB HUB BREAKDOWN
  Hub 1:  15 controllers ███████
  Hub 2:  10 controllers █████

📈 CPU USAGE (last 60s)
[ASCII graph]

🚦 HEALTH STATUS
  Latency:      ✅ EXCELLENT (<40ms)
  CPU Load:     ✅ EXCELLENT (<30%)
  Controllers:  ✅ FULL SCALE (25+)
```

### Step 5: Validate USB Hubs

```bash
# Terminal 4: Run hub monitor
python3 tools/monitor_multi_hub_performance.py
```

Expected output after 2 minutes:
```
🔌 PER-HUB BREAKDOWN:
  Hub 1 (USB Port 1):
    Controllers: 15
    Avg gap: 32.1ms
    Max gap: 45.2ms
    ✅ No missing updates

  Hub 2 (USB Port 2):
    Controllers: 10
    Avg gap: 33.8ms
    Max gap: 52.1ms
    ✅ No missing updates

🏥 HEALTH ASSESSMENT: ✅ EXCELLENT
```

---

## Common Use Cases

### Use Case 1: Validate USB Hub Setup

**Question:** Do unpowered USB hubs work with 25 controllers?

**Test:**
```bash
# Connect controllers across 2 unpowered hubs
# Run monitor for 5 minutes during gameplay
python3 tools/monitor_multi_hub_performance.py

# Check health assessment at end
# - EXCELLENT: Setup works!
# - POOR/CRITICAL: Need powered hubs
```

**Decision:**
- 0-5 disconnects: Unpowered setup works
- >20 disconnects: Upgrade to powered hubs

---

### Use Case 2: Measure Current Performance

**Question:** What's our current CPU/latency with 25 controllers at 30Hz?

**Test:**
```bash
# Start game with 25 controllers
# Run live dashboard for 5+ minutes
python3 tools/live_dashboard.py --hz 30

# Note metrics at steady state:
# - CPU usage: ~22%
# - Latency: ~33ms
# - Health: EXCELLENT
```

**Baseline established:** 30Hz is efficient and responsive

---

### Use Case 3: Compare 30Hz vs 60Hz (Manual)

**Question:** Is 60Hz better than 30Hz?

**Current approach (Phase 43):**
1. Edit `services/game_coordinator/games/base.py`: `UPDATE_FREQUENCY = 30`
2. Restart services
3. Run 5-minute test with live dashboard
4. Record: CPU, latency, disconnects
5. Edit `UPDATE_FREQUENCY = 60`
6. Restart and repeat test
7. Compare results

**Result (expected):**
| Config | Hz   | Latency | CPU | Assessment |
|--------|------|---------|-----|------------|
| 30Hz   | 30.1 | 33.2ms  | 22% | ✅ Optimal |
| 60Hz   | 59.8 | 16.7ms  | 38% | ⚠️ Higher CPU |

**Decision:** 30Hz wins (50% less CPU, latency difference imperceptible)

**Future (Phase 44):** OpenFeature will enable A/B testing without manual editing

---

## Prometheus Metrics Guide

### Viewing Metrics

```bash
# Raw Prometheus metrics
curl http://localhost:9090/metrics | grep game_configured_update_frequency_hz

# Example output:
# game_configured_update_frequency_hz 30.0
```

### Grafana Dashboards

**Create custom dashboard:**
1. Open Grafana: `http://localhost:3000`
2. Create new dashboard
3. Add panels:

**Panel 1: Actual vs Configured Hz**
```promql
game_actual_update_frequency_hz
game_configured_update_frequency_hz
```

**Panel 2: Game Loop Latency (p50, p95, p99)**
```promql
histogram_quantile(0.50, game_loop_latency_ms_bucket{mode="FFA"})
histogram_quantile(0.95, game_loop_latency_ms_bucket{mode="FFA"})
histogram_quantile(0.99, game_loop_latency_ms_bucket{mode="FFA"})
```

**Panel 3: CPU Usage**
```promql
process_cpu_percent
```

### Alerting (Optional)

```yaml
# Example alert: High latency
- alert: HighGameLoopLatency
  expr: histogram_quantile(0.95, game_loop_latency_ms_bucket) > 100
  for: 5m
  annotations:
    summary: "Game loop latency p95 > 100ms"
```

---

## Troubleshooting

### Dashboard shows no data

**Symptom:** Live dashboard says "No data yet" or shows 0 controllers

**Fix:**
1. Check services are running: `docker ps`
2. Check game is started (not just menu)
3. Verify gRPC connection: `grpcurl -plaintext localhost:50051 list`

---

### Hub monitor shows high disconnects

**Symptom:** Monitor reports >20 disconnects, POOR/CRITICAL health

**Likely causes:**
1. **Power issue:** All dongles on one unpowered hub
2. **Bandwidth issue:** USB 2.0 hub saturated
3. **Interference:** USB 3.0 port interfering with Bluetooth

**Fixes:**
1. Distribute dongles across multiple hubs
2. Use USB 2.0 ports (not USB 3.0) for Bluetooth
3. Upgrade to powered USB 3.0 hub

---

### Metrics not updating in Grafana

**Symptom:** Grafana shows old/stale metrics

**Fix:**
1. Check Prometheus scraping: `curl http://localhost:9090/targets`
2. Verify scrape interval (default: 15s)
3. Refresh Grafana dashboard (Ctrl+R)

---

## Tips for Talks/Demos

### Preparation (15 minutes before)

- [ ] Start all services
- [ ] Connect 25 controllers
- [ ] Verify all paired and ready
- [ ] Open 3 terminals:
  - Terminal 1: Live dashboard
  - Terminal 2: Game logs
  - Terminal 3: Hub monitor (run once)
- [ ] Test run 1 game to verify everything works

### Demo Flow

1. **Show problem:** Hardcoded `UPDATE_FREQUENCY = 30`
2. **Show tools:** Live dashboard running in terminal
3. **Start game:** 25 controllers in FFA
4. **Show metrics:** Real-time Hz, CPU, latency
5. **Validate USB:** Show hub monitor results
6. **Analyze:** Discuss observed performance
7. **(Future) Show OpenFeature:** Change Hz via flags (Phase 44)

### Key Talking Points

- "Observability enables data-driven decisions"
- "Measuring performance at scale (25 controllers)"
- "Per-hub breakdown identified USB constraints"
- "Real-time monitoring catches issues early"
- "Metrics provide proof, not guesses"

---

## Next Steps

**Phase 44:** OpenFeature Integration
- Dynamic Hz via feature flags (flagd)
- Automated A/B testing (30Hz vs 60Hz)
- Remote configuration changes
- Experimentation framework

**See:** `planning/phases/planned/phase-44-openfeature-configuration-experiments.md`

---

## Summary

**Phase 43 provides:**
✅ Live performance monitoring
✅ Per-hub USB validation
✅ Prometheus metrics integration
✅ Real-time dashboards
✅ Health status assessment

**What's missing (Phase 44):**
⏳ Dynamic configuration via OpenFeature
⏳ Automated A/B testing
⏳ Remote flag management

**Current capability:**
You can now measure, monitor, and validate your 25-controller setup!
