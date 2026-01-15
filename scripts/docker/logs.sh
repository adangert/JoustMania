#!/bin/bash
#
# View logs for JoustMania services
#
# Usage:
#   scripts/docker/logs.sh         # All services
#   scripts/docker/logs.sh audio   # Specific service
#

SERVICE=${1:-""}

if [ -z "$SERVICE" ]; then
    echo "Following logs for all services (Ctrl+C to exit)..."
    echo ""
    docker compose logs -f
else
    echo "Following logs for service: $SERVICE (Ctrl+C to exit)..."
    echo ""
    docker compose logs -f "$SERVICE"
fi
