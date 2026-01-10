#!/usr/bin/env bash
#
# Generate Python code from all protobuf schemas
# This script should be run from the project root directory

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "Generating Python code from protobuf schemas..."

# Generate Python code for all proto files
uv run --package joustmania-proto python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=proto \
    --grpc_python_out=proto \
    proto/*.proto

echo "✓ Generated Python code for all protobuf schemas"

# Fix imports in generated files to use absolute imports
echo "Fixing imports in generated files..."

for file in proto/*_pb2_grpc.py; do
    if [ -f "$file" ]; then
        # Replace relative imports with absolute imports
        sed -i 's/^import \([a-z_]*\)_pb2 as/from proto import \1_pb2 as/' "$file"
        echo "  ✓ Fixed imports in $(basename "$file")"
    fi
done

echo "✓ All protobuf code generated successfully"
