# CI Scripts

Docker-based CI/CD scripts for quality assurance and build validation.

## Prerequisites

- Docker installed and running
- Project cloned locally

## Scripts

### Code Quality

#### `lint.sh`
Run ruff linting on all Python code.

```bash
bash scripts/ci/lint.sh
```

Uses `joustmania/ci-lint:latest` Docker image.

#### `format-check.sh`
Check code formatting with ruff.

```bash
bash scripts/ci/format-check.sh
```

Uses `joustmania/ci-lint:latest` Docker image.

#### `typecheck.sh`
Run mypy type checking on all services.

```bash
bash scripts/ci/typecheck.sh
```

Currently in warning-only mode. Uses `joustmania/ci-lint:latest` Docker image.

#### `lint-dockerfiles.sh`
Lint all Dockerfiles with hadolint.

```bash
bash scripts/ci/lint-dockerfiles.sh
```

Uses `joustmania/ci-hadolint:latest` Docker image.

### Build Validation

#### `validate-protos.sh`
Validate protobuf file generation and bytecode compilation.

```bash
bash scripts/ci/validate-protos.sh
```

Ensures proto files are up-to-date and properly compiled. Uses `joustmania/ci-proto:latest` Docker image.

#### `build-service.sh`
Build a single service Docker image.

```bash
bash scripts/ci/build-service.sh <service-name>

# Example
bash scripts/ci/build-service.sh controller_manager
```

#### `build-all.sh`
Build all service Docker images sequentially.

```bash
bash scripts/ci/build-all.sh
```

Builds all 7 services: controller_manager, game_coordinator, settings, supervisor, menu, audio, webui.

#### `validate-packages.sh`
Validate Python package installation and imports.

```bash
bash scripts/ci/validate-packages.sh
```

Uses `joustmania/ci-proto:latest` Docker image.

## Makefile Integration

All scripts have corresponding Makefile targets for convenience:

```bash
make lint              # Run linting
make format-check      # Check formatting
make typecheck         # Type check
make lint-dockerfiles  # Lint Dockerfiles
make validate-protos   # Validate protos
make validate-packages # Validate packages
make build-service SERVICE=<name>  # Build single service
make build-all-services            # Build all services

make ci-all    # Run all quality checks
make ci-quick  # Run quick checks (lint + format)
```

## GitHub Actions Integration

These scripts are executed by GitHub Actions CI workflow (`.github/workflows/ci.yml`).

## Building Tooling Images

Before running scripts, ensure tooling images are built:

```bash
docker build -t joustmania/ci-lint:latest tools/ci-lint/
docker build -t joustmania/ci-hadolint:latest tools/ci-hadolint/
docker build -t joustmania/ci-proto:latest tools/ci-proto/

# Or use Makefile
make ci-build-tools
```

## Local Development

For quick iteration, use the Makefile targets which automatically build tooling images:

```bash
# Format code before committing
make format

# Run quick pre-commit checks
make ci-quick

# Run all CI checks (same as GitHub Actions)
make ci-all
```
