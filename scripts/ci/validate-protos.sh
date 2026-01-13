#!/usr/bin/env bash
# Validate proto file generation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Validating proto generation..."

# Generate protos in Docker container
docker run --rm \
    -v "$PROJECT_ROOT:/workspace" \
    -w /workspace \
    joustmania/ci-proto:latest \
    bash proto/generate_proto.sh

# Check for uncommitted changes
cd "$PROJECT_ROOT"
if ! git diff --exit-code proto/; then
    echo "❌ Proto files are out of sync! Run 'make protos' and commit changes."
    exit 1
fi

# Verify bytecode compilation
if [ ! -d "proto/__pycache__" ]; then
    echo "❌ Proto bytecode not generated!"
    exit 1
fi

PYC_COUNT=$(find proto/__pycache__ -name "*.opt-2.pyc" | wc -l)
if [ "$PYC_COUNT" -lt 10 ]; then
    echo "❌ Expected at least 10 .opt-2.pyc files, found $PYC_COUNT"
    exit 1
fi

echo "✅ Proto files validated! Found $PYC_COUNT bytecode files"
