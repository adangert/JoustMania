# Hardware Setup Guide

Complete guide for setting up JoustMania on Raspberry Pi 5, covering USB configuration, Bluetooth adapters, power management, and mobile deployments.

---

## Table of Contents

- [USB Port Selection](#usb-port-selection)
- [Bluetooth Adapter Recommendations](#bluetooth-adapter-recommendations)
- [Power Configurations](#power-configurations)
- [Mobile/Portable Setups](#mobileportable-setups)
- [Scaling Guide](#scaling-guide)
- [Physical Placement](#physical-placement)
- [Troubleshooting](#troubleshooting)

---

## USB Port Selection

### USB 3.0 Interference with Bluetooth

**Important**: USB 3.0 generates electromagnetic interference in the 2.4 GHz band - the same frequency Bluetooth uses.

| USB Port Type | Bluetooth Impact |
|---------------|------------------|
| USB 3.0 | Causes 2.4GHz interference, reduced range, dropouts |
| USB 2.0 | No interference, recommended for Bluetooth |

**Symptoms of USB 3.0 interference**:
- Reduced controller range
- Random disconnections
- Increased latency
- Controllers must be closer to adapter

### RPi 5 USB Layout

```
Raspberry Pi 5 (USB ports facing you)
┌─────────────────────────────────────────┐
│                                         │
│   [USB 3.0]  [USB 3.0]  ← Avoid for BT  │
│   [USB 2.0]  [USB 2.0]  ← Use for BT    │
│                                         │
└─────────────────────────────────────────┘
```

### Recommendation

**Always connect Bluetooth adapters to USB 2.0 ports** (directly or via hub).

If you must use USB 3.0 ports for other devices, keep them physically separated from Bluetooth adapters.

---

## Bluetooth Adapter Recommendations

### Class 1 vs Class 2 Adapters

| Specification | Class 2 (Typical) | Class 1 (Recommended) |
|---------------|-------------------|----------------------|
| Range | ~10 meters | ~100+ meters |
| Transmit Power | 2.5 mW | 100 mW |
| Price | $5-10 | $15-25 |
| Use Case | Desktop, close range | Large rooms, events |

### Recommended Features

For JoustMania events, look for adapters with:

- **Class 1** or **"100m+ range"** in description
- **External/dual antennas** for better signal
- **Adjustable antennas** for optimal positioning
- **Linux compatibility** (most adapters work)
- **Bluetooth 4.0+** with backward compatibility to BT 2.1 (PS Move uses Classic BT)

### Example: Quality Mobile Adapter

```
Wowfast Bluetooth 5.4 Adapter
├── Dual antennas (better coverage)
├── 150m range (Class 1)
├── Rotatable 90°/180° (optimize direction)
├── Foldable (travel-friendly)
├── Linux compatible
└── ~$15-20
```

### Controllers Per Adapter

Each Bluetooth adapter supports **up to 7 simultaneous connections** (Bluetooth piconet limit).

| Adapters | Max Controllers |
|----------|-----------------|
| 1 | 7 |
| 2 | 14 |
| 3 | 21 |
| 4 | 28 |
| 6 | 42 |

---

## Power Configurations

### USB Hub Types

| Hub Type | Power Source | Current per Port | Best For |
|----------|--------------|------------------|----------|
| Bus-powered USB 2.0 | RPi USB port | ~125mA (shared 500mA) | Mobile, small setups |
| Powered USB 2.0/3.0 | Wall adapter | 500mA+ per port | Stationary, large setups |

### Bus-Powered Hub Limits

Each RPi 5 USB 2.0 port provides **500mA total**.

| Adapters per Hub | Current Draw | Status |
|------------------|--------------|--------|
| 2 adapters | ~300mA | Safe |
| 3 adapters | ~450mA | At limit |
| 4 adapters | ~600mA | Over limit - unstable |

### Power Draw Summary

| Component | Power Draw |
|-----------|------------|
| RPi 5 (idle) | 3-5W |
| RPi 5 (active, Docker services) | 8-12W |
| Each Bluetooth adapter | ~0.5W |
| 6 adapters total | ~3W |

---

## Mobile/Portable Setups

### Power Bank Requirements

For mobile JoustMania, use a USB-C PD power bank:

| Controller Count | Adapters | System Power | Recommended Battery |
|------------------|----------|--------------|---------------------|
| 14 | 2 | ~11W | 10,000+ mAh |
| 24 | 4 | ~12W | 20,000+ mAh |
| 42 | 6 | ~13W | 26,800+ mAh |

### Runtime Estimates

| Power Bank | Capacity | Runtime @ 12W |
|------------|----------|---------------|
| 10,000 mAh | ~37Wh | ~3 hours |
| 20,000 mAh | ~74Wh | ~5-6 hours |
| 26,800 mAh | ~100Wh | ~7-8 hours |

### Mobile Configuration: 14 Controllers

```
Power Bank (USB-C PD, 20,000mAh)
         │
         ▼
      RPi 5
         │
    USB 2.0 ports
     │       │
     ▼       ▼
   [BT]     [BT]    ← 2× Class 1 adapters

14 controllers, ~11W, 6+ hours runtime
```

### Mobile Configuration: 24 Controllers

```
Power Bank (USB-C PD, 20,000mAh+)
         │
         ▼
      RPi 5
         │
    USB 2.0 ports
     │           │
     ▼           ▼
  USB Hub     USB Hub     ← 2× bus-powered 4-port hubs
  [BT][BT]    [BT][BT]    ← 4× Class 1 adapters

24 controllers (7+7+7+3), ~12W, 5-6 hours runtime
```

### Mobile Configuration: 42 Controllers

```
Power Bank (USB-C PD, 26,800mAh)
         │
         ▼
      RPi 5
         │
    USB 2.0 ports
     │           │
     ▼           ▼
  USB Hub     USB Hub     ← 2× bus-powered 4-port hubs
[BT][BT][BT] [BT][BT][BT] ← 6× Class 1 adapters

42 controllers (7×6), ~13W, 7 hours runtime
```

**Note**: 3 adapters per hub = 450mA of 500mA limit. This is tight but functional.

---

## Scaling Guide

### Performance with Parallel Polling (Phase 62)

JoustMania uses parallel controller polling via `asyncio.gather()`, which reads all controllers concurrently instead of sequentially.

| Controllers | Sequential Polling | Parallel Polling | Improvement |
|-------------|-------------------|------------------|-------------|
| 4 | 12ms | 3ms | 75% faster |
| 14 | 42ms | 3-5ms | 90% faster |
| 24 | 72ms | 5-10ms | 85% faster |
| 42 | 126ms | 5-15ms | 90% faster |

This optimization is critical for large player counts - without it, 42 controllers couldn't maintain 30Hz updates.

### Recommended Configurations by Scale

| Event Size | Controllers | Adapters | USB Setup | Power |
|------------|-------------|----------|-----------|-------|
| Small (home) | 4-7 | 1 | Direct USB 2.0 | Any |
| Medium | 8-14 | 2 | Direct USB 2.0 | 10W+ |
| Large | 15-24 | 3-4 | 2× USB hubs | 12W+ |
| Event | 25-42 | 4-6 | 2× USB hubs or powered hub | 13W+ |

### Lite Deployment (No Observability)

For resource-constrained or mobile deployments, use the lite Docker Compose configuration:

```bash
docker-compose -f docker-compose.lite.yml up
```

This excludes Jaeger, Prometheus, Grafana, and OTEL Collector, saving ~768MB RAM.

---

## Physical Placement

### Adapter Positioning

For best coverage, position Bluetooth adapters to maximize line-of-sight to players:

```
           Players
        ⭕ ⭕ ⭕ ⭕ ⭕
       ↗           ↖
    [Ant1]       [Ant2]    ← Antennas pointed toward players
       │           │
       └─── RPi ───┘
```

### USB Extension Cables

Use 1-meter USB extension cables to:
- Position adapters at player height
- Move antennas away from RPi electrical noise
- Spread adapters for better coverage

```
RPi 5
   │
   ├──[1m USB cable]──► BT adapter (left side, elevated)
   │
   └──[1m USB cable]──► BT adapter (right side, elevated)
```

### Antenna Orientation

If using adapters with adjustable antennas:
- Point antennas **toward the center** of the play area
- Angle **slightly upward** (controllers are at hand/arm height)
- Rotate antennas to find optimal signal (test with players at max distance)

---

## Troubleshooting

### Random Controller Disconnections

| Cause | Solution |
|-------|----------|
| USB 3.0 interference | Move adapters to USB 2.0 ports |
| Hub power starvation | Use powered hub or distribute across ports |
| Too many per adapter | Limit to 5-6 controllers per adapter |
| Weak signal | Use Class 1 adapters with external antennas |

### Reduced Range / Weak Signal

| Cause | Solution |
|-------|----------|
| Class 2 adapter | Upgrade to Class 1 (100m range) |
| Adapter near RPi | Use USB extension cable |
| Obstacles | Position adapters with line-of-sight |
| Interference | Move away from WiFi routers, USB 3.0 devices |

### Controllers Won't Pair

| Cause | Solution |
|-------|----------|
| Adapter limit reached | Max 7 per adapter, add more adapters |
| Power issue | Check hub isn't over current limit |
| Driver issue | Most adapters work without drivers on Linux |

### High Latency

| Cause | Solution |
|-------|----------|
| Sequential polling | Upgrade to Phase 62+ (parallel polling) |
| Too many controllers | Add adapters (reduce per-adapter load) |
| USB bandwidth | Use USB 3.0 hub for hub, adapters on 2.0 |

---

## Hardware Shopping List

### Minimum (14 Controllers, Mobile)

- [ ] Raspberry Pi 5 (4GB+)
- [ ] 2× Class 1 Bluetooth adapters (dual antenna recommended)
- [ ] USB-C PD power bank (20,000mAh+)
- [ ] 2× 1m USB extension cables (optional but recommended)

### Medium (24 Controllers, Mobile)

- [ ] Raspberry Pi 5 (4GB+)
- [ ] 4× Class 1 Bluetooth adapters
- [ ] 2× USB 2.0 hubs (4-port, bus-powered OK)
- [ ] USB-C PD power bank (20,000mAh+)

### Large (42 Controllers, Mobile)

- [ ] Raspberry Pi 5 (8GB recommended)
- [ ] 6× Class 1 Bluetooth adapters
- [ ] 2× USB 2.0 hubs (4-port, bus-powered)
- [ ] USB-C PD power bank (26,800mAh+)

### Event (42+ Controllers, Stationary)

- [ ] Raspberry Pi 5 (8GB)
- [ ] 6-8× Bluetooth adapters
- [ ] Powered USB 3.0 hub (7-10 port)
- [ ] Wall power

---

## Summary

| Goal | Key Decisions |
|------|---------------|
| **Best signal** | Class 1 adapters + USB extensions + antenna positioning |
| **Mobile friendly** | USB 2.0 bus-powered hubs + 20,000mAh+ power bank |
| **No interference** | Bluetooth on USB 2.0 only, avoid USB 3.0 |
| **Scale to 42** | 6 adapters + parallel polling (Phase 62) + lite deployment |
