# Phase 73: Docker Controller Hot-Plug Support

## Overview

Enable PS Move controller hot-plug support in Docker containers. Controllers can now connect and disconnect dynamically after container startup without requiring a container restart.

**Status:** Completed

---

## Problem

When PS Move controllers connected via Bluetooth after the controller-manager container started, they weren't detected:

1. **Device Creation**: New Bluetooth connections create `/dev/hidrawN` devices dynamically on the host
2. **Docker Limitation**: Bind-mounting `/dev:/dev` creates a point-in-time snapshot at container start
3. **Invisible Devices**: New hidraw devices created after container start weren't visible inside container
4. **Invalid Handles**: `psmove.PSMove(index)` returned objects with null C pointers, causing SWIG errors:
   ```
   in method 'PSMove_get_serial', argument 1 of type 'PSMove *'
   ```

### Symptoms

```
# Host sees 4 devices:
$ ls /dev/hidraw*
/dev/hidraw0  /dev/hidraw1  /dev/hidraw2  /dev/hidraw3

# Container only sees 1 (existed at startup):
$ docker exec joustmania-controller-manager ls /dev/hidraw*
/dev/hidraw0
```

---

## Solution

Two Docker configuration changes enable hot-plug:

### 1. Host PID Namespace

```yaml
pid: "host"
```

Run container in host's PID namespace. This improves device visibility by sharing the host's view of `/proc` and device events.

### 2. Slave Mount Propagation

```yaml
volumes:
  - /dev:/dev:rslave
```

Use recursive slave (`rslave`) mount propagation. When new devices are created on the host's `/dev`, the changes propagate into the container's mount.

### Complete Configuration

```yaml
controller-manager:
  privileged: true
  pid: "host"
  volumes:
    - /var/run/dbus:/var/run/dbus:ro
    - /var/lib/bluetooth:/var/lib/bluetooth:ro
    - ${HOME}/.psmoveapi:/root/.psmoveapi:ro
    - /dev:/dev:rslave  # rslave for hot-plug propagation
```

---

## Code Changes

### Retry Logic for New Controllers

When psmove detects a count change, newly connected controllers may not be immediately ready. Added retry mechanism:

**File:** `services/controller_manager/bluetooth_backend.py`

```python
# Retry logic: new controllers may not be immediately ready
max_retries = 3
retry_delay = 0.5  # seconds

for attempt in range(max_retries):
    # ... scan controllers ...

    if len(seen_serials) >= count or not failed_indices:
        break

    if attempt < max_retries - 1:
        logger.info(f"Retry {attempt + 1}/{max_retries} in {retry_delay}s...")
        time.sleep(retry_delay)
```

This handles the race condition where `psmove.count_connected()` returns a higher count before all controllers are fully initialized.

---

## Verification

Hot-plug confirmed working:

```
# Container starts with 0 controllers
Found 0 PS Move controllers
Backend initialized successfully

# First 2 controllers connect
Controller count changed: 0 -> 2, tracked: 0
New controller connected: 00:07:04:a8:f2:2f (index 0)
New controller connected: e0:ae:5e:4e:5d:90 (index 1)
Scan complete: found 2 serials, now tracking 2

# Third controller connects later
Controller count changed: 2 -> 3, tracked: 2
New controller connected: 00:06:f5:ed:88:8c (index 0)
Scan complete: found 3 serials, now tracking 3
Polling 3/3 controllers (active=3, idle=0)
```

---

## Platform Notes

### Raspberry Pi

- Works without `device_cgroup_rules` (cgroups v2 may not be available)
- `privileged: true` bypasses cgroup restrictions
- `rslave` propagation works on Raspberry Pi OS

### Security Considerations

- `pid: "host"` shares host PID namespace (container can see host processes)
- `privileged: true` required for Bluetooth adapter access
- `/dev:/dev:rslave` gives broad device access
- These are acceptable for a dedicated game console device

---

## Files Modified

| File | Change |
|------|--------|
| `docker-compose.yml` | Added `pid: "host"`, changed to `/dev:/dev:rslave` |
| `services/controller_manager/bluetooth_backend.py` | Added retry logic with 0.5s delay, 3 attempts |

---

## Related Work

- **Phase 57**: Backend abstraction (BluetoothBackend)
- **Phase 65**: Host pairing daemon (handles USB pairing on host)
- **Phase 72**: LED update optimization (separated from polling)
