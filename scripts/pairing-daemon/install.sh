#!/bin/bash
#
# Install PS Move Pairing Daemon
#
# Installs the pairing daemon as a systemd service.
# Run with sudo from the JoustMania directory.
#
# Usage:
#   sudo ./scripts/pairing-daemon/install.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing PS Move Pairing Daemon..."

# Copy daemon script
echo "  Installing daemon script..."
cp "$SCRIPT_DIR/psmove-pairing-daemon.sh" /usr/local/bin/
chmod +x /usr/local/bin/psmove-pairing-daemon.sh

# Install systemd service
echo "  Installing systemd service..."
cp "$SCRIPT_DIR/psmove-pairing.service" /etc/systemd/system/

# Reload systemd
echo "  Reloading systemd..."
systemctl daemon-reload

# Enable service
echo "  Enabling service..."
systemctl enable psmove-pairing.service

# Start service
echo "  Starting service..."
systemctl start psmove-pairing.service

echo ""
echo "PS Move Pairing Daemon installed and running!"
echo ""
echo "Commands:"
echo "  View logs:    journalctl -u psmove-pairing -f"
echo "  Status:       systemctl status psmove-pairing"
echo "  Restart:      sudo systemctl restart psmove-pairing"
echo "  Stop:         sudo systemctl stop psmove-pairing"
echo ""
echo "To pair a controller:"
echo "  1. Plug in PS Move via USB"
echo "  2. Wait for white flash (success)"
echo "  3. Unplug USB and press PS button"
