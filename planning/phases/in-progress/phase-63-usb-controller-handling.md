# Phase 63: USB Controller Handling Improvements

## Overview

USB-connected PS Move controllers have different capabilities than Bluetooth-connected ones. Currently, the system shows misleading warnings for USB controllers. This phase improves USB controller handling.

## Problem Statement

1. **False battery warnings**: USB controllers report battery as 0/5, triggering low battery warnings
2. **Sensor data unavailable**: Accelerometer/gyro data only works via Bluetooth, not USB
3. **Magnetometer warnings**: psmoveapi warns about uncalibrated magnetometer for USB controllers
4. **USB is only for pairing**: USB connection should be treated as temporary pairing mode, not gameplay

## Goals

1. Suppress battery warnings for USB-connected controllers
2. Don't attempt to read sensor data from USB controllers
3. Clearly indicate USB vs Bluetooth connection status in logs/UI
4. Treat USB controllers as "pairing mode" - prompt user to complete pairing

## Technical Details

### Connection Type Detection

psmoveapi provides `move.connection_type`:
- `psmove.Conn_USB` - USB connection (pairing only)
- `psmove.Conn_Bluetooth` - Bluetooth connection (full functionality)

### Changes Required

#### 1. Battery Monitoring (`monitoring.py`)

```python
def check_battery_levels(self, controllers, backend, run_async):
    for serial, info in controllers.items():
        # Skip battery check for USB-connected controllers
        if info.get("connection_type") == "USB":
            continue
        # ... existing battery check logic
```

#### 2. Controller State Updates (`bluetooth_backend.py`)

Store connection type when tracking controller:
```python
self.tracked_controllers[serial] = {
    "battery": battery,
    "ready": False,
    "connection_type": "USB" if move.connection_type == psmove.Conn_USB else "Bluetooth"
}
```

#### 3. Logging Improvements

- Log USB controllers as "Pairing mode" not just "USB"
- Add prompt: "Unplug USB and press PS button to connect via Bluetooth"

#### 4. UI Indication (WebUI)

- Show USB controllers differently (e.g., different color/icon)
- Display "Pairing..." status for USB controllers

## Tasks

- [ ] Add connection_type to tracked_controllers dict
- [ ] Skip battery warnings for USB controllers
- [ ] Skip sensor data reads for USB controllers
- [ ] Update logging to indicate USB is for pairing
- [ ] Add WebUI indication for USB vs Bluetooth status
- [ ] Test USB pairing flow end-to-end

## Testing

1. Connect controller via USB - should show "Pairing mode", no battery warnings
2. Complete pairing, connect via Bluetooth - should show battery and work normally
3. Verify sensor data only read for Bluetooth connections

## Dependencies

- Phase 57 (Windows Controller Backend) - already complete
- Phase 62 (Parallel Controller Polling) - already complete

## Notes

- psmoveapi magnetometer warnings come from C library, cannot be suppressed
- USB connection battery always shows 0 - this is expected behavior
