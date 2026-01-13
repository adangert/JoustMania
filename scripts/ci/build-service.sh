#!/usr/bin/env bash
# Build a single service Docker image
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <service-name>"
    echo "Example: $0 controller_manager"
    exit 1
fi

SERVICE=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Building $SERVICE service..."

docker build \
    -f "$PROJECT_ROOT/services/$SERVICE/Dockerfile" \
    -t "joustmania/${SERVICE}-service:ci" \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    "$PROJECT_ROOT"

echo "✅ Built $SERVICE successfully!"
