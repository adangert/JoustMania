#!/bin/bash
# Run ty type checker on the codebase

set -e

echo "Running ty type checker..."
uv run ty check

echo "✓ Type checking passed!"
