# Claude Code Guidelines for JoustMania

Multiplayer motion-controlled party game system using PS Move controllers.

## Quick Reference

```bash
make lint          # Lint code
make test          # Run integration tests
make protos        # Regenerate proto files after .proto changes
```

## Git Worktree Workflow

When working on a GitHub issue, use a separate git worktree:

```bash
git worktree add ../JoustMania-issue-<NUMBER> -b issue-<NUMBER> origin/dev-refactor
```

This isolates changes when multiple agents work in parallel.

## Key Documentation

- [Contributing Guide](docs/CONTRIBUTING.md) - Development workflow, CI checks, code style
- [Development Guide](docs/DEVELOPMENT.md) - Building, running, debugging services
- [Architecture](docs/ARCHITECTURE.md) - System design and service interactions
