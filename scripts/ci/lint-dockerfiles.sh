#!/usr/bin/env bash
# Lint all Dockerfiles with hadolint
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Linting Dockerfiles..."

# Find and lint all Dockerfiles
docker run --rm \
    --entrypoint /bin/sh \
    -v "$PROJECT_ROOT:/workspace:ro" \
    -w /workspace \
    joustmania/ci-hadolint:latest \
    -c 'find . -name "Dockerfile" -type f -exec echo "Linting {}" \; -exec hadolint {} \;'

echo "✅ All Dockerfiles passed linting!"
