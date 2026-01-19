# JoustMania PS Move API Builder Image
#
# Pre-compiles psmoveapi from source to speed up controller-manager builds.
# The psmoveapi compilation takes 10-15 minutes and rarely changes.
#
# Build:
#   docker build -t joustmania/psmove-builder:latest images/psmove-builder/
#
# Build with specific commit:
#   docker build --build-arg PSMOVE_COMMIT=abc123 -t joustmania/psmove-builder:abc123 images/psmove-builder/
#
# Usage in controller_manager Dockerfile:
#   FROM joustmania/psmove-builder:latest AS psmove-builder
#   ...
#   COPY --from=psmove-builder /psmove/psmove.py /usr/local/lib/python3.12/site-packages/
#   COPY --from=psmove-builder /psmove/_psmove.so /usr/local/lib/python3.12/site-packages/
#   COPY --from=psmove-builder /psmove/libpsmoveapi.so /usr/local/lib/
#
# Build time: ~10-15 minutes on Pi, ~2-3 minutes on fast hardware
# Output size: ~2MB of compiled libraries

FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/adangert/JoustMania"
LABEL org.opencontainers.image.description="JoustMania PS Move API builder image"
LABEL org.opencontainers.image.title="joustmania-psmove-builder"

# Tested psmoveapi commit - change via build arg if needed
ARG PSMOVE_COMMIT=8a1f8d035e9c82c5c134d848d9fbb4dd37a34b58
LABEL psmove.commit="${PSMOVE_COMMIT}"

# Install psmoveapi build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    pkg-config \
    libudev-dev \
    libbluetooth-dev \
    libusb-dev \
    libusb-1.0-0-dev \
    libdbus-1-dev \
    swig \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Clone psmoveapi at specific commit
WORKDIR /build
RUN git clone --recursive https://github.com/thp/psmoveapi.git && \
    cd psmoveapi && \
    git checkout ${PSMOVE_COMMIT}

# Build psmoveapi with Python bindings only (no tracker, no examples)
WORKDIR /build/psmoveapi/build
RUN cmake .. \
    -DPSMOVE_BUILD_CSHARP_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_EXAMPLES:BOOL=OFF \
    -DPSMOVE_BUILD_JAVA_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_OPENGL_EXAMPLES:BOOL=OFF \
    -DPSMOVE_BUILD_PROCESSING_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_TESTS:BOOL=OFF \
    -DPSMOVE_BUILD_TRACKER:BOOL=OFF \
    -DPSMOVE_USE_PSEYE:BOOL=OFF && \
    make -j$(nproc)

# Stage output files to a clean location for easy COPY
RUN mkdir -p /psmove && \
    cp /build/psmoveapi/build/psmove.py /psmove/ && \
    cp /build/psmoveapi/build/_psmove.so /psmove/ && \
    cp /build/psmoveapi/build/libpsmoveapi.so /psmove/

# Verify the build
RUN ls -la /psmove/ && \
    python -c "import sys; sys.path.insert(0, '/psmove'); import psmove; print(f'psmove version: {psmove.count_connected()}')"

# The output directory for consumers
WORKDIR /psmove
