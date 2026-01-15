#!/bin/bash
#
# Build all Docker images for JoustMania microservices
#
# Uses shared builder images for faster builds (Phase 69)
# Run 'make builders' first to build the base images.
#

set -e

echo "Building JoustMania Docker images..."
echo ""

# Ensure proto files are compiled with optimized bytecode (Phase 47)
if [ ! -d "proto/__pycache__" ] || [ -z "$(ls -A proto/__pycache__/*.opt-2.pyc 2>/dev/null)" ]; then
    echo "⚠️  Proto bytecode not found - generating now..."
    bash proto/generate_proto.sh
    echo ""
fi

# Check if builder images exist
if ! docker image inspect joustmania/builder:latest &>/dev/null; then
    echo "⚠️  Builder image not found. Run 'make builders' first for faster builds."
    echo "   Continuing with inline build (slower)..."
    echo ""
fi

# Build with builder image args (uses defaults if images don't exist)
DOCKER_BUILDKIT=1 docker compose build --parallel \
    --build-arg BUILDER_IMAGE=joustmania/builder:latest \
    --build-arg PSMOVE_BUILDER_IMAGE=joustmania/psmove-builder:latest

echo ""
echo "Build complete! All Docker images are ready."
echo ""
echo "To start the stack: make up (or scripts/docker/start.sh)"
