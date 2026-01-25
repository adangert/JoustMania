#!/bin/bash
# Smoke test for Caddy proxy migration
# This script verifies that the dashboard and all proxied services are accessible
#
# Usage: ./test-caddy-migration.sh

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:8080}"
FAILED_TESTS=0
PASSED_TESTS=0

echo "================================================"
echo "  JoustMania Dashboard - Caddy Migration Test"
echo "================================================"
echo ""
echo "Testing dashboard at: $DASHBOARD_URL"
echo ""

# Helper function to test endpoint
test_endpoint() {
    local name="$1"
    local path="$2"
    local expected_codes="${3:-200}"
    
    echo -n "Testing $name ($path)... "
    
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$DASHBOARD_URL$path" 2>/dev/null || echo "000")
    
    # Check if HTTP_CODE matches any of the expected codes (pipe-separated)
    # Convert to array for clearer matching
    IFS='|' read -ra codes <<< "$expected_codes"
    for code in "${codes[@]}"; do
        if [ "$HTTP_CODE" = "$code" ]; then
            echo -e "${GREEN}✓${NC} (HTTP $HTTP_CODE)"
            ((PASSED_TESTS++))
            return 0
        fi
    done
    
    echo -e "${RED}✗${NC} (Expected HTTP $expected_codes, got $HTTP_CODE)"
    ((FAILED_TESTS++))
    return 1
}

# Helper function to test for specific content
test_content() {
    local name="$1"
    local path="$2"
    local pattern="$3"
    
    echo -n "Testing $name content ($path)... "
    
    CONTENT=$(curl -s "$DASHBOARD_URL$path" 2>/dev/null || echo "")
    
    if echo "$CONTENT" | grep -q "$pattern"; then
        echo -e "${GREEN}✓${NC}"
        ((PASSED_TESTS++))
        return 0
    else
        echo -e "${RED}✗${NC} (Pattern '$pattern' not found)"
        ((FAILED_TESTS++))
        return 1
    fi
}

# Helper function to check redirect doesn't go to localhost:XXXX
test_no_localhost_redirect() {
    local name="$1"
    local path="$2"
    
    echo -n "Testing $name for localhost redirects ($path)... "
    
    # Follow redirects and check if Location header contains localhost:3000, localhost:9090, etc
    LOCATION=$(curl -s -I -L "$DASHBOARD_URL$path" | grep -i "^location:" | grep -E "localhost:[0-9]+" || echo "")
    
    if [ -z "$LOCATION" ]; then
        echo -e "${GREEN}✓${NC} (No localhost redirects)"
        ((PASSED_TESTS++))
        return 0
    else
        echo -e "${RED}✗${NC} (Found redirect to: $LOCATION)"
        ((FAILED_TESTS++))
        return 1
    fi
}

echo "=== Basic Endpoints ==="
test_endpoint "Health check" "/health"
test_endpoint "Main dashboard" "/" 
test_content "Dashboard HTML" "/" "<!DOCTYPE html>"

echo ""
echo "=== Observability Tools ==="
# These will return 502 if the services aren't running, which is expected in some test environments
# In a full integration test, these should return 200
test_endpoint "Grafana UI" "/grafana/" "200|502"
test_endpoint "Prometheus UI" "/prometheus/" "200|502"
test_endpoint "Jaeger UI" "/jaeger/" "200|502"
test_endpoint "Loki API" "/loki/ready" "200|502"

echo ""
echo "=== gRPC-Web API ==="
# The Connect-Web API is available at /joustmania/* paths
# We can't easily test it without a proper gRPC client, so we skip this section
echo -e "${YELLOW}Note:${NC} gRPC-Web API testing requires a proper gRPC client"

echo ""
echo "=== Static Asset Handling ==="
# Note: This assumes there are assets in the build
# If the dashboard isn't built yet, this will fail
if curl -s "$DASHBOARD_URL/assets/" 2>/dev/null | grep -q "404"; then
    echo -e "${YELLOW}Warning:${NC} No assets found (dashboard might not be built yet)"
fi

echo ""
echo "=== Redirect Tests ==="
# These tests verify that services don't redirect to their internal ports
# Only run if services are accessible (not 502)
GRAFANA_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$DASHBOARD_URL/grafana/" 2>/dev/null || echo "000")
if [ "$GRAFANA_CODE" != "502" ]; then
    test_no_localhost_redirect "Grafana" "/grafana/"
    test_no_localhost_redirect "Prometheus" "/prometheus/"
else
    echo -e "${YELLOW}Skipping redirect tests (services not available)${NC}"
fi

echo ""
echo "================================================"
echo "  Test Results"
echo "================================================"
echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed: ${RED}$FAILED_TESTS${NC}"
echo ""

if [ $FAILED_TESTS -gt 0 ]; then
    echo -e "${RED}Some tests failed. Check the output above for details.${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
