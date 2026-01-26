#!/bin/bash
#
# PS Move API Build Script
# Downloads and compiles PS Move API library
#

set -e  # Exit on error

HOMENAME="$(logname)"
HOMEDIR="/home/$HOMENAME"

echo "=========================================="
echo "PS Move API Build"
echo "=========================================="

cd "$HOMEDIR"

# Install PS Move API build dependencies
echo "[1/3] Installing PS Move API build dependencies..."
sudo apt-get install -y \
    build-essential \
    libv4l-dev libopencv-dev \
    libudev-dev libbluetooth-dev \
    libusb-dev || exit 1

# Clone PS Move API
echo "[2/3] Downloading PS Move API..."
cd "$HOMEDIR"
rm -rf psmoveapi
git clone --recursive https://github.com/thp/psmoveapi.git || exit 1
cd psmoveapi || exit 1

# Checkout specific commit (tested version)
git checkout 8a1f8d035e9c82c5c134d848d9fbb4dd37a34b58 || exit 1

# Build PS Move API
echo "[3/4] Building PS Move API (this may take several minutes)..."
mkdir -p build
cd build
cmake .. \
    -DPSMOVE_BUILD_CSHARP_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_EXAMPLES:BOOL=OFF \
    -DPSMOVE_BUILD_JAVA_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_OPENGL_EXAMPLES:BOOL=OFF \
    -DPSMOVE_BUILD_PROCESSING_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_TESTS:BOOL=OFF \
    -DPSMOVE_BUILD_TRACKER:BOOL=OFF \
    -DPSMOVE_USE_PSEYE:BOOL=OFF || exit 1

make -j4 || exit 1

# Install psmove Python bindings to venv
echo "[4/4] Installing psmove Python bindings..."
VENV="$HOMEDIR/JoustMania/venv"
SITE_PACKAGES=$(find "$VENV/lib" -type d -name "site-packages" | head -1)

if [[ -z "$SITE_PACKAGES" ]]; then
    echo "ERROR: Could not find venv site-packages directory"
    exit 1
fi

# Copy psmove Python module and native library
cp "$HOMEDIR/psmoveapi/build/psmove.py" "$SITE_PACKAGES/" || exit 1
cp "$HOMEDIR/psmoveapi/build/_psmove.so" "$SITE_PACKAGES/" || exit 1

echo "  → Installed psmove.py to $SITE_PACKAGES/"
echo "  → Installed _psmove.so to $SITE_PACKAGES/"

# Verify installation
echo "  → Verifying installation..."
"$VENV/bin/python3" -c "import psmove; print(f'  → psmove OK: {psmove.count_connected()} controllers detected')" || {
    echo "WARNING: psmove import test failed (may work after reboot)"
}

echo ""
echo "=========================================="
echo "PS Move API build complete!"
echo "=========================================="
echo ""
echo "psmove library installed to: $SITE_PACKAGES"
echo "System reboot recommended."
echo ""
