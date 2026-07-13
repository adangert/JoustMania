#!/usr/bin/env bash

set -e

if [ "$UID" -ne 0 ]; then
    exec sudo "$0" "$@"
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PYTHON="$SCRIPT_DIR/venv/bin/python3"

if [ ! -x "$PYTHON" ]; then
    PYTHON=python3
fi

"$SCRIPT_DIR/stop_joustmania.sh"
cd "$SCRIPT_DIR"
"$PYTHON" clear_devices.py
"$SCRIPT_DIR/start_joustmania.sh"
