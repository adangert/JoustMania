# Contributing to JoustMania

Thank you for your interest in contributing to JoustMania! This guide will help you set up your development environment and understand our CI/CD workflow.

## Development Setup

### Prerequisites

- **Docker** - All development tooling runs in containers
- **Git** - Version control
- **VS Code** (optional) - Recommended for dev container support

### Quick Start

#### Option 1: VS Code Dev Container (Recommended)

1. Install [VS Code](https://code.visualstudio.com/) and the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
2. Clone the repository
3. Open in VS Code
4. When prompted, click "Reopen in Container"
5. Wait for the dev container to build (~5 minutes first time)
6. You're ready to develop!

The dev container includes:
- Python 3.11
- All development tools (ruff, mypy, ipython)
- Docker-in-Docker for building service images
- Pre-configured VS Code extensions

#### Option 2: Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/WatchMeJoustMyFlags/JoustMania.git
   cd JoustMania
   ```

2. Build CI tooling images:
   ```bash
   make ci-build-tools
   ```

3. You're ready to use the CI tools!

## Development Workflow

### Git Worktree (Recommended for Issue Work)

Use git worktrees to isolate work on different issues:

```bash
# Create worktree for an issue
git worktree add ../JoustMania-issue-<NUMBER> -b issue-<NUMBER> origin/dev-refactor

# Work in the isolated directory
cd ../JoustMania-issue-<NUMBER>

# After PR is merged, clean up
git worktree remove ../JoustMania-issue-<NUMBER>
```

### Making Changes

1. Create a branch (or use worktree above):
   ```bash
   git checkout -b issue-<NUMBER>
   ```

2. Make your changes

3. Format code:
   ```bash
   make format
   ```

4. Run quick checks before committing:
   ```bash
   make ci-quick
   ```

5. Commit changes:
   ```bash
   git add .
   git commit -m "feat: Add my feature"
   ```

6. Push and create pull request:
   ```bash
   git push origin issue-<NUMBER>
   ```

## Continuous Integration

All pull requests must pass CI checks before merging:

1. **Python Linting** - Code must pass `ruff check` and `ruff format --check`
2. **Type Checking** - Ty type checking (currently warnings only)
3. **Dockerfile Linting** - All Dockerfiles must pass hadolint validation
4. **Proto Validation** - Proto files must be up-to-date (run `make protos`)
5. **Docker Builds** - All 7 services must build successfully
6. **Package Validation** - All workspace packages must install correctly

### Running Checks Locally

**Using Make (recommended):**

```bash
# Run all CI checks (same as GitHub Actions)
make ci-all

# Quick pre-commit checks (lint + format)
make ci-quick

# Individual checks
make lint
make format-check
make typecheck
make lint-dockerfiles

# Auto-fix formatting
make format
```

**Using Docker directly:**

```bash
# Lint Python code
bash scripts/ci/lint.sh

# Check formatting
bash scripts/ci/format-check.sh

# Type check
bash scripts/ci/typecheck.sh

# Lint Dockerfiles
bash scripts/ci/lint-dockerfiles.sh

# Validate protos
bash scripts/ci/validate-protos.sh

# Build a service
bash scripts/ci/build-service.sh controller_manager
```

**In Dev Container:**

- Open Command Palette (Ctrl+Shift+P)
- Run Task → "Run All CI Checks"
- Or use keyboard shortcuts for individual tasks

### Fixing Issues

**Linting errors:**
```bash
# Auto-fix with Make
make format

# Or with Docker
docker run --rm -v "$(pwd):/workspace" joustmania/ci-lint:latest ruff format .
docker run --rm -v "$(pwd):/workspace" joustmania/ci-lint:latest ruff check --fix .
```

**Dockerfile warnings:**
```bash
# Check Dockerfiles
make lint-dockerfiles

# Fix based on hadolint suggestions
# Review best practices: https://github.com/hadolint/hadolint
```

**Proto out of sync:**
```bash
# Regenerate protos
make protos

# Commit changes
git add proto/
git commit -m "chore: Regenerate proto files"
```

## Code Style

### Python

We use **ruff** for linting and formatting:
- Line length: 100 characters
- Target version: Python 3.11
- Automatic import sorting (isort)
- Comprehensive linting rules (pycodestyle, pyflakes, flake8-*)

Run `make format` to auto-fix most issues.

### Type Hints

We use **ty** (Astral type checker) for type checking:
- Gradually adopting type hints across the codebase
- Currently in warning-only mode
- New code should include type hints where possible
- Configured in `pyproject.toml` under `[tool.ty]`

### Dockerfiles

We use **hadolint** for Dockerfile linting:
- Follow best practices for layer caching
- Pin base image versions explicitly
- Minimize layer count

## Project Structure

```
JoustMania/
├── .devcontainer/          # VS Code dev container setup
├── .github/                # GitHub Actions workflows
│   └── workflows/
│       └── ci.yml          # Main CI pipeline
├── docs/                   # Documentation
├── proto/                  # Protocol buffer schemas
├── scripts/
│   ├── ci/                 # CI/CD scripts
│   └── docker/             # Docker management scripts
├── services/               # Microservices
│   ├── controller_manager/
│   ├── game_coordinator/
│   ├── settings/
│   ├── supervisor/
│   ├── menu/
│   ├── audio/
│   └── webui/
├── tools/                  # CI tooling Docker images
│   ├── ci-lint/
│   ├── ci-hadolint/
│   └── ci-proto/
└── Makefile                # Build targets
```

## Testing

### Running Tests

```bash
# Unit tests (when available)
pytest

# Integration tests
docker-compose -f docker-compose.test.yml up
```

### Adding Tests

- Place unit tests in `tests/unit/<service_name>/`
- Place integration tests in `tests/integration/`
- Follow existing test patterns

## Protobuf Changes

If you modify `.proto` files:

1. Regenerate Python code:
   ```bash
   make protos
   ```

2. Verify bytecode compilation:
   ```bash
   ls -lh proto/__pycache__/*.opt-2.pyc
   ```

3. Commit generated files:
   ```bash
   git add proto/*_pb2.py proto/*_pb2_grpc.py proto/__pycache__/
   git commit -m "chore: Regenerate proto files"
   ```

## Docker Changes

If you modify Dockerfiles:

1. Lint the Dockerfile:
   ```bash
   make lint-dockerfiles
   ```

2. Build the service:
   ```bash
   make build-service SERVICE=<service-name>
   ```

3. Test the service:
   ```bash
   docker run --rm joustmania/<service-name>-service:ci
   ```

## Commit Message Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Adding tests
- `chore:` - Maintenance tasks
- `perf:` - Performance improvements

Examples:
```
feat: Add RSSI tracking for controllers
fix: Resolve memory leak in game loop
docs: Update CONTRIBUTING guide
refactor: Extract common game base class
test: Add unit tests for settings service
chore: Regenerate proto files
```

## Getting Help

- **Documentation**: Check `/docs` directory
- **Issues**: [GitHub Issues](https://github.com/WatchMeJoustMyFlags/JoustMania/issues)
- **Discussions**: [GitHub Discussions](https://github.com/WatchMeJoustMyFlags/JoustMania/discussions)

## Resources

- [Protocol Buffers Guide](https://developers.google.com/protocol-buffers)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Hadolint Documentation](https://github.com/hadolint/hadolint)

---

Thank you for contributing to JoustMania! 🎮
