#!/usr/bin/env bash
# Run integration tests in CI
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "Building test runner image..."
docker build -t joustmania/ci-test:latest tools/ci-test/

echo "Running integration tests..."
docker run --rm \
    -v "$PROJECT_ROOT:/workspace" \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -w /workspace \
    -e DOCKER_HOST=unix:///var/run/docker.sock \
    joustmania/ci-test:latest \
    uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py -v

echo "✅ Integration tests passed!"
