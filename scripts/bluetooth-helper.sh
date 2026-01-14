#!/bin/bash
#
# JoustMania Bluetooth Helper
#
# Runs on the host and listens for bluetooth restart requests from Docker containers.
# The container writes to a Unix socket, and this script restarts the bluetooth service.
#
# Usage:
#   sudo ./scripts/bluetooth-helper.sh
#
# Or install as a systemd service (see scripts/setup/install_bluetooth_helper.sh)

SOCKET_DIR="/var/run/joustmania"
SOCKET_PATH="$SOCKET_DIR/bluetooth.sock"

# Create socket directory
mkdir -p "$SOCKET_DIR"
chmod 755 "$SOCKET_DIR"

# Remove old socket if exists
rm -f "$SOCKET_PATH"

echo "JoustMania Bluetooth Helper"
echo "Listening on: $SOCKET_PATH"
echo "Press Ctrl+C to stop"

# Cleanup on exit
cleanup() {
    echo "Shutting down..."
    rm -f "$SOCKET_PATH"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Listen for requests using netcat
while true; do
    # Create socket and wait for connection
    message=$(nc -lU "$SOCKET_PATH" 2>/dev/null)

    if [ -n "$message" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Received: $message"

        case "$message" in
            "restart")
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restarting bluetooth service..."
                systemctl restart bluetooth
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bluetooth service restarted"
                ;;
            "status")
                systemctl status bluetooth --no-pager
                ;;
            *)
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] Unknown command: $message"
                ;;
        esac
    fi

    # Small delay to prevent CPU spinning
    sleep 0.1
done
