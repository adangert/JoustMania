# Bluetooth Pairing Architecture for Microservices

**Date:** 2026-01-10
**Question:** How do we handle Bluetooth pairing in cloud-native microservices architecture?

---

## Current Pairing Implementation

### How It Works Now

**File:** `utils/pair.py` (242 lines)

**Process:**
1. USB controller plugged into Raspberry Pi
2. Detects PS Move via psmove library
3. Uses **DBus** to communicate with BlueZ (Linux Bluetooth stack)
4. Finds all Bluetooth adapters (hci0, hci1, etc.)
5. Load balances: pairs controller to adapter with fewest connections
6. **Restarts Bluetooth service:** `sudo systemctl restart bluetooth`
7. Controller now paired and can connect via Bluetooth

**System Requirements:**
- Access to **DBus system bus** (`dbus.SystemBus()`)
- Access to **Bluetooth hardware** (hci devices)
- Ability to run **sudo commands** (restart Bluetooth service)
- **psmove library** for controller detection

### When Pairing Happens

**Current trigger:** Automatic when USB controller detected in main menu loop

---

## The Docker Problem

**Challenge:** Containers are isolated from host system

### What Containers CAN'T Do by Default

1. ❌ Access host DBus (`/var/run/dbus/system_bus_socket`)
2. ❌ Access Bluetooth hardware (hci devices)
3. ❌ Run `sudo systemctl restart bluetooth` on host
4. ❌ Detect USB device connections without privileged mode

### What We Need for Pairing in Docker

1. ✅ Mount host DBus socket: `-v /var/run/dbus:/var/run/dbus`
2. ✅ Privileged mode: `--privileged` (or specific capabilities)
3. ✅ Host network mode: `--network host` (for Bluetooth)
4. ✅ USB device passthrough: `--device /dev/bus/usb`
5. ⚠️ Ability to restart host Bluetooth service (problematic!)

---

## Architecture Options

### Option 1: Pairing in ControllerManager Service (Privileged Container) ⭐ RECOMMENDED

**Architecture:**
```
┌────────────────────────────────────────┐
│  Raspberry Pi Host                     │
│                                        │
│  ┌──────────────────────────────────┐ │
│  │ ControllerManager Service        │ │
│  │ (Privileged Container)           │ │
│  │                                  │ │
│  │  - Mounts host DBus              │ │
│  │  - Access to Bluetooth hardware  │ │
│  │  - USB device passthrough        │ │
│  │  - Can restart Bluetooth service │ │
│  │                                  │ │
│  │  [Pairing Logic]                 │ │
│  │  [Controller Discovery]          │ │
│  │  [State Management]              │ │
│  └──────────────────────────────────┘ │
└────────────────────────────────────────┘
```

**docker-compose.yml:**
```yaml
controller-manager:
  build:
    context: .
    dockerfile: services/controller_manager/Dockerfile
  privileged: true  # Required for Bluetooth access
  network_mode: host  # Required for Bluetooth
  volumes:
    - /var/run/dbus:/var/run/dbus  # DBus access
  devices:
    - /dev/bus/usb:/dev/bus/usb  # USB devices
  environment:
    - DBUS_SYSTEM_BUS_ADDRESS=unix:path=/var/run/dbus/system_bus_socket
```

**PROs:**
- ✅ All controller management in one service
- ✅ Logical place for pairing (service that manages controllers)
- ✅ Can restart Bluetooth service via host command
- ✅ Automatic pairing when USB controller detected

**CONs:**
- ⚠️ Privileged container (security concern, but acceptable for Raspberry Pi)
- ⚠️ Tied to host system (not fully cloud-native)
- ⚠️ Can't easily run on Kubernetes without node-specific config

**Best for:** Raspberry Pi deployment (your use case!)

---

### Option 2: Separate Pairing Service

**Architecture:**
```
┌────────────────────────────────────────┐
│  Raspberry Pi Host                     │
│                                        │
│  ┌──────────────────────────────────┐ │
│  │ Pairing Service (Privileged)     │ │
│  │  - Only handles pairing          │ │
│  │  - Runs on-demand or background  │ │
│  └──────────────────────────────────┘ │
│                                        │
│  ┌──────────────────────────────────┐ │
│  │ ControllerManager Service        │ │
│  │  - Manages paired controllers    │ │
│  │  - No privileged access needed   │ │
│  └──────────────────────────────────┘ │
└────────────────────────────────────────┘
```

**PROs:**
- ✅ Security isolation (only one privileged service)
- ✅ Pairing service can be stopped when not needed
- ✅ Clearer separation of concerns

**CONs:**
- ❌ More complex (additional service)
- ❌ Both services need to coordinate
- ❌ Still tied to host system

**Best for:** If you want to minimize privileged containers

---

### Option 3: Host-Level Pairing Tool (Not Containerized)

**Architecture:**
```
┌────────────────────────────────────────┐
│  Raspberry Pi Host                     │
│                                        │
│  [Pairing Tool - Native Python]       │
│   - Runs directly on host (not Docker)│
│   - Manual or cron-based               │
│                                        │
│  ┌──────────────────────────────────┐ │
│  │ Docker Services                  │ │
│  │  - ControllerManager             │ │
│  │  - Only manages paired controllers│
│  └──────────────────────────────────┘ │
└────────────────────────────────────────┘
```

**PROs:**
- ✅ No Docker privilege issues
- ✅ Simple: just run Python script on host
- ✅ Can be called from WebUI via SSH or API

**CONs:**
- ❌ Not fully cloud-native
- ❌ Requires Python/dependencies on host
- ❌ Manual step or scheduling needed

**Best for:** Simplicity, if pairing is infrequent

---

### Option 4: Manual Pairing, Services Manage Paired Controllers

**Architecture:**
```
┌────────────────────────────────────────┐
│  Raspberry Pi Host                     │
│                                        │
│  [Manual Pairing - One-time Setup]    │
│   - Run pairing script during setup   │
│   - Controllers stay paired           │
│                                        │
│  ┌──────────────────────────────────┐ │
│  │ Docker Services                  │ │
│  │  - ControllerManager             │ │
│  │  - Only connects to paired ctrlrs│
│  └──────────────────────────────────┘ │
└────────────────────────────────────────┘
```

**PROs:**
- ✅ Simplest for cloud-native
- ✅ No privileged containers needed
- ✅ Controllers stay paired across reboots

**CONs:**
- ❌ Can't pair new controllers via WebUI
- ❌ Manual process to add new controllers
- ❌ Not user-friendly

**Best for:** Fixed set of controllers, rare changes

---

## Recommended Approach for Your Use Case

### For Raspberry Pi Deployment: **Option 1** (Privileged ControllerManager)

**Rationale:**
1. You're deploying to **Raspberry Pi** (not Kubernetes cluster)
2. Privileged containers are **acceptable on single-node Pi**
3. ControllerManager **already needs USB access** for PS Move
4. **Simpler architecture** - all controller logic in one place
5. Raspberry Pi is **dedicated hardware for JoustMania**

**Implementation:**

```yaml
# docker-compose.yml
controller-manager:
  build:
    context: .
    dockerfile: services/controller_manager/Dockerfile
  container_name: joustmania-controller-manager
  privileged: true  # For Bluetooth/USB access
  network_mode: host  # For Bluetooth
  volumes:
    - /var/run/dbus:/var/run/dbus  # DBus for Bluetooth pairing
  devices:
    - /dev/bus/usb:/dev/bus/usb  # USB for PS Move detection
  environment:
    - DBUS_SYSTEM_BUS_ADDRESS=unix:path=/var/run/dbus/system_bus_socket
    - OTEL_SERVICE_NAME=controller-manager-service
    - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
  depends_on:
    otel-collector:
      condition: service_healthy
    redis:
      condition: service_healthy
  networks:
    - joustmania
  restart: unless-stopped
```

**ControllerManager responsibilities:**
1. **Bluetooth pairing** (via DBus, requires privilege)
2. **USB controller detection** (requires USB access)
3. **Controller discovery** (Bluetooth scanning)
4. **Controller state management** (current responsibility)
5. **Battery monitoring** (current responsibility)

**Code organization:**
```
services/controller_manager/
  server.py           # gRPC server
  pairing.py          # MOVED from utils/pair.py
  bluetooth.py        # MOVED from jm_dbus.py
  Dockerfile
  pyproject.toml
```

---

## Questions to Decide

### 1. How often do you pair new controllers?

**Options:**
- **Once during setup** → Manual pairing (Option 4) might work
- **Occasionally** → Host-level tool (Option 3) is simple
- **Frequently** → Privileged ControllerManager (Option 1) is best

### 2. Do you want pairing via WebUI?

**If YES:**
- Need Option 1 or 2 (containerized pairing)
- WebUI can call ControllerManager's `PairController` RPC

**If NO:**
- Can use Option 3 or 4 (manual/script-based)

### 3. Is this Raspberry Pi only, or planning Kubernetes?

**Raspberry Pi only:**
- Privileged containers are fine → **Option 1 recommended**

**Kubernetes in future:**
- Need to plan for node-specific pairing
- Consider Option 3 or 4 (host-level pairing)

### 4. Should pairing be automatic or manual?

**Automatic (current behavior):**
- USB controller plugged in → auto-pairs → ready to use
- Need Option 1 or 2

**Manual:**
- Run pairing script/command
- Simpler, less magic
- Option 3 or 4

---

## My Recommendation

**For your Raspberry Pi deployment: Option 1 (Privileged ControllerManager)**

**Why:**
1. ✅ **Simplest architecture** - one service handles all controller concerns
2. ✅ **Better user experience** - plug in USB controller, auto-pairs
3. ✅ **Acceptable security** - Raspberry Pi is dedicated hardware
4. ✅ **Already needs privileges** - USB access required anyway
5. ✅ **Can restart Bluetooth** - works correctly with BlueZ

**Implementation plan:**
1. Move `utils/pair.py` → `services/controller_manager/pairing.py`
2. Move `jm_dbus.py` → `services/controller_manager/bluetooth.py`
3. Update ControllerManager Dockerfile to install dbus-python
4. Update docker-compose.yml with privileged mode + DBus mount
5. Add `PairController` RPC to controller_manager.proto
6. Implement pairing in ControllerManager server

**Trade-off accepted:**
- ⚠️ Not pure cloud-native (tied to host Bluetooth)
- ✅ But appropriate for Raspberry Pi use case
- ✅ Can still use observability, gRPC, Docker Compose
- ✅ Future Kubernetes deployment can use DaemonSet per node

---

## Alternative for Future: Kubernetes with DaemonSet

If you eventually deploy to Kubernetes cluster with multiple nodes:

```yaml
# controller-manager-daemonset.yaml
apiVersion: apps/v1
kind: DaemonSet  # Runs one per node
metadata:
  name: controller-manager
spec:
  template:
    spec:
      hostNetwork: true  # For Bluetooth
      containers:
      - name: controller-manager
        securityContext:
          privileged: true  # For Bluetooth
        volumeMounts:
        - name: dbus
          mountPath: /var/run/dbus
        - name: usb
          mountPath: /dev/bus/usb
      volumes:
      - name: dbus
        hostPath:
          path: /var/run/dbus
      - name: usb
        hostPath:
          path: /dev/bus/usb
```

Each Raspberry Pi node gets its own ControllerManager instance that manages that node's Bluetooth hardware.

---

## What do you prefer?

Please let me know:
1. **How often do you pair controllers?** (once, occasionally, frequently)
2. **Do you want WebUI pairing?** (yes/no)
3. **Is this Raspberry Pi only?** (yes/future Kubernetes)
4. **Automatic or manual pairing?** (auto-pair when USB plugged in, or manual script)

Based on your answers, I'll implement the right approach for Phase 9.
