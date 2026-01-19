# Claude Code Guidelines for JoustMania

Project-specific instructions for Claude Code when working on this repository.

## Git Worktree Workflow

When working on a GitHub issue, use a separate git worktree to isolate changes:

```bash
# Create worktree for an issue
git worktree add ../JoustMania-issue-<NUMBER> -b issue-<NUMBER>

# Work in the isolated directory
cd ../JoustMania-issue-<NUMBER>

# After PR is merged, clean up
git worktree remove ../JoustMania-issue-<NUMBER>
```

**Why:** This prevents mingling changes when multiple agents or tasks work in parallel. Each issue gets its own isolated working directory.

**Directory structure:**
```
~/
├── JoustMania/                    # Main worktree (dev-refactor)
├── JoustMania-issue-28/           # Work on issue #28
├── JoustMania-issue-29/           # Work on issue #29
```

## Branch Naming

- `issue-<NUMBER>` - Feature/fix branches tied to GitHub issues
- `dev-refactor` - Main development branch
- `master` - Stable branch

## Testing

Run tests before committing:
```bash
make test          # Run all integration tests
make test-ffa      # Run FFA game test only
make lint          # Run linting
```

## Proto Changes

After modifying `.proto` files:
```bash
make protos        # Regenerate Python code
```

## Docker

```bash
make builders      # Build base images (once)
make images        # Build all service images
make up            # Start the stack
make up-mock       # Start in mock mode (no hardware)
```
