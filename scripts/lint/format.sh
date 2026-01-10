#!/bin/bash
# Format code with ruff

set -e

echo "Formatting code with ruff..."
uv run ruff format .

echo "✓ Code formatted!"
