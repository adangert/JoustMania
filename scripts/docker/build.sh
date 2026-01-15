#!/bin/bash
#
# Build all Docker images for JoustMania microservices
#
# This script is a wrapper for 'make images'.
# For more control, use the Makefile directly:
#   make builders  - Build base images (once)
#   make images    - Build all service images
#   make up        - Build and start everything
#

set -e

echo "Building JoustMania Docker images..."
echo ""

# Delegate to make
make images

echo ""
echo "Build complete! Run 'make up' or 'docker compose up -d' to start."
