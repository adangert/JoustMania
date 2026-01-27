# Claude Code Guidelines for JoustMania

Multiplayer motion-controlled party game system using PS Move controllers.

**Main branch: `dev-refactor`** (not master)

## Quick Reference

```bash
make lint          # Lint code
make test          # Run integration tests (docker compose)
make protos        # Regenerate proto files after .proto changes
```

## Testing

**Integration tests** run with docker compose:
```bash
make test                    # Run all integration tests
SKIP_TEARDOWN=1 make test    # Keep docker running after tests (for debugging)
```

**Unit tests** run with uv from each service directory:
```bash
cd services/<service-name>
uv run pytest
```

## Git Worktree Workflow

**Always create a new worktree for changes.** Never commit directly to the main checkout directory.

```bash
git worktree add ../JoustMania-issue-<NUMBER> -b fix/description origin/dev-refactor
cd ../JoustMania-issue-<NUMBER>
```

This keeps the main checkout clean and isolates changes when multiple agents work in parallel.

## Key Documentation

- [Contributing Guide](docs/CONTRIBUTING.md) - Development workflow, CI checks, code style
- [Development Guide](docs/DEVELOPMENT.md) - Building, running, debugging services
- [Architecture](docs/ARCHITECTURE.md) - System design and service interactions
