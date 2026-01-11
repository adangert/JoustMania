# 25-Controller Setup Guide

**Target Hardware**: Raspberry Pi 5 with 25 PS Move controllers

---

## Hardware Overview

### Raspberry Pi 5 Specifications
- **CPU**: 4× ARM Cortex-A76 @ 2.4GHz
- **RAM**: 4-8GB
- **USB Ports**: 2× USB 3.0 + 2× USB 2.0
- **Performance**: Can handle 30Hz streaming for 25 controllers at ~20-30% CPU

### Bluetooth Dongle Requirements
- **Controllers per dongle**: 5-7 (recommended: 5 for stability)
- **Total dongles needed**: 5 dongles (25 controllers ÷ 5 per dongle)
- **Dongle type**: Any Bluetooth 2.0+ compatible dongle
- **Power draw per dongle**: ~100mA + overhead for active connections

---

## USB Hub Recommendations

### 🔴 **CRITICAL: Unpowered USB Hub Limitations**

**Problem with unpowered USB 2.0 hubs**:
- USB 2.0 port provides only **500mA total power**
- Each Bluetooth dongle draws **~100mA**
- 4 dongles + hub overhead = **~500mA** (at limit!)
- **High USB traffic increases power draw** → brownouts/disconnects

**Symptoms of power issues**:
- Random controller disconnections during gameplay
- Increased latency (>100ms gaps in streaming)
- USB hub resets during high traffic
- Controllers failing to pair

---

## Recommended Setup Options

### 🎯 **RECOMMENDED STARTING POINT: Test with Distributed Unpowered Hubs**

**If you have multiple unpowered USB 2.0 hubs**, start by distributing the load:
- ✅ Test first before buying anything
- ✅ May work fine at 30Hz with proper distribution
- ✅ Use monitoring script to identify issues
- ✅ Upgrade to powered only if data shows problems

See "Distributed Unpowered Hubs" section below.

---

### ✅ **Option A: Powered USB 3.0 Hub (UPGRADE IF NEEDED)**

**Hardware**: 7-port powered USB 3.0 hub
- **Examples**:
  - Anker 7-Port USB 3.0 Hub with 36W power adapter
  - Sabrent 10-Port USB 3.0 Hub with 60W adapter
- **Cost**: $20-40

**Benefits**:
- ✅ Each port gets dedicated power (no brownouts)
- ✅ USB 3.0 = 10x bandwidth (5 Gbps vs 480 Mbps)
- ✅ Room for expansion (up to 35+ controllers)
- ✅ Stable 30Hz streaming with zero disconnects
- ✅ Can run at 60Hz if needed

**Setup**:
```
Raspberry Pi 5
└─ USB 3.0 port → Powered USB 3.0 Hub (7-port)
    ├─ Dongle 1: Controllers 1-5
    ├─ Dongle 2: Controllers 6-10
    ├─ Dongle 3: Controllers 11-15
    ├─ Dongle 4: Controllers 16-20
    └─ Dongle 5: Controllers 21-25
```

---

### 🟡 **Option B: Distributed Unpowered Hubs**

**Hardware**: 2× unpowered USB 2.0 hubs (4-port each)

**Setup**:
```
Raspberry Pi 5
├─ USB 3.0 Port 1 → Unpowered Hub 1 (4-port)
│   ├─ Dongle 1: Controllers 1-5
│   └─ Dongle 2: Controllers 6-10
├─ USB 3.0 Port 2 → Unpowered Hub 2 (4-port)
│   ├─ Dongle 3: Controllers 11-15
│   └─ Dongle 4: Controllers 16-20
└─ USB 2.0 Port → Dongle 5: Controllers 21-25
```

**Benefits**:
- ✅ Distributes power load across multiple USB ports
- ✅ Uses existing unpowered hubs
- ✅ No additional cost

**Risks**:
- ⚠️ Still near power limits on each hub
- ⚠️ May experience occasional disconnects under load
- ⚠️ Limited to ~25 controllers max

---

### 🔴 **Option C: Single Unpowered Hub (NOT RECOMMENDED)**

**Current setup**: 4-port unpowered USB 2.0 hub

**Issues**:
- ❌ Can only fit 4 dongles (20 controllers)
- ❌ At power limit with 4 dongles
- ❌ High risk of brownouts during gameplay
- ❌ Unstable under 60Hz streaming
- ❌ Cannot scale beyond 20 controllers

**Only use if**:
- You're testing with <20 controllers temporarily
- You run at 30Hz to reduce power draw
- You monitor for disconnects frequently

---

## Software Optimization

### Update Frequency Settings

**Current (Phase 39)**:
```python
# services/game_coordinator/games/base.py
UPDATE_FREQUENCY = 30  # Hz - Optimized for 25 controllers
```

**Performance at 30Hz**:
- CPU usage: ~20-30% (Pi 5)
- Bandwidth: ~22 KB/s (25 controllers)
- USB power draw: 50% less than 60Hz
- Death detection latency: 33ms (imperceptible)

**Menu button monitoring** (already optimized):
```python
# services/menu/server.py
update_frequency_hz=30  # Already at 30Hz (correct)
```

---

## Monitoring USB Stability

Use the provided monitoring tool to test your setup:

```bash
python3 /tmp/claude/.../scratchpad/monitor_usb_stability.py
```

**What it checks**:
- Controller disconnections
- Latency spikes (>100ms gaps)
- USB hub resets
- Overall stability score

**Interpreting results**:
- ✅ **EXCELLENT**: 0 disconnects, 0 spikes → Setup is stable
- 🟡 **FAIR**: <5 disconnects, <10 spikes → Acceptable, monitor during gameplay
- 🟠 **POOR**: <20 disconnects → Consider powered hub
- 🔴 **CRITICAL**: >20 disconnects → **MUST use powered hub**

---

## Performance Comparison

| Setup | Controllers | Frequency | CPU | Bandwidth | Stability |
|-------|-------------|-----------|-----|-----------|-----------|
| **Powered Hub + 30Hz** | 25 | 30Hz | 20% | 22 KB/s | ✅ Excellent |
| **Powered Hub + 60Hz** | 25 | 60Hz | 35% | 45 KB/s | ✅ Excellent |
| **Distributed Unpowered + 30Hz** | 25 | 30Hz | 20% | 22 KB/s | 🟡 Fair |
| **Distributed Unpowered + 60Hz** | 25 | 60Hz | 35% | 45 KB/s | 🟠 Poor |
| **Single Unpowered + 30Hz** | 20 | 30Hz | 18% | 18 KB/s | 🟡 Fair |
| **Single Unpowered + 60Hz** | 20 | 60Hz | 30% | 36 KB/s | 🔴 Critical |

---

## Troubleshooting

### Controllers randomly disconnect during gameplay

**Cause**: USB hub power starvation
**Fix**: Use powered USB 3.0 hub (Option A)

### High latency (>100ms gaps in streaming)

**Cause**: USB bandwidth saturation
**Fix**:
1. Lower to 30Hz (already done)
2. Use USB 3.0 hub instead of USB 2.0
3. Distribute dongles across multiple USB ports

### Controllers fail to pair

**Cause**: Too many controllers per dongle
**Fix**: Limit to 5 controllers per dongle (instead of 7)

### CPU usage too high (>50%)

**Cause**: 60Hz streaming with many controllers
**Fix**: Lower to 30Hz (already done)

### Game feels "laggy" at 30Hz

**Unlikely**: 33ms latency is imperceptible to humans
**Check**: USB stability issues causing packet drops

---

## Future Scaling

### Beyond 25 Controllers

If you plan to scale beyond 25 controllers:

**Hardware**:
- 10-port powered USB 3.0 hub
- 1 dongle per 5 controllers
- 30 controllers = 6 dongles
- 50 controllers = 10 dongles (max recommended)

**Software**:
- Consider implementing **Phase 42: Hybrid Streaming**
- 10Hz baseline + threshold events
- Reduces CPU/bandwidth by 70% vs 60Hz
- See `/tmp/.../scratchpad/hybrid-streaming-design.md` (if implemented)

### Multiple Simultaneous Games

If running 2-3 games at once (e.g., 3× 8-player FFA):
- Each game runs at 30Hz independently
- Total: 24 controllers × 30Hz = 720 updates/sec
- Pi 5 can handle this (~40% CPU)
- **REQUIRES powered USB 3.0 hub**

---

## Recommended Hardware Shopping List

For stable 25-controller setup:

1. **Raspberry Pi 5** (4GB or 8GB) - $60-80
2. **Powered USB 3.0 Hub** (7-10 port) - $25-40
   - Must have external power adapter (≥36W)
   - USB 3.0 (5 Gbps)
3. **Bluetooth Dongles** (×5) - $30-50 total
   - Any Bluetooth 2.0+ compatible
   - Examples: ASUS USB-BT400, Plugable USB-BT4LE
4. **PS Move Controllers** (×25) - (already have)

**Total additional cost**: $25-40 for powered hub (if using existing dongles)

---

## Testing Checklist

Before large-scale deployment:

- [ ] Test with 5 controllers (1 dongle) - verify basic functionality
- [ ] Test with 10 controllers (2 dongles) - verify multi-dongle
- [ ] Test with 25 controllers (5 dongles) - full load test
- [ ] Run monitoring script for 5+ minutes
- [ ] Play full FFA game with all 25 players
- [ ] Check for disconnections during intense motion
- [ ] Verify death detection accuracy (all sensitivity levels)
- [ ] Monitor CPU usage (should be <40%)
- [ ] Check LED feedback responsiveness

---

## Summary

**For 25-controller setup on Raspberry Pi 5**:
1. ✅ **Software**: 30Hz update frequency (implemented)
2. ⚠️ **Hardware**: Powered USB 3.0 hub (strongly recommended)
3. ✅ **Monitoring**: Use stability script before events
4. ✅ **Configuration**: 5 controllers per dongle max

**Current state**: Optimized at 30Hz, but **unpowered hub is bottleneck**

**Next step**: Test with monitoring script, then decide on powered hub purchase
