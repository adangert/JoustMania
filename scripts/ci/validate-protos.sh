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

# Check for uncommitted changes in proto .py files
cd "$PROJECT_ROOT"
if ! git diff --exit-code -- 'proto/*.py'; then
    echo "❌ Proto files are out of sync! Run 'make protos' and commit changes."
    exit 1
fi

echo "✅ Proto files validated!"
