# Git Workflow

## Worktrees are Mandatory

Never commit directly to the main checkout. Always use git worktrees:

```bash
git worktree add ../JoustMania-issue-<NUMBER> -b fix/description origin/dev-refactor
cd ../JoustMania-issue-<NUMBER>
# ... make changes ...
git push -u origin fix/description
gh pr create --base dev-refactor
```

This keeps the main checkout clean for:
- Multiple parallel agent work
- Quick reference and exploration
- Avoiding accidental commits to wrong branch

## Main Branch

The main development branch is **`dev-refactor`** (not `master`).

All PRs target `dev-refactor`.

## Branch Naming

- `fix/description` - Bug fixes
- `feat/description` - New features
- `refactor/description` - Code improvements
- `docs/description` - Documentation
- `perf/description` - Performance improvements

Include issue number when applicable: `fix/issue-256-clear-ready-state`

## Commit Messages

Follow conventional commits:

```
type: Short description

Longer explanation if needed.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

Types: `fix`, `feat`, `refactor`, `docs`, `perf`, `test`, `chore`

## Pre-commit Checks

Hooks run automatically:
- `ruff check` - Linting
- `ruff format` - Formatting

Run manually before committing:
```bash
make lint
```

## Pull Requests

1. Create via `gh pr create --base dev-refactor`
2. Include issue reference: `Fixes #123`
3. Add test plan with checkboxes
4. Wait for CI to pass
