#!/bin/bash
#
# PS Move API Install Script
# Extracts prebuilt PS Move API binaries from the controller-manager Docker image
# (which is already required for the game to run)
#

set -e  # Exit on error

HOMENAME="$(logname)"
HOMEDIR="/home/$HOMENAME"

# Controller manager image (same as used by docker-compose)
CONTROLLER_MANAGER_IMAGE="${CONTROLLER_MANAGER_IMAGE:-ghcr.io/watchmejoustmyflags/joustmania/controller-manager-service:latest}"

echo "=========================================="
echo "PS Move API Install (from Docker image)"
echo "=========================================="

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed. Please run setup_host.sh first."
    exit 1
fi

# Check if user can run docker
if ! docker info &> /dev/null; then
    echo "ERROR: Cannot connect to Docker. Make sure Docker is running and user has permissions."
    echo "Try: sudo usermod -aG docker $USER && newgrp docker"
    exit 1
fi

# Pull the controller-manager image if not present
echo "[1/4] Ensuring controller-manager image is available..."
if ! docker image inspect "$CONTROLLER_MANAGER_IMAGE" &> /dev/null; then
    echo "  → Pulling $CONTROLLER_MANAGER_IMAGE..."
    docker pull "$CONTROLLER_MANAGER_IMAGE" || exit 1
else
    echo "  → Image already available"
fi

# Create a temporary container to extract files
echo "[2/4] Extracting psmove binaries from container..."
CONTAINER_ID=$(docker create "$CONTROLLER_MANAGER_IMAGE")
trap "docker rm $CONTAINER_ID > /dev/null 2>&1" EXIT

# Create temp directory for extraction
TEMP_DIR=$(mktemp -d)
trap "docker rm $CONTAINER_ID > /dev/null 2>&1; rm -rf $TEMP_DIR" EXIT

# Copy psmove files from container
docker cp "$CONTAINER_ID:/usr/local/lib/python3.11/site-packages/psmove.py" "$TEMP_DIR/" || exit 1
docker cp "$CONTAINER_ID:/usr/local/lib/python3.11/site-packages/_psmove.so" "$TEMP_DIR/" || exit 1
docker cp "$CONTAINER_ID:/usr/local/lib/libpsmoveapi.so" "$TEMP_DIR/" || exit 1

echo "  → Extracted psmove.py"
echo "  → Extracted _psmove.so"
echo "  → Extracted libpsmoveapi.so"

# Install psmove Python bindings to venv
echo "[3/4] Installing psmove Python bindings..."
VENV="$HOMEDIR/JoustMania/venv"
SITE_PACKAGES=$(find "$VENV/lib" -type d -name "site-packages" | head -1)

if [[ -z "$SITE_PACKAGES" ]]; then
    echo "ERROR: Could not find venv site-packages directory"
    echo "Make sure the venv exists at $VENV"
    exit 1
fi

# Copy psmove Python module and native library to venv
cp "$TEMP_DIR/psmove.py" "$SITE_PACKAGES/" || exit 1
cp "$TEMP_DIR/_psmove.so" "$SITE_PACKAGES/" || exit 1

echo "  → Installed psmove.py to $SITE_PACKAGES/"
echo "  → Installed _psmove.so to $SITE_PACKAGES/"

# Also install to pairing daemon venv if it exists
PAIRING_DAEMON_VENV="/opt/joustmania/scripts/pairing-daemon/venv"
if [[ -d "$PAIRING_DAEMON_VENV" ]]; then
    PAIRING_SITE_PACKAGES=$(find "$PAIRING_DAEMON_VENV/lib" -type d -name "site-packages" | head -1)
    if [[ -n "$PAIRING_SITE_PACKAGES" ]]; then
        sudo cp "$TEMP_DIR/psmove.py" "$PAIRING_SITE_PACKAGES/" || echo "  → Warning: Could not copy to pairing daemon venv"
        sudo cp "$TEMP_DIR/_psmove.so" "$PAIRING_SITE_PACKAGES/" || echo "  → Warning: Could not copy to pairing daemon venv"
        echo "  → Installed psmove.py to $PAIRING_SITE_PACKAGES/"
        echo "  → Installed _psmove.so to $PAIRING_SITE_PACKAGES/"
    fi
fi

# Install shared library to system
echo "[4/4] Installing shared library..."
sudo cp "$TEMP_DIR/libpsmoveapi.so" /usr/local/lib/ || exit 1
sudo ldconfig

echo "  → Installed libpsmoveapi.so to /usr/local/lib/"
echo "  → Updated library cache"

# Verify installation
echo ""
echo "Verifying installation..."
"$VENV/bin/python3" -c "import psmove; print(f'  → psmove OK: {psmove.count_connected()} controllers detected')" || {
    echo "WARNING: psmove import test failed (may work after reboot)"
}

echo ""
echo "=========================================="
echo "PS Move API installation complete!"
echo "=========================================="
echo ""
echo "psmove library installed to: $SITE_PACKAGES"
echo "Shared library installed to: /usr/local/lib/libpsmoveapi.so"
echo ""
