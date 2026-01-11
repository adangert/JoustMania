# Phase Management Scripts

Helper scripts for managing JoustMania development phases.

## Phase Lifecycle

```
📋 planned/ → 🏗️ in-progress/ → ✅ completed/
```

Phases are organized in three directories:
- `planning/phases/planned/` - Future work (16 phases)
- `planning/phases/in-progress/` - Currently active phases
- `planning/phases/completed/` - Finished phases (23 phases)

## Scripts

### `phase-status.sh`
Show current phase status across all directories.

```bash
./scripts/planning/phase-status.sh
```

**Output:**
- In-progress phases (what's currently being worked on)
- Planned phase count
- Completed phase count with latest 5

### `phase-start.sh <number>`
Move a phase from planned to in-progress.

```bash
./scripts/planning/phase-start.sh 36
```

**What it does:**
1. Finds `phase-36-*.md` in `planned/`
2. Moves it to `in-progress/`
3. Shows next steps

**Example workflow:**
```bash
# Check available phases
./scripts/planning/phase-start.sh

# Start Phase 36
./scripts/planning/phase-start.sh 36

# Manually update IMPLEMENTATION_STATUS.md
# Set status to: 🏗️ In Progress

# Work on the phase tasks...
```

### `phase-complete.sh <number>`
Move a phase from in-progress to completed.

```bash
./scripts/planning/phase-complete.sh 36
```

**What it does:**
1. Finds `phase-36-*.md` in `in-progress/`
2. Moves it to `completed/`
3. Shows next steps

**Example workflow:**
```bash
# Complete Phase 36
./scripts/planning/phase-complete.sh 36

# Manually update IMPLEMENTATION_STATUS.md
# Set status to: ✅ Complete

# Update claude.md if significant
# Create completion commit
git commit -m "docs: Mark Phase 36 as complete"
```

## Workflow Example

Complete workflow for implementing a phase:

```bash
# 1. Check status
./scripts/planning/phase-status.sh

# 2. Start the phase
./scripts/planning/phase-start.sh 36

# 3. Update IMPLEMENTATION_STATUS.md
# Change: | 36 | Span Hierarchy Rework | HIGH | ⚡ Planned | ...
# To:     | 36 | Span Hierarchy Rework | HIGH | 🏗️ In Progress | ...

# 4. Work on tasks, commit regularly
git add services/game_coordinator/server.py
git commit -m "feat(phase-36): Add parent game_session span"

# 5. When all tasks done, mark complete
./scripts/planning/phase-complete.sh 36

# 6. Update IMPLEMENTATION_STATUS.md
# Change: | 36 | Span Hierarchy Rework | HIGH | 🏗️ In Progress | ...
# To:     | 36 | Span Hierarchy Rework | HIGH | ✅ Complete | ...

# 7. Update claude.md Recent Achievements

# 8. Create completion commit
git commit -m "docs: Mark Phase 36 as complete"
```

## Phase Status Indicators

| Status | Emoji | Location |
|--------|-------|----------|
| Planned | ⚡ 📋 🚀 | `planned/` |
| In Progress | 🏗️ | `in-progress/` |
| Complete | ✅ | `completed/` |

## Notes

- Only one or two phases should be in `in-progress/` at a time
- Always update `IMPLEMENTATION_STATUS.md` when moving phases
- Phase files are markdown with task checklists
- Check off tasks with `[x]` as you complete them
