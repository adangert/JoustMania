#!/bin/bash
# Run ruff linter on the codebase

set -e

echo "Running ruff linter..."
uv run ruff check .

echo "✓ Linting passed!"
