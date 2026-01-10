#!/bin/bash
#
# Start the JoustMania microservices stack
#

set -e

echo "Starting JoustMania stack..."
echo ""

docker-compose up -d

echo ""
echo "=========================================="
echo "JoustMania stack started!"
echo "=========================================="
echo ""
echo "Services:"
echo "  - Jaeger UI:     http://localhost:16686"
echo "  - Web UI:        http://localhost:80"
echo "  - Prometheus:    http://localhost:8888/metrics"
echo ""
echo "To view logs:     scripts/docker/logs.sh [service]"
echo "To stop:          scripts/docker/stop.sh"
echo ""
docker-compose ps
