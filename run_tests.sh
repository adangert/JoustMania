#!/bin/bash

# Test runner for JoustMania state-based architecture
# Runs unit tests and performance benchmarks

set -e  # Exit on error

echo "========================================"
echo "JoustMania State-Based Architecture Tests"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Raspberry Pi or development machine
if [ -f /proc/device-tree/model ]; then
    PI_MODEL=$(cat /proc/device-tree/model)
    echo -e "${YELLOW}Running on: ${PI_MODEL}${NC}"
else
    echo -e "${YELLOW}Running on: Development Machine${NC}"
fi
echo ""

# Run unit tests
echo "========================================"
echo "Running Unit Tests"
echo "========================================"
python3 -m pytest testing/test_controller_state.py -v

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Unit tests passed${NC}"
else
    echo -e "${RED}✗ Unit tests failed${NC}"
    exit 1
fi

echo ""
echo "========================================"
echo "Running Performance Benchmarks"
echo "========================================"
python3 -m pytest testing/test_performance_benchmark.py -v -s

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Performance benchmarks passed${NC}"
else
    echo -e "${RED}✗ Performance benchmarks failed${NC}"
    exit 1
fi

echo ""
echo "========================================"
echo "All Tests Passed!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Review benchmark results above"
echo "2. Compare CPU usage with expected < 2% per controller"
echo "3. Verify latency improvements (target: < 5ms average)"
echo "4. Test with real Move controllers if available"
