#!/usr/bin/env bash
# Run ty type checking in Docker container
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Running ty type checking..."

# Array of services to check
SERVICES=(
    "controller_manager"
    "game_coordinator"
    "settings"
    "supervisor"
    "menu"
    "audio"
    "webui"
)

FAILED=0

for service in "${SERVICES[@]}"; do
    echo "Checking services/$service..."

    docker run --rm \
        -v "$PROJECT_ROOT:/workspace:ro" \
        -w /workspace \
        joustmania/ci-lint:latest \
        ty check "services/$service" \
        || FAILED=1
done

if [ $FAILED -eq 1 ]; then
    echo "❌ Type checking found issues (warnings only for now)"
    exit 0  # Warning-only mode, change to exit 1 when ready to enforce
else
    echo "✅ Type checking passed!"
fi
