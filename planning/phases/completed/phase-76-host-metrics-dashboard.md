# Phase 76: Host Metrics Dashboard

## Overview

Add Raspberry Pi host system monitoring to the observability stack using Prometheus Node Exporter. Provides visibility into CPU temperature, memory usage, disk space, and network I/O alongside existing service metrics.

**Status:** Completed

---

## Motivation

The existing observability stack (Phase 38) monitors JoustMania microservices but lacks visibility into the underlying Raspberry Pi hardware. This is critical for:

1. **Thermal Management**: PS Move Bluetooth polling is CPU-intensive; monitoring temperature prevents throttling
2. **Resource Planning**: Track memory/disk usage to identify capacity issues
3. **Performance Correlation**: Correlate service performance with host resource availability
4. **Proactive Alerts**: Detect issues before they impact gameplay

---

## Solution

### 1. Node Exporter Service

Added Prometheus Node Exporter to docker-compose.yml:

```yaml
node-exporter:
  image: prom/node-exporter:v1.7.0
  container_name: joustmania-node-exporter
  command:
    - '--path.procfs=/host/proc'
    - '--path.sysfs=/host/sys'
    - '--path.rootfs=/rootfs'
    - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    # Disable slow/unnecessary collectors for Raspberry Pi
    - '--no-collector.arp'
    - '--no-collector.bcache'
    - '--no-collector.bonding'
    - '--no-collector.btrfs'
    - '--no-collector.conntrack'
    - '--no-collector.edac'
    - '--no-collector.entropy'
    - '--no-collector.fibrechannel'
    - '--no-collector.infiniband'
    - '--no-collector.ipvs'
    - '--no-collector.mdadm'
    - '--no-collector.nfs'
    - '--no-collector.nfsd'
    - '--no-collector.nvme'
    - '--no-collector.powersupplyclass'
    - '--no-collector.pressure'
    - '--no-collector.rapl'
    - '--no-collector.schedstat'
    - '--no-collector.softnet'
    - '--no-collector.tapestats'
    - '--no-collector.textfile'
    - '--no-collector.timex'
    - '--no-collector.xfs'
    - '--no-collector.zfs'
  volumes:
    - /proc:/host/proc:ro
    - /sys:/host/sys:ro
    - /:/rootfs:ro
  networks:
    - joustmania
  restart: unless-stopped
  healthcheck:
    # Use /-/healthy endpoint, not /metrics (avoids broken pipe errors)
    test: ["CMD", "wget", "-q", "-O", "/dev/null", "http://localhost:9100/-/healthy"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 5s
```

### 2. Prometheus Scrape Configuration

Added scrape target in `services/prometheus/prometheus.yml`:

```yaml
- job_name: 'node'
  scrape_interval: 30s  # Longer interval for Pi
  scrape_timeout: 25s   # Must be < interval
  static_configs:
    - targets: ['node-exporter:9100']
      labels:
        instance: 'raspberry-pi'
```

**Note:** The scrape interval is set to 30s (vs 10s default) because node-exporter metric collection can be slow on Raspberry Pi. The timeout must be less than the interval.

### 3. Grafana Dashboard

Created comprehensive dashboard at `services/grafana/dashboards/host-metrics.json`:

#### Summary Row (Gauges)

| Panel | Metric | Thresholds |
|-------|--------|------------|
| CPU Temperature | `node_hwmon_temp_celsius` | 70°C yellow, 85°C red |
| CPU Usage | 100 - idle% | 70% yellow, 90% red |
| Memory Usage | (Total - Available) / Total | 70% yellow, 85% red |
| Disk Usage (/) | (Size - Avail) / Size | 70% yellow, 85% red |
| System Uptime | time - boot_time | - |
| Load Average | `node_load1` | 2 yellow, 4 red |

#### Time Series Charts

| Panel | Description |
|-------|-------------|
| CPU Usage by Mode | Stacked % breakdown (user, system, iowait, idle) |
| Memory Usage (Stacked) | Used, Buffers, Cached, Free in bytes |
| CPU Temperature Over Time | Historical temp with threshold lines |
| System Load Average | 1m, 5m, 15m load trends |
| Network I/O | Receive/Transmit bytes per interface (excludes loopback, veth, docker) |
| Disk I/O | Read/Write bytes per device (excludes loop devices) |
| Filesystem Usage | Bar gauge for all mounted filesystems |

---

## Key Metrics

### Raspberry Pi Temperature

```promql
node_hwmon_temp_celsius{job="node"}
```

Monitors CPU temperature. Raspberry Pi 4 throttles at:
- 80°C: Soft throttle begins
- 85°C: Hard throttle

### Memory Pressure

```promql
100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))
```

Shows effective memory usage accounting for buffers/cache.

### CPU Utilization

```promql
100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

Aggregate CPU usage across all cores.

### Disk Space

```promql
100 - ((node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100)
```

Root filesystem usage percentage.

---

## Files Modified

| File | Change |
|------|--------|
| `docker-compose.yml` | Added node-exporter service |
| `services/prometheus/prometheus.yml` | Added node job scrape config |
| `services/grafana/dashboards/host-metrics.json` | New dashboard (created) |

---

## Deployment

```bash
# Rebuild and restart services
docker compose up -d --build

# Verify node-exporter is running
docker compose ps node-exporter

# Check metrics endpoint
curl http://localhost:9100/metrics | grep node_cpu
```

The dashboard appears automatically in Grafana as "JoustMania - Host Metrics (Raspberry Pi)".

---

## Dashboard Preview

The dashboard provides at-a-glance health status:

```
┌──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│ CPU Temp     │ CPU Usage    │ Memory       │ Disk (/)     │ Uptime       │ Load (1m)    │
│   45°C       │    23%       │    67%       │    42%       │  3d 12h      │    1.2       │
│   [GAUGE]    │   [GAUGE]    │   [GAUGE]    │   [GAUGE]    │   [STAT]     │   [STAT]     │
└──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
┌────────────────────────────────────┬────────────────────────────────────┐
│ CPU Usage by Mode                  │ Memory Usage (Stacked)             │
│ [STACKED AREA CHART]               │ [STACKED AREA CHART]               │
└────────────────────────────────────┴────────────────────────────────────┘
┌────────────────────────────────────┬────────────────────────────────────┐
│ CPU Temperature Over Time          │ System Load Average                │
│ [LINE CHART with thresholds]       │ [LINE CHART: 1m, 5m, 15m]          │
└────────────────────────────────────┴────────────────────────────────────┘
┌────────────────────────────────────┬────────────────────────────────────┐
│ Network I/O                        │ Disk I/O                           │
│ [LINE CHART: RX up, TX down]       │ [LINE CHART: Read up, Write down]  │
└────────────────────────────────────┴────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────┐
│ Filesystem Usage                                                        │
│ [BAR GAUGE: /, /boot, etc.]                                            │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Broken Pipe Errors

**Symptom:** Repeated `write: broken pipe` errors in node-exporter logs.

**Cause:** The healthcheck was using `wget --spider` on `/metrics`, which closes the connection immediately while node-exporter is streaming thousands of metrics.

**Solution:** Use the dedicated health endpoint `/-/healthy` instead of `/metrics`.

### Scrape Timeout Errors

**Symptom:** Prometheus fails to start with "scrape timeout greater than scrape interval".

**Cause:** Default scrape_interval is 10s but we set scrape_timeout to 30s.

**Solution:** Set `scrape_interval: 30s` and `scrape_timeout: 25s` (timeout must be < interval).

### Slow Metric Collection

**Symptom:** Node-exporter takes too long to respond, causing timeouts.

**Cause:** Default collectors include many irrelevant subsystems (btrfs, nfs, zfs, etc.).

**Solution:** Disable unnecessary collectors with `--no-collector.*` flags. The essential collectors for Raspberry Pi are: cpu, cpufreq, diskstats, filesystem, hwmon, loadavg, meminfo, netdev, thermal_zone.

---

## Related Work

- **Phase 38**: Production metrics monitoring (Prometheus/Grafana setup)
- **Phase observability-1**: Loki log aggregation
- **Phase 48**: Controller connection strength monitoring (RSSI)
