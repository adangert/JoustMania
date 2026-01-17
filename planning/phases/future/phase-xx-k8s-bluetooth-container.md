# Phase XX: Kubernetes-Ready Bluetooth Container (Fallback Approach)

> **Status**: Future / On Hold - Fallback Option
>
> **Note**: The preferred approach for Kubernetes is the moved2 daemon architecture.
> See: Phase 66 → 67 → 68 for the recommended cloud-native path.
>
> This phase documents the fallback approach of running BlueZ inside the container,
> which may be useful if the moved2 approach is not viable.

## Overview

Run BlueZ stack inside the controller-manager container for Kubernetes deployments. This makes the pod self-contained and reduces host dependencies, which is preferable for K8s environments.

## Motivation

Current approach (Phase 65) uses:
- Host pairing daemon
- Host BlueZ via D-Bus socket mount
- Host configuration (ClassicBondedOnly, etc.)

This works well for single-node Docker Compose but has issues in Kubernetes:
- `hostPath` volumes require node affinity
- Depends on host systemd services running
- Node setup required before pod scheduling
- Less portable across nodes

## Proposed Solution

Run `dbus-daemon` and `bluetoothd` inside the container, making it self-contained.

### Architecture

```
┌─────────────────────────────────────────────────┐
│ Pod: controller-manager                         │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ Container: controller-manager            │   │
│  │                                          │   │
│  │  entrypoint.sh:                          │   │
│  │    1. Start dbus-daemon --system         │   │
│  │    2. Start bluetoothd                   │   │
│  │    3. Reset BT adapter (prevent stuck)   │   │
│  │    4. Run controller-manager app         │   │
│  │                                          │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
└─────────────────────────────────────────────────┘
         │
    hostNetwork: true (required for BT adapter)
         │
    ┌────┴────┐
    │ hci0    │  Bluetooth Adapter
    └─────────┘
```

### Kubernetes Manifest

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: controller-manager
  namespace: joustmania
spec:
  selector:
    matchLabels:
      app: controller-manager
  template:
    metadata:
      labels:
        app: controller-manager
    spec:
      # Required for Bluetooth adapter access
      hostNetwork: true

      # Only schedule on nodes with Bluetooth hardware
      nodeSelector:
        joustmania.io/bluetooth: "true"

      # Tolerate dedicated game nodes
      tolerations:
      - key: "joustmania.io/dedicated"
        operator: "Exists"
        effect: "NoSchedule"

      containers:
      - name: controller-manager
        image: joustmania/controller-manager:latest

        # Start dbus + bluetoothd before app
        command: ["/app/entrypoint-k8s.sh"]

        securityContext:
          capabilities:
            add:
            - NET_ADMIN    # Bluetooth adapter control
            - NET_RAW      # Low-level BLE packets
            - SYS_ADMIN    # May be needed for some BT operations

        env:
        - name: CONTROLLER_BACKEND
          value: "bluetooth"
        - name: DBUS_SYSTEM_BUS_ADDRESS
          value: "unix:path=/var/run/dbus/system_bus_socket"

        resources:
          limits:
            memory: 256Mi
          requests:
            memory: 128Mi

        # Health check via gRPC
        livenessProbe:
          exec:
            command: ["python", "-c", "...grpc health check..."]
          initialDelaySeconds: 30
          periodSeconds: 10

        # Lifecycle hook to clean up Bluetooth on termination
        lifecycle:
          preStop:
            exec:
              command: ["/app/cleanup-bluetooth.sh"]
```

### Entrypoint Script

```bash
#!/bin/bash
# entrypoint-k8s.sh - Start BlueZ stack and controller-manager

set -e

echo "[K8S] Starting D-Bus system bus..."
mkdir -p /var/run/dbus
dbus-daemon --system --nofork --nopidfile &
DBUS_PID=$!
sleep 1

echo "[K8S] Starting BlueZ bluetoothd..."
/usr/lib/bluetooth/bluetoothd --noplugin=sap &
BLUETOOTHD_PID=$!
sleep 2

echo "[K8S] Resetting Bluetooth adapter (prevent stuck state)..."
hciconfig hci0 down 2>/dev/null || true
sleep 1
hciconfig hci0 up 2>/dev/null || true
sleep 1

echo "[K8S] Bluetooth adapter status:"
hciconfig hci0

# Trap signals for clean shutdown
cleanup() {
    echo "[K8S] Shutting down..."
    kill $BLUETOOTHD_PID 2>/dev/null || true
    kill $DBUS_PID 2>/dev/null || true
    hciconfig hci0 down 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

echo "[K8S] Starting controller-manager..."
exec python -m services.controller_manager.main
```

### Cleanup Script

```bash
#!/bin/bash
# cleanup-bluetooth.sh - Clean shutdown to prevent stuck adapter

echo "[K8S] Pre-stop cleanup..."

# Turn off all controller LEDs
python -c "
import psmove
for i in range(psmove.count_connected()):
    m = psmove.PSMove(i)
    m.set_leds(0,0,0)
    m.update_leds()
    m.set_rumble(0)
" 2>/dev/null || true

# Reset adapter
hciconfig hci0 down 2>/dev/null || true

echo "[K8S] Cleanup complete"
```

### Dockerfile Changes

```dockerfile
# Add BlueZ stack to controller-manager image
FROM python:3.12-slim AS runtime

# Install BlueZ and D-Bus
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    dbus \
    && rm -rf /var/lib/apt/lists/*

# D-Bus configuration for container
RUN mkdir -p /var/run/dbus

# Copy entrypoint scripts
COPY scripts/k8s/entrypoint-k8s.sh /app/
COPY scripts/k8s/cleanup-bluetooth.sh /app/
RUN chmod +x /app/*.sh

# ... rest of Dockerfile
```

## Pairing Strategy for Kubernetes

Controller pairing still requires USB, which is a physical operation. Options:

### Option A: Pre-pair on Host (Recommended)

1. Pair controllers on host before deploying K8s
2. Controllers stored in host's `/var/lib/bluetooth`
3. Mount as read-only volume if needed

```yaml
volumes:
- name: bluetooth-pairings
  hostPath:
    path: /var/lib/bluetooth
    type: Directory
volumeMounts:
- name: bluetooth-pairings
  mountPath: /var/lib/bluetooth
  readOnly: true
```

### Option B: Pairing Job

Run a Kubernetes Job for pairing when needed:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: pair-controllers
spec:
  template:
    spec:
      hostNetwork: true
      restartPolicy: Never
      containers:
      - name: pairing
        image: joustmania/controller-manager:latest
        command: ["/app/pair-controllers.sh"]
        securityContext:
          privileged: true  # Required for USB access
```

### Option C: Pairing Sidecar (Complex)

Run pairing daemon as sidecar container - complex and probably overkill.

## Comparison: Current vs K8s Approach

| Aspect | Current (Phase 65) | K8s Approach |
|--------|-------------------|--------------|
| BlueZ location | Host | Container |
| D-Bus | Host socket mount | In-container daemon |
| Host dependencies | BlueZ, pairing daemon | Just BT hardware |
| Portability | Low (host setup) | High (self-contained) |
| Pairing | Host daemon | Pre-pair or Job |
| Network mode | Normal | hostNetwork required |
| Complexity | Lower | Higher |
| Recovery | Clean | Need adapter reset |

## Tasks (When Implemented)

- [ ] Create `scripts/k8s/entrypoint-k8s.sh`
- [ ] Create `scripts/k8s/cleanup-bluetooth.sh`
- [ ] Update Dockerfile with BlueZ stack option
- [ ] Create Kubernetes manifests (`k8s/` directory)
- [ ] Add node labeling documentation
- [ ] Test adapter stuck recovery
- [ ] Test multi-node deployment
- [ ] Document pairing workflow for K8s

## Prerequisites

- Phase 65 complete (current pairing approach working)
- Kubernetes cluster with Bluetooth-equipped nodes
- Node labeling for hardware selection

## References

- [How to run containerized Bluetooth applications with BlueZ](https://medium.com/omi-uulm/how-to-run-containerized-bluetooth-applications-with-bluez-dced9ab767f6)
- [Docker Bluetooth without --privileged](https://forums.docker.com/t/docker-bluetooth-and-bluez-without-privileged-net-host/125955)
- [BlueZ in Docker - hertz.gg](http://hertz.gg/blog/2020-09-27-bluez-in-docker.html)

## Alternative: psmoveapi Daemon (moved2)

Another approach worth exploring is using psmoveapi's built-in daemon (`moved2`), which exposes controllers over UDP.

**Current moved2 protocol supports:**
- `DISCOVER` - Find daemon on network
- `COUNT_CONNECTED` - Get controller count
- `SET_LEDS` - Control LED color
- `READ_INPUT` - Poll sensor/button data (49 bytes)
- `GET_SERIAL` - Get controller BT address
- `REGISTER_CONTROLLER` - Register for pairing

**Missing for JoustMania:**
- **Rumble/vibration command** - Not in current protocol

If rumble support were added to moved2 (upstream contribution or fork), this could be a cleaner architecture:

```
┌─────────────────────┐     UDP      ┌─────────────────────┐
│ K8s Pod             │◄────────────►│ Host: moved2 daemon │
│ controller-manager  │   :17778     │ (handles BlueZ)     │
│ (no BlueZ needed)   │              │                     │
└─────────────────────┘              └─────────────────────┘
```

**Pros:**
- No `hostNetwork` needed (just UDP port)
- No BlueZ in container
- Clean separation of concerns
- Could support multiple game servers

**Cons:**
- Requires upstream changes or fork
- Additional latency (UDP hop)
- Another daemon to manage on host

**Action item**: Consider contributing rumble support to psmoveapi if this approach is pursued.

See: [psmoveapi moved documentation](https://psmoveapi.readthedocs.io/en/latest/moved.html)

---

## Notes

- `hostNetwork: true` is required for Bluetooth adapter access - this is a Kubernetes limitation
- Adapter can get stuck if container exits uncleanly - entrypoint includes reset
- Consider using `priorityClassName` for game-critical pods
- May need `SYS_ADMIN` capability depending on kernel/BlueZ version
- Test thoroughly - Bluetooth in containers has many edge cases

## Related Phases

**Preferred Kubernetes approach (moved2 daemon):**
- [Phase 66: psmoveapi Rumble Contribution](phase-66-psmoveapi-rumble-contribution.md) - Add rumble to moved2 protocol
- [Phase 67: moved2 Backend](phase-67-moved2-backend.md) - UDP backend for controller-manager
- [Phase 68: Kubernetes Manifests](phase-68-kubernetes-manifests.md) - Full K8s deployment

**Current approach (non-K8s):**
- Phase 65: Host Pairing Daemon - Works for Docker Compose deployments
