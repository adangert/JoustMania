#!/bin/bash
#
# Build all Docker images for JoustMania microservices
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

docker-compose build --parallel

echo ""
echo "Build complete! All Docker images are ready."
echo ""
echo "To start the stack: scripts/docker/start.sh"
echo "Or manually: docker-compose up -d"
