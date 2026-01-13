#!/usr/bin/env bash
# Build all service Docker images
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SERVICES=(
    "controller_manager"
    "game_coordinator"
    "settings"
    "supervisor"
    "menu"
    "audio"
    "webui"
)

echo "Building all services..."

for service in "${SERVICES[@]}"; do
    echo ""
    echo "========================================"
    echo "Building $service"
    echo "========================================"
    "$SCRIPT_DIR/build-service.sh" "$service"
done

echo ""
echo "✅ All services built successfully!"
