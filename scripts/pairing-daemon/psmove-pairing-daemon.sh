#!/bin/bash
#
# PS Move Controller Pairing Daemon
#
# Polls for USB-connected PS Move controllers and pairs them automatically.
# Run as a systemd service on the host (not in Docker).
#
# LED Feedback:
#   - Yellow solid: Pairing in progress
#   - White flash 3x: Success - unplug and press PS button
#   - Red flash 3x: Error
#
# Usage:
#   sudo systemctl start psmove-pairing
#   journalctl -u psmove-pairing -f
#

POLL_INTERVAL=${POLL_INTERVAL:-30}

# Flash controller LED to indicate status
flash_led() {
    local count=$1
    local r=$2 g=$3 b=$4

    for i in $(seq 1 "$count"); do
        psmove set-leds "$r" "$g" "$b" 2>/dev/null
        sleep 0.2
        psmove set-leds 0 0 0 2>/dev/null
        sleep 0.2
    done
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "PS Move Pairing Daemon started (polling every ${POLL_INTERVAL}s)"

while true; do
    # Check for USB-connected PS Move controllers
    # psmove list output format: "Controller 0: aa:bb:cc:dd:ee:ff (USB)"
    usb_controllers=$(psmove list 2>/dev/null | grep -i "(USB)" | grep -oE '([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}')

    for serial in $usb_controllers; do
        # Normalize to uppercase for comparison
        serial_upper=$(echo "$serial" | tr '[:lower:]' '[:upper:]')

        # Skip if already paired in BlueZ
        if bluetoothctl devices Paired 2>/dev/null | grep -qi "$serial_upper"; then
            continue
        fi

        log "Found unpaired controller: $serial"

        # Yellow - pairing in progress
        psmove set-leds 255 255 0 2>/dev/null

        # Pair controller (writes host BT MAC to controller)
        if psmove pair 2>&1 | grep -qi "paired"; then
            # Trust in BlueZ
            bluetoothctl trust "$serial_upper" 2>/dev/null

            log "Paired $serial successfully"
            log "Restarting bluetooth service..."

            # Restart bluetooth to recognize new device
            systemctl restart bluetooth

            log "Done! Unplug USB cable and press PS button to connect"

            # Flash white 3x - success
            flash_led 3 255 255 255
        else
            log "Failed to pair $serial"

            # Flash red 3x - error
            flash_led 3 255 0 0
        fi
    done

    sleep "$POLL_INTERVAL"
done
