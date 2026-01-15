#!/bin/bash
#
# Start the JoustMania microservices stack
#

set -e

echo "Starting JoustMania stack..."
echo ""

docker compose up -d

echo ""
echo "=========================================="
echo "JoustMania stack started!"
echo "=========================================="
echo ""
echo "Services:"
echo "  - Jaeger UI:     http://localhost:16686"
echo "  - Web UI:        http://localhost:80"
echo "  - Prometheus:    http://localhost:9090"
echo "  - Grafana:       http://localhost:3000"
echo ""
echo "To view logs:     make logs (or scripts/docker/logs.sh)"
echo "To stop:          make down (or scripts/docker/stop.sh)"
echo ""
docker compose ps
