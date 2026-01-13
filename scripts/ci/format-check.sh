#!/usr/bin/env bash
# Check code formatting with ruff
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Checking code formatting..."

docker run --rm \
    -v "$PROJECT_ROOT:/workspace:ro" \
    -w /workspace \
    joustmania/ci-lint:latest \
    ruff format --check .

echo "✅ Formatting is correct!"
