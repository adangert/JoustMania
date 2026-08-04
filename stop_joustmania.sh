#!/usr/bin/env bash

set -e

if [ "$UID" -ne 0 ]; then
    exec sudo "$0" "$@"
fi

# Stops JoustMania and any controller processes left behind during development.
supervisorctl stop joustmania
pkill -9 -f '^JoustMania-' || true
