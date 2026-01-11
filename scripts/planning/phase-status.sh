#!/usr/bin/env bash
# Show current phase status

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PLANNED_DIR="$PROJECT_ROOT/planning/phases/planned"
PROGRESS_DIR="$PROJECT_ROOT/planning/phases/in-progress"
COMPLETED_DIR="$PROJECT_ROOT/planning/phases/completed"

echo "📊 JoustMania Phase Status"
echo "=" | awk '{s=sprintf("%80s",""); gsub(/ /,"=",$0); print}'
echo ""

# In Progress
echo "🏗️  IN PROGRESS:"
if [ -z "$(ls -A "$PROGRESS_DIR" 2>/dev/null)" ]; then
    echo "  (none)"
else
    ls "$PROGRESS_DIR" | sed 's/^/  /'
fi
echo ""

# Planned (show count)
PLANNED_COUNT=$(ls -1 "$PLANNED_DIR" | wc -l)
echo "📋 PLANNED: $PLANNED_COUNT phases"
echo "  (Run './scripts/planning/phase-start.sh <number>' to begin one)"
echo ""

# Completed (show count and latest)
COMPLETED_COUNT=$(ls -1 "$COMPLETED_DIR" | wc -l)
echo "✅ COMPLETED: $COMPLETED_COUNT phases"
echo ""
echo "  Latest 5:"
ls -t "$COMPLETED_DIR" | head -5 | sed 's/^/    /'
echo ""

echo "Commands:"
echo "  ./scripts/planning/phase-start.sh <number>    - Start a planned phase"
echo "  ./scripts/planning/phase-complete.sh <number> - Mark in-progress phase as complete"
echo "  ./scripts/planning/phase-status.sh            - Show this status"
