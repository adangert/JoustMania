# Phase 65: Host-Based PS Move Pairing Daemon

## Overview

Move controller pairing from Docker container to a dedicated host daemon. This simplifies the Docker architecture by keeping all Bluetooth/USB hardware interaction on the host where it belongs.

## Problem Statement

Current approach has complexity:
1. Docker container needs privileged mode + many /dev mounts
2. Bluetooth restart requires socket communication to host helper
3. USB hot-plug detection is polling-based in container
4. BlueZ trust operations need host-level access
5. psmoveapi must be built in container image

## Solution

Run a simple polling daemon on the host that:
1. Detects USB-connected PS Move controllers
2. Pairs them using psmoveapi
3. Trusts them in BlueZ
4. Restarts Bluetooth service
5. Tracks paired controllers to avoid re-pairing

The Docker container then only handles Bluetooth-connected (already paired) controllers.

## Benefits

- **Simpler Docker setup**: No USB/hidraw mounts, no privileged mode for pairing
- **Native hardware access**: Daemon runs on host with full permissions
- **Easy debugging**: `journalctl -u psmove-pairing -f` to watch pairing
- **Reliable**: Polling catches any USB connection, no udev race conditions
- **Single responsibility**: Host handles hardware, container handles game logic

## Implementation

### 1. Pairing Daemon Script

`/usr/local/bin/psmove-pairing-daemon.sh`:

```bash
#!/bin/bash
# PS Move Controller Pairing Daemon
# Polls for USB-connected controllers and pairs them automatically

POLL_INTERVAL=30

# Flash controller LED to indicate status
flash_led() {
    local count=$1
    local r=$2 g=$3 b=$4

    for i in $(seq 1 $count); do
        psmove set-leds $r $g $b 2>/dev/null
        sleep 0.2
        psmove set-leds 0 0 0 2>/dev/null
        sleep 0.2
    done
}

echo "PS Move Pairing Daemon started (polling every ${POLL_INTERVAL}s)"

while true; do
    # Check for USB-connected PS Move controllers
    for serial in $(psmove list --usb 2>/dev/null | grep -oE '[0-9A-Fa-f:]{17}'); do
        # Skip if already paired in BlueZ
        if bluetoothctl devices Paired | grep -qi "$serial"; then
            continue
        fi

        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Found unpaired controller: $serial"

        # Yellow pulse - pairing in progress
        psmove set-leds 255 255 0 2>/dev/null

        # Pair controller (writes host BT MAC to controller)
        if psmove pair; then
            # Trust in BlueZ
            bluetoothctl trust "$serial"

            # Restart bluetooth to recognize new device
            systemctl restart bluetooth

            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Paired $serial successfully"
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Unplug USB cable and press PS button to connect"

            # Flash white 3x - success, unplug now
            flash_led 3 255 255 255
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Failed to pair $serial"

            # Flash red 3x - error
            flash_led 3 255 0 0
        fi
    done

    sleep "$POLL_INTERVAL"
done
```

### 2. Systemd Service

`/etc/systemd/system/psmove-pairing.service`:

```ini
[Unit]
Description=PS Move Controller Pairing Daemon
Documentation=https://github.com/adangert/JoustMania
After=bluetooth.service
Requires=bluetooth.service

[Service]
Type=simple
ExecStart=/usr/local/bin/psmove-pairing-daemon.sh
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=psmove-pairing

[Install]
WantedBy=multi-user.target
```

### 3. Setup Script Integration

Add to `scripts/setup.sh`:

```bash
install_pairing_daemon() {
    echo "Installing PS Move pairing daemon..."

    # Copy daemon script
    sudo cp scripts/psmove-pairing-daemon.sh /usr/local/bin/
    sudo chmod +x /usr/local/bin/psmove-pairing-daemon.sh

    # Install systemd service
    sudo cp scripts/psmove-pairing.service /etc/systemd/system/

    # Enable and start service
    sudo systemctl daemon-reload
    sudo systemctl enable psmove-pairing.service
    sudo systemctl start psmove-pairing.service

    echo "Pairing daemon installed and running"
}
```

### 4. Simplify Docker Container

Remove from `docker-compose.lite.yml` controller-manager:
- `/dev:/dev` mount (no longer need hidraw for USB)
- `/dev/bus/usb:/dev/bus/usb` mount
- `/var/run/joustmania:/var/run/joustmania` socket mount

Keep:
- `/var/run/dbus:/var/run/dbus:ro` for BlueZ communication
- `/var/lib/bluetooth:/var/lib/bluetooth:ro` (can be read-only now)
- Bluetooth-related environment variables

### 5. Remove Container Pairing Code

**Delete entirely:**
- `services/controller_manager/pairing.py` - No longer needed
- `scripts/bluetooth-helper.sh` - Replaced by daemon

**Simplify `bluetooth_backend.py`:**

Remove USB auto-pairing from `get_connected_controllers()`:

```python
def get_connected_controllers(self) -> list[str]:
    """Get list of connected controller serials (Bluetooth only)."""
    try:
        count = psmove.count_connected()

        for move_num in range(count):
            move = psmove.PSMove(move_num)
            if move is None:
                continue

            # Skip USB controllers - pairing handled by host daemon
            if move.connection_type == psmove.Conn_USB:
                continue

            try:
                serial = move.get_serial()
                if serial and serial not in self.controllers:
                    self.controllers[serial] = move
                    self.controller_states[serial] = ControllerState()
                    logger.info(f"Bluetooth controller connected: {serial}")
            except Exception as e:
                logger.debug(f"Error reading controller {move_num}: {e}")

    except Exception as e:
        logger.error(f"Error scanning controllers: {e}")

    return list(self.controllers.keys())
```

Remove from `initialize()`:
- USB auto-pair logic
- `connect_controller()` can be simplified (no USB pairing)

Remove imports:
- `from services.controller_manager.pairing import Pair`

## Tasks

**Host daemon:**
- [x] Create `scripts/psmove-pairing-daemon.sh`
- [x] Create `scripts/psmove-pairing.service`
- [x] Update `scripts/setup.sh` with daemon installation function

**Controller manager cleanup:**
- [x] Delete `services/controller_manager/pairing.py`
- [x] Remove USB auto-pair logic from `bluetooth_backend.py`
- [x] Remove Pair import from `bluetooth_backend.py`
- [x] Update `initialize()` to skip USB controllers
- [x] Update `get_connected_controllers()` to skip USB controllers

**Docker cleanup:**
- [x] Remove `/dev:/dev` mount from `docker-compose.lite.yml`
- [x] Remove `/dev/bus/usb:/dev/bus/usb` mount
- [x] Remove `/var/run/joustmania` socket mount
- [x] Delete `scripts/bluetooth-helper.sh`

**Documentation:**
- [x] Update hardware setup guide with new pairing flow
- [x] Document `journalctl -u psmove-pairing -f` for debugging
- [x] Add README to scripts/pairing-daemon/

**Testing:**
- [ ] Test daemon on Raspberry Pi
- [ ] Verify LED feedback (yellow during, white flash on success)
- [ ] Test full pair -> connect -> gameplay flow

## User Workflow

1. Run `setup.sh` (installs daemon as systemd service)
2. Start JoustMania: `docker-compose -f docker-compose.lite.yml up`
3. To pair new controller:
   - Plug in PS Move via USB
   - Wait ~30 seconds (daemon detects and pairs)
   - Check logs: `journalctl -u psmove-pairing -f`
   - Unplug USB, press PS button
   - Controller connects via Bluetooth

## Testing

1. Fresh install with `setup.sh`
2. Verify daemon running: `systemctl status psmove-pairing`
3. Plug in USB controller
4. Watch logs: `journalctl -u psmove-pairing -f`
5. Verify pairing completes
6. Unplug and connect via Bluetooth
7. Verify controller works in JoustMania

## Dependencies

- psmoveapi installed on host (via setup.sh)
- BlueZ/bluetoothctl available
- `ClassicBondedOnly=false` in `/etc/bluetooth/input.conf`

## Migration

This phase supersedes:
- Phase 63 USB handling (no longer relevant - USB only on host)
- Phase 64 auto-discovery (handled by host daemon)
- `bluetooth-helper.sh` socket approach

## Notes

- 30-second polling interval is conservative; can reduce if faster detection needed
- Uses `bluetoothctl devices Paired` to check pairing state - no separate state file
- If user manually unpairs a controller, daemon will re-pair it automatically
- First-gen PS Move controllers require `ClassicBondedOnly=false` (handled in setup.sh)
- Daemon logs to journal for easy debugging
