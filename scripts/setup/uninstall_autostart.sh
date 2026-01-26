#!/bin/bash
# Uninstall JoustMania systemd service

set -e

SERVICE_NAME="joustmania.service"
SYSTEMD_DIR="/etc/systemd/system"

echo "Uninstalling JoustMania autostart service..."

# Check if running as root
if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)"
    exit 1
fi

# Stop the service if running
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Stopping $SERVICE_NAME..."
    systemctl stop "$SERVICE_NAME"
fi

# Disable the service
if systemctl is-enabled --quiet "$SERVICE_NAME"; then
    echo "Disabling $SERVICE_NAME..."
    systemctl disable "$SERVICE_NAME"
fi

# Remove service file
if [[ -f "$SYSTEMD_DIR/$SERVICE_NAME" ]]; then
    echo "Removing service file from $SYSTEMD_DIR/$SERVICE_NAME"
    rm "$SYSTEMD_DIR/$SERVICE_NAME"
fi

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload
systemctl reset-failed

echo ""
echo "✓ JoustMania autostart service uninstalled successfully!"
echo ""
echo "JoustMania will no longer start automatically on boot."
echo "You can manually start it with: docker compose up -d"
