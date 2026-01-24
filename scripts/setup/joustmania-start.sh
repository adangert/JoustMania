#!/bin/bash
# JoustMania startup script with optional auto-update
# Gracefully handles missing internet connection

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JOUSTMANIA_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
STATUS_DIR="/tmp/joustmania"
STATUS_FILE="$STATUS_DIR/update-status.json"

cd "$JOUSTMANIA_DIR"

echo "=== JoustMania Startup ==="
echo "Working directory: $JOUSTMANIA_DIR"

# Create status directory
mkdir -p "$STATUS_DIR"

# Files to track for updates
TRACKED_FILES=(
    "scripts/setup/joustmania.service"
    "scripts/setup/joustmania-start.sh"
    "scripts/setup/install_autostart.sh"
)

# Calculate checksums before git pull
declare -A CHECKSUMS_BEFORE
for file in "${TRACKED_FILES[@]}"; do
    if [ -f "$file" ]; then
        CHECKSUMS_BEFORE["$file"]=$(sha256sum "$file" 2>/dev/null | cut -d' ' -f1)
    fi
done

# Attempt git pull (non-fatal)
echo "Checking for code updates..."
GIT_PULL_STATUS="success"
if git pull --ff-only 2>&1; then
    echo "Code updated successfully"
else
    echo "Could not update code (offline or conflict) - continuing with current version"
    GIT_PULL_STATUS="failed"
fi

# Check which files changed
CHANGED_FILES=()
for file in "${TRACKED_FILES[@]}"; do
    if [ -f "$file" ]; then
        CHECKSUM_AFTER=$(sha256sum "$file" 2>/dev/null | cut -d' ' -f1)
        if [ "${CHECKSUMS_BEFORE[$file]}" != "$CHECKSUM_AFTER" ]; then
            CHANGED_FILES+=("$file")
            echo "Service file changed: $file"
        fi
    fi
done

# Write status file for observability
CHANGED_FILES_JSON=$(printf '%s\n' "${CHANGED_FILES[@]}" | jq -R . | jq -s .)
cat > "$STATUS_FILE" << EOF
{
    "timestamp": "$(date -Iseconds)",
    "git_pull_status": "$GIT_PULL_STATUS",
    "service_files_changed": ${CHANGED_FILES_JSON:-[]},
    "update_pending": $([ ${#CHANGED_FILES[@]} -gt 0 ] && echo "true" || echo "false")
}
EOF

if [ ${#CHANGED_FILES[@]} -gt 0 ]; then
    echo "WARNING: Service files have changed. Run 'sudo ./scripts/setup/install_autostart.sh' to apply updates."
fi

# Attempt docker compose pull (non-fatal)
echo "Checking for image updates..."
if docker compose pull 2>&1; then
    echo "Images updated successfully"
else
    echo "Could not pull images (offline) - continuing with cached images"
fi

# Clean up any orphaned containers
echo "Cleaning up..."
docker compose down --remove-orphans || true

# Start services (this must succeed)
echo "Starting JoustMania..."
exec docker compose up -d
