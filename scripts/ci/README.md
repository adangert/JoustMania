# CI Scripts

Scripts for complex CI operations that require multi-step logic.

Most CI operations are now inlined in the Makefile. These scripts handle
operations too complex to express cleanly in Make syntax.

## Prerequisites

- Docker installed and running
- Project cloned locally

## Scripts

### `validate-protos.sh`

Validate protobuf file generation and bytecode compilation.

- Generates proto files in Docker container
- Checks for uncommitted changes via git diff
- Verifies bytecode compilation (.opt-2.pyc files)

```bash
make validate-protos  # Recommended
# or
bash scripts/ci/validate-protos.sh
```

### `validate-packages.sh`

Validate Python package installation and imports.

- Installs all workspace packages with uv
- Tests proto imports work correctly
- Checks for dependency conflicts

```bash
make validate-packages  # Recommended
# or
bash scripts/ci/validate-packages.sh
```

## Makefile Targets

All CI operations are available as Make targets:

```bash
# Code Quality (inlined in Makefile)
make lint              # Run ruff linting
make format            # Format code with ruff
make format-check      # Check formatting
make typecheck         # Type check all services
make lint-dockerfiles  # Lint Dockerfiles with hadolint

# Validation (uses these scripts)
make validate-protos   # Validate proto generation
make validate-packages # Validate package installation

# Building (inlined in Makefile)
make build-service SERVICE=<name>  # Build single service
make build-all-services            # Build all services

# Combined
make ci-all    # Run all quality checks
make ci-quick  # Run quick checks (lint + format)
make test      # Run integration tests
```

## Local Development

```bash
# Format code before committing
make format

# Run quick pre-commit checks
make ci-quick

# Run all CI checks (same as GitHub Actions)
make ci-all
```
