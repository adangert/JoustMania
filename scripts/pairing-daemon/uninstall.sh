#!/bin/bash
#
# Uninstall PS Move Pairing Daemon
#
# Removes the pairing daemon systemd service.
# Run with sudo.
#
# Usage:
#   sudo ./scripts/pairing-daemon/uninstall.sh
#

set -e

echo "Uninstalling PS Move Pairing Daemon..."

# Stop service if running
if systemctl is-active --quiet psmove-pairing.service 2>/dev/null; then
    echo "  Stopping service..."
    systemctl stop psmove-pairing.service
fi

# Disable service
if systemctl is-enabled --quiet psmove-pairing.service 2>/dev/null; then
    echo "  Disabling service..."
    systemctl disable psmove-pairing.service
fi

# Remove files
echo "  Removing files..."
rm -f /etc/systemd/system/psmove-pairing.service
rm -f /usr/local/bin/psmove-pairing-daemon.sh

# Reload systemd
echo "  Reloading systemd..."
systemctl daemon-reload

echo ""
echo "PS Move Pairing Daemon uninstalled."
