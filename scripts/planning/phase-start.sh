#!/usr/bin/env bash
# Move a phase from planned to in-progress

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PLANNED_DIR="$PROJECT_ROOT/planning/phases/planned"
PROGRESS_DIR="$PROJECT_ROOT/planning/phases/in-progress"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <phase-number>"
    echo ""
    echo "Example: $0 36"
    echo ""
    echo "Available phases:"
    echo ""
    ls "$PLANNED_DIR" | grep -o 'phase-[0-9]*' | sort -u | sed 's/phase-/  /'
    exit 1
fi

PHASE_NUM="$1"
PHASE_FILE=$(find "$PLANNED_DIR" -name "phase-${PHASE_NUM}-*.md" -type f | head -1)

if [ -z "$PHASE_FILE" ]; then
    echo "❌ Phase $PHASE_NUM not found in planned/"
    echo ""
    echo "Available phases:"
    ls "$PLANNED_DIR" | grep -o 'phase-[0-9]*' | sort -u | sed 's/phase-/  /'
    exit 1
fi

PHASE_NAME=$(basename "$PHASE_FILE")
TARGET="$PROGRESS_DIR/$PHASE_NAME"

# Check if already in progress
if [ -f "$TARGET" ]; then
    echo "⚠️  Phase $PHASE_NUM is already in progress!"
    echo "File: $TARGET"
    exit 1
fi

# Move the phase
mv "$PHASE_FILE" "$TARGET"

echo "✅ Phase $PHASE_NUM moved to in-progress/"
echo ""
echo "📄 File: planning/phases/in-progress/$PHASE_NAME"
echo ""
echo "Next steps:"
echo "  1. Review the phase tasks"
echo "  2. Update IMPLEMENTATION_STATUS.md status: 🏗️ In Progress"
echo "  3. Start working on the tasks"
echo "  4. When complete, run: ./scripts/planning/phase-complete.sh $PHASE_NUM"
