#!/bin/bash
#
# Host System Setup for JoustMania
# Installs system dependencies, Docker, and configures hardware
#

set -e  # Exit on error

# Prevent apt from prompting about restarting services
export DEBIAN_FRONTEND=noninteractive

HOMENAME="$(logname)"
HOMEDIR="/home/$HOMENAME"

echo "=========================================="
echo "JoustMania Host System Setup"
echo "=========================================="

cd "$HOMEDIR"

# Remove conflicting software
echo "[1/8] Removing conflicting software..."
sudo apt-get remove realvnc-vnc-server -y

# Update system
echo "[2/8] Updating system packages..."
sudo apt-get update -y || exit 1
sudo apt-get upgrade -y || exit 1

# Install core dependencies
echo "[3/8] Installing system dependencies..."
sudo apt-get install -y  \
    python3 python3-dev python3-pip \
    python3-pkg-resources python3-setuptools libdpkg-perl \
    libsdl1.2-dev libsdl-mixer1.2-dev libsdl-sound1.2-dev \
    libportmidi-dev portaudio19-dev \
    libsdl-image1.2-dev libsdl-ttf2.0-dev \
    libblas-dev liblapack-dev \
    bluez bluez-tools iptables rfkill supervisor cmake ffmpeg \
    libudev-dev swig libbluetooth-dev \
    alsa-utils alsa-tools libasound2-dev libsdl2-mixer-2.0-0 \
    python-dbus-dev python3-dbus libdbus-glib-1-dev usbutils libopenblas-dev \
    python3-pyaudio python3-psutil || exit 1

# Install Docker
echo "[4/8] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh

    # Add user to docker group
    sudo usermod -aG docker "$USER"
    echo "  → Docker installed. You may need to log out and back in for group changes to take effect."
else
    echo "  → Docker already installed"
fi

# Install Python virtual environment tools
echo "[5/8] Installing Python development tools..."
sudo apt-get install -y python3-dev python3-virtualenv libasound2-dev libasound2 python3-scipy cmake || exit 1

# Create virtual environment
VENV="$HOMEDIR/JoustMania/venv"
if [[ ! -d "$VENV" ]]; then
    echo "  → Creating virtual environment at $VENV"
    /usr/bin/python3 -m virtualenv --system-site-packages "$VENV" || exit 1
else
    echo "  → Virtual environment already exists"
fi
PYTHON="$VENV/bin/python3"

# Install uv for dependency management
echo "[6/8] Installing uv package manager..."
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "  → uv installed"
else
    echo "  → uv already installed"
fi

# Sync Python dependencies
echo "  → Syncing Python dependencies..."
cd "$HOMEDIR/JoustMania"
uv sync --python "$PYTHON" || exit 1

# Configure audio
echo "[7/9] Configuring audio (ALSA)..."
amixer sset PCM,0 100% 2>/dev/null || echo "  → Could not set PCM volume (may not be available)"
sudo alsactl store 2>/dev/null || echo "  → Could not store ALSA state"

# Configure Bluetooth
echo "[8/9] Configuring Bluetooth..."

# Detect config.txt location based on distribution
DIST_REL=$(lsb_release -r | cut -f2)
if [[ "$DIST_REL" -ge 12 ]]; then
    config_loc=/boot/firmware/config.txt
else
    config_loc=/boot/config.txt
fi

# Disable internal Bluetooth (required for OpenTelemetry demo, prevents Wi-Fi/USB interference)
echo "  → Disabling internal Bluetooth..."
sudo grep -qxF 'dtoverlay=disable-bt' "$config_loc" || {
    echo "dtoverlay=disable-bt" | sudo tee -a "$config_loc"
    sudo rm -rf /var/lib/bluetooth/*
} || exit 1

# Disable hciuart on older distributions
if [[ "$DIST_REL" -le 12 ]]; then
    sudo systemctl disable hciuart 2>/dev/null || echo "  → hciuart not active"
fi

# Configure Bluetooth ClassicBondedOnly
echo "  → Configuring Bluetooth input.conf..."
sudo sed -i '/^#\?ClassicBondedOnly=\(true\|false\)$/s/.*/ClassicBondedOnly=false/' '/etc/bluetooth/input.conf' || exit 1

# Install PS Move pairing daemon
echo "[9/9] Installing PS Move pairing daemon..."
if [[ -f "$HOMEDIR/JoustMania/scripts/pairing-daemon/install.sh" ]]; then
    sudo bash "$HOMEDIR/JoustMania/scripts/pairing-daemon/install.sh"
    echo "  → Pairing daemon installed"
else
    echo "  → Pairing daemon script not found, skipping"
fi

# Fix permissions
echo "Fixing JoustMania directory permissions..."
uname2="$(stat --format '%U' "$HOMEDIR/JoustMania/setup.sh")"
if [[ "${uname2}" = "root" ]]; then
    sudo chown -R "$HOMENAME:$HOMENAME" "$HOMEDIR/JoustMania/" || exit 1
    echo "  → Permissions updated"
else
    echo "  → Permissions correct"
fi

# Install supervisor configuration
CONFIG_DIR="/etc/supervisor/conf.d"
CONFIG_FILE="$CONFIG_DIR/joust.conf"
if [[ -d "$HOMEDIR/JoustMania/conf/supervisor" ]]; then
    echo "Installing supervisor configuration..."
    sudo cp -r "$HOMEDIR/JoustMania/conf/supervisor/" /etc/ || exit 1
    sudo sed -i -e "s|/home/[^/]*\/JoustMania|$HOMEDIR/JoustMania|g" "$CONFIG_FILE" || exit 1
    echo "  → Supervisor config installed"
fi

echo ""
echo "=========================================="
echo "Host system setup complete!"
echo "=========================================="
echo ""
echo "Next step: Run scripts/setup/build_psmoveapi.sh to build PS Move API"
echo ""
