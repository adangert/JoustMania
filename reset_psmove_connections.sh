#!/usr/bin/env bash

set -e

if [ "$UID" -ne 0 ]; then
    exec sudo "$0" "$@"
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PYTHON="$SCRIPT_DIR/venv/bin/python3"
JOUSTMANIA_STOPPED=0

restart_joustmania() {
    if [ "$JOUSTMANIA_STOPPED" -eq 1 ]; then
        echo "Starting JoustMania..."
        "$SCRIPT_DIR/start_joustmania.sh" || true
    fi
}

# Once this workflow stops the service, make a best effort to start it even
# when controller cleanup fails.
trap restart_joustmania EXIT

if [ ! -x "$PYTHON" ]; then
    PYTHON=python3
fi

JOUSTMANIA_STOPPED=1
"$SCRIPT_DIR/stop_joustmania.sh"
cd "$SCRIPT_DIR"
"$PYTHON" clear_devices.py
