#!/bin/bash
# Run all code quality checks

set -e

echo "======================================"
echo "Running all code quality checks..."
echo "======================================"
echo ""

# Run type checking
./scripts/lint/check-types.sh
echo ""

# Run linting
./scripts/lint/check-lint.sh
echo ""

echo "======================================"
echo "✓ All checks passed!"
echo "======================================"
