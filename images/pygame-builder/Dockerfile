# JoustMania Pygame Builder Image
#
# Pre-compiles pygame with SDL2 support to speed up audio service builds.
# Pygame compilation can take 2-5 minutes on ARM and rarely changes.
#
# Build:
#   docker build -t joustmania/pygame-builder:latest images/pygame-builder/
#
# Build with specific version:
#   docker build --build-arg PYGAME_VERSION=2.5.2 -t joustmania/pygame-builder:2.5.2 images/pygame-builder/
#
# Usage in audio Dockerfile:
#   FROM joustmania/pygame-builder:latest AS pygame-builder
#   ...
#   COPY --from=pygame-builder /pygame /usr/local/lib/python3.11/site-packages/pygame
#
# Build time: ~2-5 minutes on Pi, ~30 seconds on fast hardware
# Output size: ~15MB of compiled libraries

FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/adangert/JoustMania"
LABEL org.opencontainers.image.description="JoustMania Pygame builder image"
LABEL org.opencontainers.image.title="joustmania-pygame-builder"

# Pygame version - change via build arg if needed
ARG PYGAME_VERSION=2.5.2
LABEL pygame.version="${PYGAME_VERSION}"

# Install SDL2 development libraries for building pygame
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    python3-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libfreetype6-dev \
    libportmidi-dev \
    libjpeg-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pygame from source (not wheel) to link against system SDL2
# --no-binary forces compilation from source
RUN pip install --no-cache-dir --no-binary pygame pygame==${PYGAME_VERSION}

# Verify the build (links against system SDL2 libs)
RUN python -c "import pygame; print(f'pygame version: {pygame.version.ver}')"

# Stage output files to a clean location for easy COPY
# Copy the entire pygame package including bundled SDL2 libs
RUN mkdir -p /pygame && \
    cp -r /usr/local/lib/python3.11/site-packages/pygame/* /pygame/

# The output directory for consumers
WORKDIR /pygame
