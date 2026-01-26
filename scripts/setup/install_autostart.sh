#!/bin/bash
# Install JoustMania systemd service for autostart on boot

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/joustmania.service"
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_NAME="joustmania.service"

echo "Installing JoustMania autostart service..."

# Check if running as root
if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)"
    exit 1
fi

# Get the actual user (not root when using sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")

# Update service file with actual paths
echo "Configuring service for user: $ACTUAL_USER"
echo "Home directory: $ACTUAL_HOME"

# Create temporary service file with correct paths
TMP_SERVICE=$(mktemp)
sed "s|/home/pi|$ACTUAL_HOME|g" "$SERVICE_FILE" | \
sed "s|User=pi|User=$ACTUAL_USER|g" | \
sed "s|Group=pi|Group=$ACTUAL_USER|g" > "$TMP_SERVICE"

# Copy service file to systemd directory
echo "Installing service file to $SYSTEMD_DIR/$SERVICE_NAME"
cp "$TMP_SERVICE" "$SYSTEMD_DIR/$SERVICE_NAME"
rm "$TMP_SERVICE"

# Set proper permissions
chmod 644 "$SYSTEMD_DIR/$SERVICE_NAME"

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable the service
echo "Enabling $SERVICE_NAME..."
systemctl enable "$SERVICE_NAME"

# Show service status
echo ""
echo "✓ JoustMania autostart service installed successfully!"
echo ""
echo "Available commands:"
echo "  sudo systemctl start joustmania    - Start JoustMania now"
echo "  sudo systemctl stop joustmania     - Stop JoustMania"
echo "  sudo systemctl restart joustmania  - Restart JoustMania"
echo "  sudo systemctl status joustmania   - Check service status"
echo "  sudo systemctl disable joustmania  - Disable autostart"
echo "  sudo journalctl -u joustmania -f   - View logs (follow mode)"
echo ""
echo "JoustMania will now start automatically on boot."
