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
# Environment:
#   POLL_INTERVAL - seconds between polls (default: 10)
#   PSMOVE_PATH   - path to psmove binary (default: auto-detect)
#   DEBUG         - set to 1 for verbose logging
#

POLL_INTERVAL=${POLL_INTERVAL:-10}
DEBUG=${DEBUG:-0}

# Find psmove binary
if [ -n "$PSMOVE_PATH" ]; then
    PSMOVE="$PSMOVE_PATH"
elif command -v psmove &>/dev/null; then
    PSMOVE="psmove"
elif [ -x "$HOME/psmoveapi/build/psmove" ]; then
    PSMOVE="$HOME/psmoveapi/build/psmove"
elif [ -x "/home/$(logname 2>/dev/null)/psmoveapi/build/psmove" ]; then
    PSMOVE="/home/$(logname 2>/dev/null)/psmoveapi/build/psmove"
else
    echo "ERROR: psmove binary not found. Install psmoveapi or set PSMOVE_PATH"
    exit 1
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

debug() {
    if [ "$DEBUG" = "1" ]; then
        log "[DEBUG] $*"
    fi
}

# Flash controller LED to indicate status
# Note: LED control requires hidapi, not available via psmove CLI
# This is a no-op placeholder for now
flash_led() {
    local count=$1
    debug "LED flash requested (not implemented via CLI)"
}

log "PS Move Pairing Daemon started"
log "  psmove binary: $PSMOVE"
log "  poll interval: ${POLL_INTERVAL}s"
log "  debug mode: $DEBUG"

# Verify psmove works
if ! $PSMOVE list &>/dev/null; then
    log "WARNING: 'psmove list' failed - check permissions/udev rules"
fi

poll_count=0
while true; do
    poll_count=$((poll_count + 1))
    debug "Poll #$poll_count"

    # Get raw psmove output for debugging
    psmove_output=$($PSMOVE list 2>&1)
    psmove_exit=$?

    debug "psmove list exit code: $psmove_exit"
    if [ "$DEBUG" = "1" ]; then
        echo "$psmove_output" | while read -r line; do
            debug "psmove: $line"
        done
    fi

    # Check for errors
    if [ $psmove_exit -ne 0 ]; then
        debug "psmove list failed"
        sleep "$POLL_INTERVAL"
        continue
    fi

    # Check for USB-connected controllers
    # Look for lines containing "USB" and extract controller info
    usb_count=$(echo "$psmove_output" | grep -ci "USB" || true)
    usb_count=${usb_count:-0}
    debug "USB controllers detected: $usb_count"

    if [ "$usb_count" = "0" ] || [ -z "$usb_count" ]; then
        debug "No USB controllers found"
        sleep "$POLL_INTERVAL"
        continue
    fi

    # Extract serial numbers - handle various psmove output formats
    # Format 1: "Controller 0: aa:bb:cc:dd:ee:ff (USB)"
    # Format 2: just MAC addresses with USB indicator
    usb_controllers=$(echo "$psmove_output" | grep -i "USB" | grep -oE '([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}')

    if [ -z "$usb_controllers" ]; then
        log "USB controller detected but couldn't extract serial"
        log "Raw output: $psmove_output"
        sleep "$POLL_INTERVAL"
        continue
    fi

    for serial in $usb_controllers; do
        # Normalize to uppercase for comparison
        serial_upper=$(echo "$serial" | tr '[:lower:]' '[:upper:]')
        debug "Processing controller: $serial_upper"

        # Check if already paired in BlueZ
        paired_devices=$(bluetoothctl devices Paired 2>/dev/null)
        debug "Paired devices: $paired_devices"

        if echo "$paired_devices" | grep -qi "$serial_upper"; then
            debug "Controller $serial_upper already paired, skipping"
            continue
        fi

        log "Found unpaired USB controller: $serial"

        # Pair controller (writes host BT MAC to controller)
        log "Running: $PSMOVE pair"
        pair_output=$($PSMOVE pair 2>&1)
        pair_exit=$?
        log "Pair output: $pair_output"
        log "Pair exit code: $pair_exit"

        if echo "$pair_output" | grep -qi "paired\|success\|master"; then
            # Trust in BlueZ
            log "Trusting device in BlueZ: $serial_upper"
            bluetoothctl trust "$serial_upper" 2>&1 | while read -r line; do
                log "bluetoothctl: $line"
            done

            log "Paired $serial successfully"
            log "Restarting bluetooth service..."

            # Restart bluetooth to recognize new device
            systemctl restart bluetooth
            sleep 2

            log "Done! Unplug USB cable and press PS button to connect"

            # Flash white 3x - success
            flash_led 3 255 255 255
        else
            log "Failed to pair $serial"
            log "Pair output was: $pair_output"

            # Flash red 3x - error
            flash_led 3 255 0 0
        fi
    done

    sleep "$POLL_INTERVAL"
done
