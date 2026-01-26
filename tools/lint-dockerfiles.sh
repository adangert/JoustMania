#!/bin/bash
# Dockerfile linting script using hadolint
# Can be run locally or in CI/CD pipelines
#
# Usage:
#   ./tools/lint-dockerfiles.sh              # Lint all Dockerfiles
#   ./tools/lint-dockerfiles.sh services/*/  # Lint specific directories
#   CI=true ./tools/lint-dockerfiles.sh      # Run in CI mode (strict)

set -uo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
HADOLINT_VERSION="2.12.0"
HADOLINT_CONFIG=".hadolint.yaml"
EXIT_CODE=0

echo "🐳 Dockerfile Linting Script"
echo "=============================="
echo ""

# Check if running in CI mode
if [[ "${CI:-false}" == "true" ]]; then
    echo "Running in CI mode (strict)"
    STRICT_MODE=true
else
    echo "Running in local mode"
    STRICT_MODE=false
fi

# Function to run hadolint via Docker
lint_dockerfile() {
    local dockerfile="$1"
    local relative_path="${dockerfile#./}"

    echo -n "Linting: $relative_path ... "

    # Run hadolint via Docker and capture output
    local output_file="/tmp/hadolint_output_$$.txt"
    docker run --rm -i \
        -v "$(pwd)/$HADOLINT_CONFIG:/$HADOLINT_CONFIG:ro" \
        "hadolint/hadolint:v${HADOLINT_VERSION}" \
        hadolint --config "/$HADOLINT_CONFIG" - < "$dockerfile" > "$output_file" 2>&1
    local hadolint_exit=$?

    # Check exit code
    if [[ $hadolint_exit -eq 0 ]]; then
        # Success - show any info/warnings but don't fail
        if [[ -s "$output_file" ]]; then
            echo -e "${YELLOW}⚠ WARNINGS${NC}"
            cat "$output_file"
        else
            echo -e "${GREEN}✓ PASS${NC}"
        fi
    else
        # Failure - hadolint found errors
        echo -e "${RED}✗ FAIL${NC}"
        cat "$output_file"
        EXIT_CODE=1
    fi

    rm -f "$output_file"
}

# Find all Dockerfiles
if [[ $# -eq 0 ]]; then
    # No arguments - scan entire repo
    DOCKERFILES=$(find . -type f -name "Dockerfile*" | grep -v "^\./\." | grep -v "/node_modules/" || true)
else
    # Scan provided directories/files
    DOCKERFILES=$(find "$@" -type f -name "Dockerfile*" | grep -v "^\./\." | grep -v "/node_modules/" || true)
fi

# Check if hadolint config exists
if [[ ! -f "$HADOLINT_CONFIG" ]]; then
    echo -e "${YELLOW}Warning: $HADOLINT_CONFIG not found. Using default configuration.${NC}"
    echo ""
fi

# Lint each Dockerfile
TOTAL=0
for dockerfile in $DOCKERFILES; do
    lint_dockerfile "$dockerfile"
    ((TOTAL++))
done

echo ""
echo "=============================="
if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}✓ All $TOTAL Dockerfiles passed linting!${NC}"
else
    echo -e "${RED}✗ Some Dockerfiles failed linting. Please fix the issues above.${NC}"

    if [[ "$STRICT_MODE" == "true" ]]; then
        echo ""
        echo "Running in CI mode - exiting with failure."
    fi
fi

exit "$EXIT_CODE"
