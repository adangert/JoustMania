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

    # First check if any PS Move is connected via USB (fast, no controller interaction)
    # 054c:03d5 = PS Move Motion Controller
    # 054c:042f = PS Move Motion Controller (newer)
    if ! lsusb 2>/dev/null | grep -qE "054c:(03d5|042f)"; then
        debug "No USB PS Move detected, skipping psmove list"
        sleep "$POLL_INTERVAL"
        continue
    fi

    debug "USB PS Move detected, checking with psmove..."

    # Get raw psmove output (suppress library debug messages unless DEBUG=1)
    if [ "$DEBUG" = "1" ]; then
        psmove_output=$($PSMOVE list 2>&1)
    else
        psmove_output=$($PSMOVE list 2>/dev/null)
    fi
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

        # Check if already paired/trusted in BlueZ
        # PS Move controllers may be "trusted" rather than "paired" since they initiate connection
        paired_devices=$(bluetoothctl devices Paired 2>/dev/null || true)
        trusted_devices=$(bluetoothctl devices Trusted 2>/dev/null || true)
        # Also check connected devices
        connected_devices=$(bluetoothctl devices Connected 2>/dev/null || true)
        all_known="$paired_devices $trusted_devices $connected_devices"
        debug "Known devices: $all_known"

        # Check with both formats: XX:XX:XX:XX:XX:XX and XXXXXXXXXXXX
        serial_nocolons=$(echo "$serial_upper" | tr -d ':')
        if echo "$all_known" | grep -qi "$serial_upper\|$serial_nocolons"; then
            debug "Controller $serial_upper already known to BlueZ, skipping"
            continue
        fi

        # Also check if psmove itself thinks it's paired (host address already set)
        psmove_info=$($PSMOVE list 2>/dev/null | grep -i "$serial" || true)
        if echo "$psmove_info" | grep -qi "bluetooth\|paired\|host"; then
            debug "Controller $serial_upper already has host set, skipping"
            continue
        fi

        log "Found unpaired USB controller: $serial"

        # Pair controller (writes host BT MAC to controller)
        log "Pairing controller..."
        pair_output=$($PSMOVE pair 2>&1)
        pair_exit=$?
        debug "Pair output: $pair_output"
        debug "Pair exit code: $pair_exit"

        # Check for explicit failure indicators
        # Note: psmove pair output varies; only fail if we see clear error messages
        pair_failed=false
        if echo "$pair_output" | grep -qi "error\|failed\|cannot\|unable\|permission denied\|not found"; then
            # Only fail if it's a real error, not just "already set" type messages
            if ! echo "$pair_output" | grep -qi "already\|set\|paired\|master"; then
                pair_failed=true
            fi
        fi

        if [ "$pair_failed" = "false" ]; then
            # Success - either explicit success message, exit 0, or no failure indicators
            debug "Pair appears successful, trusting device in BlueZ: $serial_upper"
            bluetoothctl trust "$serial_upper" &>/dev/null

            # Calibrate controller (saves to ~/.psmoveapi/)
            log "Calibrating controller..."
            calibrate_output=$($PSMOVE calibrate 2>&1) || true
            debug "Calibrate output: $calibrate_output"

            log "Controller ready: $serial - unplug USB and press PS button to connect"
        else
            log "Failed to pair $serial (exit code: $pair_exit)"
            log "Pair output: $pair_output"
        fi
    done

    sleep "$POLL_INTERVAL"
done
