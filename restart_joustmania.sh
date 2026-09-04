#!/usr/bin/env bash

set -euo pipefail

if [ "${UID}" -ne 0 ]; then
    echo "Not root. Using sudo."
    exec sudo "$0" "$@"
fi

echo "Restarting JoustMania..."
supervisorctl restart joustmania
supervisorctl status joustmania
