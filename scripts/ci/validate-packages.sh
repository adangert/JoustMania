#!/usr/bin/env bash
# Validate Python package installation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Validating Python packages..."

docker run --rm \
    -v "$PROJECT_ROOT:/workspace" \
    -w /workspace \
    joustmania/ci-proto:latest \
    bash -c '
        set -e
        echo "Installing workspace packages..."
        uv sync --all-packages

        echo "Testing proto imports..."
        uv run python -c "from proto import settings_pb2, controller_manager_pb2; print(\"✅ Proto imports work\")"

        echo "Checking for dependency conflicts..."
        uv pip check

        echo "✅ All packages validated!"
    '
