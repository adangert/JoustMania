#!/bin/bash
#
# Build all Docker images for JoustMania microservices
#

set -e

echo "Building JoustMania Docker images..."
echo ""

docker-compose build --parallel

echo ""
echo "Build complete! All Docker images are ready."
echo ""
echo "To start the stack: scripts/docker/start.sh"
echo "Or manually: docker-compose up -d"
