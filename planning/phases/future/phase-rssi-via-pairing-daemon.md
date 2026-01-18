# Phase: RSSI Monitoring via Pairing Daemon

## Overview

Move RSSI (signal strength) collection from the containerized controller-manager to the host-side pairing daemon. This enables reliable Bluetooth signal monitoring in containerized and Kubernetes environments.

**Status:** Planned

---

## Problem

The controller-manager runs in a Docker container and cannot access host Bluetooth HCI connections due to network namespace isolation. Even with `privileged: true` and `/dev` mounts, `hcitool con` and `hcitool rssi` return empty results from within containers.

Current workaround: RSSI panel shows "Host Only" and filters out 0 values.

---

## Proposed Solution

The **pairing daemon** already runs on the host (outside Docker) to handle Bluetooth pairing. Extend it to:

1. Periodically collect RSSI for connected controllers using `hcitool rssi`
2. Publish RSSI values to Redis with TTL
3. Controller-manager reads RSSI from Redis instead of querying Bluetooth directly

### Architecture

```
[Host]                              [Docker/K8s]
┌─────────────────┐                ┌─────────────────────┐
│ Pairing Daemon  │                │ Controller Manager  │
│                 │    Redis       │                     │
│ - Bluetooth     │ ──────────────>│ - Reads RSSI from   │
│   pairing       │   rssi:{addr}  │   Redis             │
│ - RSSI polling  │                │ - Exposes metrics   │
│   (10s interval)│                │                     │
└─────────────────┘                └─────────────────────┘
```

---

## Implementation Tasks

### Task 1: Add RSSI Collection to Pairing Daemon

**File:** `services/pairing_daemon/pairing_daemon.py`

- Add periodic RSSI check (every 10 seconds)
- Use `hcitool con` to get connected device addresses
- Use `hcitool rssi <addr>` to get signal strength
- Publish to Redis: `SET rssi:<address> <value> EX 30`

```python
async def collect_rssi():
    """Collect RSSI for all connected Bluetooth devices."""
    # Get connected addresses from hcitool con
    result = subprocess.run(["hcitool", "con"], capture_output=True, text=True)
    for line in result.stdout.split("\n"):
        if "ACL" in line:
            address = line.split()[2]
            rssi_result = subprocess.run(
                ["hcitool", "rssi", address],
                capture_output=True, text=True
            )
            if "RSSI return value:" in rssi_result.stdout:
                rssi = int(rssi_result.stdout.split(":")[-1].strip())
                redis.set(f"rssi:{address.lower()}", rssi, ex=30)
```

### Task 2: Update Controller Manager to Read from Redis

**File:** `services/controller_manager/bluetooth_backend.py`

- Modify `get_rssi()` to read from Redis instead of calling hcitool
- Fall back to 0 if key doesn't exist (no data from host)

```python
async def get_rssi(self, serial: str) -> int | None:
    """Get RSSI from Redis (published by pairing daemon)."""
    key = f"rssi:{serial.lower()}"
    value = await self.redis.get(key)
    if value:
        return int(value)
    return None
```

### Task 3: Add Prometheus Metrics to Pairing Daemon

The pairing daemon should also expose RSSI as Prometheus metrics directly:
- `pairing_daemon_controller_rssi_dbm{address="..."}`

This provides redundancy and allows direct scraping from the host.

### Task 4: Kubernetes DaemonSet

For K8s deployment, the pairing daemon becomes a DaemonSet that runs on nodes with Bluetooth hardware:
- Node selector for Bluetooth-enabled nodes
- Host network mode for Bluetooth access
- Publishes to cluster Redis

---

## Redis Key Schema

| Key | Value | TTL | Description |
|-----|-------|-----|-------------|
| `rssi:<address>` | Integer (dBm) | 30s | Signal strength for controller |

Address format: lowercase with colons (e.g., `00:06:f5:ed:88:8c`)

---

## Success Criteria

- [ ] RSSI values appear on dashboard when running in Docker
- [ ] RSSI values appear on dashboard when running in Kubernetes
- [ ] No host-level access required from controller-manager container
- [ ] Pairing daemon exposes RSSI via Prometheus metrics

---

## Files to Modify

| File | Changes |
|------|---------|
| `services/pairing_daemon/pairing_daemon.py` | Add RSSI collection and Redis publishing |
| `services/controller_manager/bluetooth_backend.py` | Read RSSI from Redis |
| `services/controller_manager/monitoring.py` | Update RSSI check to use Redis |
| `k8s/pairing-daemon-daemonset.yaml` | NEW - K8s DaemonSet for pairing daemon |

---

## Related Work

- Phase 48: Original RSSI monitoring implementation
- Phase 78: Pairing daemon observability (metrics/tracing foundation)
