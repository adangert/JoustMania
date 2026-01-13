#!/usr/bin/env bash
# Run ruff linting in Docker container
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Running ruff linting..."

docker run --rm \
    -v "$PROJECT_ROOT:/workspace:ro" \
    -w /workspace \
    joustmania/ci-lint:latest \
    ruff check . --output-format=github

echo "✅ Linting passed!"
