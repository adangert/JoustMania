#!/bin/bash
#
# PS Move API Build Script
# Downloads and compiles PS Move API library
#

set -e  # Exit on error

HOMENAME=`logname`
HOMEDIR=/home/$HOMENAME

echo "=========================================="
echo "PS Move API Build"
echo "=========================================="

cd $HOMEDIR

# Install PS Move API build dependencies
echo "[1/3] Installing PS Move API build dependencies..."
sudo apt-get install -y \
    build-essential \
    libv4l-dev libopencv-dev \
    libudev-dev libbluetooth-dev \
    libusb-dev || exit -1

# Clone PS Move API
echo "[2/3] Downloading PS Move API..."
cd $HOMEDIR
rm -rf psmoveapi
git clone --recursive https://github.com/thp/psmoveapi.git || exit -1
cd psmoveapi || exit -1

# Checkout specific commit (tested version)
git checkout 8a1f8d035e9c82c5c134d848d9fbb4dd37a34b58 || exit -1

# Build PS Move API
echo "[3/3] Building PS Move API (this may take several minutes)..."
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
    -DPSMOVE_USE_PSEYE:BOOL=OFF || exit -1

make -j4 || exit -1

echo ""
echo "=========================================="
echo "PS Move API build complete!"
echo "=========================================="
echo ""
echo "Installation complete. System reboot recommended."
echo ""
