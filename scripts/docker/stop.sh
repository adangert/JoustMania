#!/bin/bash
#
# Stop and clean up the JoustMania microservices stack
#

set -e

echo "Stopping JoustMania stack..."
echo ""

docker compose down

echo ""
echo "Stack stopped and cleaned up."
