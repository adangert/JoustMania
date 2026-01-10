#!/bin/bash
#
# JoustMania Setup Script
# Wrapper that calls modular setup scripts
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "JoustMania Setup"
echo "=========================================="
echo ""
echo "This will:"
echo "  1. Install system dependencies and configure host"
echo "  2. Build PS Move API from source"
echo ""
echo "This process will take 10-30 minutes and requires a reboot."
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Setup cancelled."
    exit 0
fi

# Run host setup
echo ""
echo "=========================================="
echo "Step 1/2: Host System Setup"
echo "=========================================="
bash "$SCRIPT_DIR/scripts/setup/setup_host.sh" 2>&1 | tee setup_host.log
if [ $? -ne 0 ]; then
    echo "ERROR: Host setup failed. Check setup_host.log for details."
    exit 1
fi

# Run PS Move API build
echo ""
echo "=========================================="
echo "Step 2/2: PS Move API Build"
echo "=========================================="
bash "$SCRIPT_DIR/scripts/setup/build_psmoveapi.sh" 2>&1 | tee setup_psmoveapi.log
if [ $? -ne 0 ]; then
    echo "ERROR: PS Move API build failed. Check setup_psmoveapi.log for details."
    exit 1
fi

echo ""
echo "=========================================="
echo "JoustMania setup complete!"
echo "=========================================="
echo ""
echo "System will reboot in 5 seconds..."
echo "After reboot, you can start JoustMania with: docker-compose up"
echo ""

# Pause before rebooting
(sleep 5; sudo reboot) &
