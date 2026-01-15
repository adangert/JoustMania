#!/bin/bash
#
# JoustMania Runtime Setup (Minimal)
#
# Sets up only what's needed to RUN JoustMania with Docker.
# For development (running tests, building outside Docker), use setup_host.sh instead.
#
# What this installs:
#   - Docker and docker-compose
#   - Bluetooth configuration
#   - PS Move pairing daemon
#
# What this does NOT install:
#   - Python/uv (not needed - runs in Docker)
#   - psmoveapi build (not needed if already installed, or for manual pairing)
#
# Prerequisites:
#   - Raspberry Pi OS (64-bit recommended)
#   - psmove CLI (for pairing daemon) - already present on old JoustMania installs
#

set -e  # Exit on error

# Prevent apt from prompting about restarting services
export DEBIAN_FRONTEND=noninteractive

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

HOMENAME=$(logname 2>/dev/null || echo $USER)
HOMEDIR=/home/$HOMENAME
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JOUSTMANIA_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo "=========================================="
echo "JoustMania Runtime Setup"
echo "=========================================="
echo ""
echo "This installs the minimum needed to run JoustMania."
echo "For development, use: ./scripts/setup/setup_host.sh"
echo ""

# Check if running as root (we need sudo for some things)
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Please run without sudo. The script will ask for sudo when needed.${NC}"
    exit 1
fi

# Step 1: Install Docker
echo "[1/5] Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "  → Installing Docker..."
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
    rm /tmp/get-docker.sh

    # Add user to docker group
    sudo usermod -aG docker $USER
    echo -e "  → ${GREEN}Docker installed${NC}"
    echo -e "  → ${YELLOW}NOTE: Log out and back in for docker group to take effect${NC}"
    DOCKER_GROUP_CHANGED=true
else
    echo -e "  → ${GREEN}Docker already installed${NC}"
fi

# Check docker-compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "  → Installing docker-compose plugin..."
    sudo apt-get update -y
    sudo apt-get install -y docker-compose-plugin
fi

# Step 2: Install minimal system dependencies
echo "[2/5] Installing system dependencies..."
sudo apt-get update -y
sudo apt-get install -y \
    bluez \
    bluez-tools \
    alsa-utils \
    || exit 1
echo -e "  → ${GREEN}Dependencies installed${NC}"

# Step 3: Configure Bluetooth
echo "[3/5] Configuring Bluetooth..."

# Detect config.txt location based on distribution
DIST_REL=$(lsb_release -r -s 2>/dev/null | cut -d. -f1 || echo "12")
if [ "$DIST_REL" -ge 12 ]; then
    config_loc=/boot/firmware/config.txt
else
    config_loc=/boot/config.txt
fi

# Disable internal Bluetooth (use USB adapters for better performance)
if [ -f "$config_loc" ]; then
    if ! grep -q 'dtoverlay=disable-bt' "$config_loc" 2>/dev/null; then
        echo "  → Disabling internal Bluetooth (USB adapters recommended)..."
        echo "dtoverlay=disable-bt" | sudo tee -a "$config_loc" > /dev/null
        sudo rm -rf /var/lib/bluetooth/* 2>/dev/null || true
        REBOOT_NEEDED=true
    else
        echo "  → Internal Bluetooth already disabled"
    fi
fi

# Configure ClassicBondedOnly for PS Move controllers
if [ -f "/etc/bluetooth/input.conf" ]; then
    if grep -q "ClassicBondedOnly=true" /etc/bluetooth/input.conf 2>/dev/null; then
        echo "  → Setting ClassicBondedOnly=false..."
        sudo sed -i 's/ClassicBondedOnly=true/ClassicBondedOnly=false/' /etc/bluetooth/input.conf
    elif ! grep -q "ClassicBondedOnly" /etc/bluetooth/input.conf 2>/dev/null; then
        echo "  → Adding ClassicBondedOnly=false..."
        echo "ClassicBondedOnly=false" | sudo tee -a /etc/bluetooth/input.conf > /dev/null
    else
        echo "  → Bluetooth already configured"
    fi
else
    echo "  → Creating /etc/bluetooth/input.conf..."
    echo -e "[General]\nClassicBondedOnly=false" | sudo tee /etc/bluetooth/input.conf > /dev/null
fi
echo -e "  → ${GREEN}Bluetooth configured${NC}"

# Step 4: Check for psmove CLI (needed for pairing daemon)
echo "[4/5] Checking for psmove CLI..."
PSMOVE_AVAILABLE=false
if command -v psmove &> /dev/null; then
    echo -e "  → ${GREEN}psmove CLI found${NC}"
    PSMOVE_AVAILABLE=true
elif [ -f "$HOMEDIR/psmoveapi/build/psmove" ]; then
    echo "  → Found psmove in ~/psmoveapi/build/"
    echo "  → Adding to PATH..."
    export PATH="$HOMEDIR/psmoveapi/build:$PATH"
    # Add to .bashrc for persistence
    if ! grep -q "psmoveapi/build" "$HOMEDIR/.bashrc" 2>/dev/null; then
        echo 'export PATH="$HOME/psmoveapi/build:$PATH"' >> "$HOMEDIR/.bashrc"
    fi
    PSMOVE_AVAILABLE=true
else
    echo -e "  → ${YELLOW}psmove CLI not found${NC}"
    echo ""
    echo "    The pairing daemon needs the psmove CLI to pair controllers."
    echo "    Options:"
    echo "      1. Build psmoveapi: ./scripts/setup/build_psmoveapi.sh"
    echo "      2. Pair manually: Connect via USB, use bluetoothctl"
    echo "      3. Skip pairing daemon (existing paired controllers will work)"
    echo ""
fi

# Step 5: Install pairing daemon
echo "[5/5] Installing PS Move pairing daemon..."
PAIRING_SCRIPT="$JOUSTMANIA_DIR/scripts/pairing-daemon/install.sh"
if [ -f "$PAIRING_SCRIPT" ]; then
    if [ "$PSMOVE_AVAILABLE" = true ]; then
        sudo bash "$PAIRING_SCRIPT"
        echo -e "  → ${GREEN}Pairing daemon installed${NC}"
    else
        echo -e "  → ${YELLOW}Skipping pairing daemon (psmove CLI not available)${NC}"
        echo "    Install psmoveapi first, then run:"
        echo "    sudo $PAIRING_SCRIPT"
    fi
else
    echo -e "  → ${RED}Pairing daemon script not found${NC}"
fi

# Configure audio (optional, best effort)
echo ""
echo "Configuring audio..."
amixer sset PCM,0 100% 2>/dev/null && echo -e "  → ${GREEN}Audio configured${NC}" || echo "  → Audio config skipped (may not be available)"

# Summary
echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""

if [ "$REBOOT_NEEDED" = true ]; then
    echo -e "${YELLOW}ACTION REQUIRED: Reboot to disable internal Bluetooth${NC}"
    echo "  sudo reboot"
    echo ""
fi

if [ "$DOCKER_GROUP_CHANGED" = true ]; then
    echo -e "${YELLOW}ACTION REQUIRED: Log out and back in for docker group${NC}"
    echo ""
fi

echo "To start JoustMania:"
echo "  cd $JOUSTMANIA_DIR"
echo "  docker compose -f docker-compose.lite.yml up -d"
echo ""

if [ "$PSMOVE_AVAILABLE" = false ]; then
    echo -e "${YELLOW}Note: Pairing daemon not installed (psmove CLI missing)${NC}"
    echo "  To enable automatic controller pairing, build psmoveapi:"
    echo "  ./scripts/setup/build_psmoveapi.sh"
    echo ""
fi

echo "To pair controllers (if pairing daemon is running):"
echo "  1. Connect controller via USB"
echo "  2. Wait for white LED flash (success)"
echo "  3. Unplug USB, press PS button"
echo ""
