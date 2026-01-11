#!/usr/bin/env bash
# Move a phase from in-progress to completed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROGRESS_DIR="$PROJECT_ROOT/planning/phases/in-progress"
COMPLETED_DIR="$PROJECT_ROOT/planning/phases/completed"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <phase-number>"
    echo ""
    echo "Example: $0 36"
    echo ""
    echo "In-progress phases:"
    echo ""
    if [ -z "$(ls -A "$PROGRESS_DIR")" ]; then
        echo "  (none)"
    else
        ls "$PROGRESS_DIR" | grep -o 'phase-[0-9]*' | sort -u | sed 's/phase-/  /'
    fi
    exit 1
fi

PHASE_NUM="$1"
PHASE_FILE=$(find "$PROGRESS_DIR" -name "phase-${PHASE_NUM}-*.md" -type f | head -1)

if [ -z "$PHASE_FILE" ]; then
    echo "❌ Phase $PHASE_NUM not found in in-progress/"
    echo ""
    echo "In-progress phases:"
    if [ -z "$(ls -A "$PROGRESS_DIR")" ]; then
        echo "  (none)"
    else
        ls "$PROGRESS_DIR" | grep -o 'phase-[0-9]*' | sort -u | sed 's/phase-/  /'
    fi
    exit 1
fi

PHASE_NAME=$(basename "$PHASE_FILE")
TARGET="$COMPLETED_DIR/$PHASE_NAME"

# Check if already completed
if [ -f "$TARGET" ]; then
    echo "⚠️  Phase $PHASE_NUM is already in completed/"
    echo "File: $TARGET"
    exit 1
fi

# Move the phase
mv "$PHASE_FILE" "$TARGET"

echo "✅ Phase $PHASE_NUM marked as complete!"
echo ""
echo "📄 File: planning/phases/completed/$PHASE_NAME"
echo ""
echo "Next steps:"
echo "  1. Update IMPLEMENTATION_STATUS.md status: ✅ Complete"
echo "  2. Update claude.md if needed"
echo "  3. Create commit documenting completion"
