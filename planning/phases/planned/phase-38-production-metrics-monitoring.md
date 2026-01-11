# Phase 38: Production Metrics & Monitoring

**Status:** 📊 PLANNED
**Priority:** HIGH
**Estimated Effort:** Large (3-5 days)

## Goal

Implement comprehensive metrics collection and monitoring for production deployment on Raspberry Pi. Provide real-time visibility into controller health, system performance, and game quality.

## Motivation

**Current Gaps:**
- No visibility into controller battery levels during gameplay
- Can't measure input lag or detect Bluetooth issues
- No way to detect performance degradation on Raspberry Pi
- Missing operational metrics for troubleshooting
- No alerting for critical issues (low battery, high CPU, disconnects)

**Production Needs:**
- Monitor 8+ controllers during multi-hour gaming sessions
- Detect and warn about low batteries before controllers die
- Track Bluetooth stability (disconnects, reconnects, signal quality)
- Measure end-to-end input latency to ensure responsive gameplay
- Monitor Raspberry Pi resource usage (CPU, memory, temperature)
- Track game quality metrics (completion rate, frame consistency)

**Value:**
- **Proactive**: Warn players about low batteries before they die mid-game
- **Diagnostic**: Quickly identify performance bottlenecks
- **Quality**: Measure and maintain 60 FPS gameplay
- **Reliability**: Detect service degradation or crashes
- **Planning**: Understand usage patterns for hardware decisions

## Architecture

### Metrics Stack

```
┌─────────────────────────────────────────────────────────┐
│                    Grafana (Port 3000)                  │
│              Visualization & Dashboards                 │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                 Prometheus (Port 9090)                   │
│          Metrics Collection & Storage                    │
└─┬─────┬──────┬──────┬──────┬──────┬──────┬─────────────┘
  │     │      │      │      │      │      │
  ▼     ▼      ▼      ▼      ▼      ▼      ▼
┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐
│Ctrl││Game││Menu││Set ││Supv││Web ││Audi│
│Mgr ││Cord││    ││    ││    ││UI  ││o   │
└────┘└────┘└────┘└────┘└────┘└────┘└────┘
/metrics endpoints (HTTP)
```

### Metrics Categories

**1. Controller Health Metrics** (controller_manager)
- Battery levels (gauge)
- Connection status (gauge: 0=disconnected, 1=connected)
- Input latency (histogram)
- Disconnect/reconnect events (counter)
- Active controller count (gauge)

**2. System Performance Metrics** (all services)
- CPU usage % (gauge)
- Memory usage MB (gauge)
- gRPC call latency (histogram)
- gRPC call success/error rate (counter)
- Active stream count (gauge)

**3. Game Quality Metrics** (game_coordinator)
- Frame time (histogram)
- Frame consistency % (gauge)
- GC pause duration (histogram)
- Games started/completed (counter)
- Average game duration (histogram)

**4. Infrastructure Metrics** (Docker + OS)
- Container CPU/memory (from Docker stats)
- Raspberry Pi CPU temperature (gauge)
- Disk usage (gauge)
- Network I/O (counter)

## Tasks

### Task 1: Prometheus Infrastructure Setup

**Files:** `docker-compose.yml`, `docker-compose.mock.yml`, `prometheus.yml`

- [ ] Add Prometheus container to docker-compose
  - Port 9090 for Prometheus UI
  - Port 9091 for Pushgateway (optional, for batch jobs)
  - Volume for persistent storage: `prometheus-data:/prometheus`
  - Configuration: `./prometheus.yml:/etc/prometheus/prometheus.yml`

**docker-compose.yml additions:**
```yaml
prometheus:
  image: prom/prometheus:v2.48.1
  container_name: joustmania-prometheus
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'
    - '--storage.tsdb.path=/prometheus'
    - '--storage.tsdb.retention.time=30d'
    - '--web.console.libraries=/usr/share/prometheus/console_libraries'
    - '--web.console.templates=/usr/share/prometheus/consoles'
  ports:
    - "9090:9090"
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    - prometheus-data:/prometheus
  networks:
    - joustmania
  restart: unless-stopped
  deploy:
    resources:
      limits:
        memory: 256M
      reservations:
        memory: 128M
```

- [ ] Create Prometheus configuration file
  - Scrape interval: 10s (balance between freshness and overhead)
  - Scrape all services on `/metrics` endpoint
  - Relabeling for service discovery

**prometheus.yml:**
```yaml
global:
  scrape_interval: 10s
  evaluation_interval: 10s
  external_labels:
    cluster: 'joustmania'
    environment: 'production'

scrape_configs:
  # Controller Manager
  - job_name: 'controller-manager'
    static_configs:
      - targets: ['controller-manager:8000']
        labels:
          service: 'controller-manager'

  # Game Coordinator
  - job_name: 'game-coordinator'
    static_configs:
      - targets: ['game-coordinator:8000']
        labels:
          service: 'game-coordinator'

  # Menu Service
  - job_name: 'menu'
    static_configs:
      - targets: ['menu:8000']
        labels:
          service: 'menu'

  # Settings Service
  - job_name: 'settings'
    static_configs:
      - targets: ['settings:8000']
        labels:
          service: 'settings'

  # Supervisor Service
  - job_name: 'supervisor'
    static_configs:
      - targets: ['supervisor:8000']
        labels:
          service: 'supervisor'

  # WebUI Service
  - job_name: 'webui'
    static_configs:
      - targets: ['webui:8000']
        labels:
          service: 'webui'

  # Audio Service
  - job_name: 'audio'
    static_configs:
      - targets: ['audio:8000']
        labels:
          service: 'audio'

  # Prometheus itself
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
```

### Task 2: Add Grafana for Visualization

**Files:** `docker-compose.yml`, `grafana/`

- [ ] Add Grafana container to docker-compose
  - Port 3000 for Grafana UI
  - Pre-configured Prometheus data source
  - Persistent dashboards volume

**docker-compose.yml additions:**
```yaml
grafana:
  image: grafana/grafana:10.2.3
  container_name: joustmania-grafana
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_USER=admin
    - GF_SECURITY_ADMIN_PASSWORD=joustmania
    - GF_USERS_ALLOW_SIGN_UP=false
    - GF_SERVER_ROOT_URL=http://localhost:3000
  volumes:
    - ./grafana/provisioning:/etc/grafana/provisioning:ro
    - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    - grafana-data:/var/lib/grafana
  depends_on:
    - prometheus
  networks:
    - joustmania
  restart: unless-stopped
  deploy:
    resources:
      limits:
        memory: 256M
      reservations:
        memory: 128M
```

- [ ] Create Grafana provisioning configs
  - Auto-configure Prometheus data source
  - Auto-load dashboards

**grafana/provisioning/datasources/prometheus.yml:**
```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

**grafana/provisioning/dashboards/dashboards.yml:**
```yaml
apiVersion: 1

providers:
  - name: 'JoustMania Dashboards'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
```

### Task 3: Instrument Controller Manager with Metrics

**Files:** `services/controller_manager/server.py`, `services/controller_manager/metrics.py`

- [ ] Add prometheus_client dependency to pyproject.toml
  ```toml
  prometheus-client = ">=0.19.0"
  ```

- [ ] Create metrics module for controller manager

**services/controller_manager/metrics.py:**
```python
"""Prometheus metrics for Controller Manager."""

from prometheus_client import Counter, Gauge, Histogram, Info

# Controller health metrics
controller_battery_level = Gauge(
    'controller_battery_level',
    'Controller battery level (0-5)',
    ['serial']
)

controller_connected = Gauge(
    'controller_connected',
    'Controller connection status (0=disconnected, 1=connected)',
    ['serial']
)

controller_disconnect_total = Counter(
    'controller_disconnect_total',
    'Total number of controller disconnects',
    ['serial']
)

controller_reconnect_total = Counter(
    'controller_reconnect_total',
    'Total number of controller reconnects',
    ['serial']
)

active_controllers = Gauge(
    'active_controllers_total',
    'Number of currently active controllers'
)

# Input latency metrics
controller_input_lag_seconds = Histogram(
    'controller_input_lag_seconds',
    'Time from button press to gRPC transmission',
    ['serial'],
    buckets=[0.001, 0.005, 0.010, 0.016, 0.020, 0.030, 0.050, 0.100, 0.200]
)

controller_state_update_hz = Gauge(
    'controller_state_update_hz',
    'Controller state update frequency',
    ['serial']
)

# Stream metrics
active_streams = Gauge(
    'controller_streams_active',
    'Number of active controller state streams'
)

stream_updates_total = Counter(
    'controller_stream_updates_total',
    'Total controller state updates sent',
    ['subscriber_id']
)

# Cache metrics (Phase 18 validation)
state_cache_hits_total = Counter(
    'controller_state_cache_hits_total',
    'Number of state cache hits (no rebuild needed)'
)

state_cache_misses_total = Counter(
    'controller_state_cache_misses_total',
    'Number of state cache misses (rebuild required)'
)

object_pool_utilization = Gauge(
    'controller_object_pool_utilization',
    'Object pool utilization percentage',
    ['pool_type']  # 'controller_state' or 'vector3'
)
```

- [ ] Integrate metrics into ControllerManagerServicer

**Key integration points:**
```python
# In __init__: Update active controller count
active_controllers.set(len(self.tracked_controllers))

# When controller connects
controller_connected.labels(serial=serial).set(1)
controller_battery_level.labels(serial=serial).set(battery)

# When controller disconnects
controller_connected.labels(serial=serial).set(0)
controller_disconnect_total.labels(serial=serial).inc()

# When controller reconnects
controller_reconnect_total.labels(serial=serial).inc()

# In _build_or_get_cached_state: Track cache efficiency
if cache_entry and cache_entry["snapshot_hash"] == current_hash:
    state_cache_hits_total.inc()
else:
    state_cache_misses_total.inc()

# Track object pool utilization
controller_state_pool_size = len(self.controller_state_pool.pool)
controller_state_total = 10  # pool_size from __init__
object_pool_utilization.labels(pool_type='controller_state').set(
    controller_state_pool_size / controller_state_total
)
```

- [ ] Add HTTP metrics endpoint (port 8000)

**services/controller_manager/server.py additions:**
```python
from prometheus_client import start_http_server
import metrics  # Import our metrics module

async def serve(port=50052, metrics_port=8000):
    """Start the ControllerManager async gRPC server."""
    # ... existing setup ...

    # Start Prometheus metrics HTTP server
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics available at http://0.0.0.0:{metrics_port}/metrics")

    # ... rest of server startup ...
```

- [ ] Add metrics to Dockerfile EXPOSE
  ```dockerfile
  EXPOSE 50052  # gRPC
  EXPOSE 8000   # Prometheus metrics
  ```

### Task 4: Instrument Game Coordinator with Metrics

**Files:** `services/game_coordinator/server.py`, `services/game_coordinator/metrics.py`

- [ ] Create metrics module for game coordinator

**services/game_coordinator/metrics.py:**
```python
"""Prometheus metrics for Game Coordinator."""

from prometheus_client import Counter, Gauge, Histogram, Summary

# Game lifecycle metrics
games_started_total = Counter(
    'games_started_total',
    'Total number of games started',
    ['game_mode']
)

games_completed_total = Counter(
    'games_completed_total',
    'Total number of games completed normally',
    ['game_mode']
)

games_force_ended_total = Counter(
    'games_force_ended_total',
    'Total number of games force-ended',
    ['game_mode']
)

current_game_state = Gauge(
    'current_game_state',
    'Current game state (0=idle, 1=starting, 2=running, 3=paused, 4=ended)',
    ['game_mode']
)

game_duration_seconds = Histogram(
    'game_duration_seconds',
    'Game duration in seconds',
    ['game_mode'],
    buckets=[30, 60, 120, 180, 300, 600, 900, 1800, 3600]
)

# Player metrics
active_players = Gauge(
    'game_active_players',
    'Number of active players in current game'
)

player_deaths_total = Counter(
    'player_deaths_total',
    'Total number of player deaths',
    ['game_mode', 'serial']
)

player_respawns_total = Counter(
    'player_respawns_total',
    'Total number of player respawns',
    ['game_mode', 'serial']
)

# Performance metrics
game_loop_frame_time_seconds = Histogram(
    'game_loop_frame_time_seconds',
    'Game loop frame processing time',
    ['game_mode'],
    buckets=[0.005, 0.010, 0.0167, 0.020, 0.030, 0.050, 0.100]
)

game_loop_frame_consistency = Gauge(
    'game_loop_frame_consistency_percent',
    'Percentage of frames within 16.7ms ± 2ms window',
    ['game_mode']
)

gc_pause_seconds = Histogram(
    'gc_pause_seconds',
    'Python garbage collection pause duration',
    buckets=[0.001, 0.002, 0.005, 0.010, 0.020, 0.050, 0.100]
)

# gRPC metrics
grpc_requests_total = Counter(
    'grpc_requests_total',
    'Total gRPC requests received',
    ['method', 'status']
)

grpc_request_duration_seconds = Histogram(
    'grpc_request_duration_seconds',
    'gRPC request duration',
    ['method'],
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0]
)
```

- [ ] Add frame timing tracking to game loops

**In game mode files (ffa.py, teams.py, etc.):**
```python
async def _game_loop(self):
    """Main game loop with frame timing metrics."""
    import time
    from services.game_coordinator import metrics

    frame_times = []  # Rolling window for consistency calculation
    target_frame_time = 1.0 / 60.0  # 16.7ms

    while self.running:
        frame_start = time.perf_counter()

        # Game logic here...
        await self._process_frame()

        # Measure frame time
        frame_end = time.perf_counter()
        frame_duration = frame_end - frame_start

        metrics.game_loop_frame_time_seconds.labels(
            game_mode=self.game_mode
        ).observe(frame_duration)

        # Track frame consistency (within 16.7ms ± 2ms)
        frame_times.append(frame_duration)
        if len(frame_times) > 300:  # 5 seconds at 60 FPS
            frame_times.pop(0)

        if len(frame_times) >= 60:  # Update every second
            consistent_frames = sum(
                1 for t in frame_times
                if abs(t - target_frame_time) < 0.002  # ±2ms
            )
            consistency_pct = (consistent_frames / len(frame_times)) * 100
            metrics.game_loop_frame_consistency.labels(
                game_mode=self.game_mode
            ).set(consistency_pct)

        # Sleep for remaining frame time
        sleep_time = max(0, target_frame_time - frame_duration)
        await asyncio.sleep(sleep_time)
```

- [ ] Add GC pause tracking

**In game coordinator server.py:**
```python
import gc
import time

# Enable GC stats collection
gc.set_debug(gc.DEBUG_STATS)

# Periodically measure GC pause time
async def track_gc_metrics():
    """Background task to track GC metrics."""
    while True:
        gc_start = time.perf_counter()
        gc.collect()
        gc_duration = time.perf_counter() - gc_start

        metrics.gc_pause_seconds.observe(gc_duration)

        await asyncio.sleep(30)  # Check every 30 seconds

# Start in serve()
asyncio.create_task(track_gc_metrics())
```

- [ ] Add HTTP metrics endpoint (port 8000)

### Task 5: Instrument Remaining Services

**Files:** Each service's `server.py` and `metrics.py`

- [ ] **Menu Service** - Basic gRPC metrics
- [ ] **Settings Service** - Basic gRPC metrics + settings read/write counters
- [ ] **Supervisor Service** - Service status gauges
- [ ] **WebUI Service** - HTTP request metrics
- [ ] **Audio Service** - Audio playback counters

**Common metrics for all services:**
```python
# CPU and memory (from psutil)
process_cpu_percent = Gauge('process_cpu_percent', 'Process CPU usage')
process_memory_mb = Gauge('process_memory_mb', 'Process memory usage in MB')

# gRPC metrics
grpc_requests_total = Counter(
    'grpc_requests_total',
    'Total gRPC requests',
    ['method', 'status']
)
grpc_request_duration_seconds = Histogram(
    'grpc_request_duration_seconds',
    'gRPC request latency',
    ['method']
)
```

### Task 6: Create Grafana Dashboards

**Files:** `grafana/dashboards/`

- [ ] **Dashboard 1: Controller Health** (`controller-health.json`)
  - Battery level gauges (colored: green >3, yellow 2-3, red <2)
  - Connection status indicators (green/red dots)
  - Input lag graph (p50, p95, p99)
  - Disconnect/reconnect event timeline
  - Active controller count

- [ ] **Dashboard 2: System Performance** (`system-performance.json`)
  - CPU usage per service (stacked area chart)
  - Memory usage per service (stacked area chart)
  - gRPC call latency heatmap
  - gRPC error rate
  - Active stream count
  - Raspberry Pi temperature (if available)

- [ ] **Dashboard 3: Game Quality** (`game-quality.json`)
  - Frame time distribution (histogram)
  - Frame consistency % (gauge - target >95%)
  - GC pause duration (graph)
  - Games started vs completed (comparison)
  - Average game duration per mode
  - Player count per game

- [ ] **Dashboard 4: Cache Performance** (`cache-performance.json`)
  - State cache hit rate % (Phase 18 validation)
  - Object pool utilization %
  - Allocations per second (before/after comparison)

**Example dashboard panel (Controller Battery):**
```json
{
  "type": "gauge",
  "title": "Controller Battery Levels",
  "targets": [
    {
      "expr": "controller_battery_level",
      "legendFormat": "{{serial}}"
    }
  ],
  "fieldConfig": {
    "defaults": {
      "min": 0,
      "max": 5,
      "thresholds": {
        "steps": [
          {"value": 0, "color": "red"},
          {"value": 2, "color": "yellow"},
          {"value": 3, "color": "green"}
        ]
      }
    }
  }
}
```

### Task 7: Add Alerting Rules

**Files:** `prometheus-alerts.yml`

- [ ] Create alert rules for critical conditions

**prometheus-alerts.yml:**
```yaml
groups:
  - name: joustmania_alerts
    interval: 30s
    rules:
      # Controller alerts
      - alert: ControllerLowBattery
        expr: controller_battery_level < 2
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Controller {{$labels.serial}} has low battery"
          description: "Battery level is {{$value}}/5. Replace or charge soon."

      - alert: ControllerDisconnected
        expr: controller_connected == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "Controller {{$labels.serial}} disconnected"
          description: "Controller lost connection during active game."

      - alert: HighInputLatency
        expr: histogram_quantile(0.95, rate(controller_input_lag_seconds_bucket[5m])) > 0.050
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High input latency detected"
          description: "P95 input latency is {{$value}}s (>50ms threshold)."

      # System alerts
      - alert: HighCPUUsage
        expr: process_cpu_percent > 90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage on {{$labels.service}}"
          description: "CPU usage is {{$value}}% for 5 minutes."

      - alert: HighMemoryUsage
        expr: process_memory_mb > 450
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on {{$labels.service}}"
          description: "Memory usage is {{$value}}MB, approaching limit."

      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{$labels.job}} is down"
          description: "Prometheus cannot scrape metrics from {{$labels.job}}."

      # Game quality alerts
      - alert: PoorFrameConsistency
        expr: game_loop_frame_consistency_percent < 90
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Poor frame consistency in {{$labels.game_mode}}"
          description: "Only {{$value}}% of frames within target (should be >95%)."

      - alert: HighGCPauses
        expr: histogram_quantile(0.95, rate(gc_pause_seconds_bucket[5m])) > 0.010
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "High garbage collection pauses"
          description: "P95 GC pause is {{$value}}s (>10ms threshold)."

      - alert: GameCrashRate
        expr: rate(games_force_ended_total[10m]) / rate(games_started_total[10m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High game crash rate"
          description: "{{$value | humanizePercentage}} of games are crashing."
```

- [ ] Update prometheus.yml to include alert rules
  ```yaml
  rule_files:
    - 'prometheus-alerts.yml'
  ```

### Task 8: Add psutil for System Metrics

**Files:** All service `pyproject.toml`, metrics collection code

- [ ] Add psutil dependency to all services
  ```toml
  psutil = ">=5.9.0"
  ```

- [ ] Create system metrics collector

**Common code for all services:**
```python
import psutil
from prometheus_client import Gauge

# System metrics
process_cpu_percent = Gauge('process_cpu_percent', 'CPU usage %')
process_memory_mb = Gauge('process_memory_mb', 'Memory usage MB')
process_threads = Gauge('process_threads', 'Number of threads')

async def update_system_metrics():
    """Background task to update system metrics."""
    process = psutil.Process()
    while True:
        process_cpu_percent.set(process.cpu_percent(interval=1))
        process_memory_mb.set(process.memory_info().rss / 1024 / 1024)
        process_threads.set(process.num_threads())
        await asyncio.sleep(10)

# Start in serve()
asyncio.create_task(update_system_metrics())
```

### Task 9: Add Raspberry Pi Temperature Monitoring

**Files:** New `services/system_monitor/` (optional separate service)

- [ ] Create lightweight system monitor service (optional)
  - Read `/sys/class/thermal/thermal_zone0/temp` for CPU temp
  - Expose as Prometheus metric
  - Alert if temp > 80°C

**OR**

- [ ] Add to supervisor service (simpler)
  ```python
  def read_cpu_temperature():
      """Read Raspberry Pi CPU temperature."""
      try:
          with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
              temp = int(f.read().strip()) / 1000.0
              return temp
      except Exception:
          return None

  cpu_temperature_celsius = Gauge('cpu_temperature_celsius', 'CPU temperature')

  async def update_temperature():
      while True:
          temp = read_cpu_temperature()
          if temp:
              cpu_temperature_celsius.set(temp)
          await asyncio.sleep(30)
  ```

### Task 10: End-to-End Latency Tracking

**Files:** `services/controller_manager/server.py`, `services/game_coordinator/games/*.py`

- [ ] Add timestamp to controller state messages

**Update proto/controller_manager.proto:**
```protobuf
message ControllerState {
    // ... existing fields ...

    // Timestamp when button state was read (for latency tracking)
    int64 input_timestamp_ns = 20;  // nanoseconds since epoch
}
```

- [ ] Capture timestamp in controller manager when reading button state
  ```python
  import time

  # When reading button state
  input_timestamp_ns = time.time_ns()

  # Add to ControllerState message
  controller_state.input_timestamp_ns = input_timestamp_ns
  ```

- [ ] Measure latency in game coordinator when processing input
  ```python
  # In game loop when processing controller state
  current_time_ns = time.time_ns()
  latency_seconds = (current_time_ns - controller_state.input_timestamp_ns) / 1e9

  metrics.end_to_end_input_latency_seconds.labels(
      game_mode=self.game_mode,
      serial=controller_state.serial
  ).observe(latency_seconds)
  ```

### Task 11: Documentation

**Files:** `docs/monitoring.md`, `README.md`

- [ ] Create monitoring documentation
  - How to access Grafana (http://localhost:3000)
  - Default credentials
  - Dashboard overview
  - How to interpret metrics
  - Alert descriptions and troubleshooting

- [ ] Update README.md with monitoring section
  - Quick start for viewing metrics
  - Links to dashboards
  - Common troubleshooting scenarios

- [ ] Add metric naming conventions guide
  - Prometheus best practices
  - Label usage guidelines
  - When to add new metrics

### Task 12: Testing & Validation

- [ ] Test metrics collection with mock controllers
  - Start mock environment
  - Verify all metrics are being exported
  - Check Prometheus scraping (targets page)
  - View dashboards in Grafana

- [ ] Validate alert rules
  - Trigger low battery condition (mock controller API)
  - Trigger high CPU usage (stress test)
  - Verify alerts fire in Prometheus

- [ ] Load testing
  - Run 8-player game for 1 hour
  - Monitor frame consistency
  - Check for memory leaks
  - Verify cache hit rate remains high (Phase 18)

- [ ] Raspberry Pi testing
  - Deploy to actual Raspberry Pi
  - Monitor CPU temperature
  - Verify resource limits are working
  - Test with real PSMove controllers

## Expected Metrics

### Controller Health
- **Battery Level**: 0-5 gauge per controller (updated every 10s)
- **Connection Status**: 0/1 per controller
- **Input Lag P95**: <20ms (target), warn >50ms
- **Disconnect Rate**: <0.1 disconnects/hour per controller
- **Active Controllers**: Typically 4-8

### System Performance
- **Controller Manager CPU**: 20-25% during gameplay
- **Game Coordinator CPU**: 25-30% during gameplay
- **Total System CPU**: <60% on Raspberry Pi 4
- **Memory Usage**: <1.5GB total across all services
- **gRPC Latency P95**: <5ms internal calls

### Game Quality
- **Frame Consistency**: >95% of frames within 16.7ms ± 2ms
- **GC Pause P95**: <5ms
- **Game Completion Rate**: >95% (detect crashes)
- **Average Game Duration**: 2-5 minutes for FFA
- **Deaths per Game**: 5-20 depending on mode

### Cache Performance (Phase 18 Validation)
- **State Cache Hit Rate**: >90% (validate Phase 18 is working)
- **Object Pool Utilization**: 30-50% (pools not exhausted)
- **Allocations/sec**: <50/sec (down from 240/sec pre-Phase 18)

## Success Criteria

- ✅ Prometheus successfully scrapes all services every 10s
- ✅ Grafana dashboards display real-time metrics
- ✅ Controller battery levels visible during gameplay
- ✅ Input latency P95 < 20ms during normal operation
- ✅ Alerts fire correctly for low battery, high CPU, disconnects
- ✅ Frame consistency >95% during 8-player games
- ✅ Cache hit rate >90% (validates Phase 18 optimizations)
- ✅ System runs stably for 8+ hours with metrics enabled
- ✅ Metrics add <5% CPU overhead
- ✅ Dashboard loads in <2 seconds

## Dependencies

- Phase 18 (Game Loop CPU Optimization) - ✅ Complete (validates optimizations)
- Phase 26 (Critical Performance Fixes) - ✅ Complete (metrics for channel pooling)
- Docker and Docker Compose setup - ✅ Complete

## Performance Impact

**Prometheus:**
- Memory: ~128MB (30 days retention)
- CPU: <2% (scraping every 10s)
- Disk: ~100MB/week for metrics storage

**Grafana:**
- Memory: ~64MB
- CPU: <1%

**Per-Service Overhead:**
- prometheus_client: ~5MB memory
- CPU: <1% for metric updates
- HTTP endpoint: Minimal (only scraped every 10s)

**Total Overhead:** ~5-8% CPU, ~200MB memory across all services

## Notes

- Metrics retention: 30 days in Prometheus (configurable)
- Alert notifications: Can integrate with Slack, email, PagerDuty
- Dashboard export: JSON files can be version controlled
- Metrics are **pull-based** (Prometheus scrapes services)
- Optional: Add Alertmanager for advanced alert routing
- Optional: Add push gateway for short-lived batch jobs
- Consider: Lightweight alternatives like VictoriaMetrics for lower memory usage on RPi

## Future Enhancements

- **Distributed Tracing Integration**: Correlate traces (Jaeger) with metrics (Prometheus)
- **Anomaly Detection**: ML-based alerting for unusual patterns
- **Historical Analysis**: Long-term metric storage for trend analysis
- **Player Profiles**: Per-player statistics tracking
- **Tournament Mode**: Special metrics for competitive play
- **Remote Monitoring**: Secure access to metrics from mobile devices

## Related Files

**Primary:**
- All service `server.py` files (add metrics endpoints)
- `docker-compose.yml` (add Prometheus + Grafana)
- `prometheus.yml` (scrape configuration)
- `prometheus-alerts.yml` (alert rules)
- `grafana/dashboards/*.json` (dashboard definitions)

**New:**
- `services/*/metrics.py` (metrics definitions per service)
- `docs/monitoring.md` (monitoring documentation)
- `grafana/provisioning/` (Grafana auto-configuration)
