#!/bin/bash
#
# JoustMania Setup Script
# Choose between minimal runtime setup or full development setup
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "JoustMania Setup"
echo "=========================================="
echo ""
echo "Choose setup type:"
echo ""
echo "  1) Runtime Only (5 min)"
echo "     - Docker, Bluetooth config, pairing daemon"
echo "     - For running JoustMania on a Pi"
echo "     - Requires existing psmoveapi (from old install) for pairing"
echo ""
echo "  2) Full Development Setup (15-30 min)"
echo "     - Everything in Runtime, plus:"
echo "     - Python/uv, build psmoveapi from source"
echo "     - For development and testing outside Docker"
echo ""
echo "  3) Cancel"
echo ""

read -p "Select option [1-3]: " -n 1 -r
echo
echo ""

case "$REPLY" in
    1)
        echo "=========================================="
        echo "Runtime Setup"
        echo "=========================================="
        bash "$SCRIPT_DIR/scripts/setup/setup_runtime.sh" 2>&1 | tee setup_runtime.log
        if [[ $? -ne 0 ]]; then
            echo "ERROR: Runtime setup failed. Check setup_runtime.log for details."
            exit 1
        fi

        # Check if psmove is available
        if ! command -v psmove &> /dev/null; then
            echo ""
            echo "Note: psmove CLI not found. To enable automatic pairing,"
            echo "you'll need to build psmoveapi:"
            echo "  ./scripts/setup/build_psmoveapi.sh"
            echo ""
        fi
        ;;

    2)
        echo "=========================================="
        echo "Full Development Setup"
        echo "=========================================="
        echo ""
        echo "This will:"
        echo "  1. Install system dependencies and configure host"
        echo "  2. Build PS Move API from source (~10 min)"
        echo ""
        echo "This process requires a reboot when complete."
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
        if [[ $? -ne 0 ]]; then
            echo "ERROR: Host setup failed. Check setup_host.log for details."
            exit 1
        fi

        # Run PS Move API build
        echo ""
        echo "=========================================="
        echo "Step 2/2: PS Move API Build"
        echo "=========================================="
        bash "$SCRIPT_DIR/scripts/setup/build_psmoveapi.sh" 2>&1 | tee setup_psmoveapi.log
        if [[ $? -ne 0 ]]; then
            echo "ERROR: PS Move API build failed. Check setup_psmoveapi.log for details."
            exit 1
        fi

        echo ""
        echo "=========================================="
        echo "Full setup complete!"
        echo "=========================================="
        echo ""
        echo "Would you like to enable autostart on boot?"
        read -p "Enable autostart? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo "$SCRIPT_DIR/scripts/setup/install_autostart.sh"
        fi

        echo ""
        echo "System will reboot in 5 seconds..."
        (sleep 5; sudo reboot) &
        exit 0
        ;;

    3|*)
        echo "Setup cancelled."
        exit 0
        ;;
esac

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To start JoustMania:"
echo "  docker compose -f docker-compose.lite.yml up -d"
echo ""
echo "To enable autostart on boot:"
echo "  sudo ./scripts/setup/install_autostart.sh"
echo ""
