# Phase 64: USB Controller Auto-Discovery Improvements

## Overview

USB-connected PS Move controllers should be automatically detected and paired without requiring service restarts. Currently, hot-plug detection has been partially implemented but needs refinement.

## Problem Statement

1. **Delayed detection**: USB controllers plugged in after service start may not be detected immediately
2. **Pairing workflow**: Auto-pairing triggers bluetooth restart, but this happens on host (not in container)
3. **Multiple controller pairing**: Users want to pair multiple controllers sequentially without restarts
4. **Detection feedback**: No clear indication when a USB controller is detected and ready for pairing

## Current Implementation

### What Works
- `get_connected_controllers()` in `bluetooth_backend.py` rescans for new controllers each call
- Auto-pairing triggers when USB controller is detected
- Socket-based bluetooth restart communicates with host helper

### What Needs Improvement
- Detection polling interval may be too slow for responsive hot-plug
- No batching of multiple controller pairs before bluetooth restart
- Missing user feedback during pairing process
- Pairing status not clearly communicated to WebUI

## Goals

1. Responsive USB hot-plug detection (< 2 second delay)
2. Batch pairing support - pair multiple controllers before restart
3. Clear pairing status in logs and WebUI
4. Reliable pairing completion detection

## Technical Details

### Detection Improvements

The `get_connected_controllers()` method already rescans, but consider:
- Dedicated USB event monitoring (udev/pyudev)
- Faster polling during "pairing mode"
- Event-driven detection vs polling

### Batch Pairing Flow

```python
# Proposed pairing workflow
class PairingSession:
    def __init__(self):
        self.pending_controllers = []
        self.pairing_active = False

    def start_pairing_mode(self):
        """Enter pairing mode - collect controllers without restart"""
        self.pairing_active = True
        self.pending_controllers = []

    def add_controller(self, serial):
        """Add controller to pending list"""
        self.pending_controllers.append(serial)

    def finish_pairing(self):
        """Trigger single bluetooth restart for all controllers"""
        if self.pending_controllers:
            self._restart_bluetooth()
        self.pairing_active = False
```

### WebUI Integration

- Add "Pairing Mode" button to enter batch pairing
- Show list of pending controllers
- "Finish Pairing" button to complete and restart bluetooth
- Real-time status updates via WebSocket

## Tasks

- [ ] Add pyudev for USB event monitoring (optional enhancement)
- [ ] Implement PairingSession class for batch pairing
- [ ] Add pairing mode API endpoints to controller manager
- [ ] Update WebUI with pairing mode controls
- [ ] Add pairing status to controller list display
- [ ] Test hot-plug detection timing
- [ ] Document pairing workflow for users

## Testing

1. Start service with no controllers
2. Plug in USB controller - should detect within 2 seconds
3. Pair first controller (should NOT restart bluetooth yet)
4. Plug in second controller - should detect and pair
5. Click "Finish Pairing" - single bluetooth restart
6. Both controllers should connect via Bluetooth

## Dependencies

- Phase 57 (Windows Controller Backend) - complete
- Phase 62 (Parallel Controller Polling) - complete
- Phase 63 (USB Controller Handling) - in progress

## Notes

- pyudev adds a dependency but provides instant USB detection
- Current polling approach works but may have 1-5 second delay
- Consider WebSocket push for real-time pairing status
- First-gen PS Move controllers require ClassicBondedOnly=false in BlueZ config

## Related Files

- `services/controller_manager/bluetooth_backend.py` - Detection logic
- `services/controller_manager/pairing.py` - Pairing operations
- `scripts/bluetooth-helper.sh` - Host bluetooth restart helper
- `services/webui/` - WebUI for pairing controls
