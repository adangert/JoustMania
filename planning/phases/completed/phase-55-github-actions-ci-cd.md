# Phase 55: GitHub Actions CI/CD Pipeline

**Status**: PLANNED
**Priority**: HIGH - Quality assurance for production
**Complexity**: Medium
**Estimated Effort**: 6-8 hours

## Goal

Establish comprehensive CI/CD pipeline using GitHub Actions to ensure code quality, prevent regressions, and validate builds before deployment.

**Core Principles:**
1. **Docker-First**: All tooling runs in containers for consistency
2. **Script-Based**: GitHub Actions executes bash scripts (reusable locally)
3. **Make Integration**: Simple `make lint`, `make format` commands
4. **Dev Containers**: One-click VS Code development environment
5. **Zero Setup**: Developers just need Docker installed

## Motivation

**Current State:**
- ❌ No automated quality checks on pull requests
- ❌ No validation that code builds successfully
- ❌ No automated linting or type checking in CI
- ❌ No Dockerfile validation
- ⚠️ Risk of merging broken code to main branches

**Benefits:**
- ✅ **Quality gates**: Prevent merging code that doesn't meet standards
- ✅ **Fast feedback**: Developers know immediately if PR breaks build
- ✅ **Parallelization**: Multiple checks run simultaneously
- ✅ **Confidence**: Deploy knowing all checks passed
- ✅ **Documentation**: CI results show what quality standards are enforced

## Architecture

### Docker-First CI/CD Approach

**Philosophy:**
- All tooling runs in Docker containers
- Scripts in `scripts/ci/` wrap Docker commands
- GitHub Actions simply executes scripts
- Developers use same scripts locally
- Zero dependency setup in CI (just Docker)

### Multi-Stage Pipeline

```
GitHub Actions Pipeline (runs on: pull_request, push to main/master/dev-refactor)
│
├─ Stage 1: Code Quality (Parallel Jobs)
│  ├─ Job: Python Linting
│  │  └─ scripts/ci/lint.sh (runs ruff in Docker)
│  │
│  ├─ Job: Type Checking
│  │  └─ scripts/ci/typecheck.sh (runs mypy in Docker)
│  │
│  └─ Job: Dockerfile Linting
│     └─ scripts/ci/lint-dockerfiles.sh (runs hadolint in Docker)
│
├─ Stage 2: Build Validation (Parallel Jobs)
│  ├─ Job: Proto Generation
│  │  └─ scripts/ci/validate-protos.sh (runs in Docker)
│  │
│  ├─ Job: Docker Build (Matrix Strategy)
│  │  └─ scripts/ci/build-service.sh <service-name>
│  │
│  └─ Job: Package Validation
│     └─ scripts/ci/validate-packages.sh (runs in Docker)
│
└─ Stage 3: Testing (Future - Phase 56)
   └─ Job: Unit Tests
      └─ scripts/ci/test.sh (runs pytest in Docker)

All scripts use Docker containers:
- tools/ci-lint:latest       (ruff + mypy)
- tools/ci-hadolint:latest   (hadolint)
- tools/ci-proto:latest      (protoc + Python)
```

## Implementation Plan

### 1. Create CI Tooling Docker Images

**Structure:**
```
tools/
├── ci-lint/
│   ├── Dockerfile           # Ruff + mypy
│   └── README.md
├── ci-hadolint/
│   ├── Dockerfile           # Hadolint
│   └── README.md
└── ci-proto/
    ├── Dockerfile           # Protoc + Python + uv
    └── README.md
```

#### Tool Image: ci-lint (Ruff + mypy)

**File:** `tools/ci-lint/Dockerfile`

```dockerfile
FROM python:3.11-slim

# Install linting and type checking tools
RUN pip install --no-cache-dir \
    ruff==0.8.4 \
    mypy==1.13.0 \
    types-PyYAML \
    types-requests

WORKDIR /workspace

# Default command shows help
CMD ["ruff", "--help"]
```

#### Tool Image: ci-hadolint

**File:** `tools/ci-hadolint/Dockerfile`

```dockerfile
FROM hadolint/hadolint:v2.12.0-alpine

# Wrapper script for easier usage
COPY <<'EOF' /usr/local/bin/lint-all-dockerfiles.sh
#!/bin/sh
set -e
find /workspace -name "Dockerfile" -type f -exec echo "Linting {}" \; -exec hadolint {} \;
EOF

RUN chmod +x /usr/local/bin/lint-all-dockerfiles.sh

WORKDIR /workspace
ENTRYPOINT ["/bin/hadolint"]
```

#### Tool Image: ci-proto

**File:** `tools/ci-proto/Dockerfile`

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv==0.5.11

WORKDIR /workspace

# Default command
CMD ["/bin/bash"]
```

### 2. Create CI Scripts

**Structure:**
```
scripts/ci/
├── lint.sh                  # Run ruff linting
├── typecheck.sh             # Run mypy type checking
├── format-check.sh          # Check code formatting
├── lint-dockerfiles.sh      # Lint all Dockerfiles
├── validate-protos.sh       # Validate proto generation
├── build-service.sh         # Build single service
├── build-all.sh             # Build all services
├── validate-packages.sh     # Validate Python packages
└── README.md                # Documentation
```

#### Script: lint.sh

**File:** `scripts/ci/lint.sh`

```bash
#!/usr/bin/env bash
# Run ruff linting in Docker container
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Running ruff linting..."

docker run --rm \
    -v "$PROJECT_ROOT:/workspace:ro" \
    -w /workspace \
    joustmania/ci-lint:latest \
    ruff check . --output-format=github

echo "✅ Linting passed!"
```

#### Script: typecheck.sh

**File:** `scripts/ci/typecheck.sh`

```bash
#!/usr/bin/env bash
# Run mypy type checking in Docker container
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Running mypy type checking..."

# Array of services to check
SERVICES=(
    "controller_manager"
    "game_coordinator"
    "settings"
    "supervisor"
    "menu"
    "audio"
    "webui"
)

FAILED=0

for service in "${SERVICES[@]}"; do
    echo "Checking services/$service..."

    docker run --rm \
        -v "$PROJECT_ROOT:/workspace:ro" \
        -w /workspace \
        joustmania/ci-lint:latest \
        mypy "services/$service" --check-untyped-defs --ignore-missing-imports \
        || FAILED=1
done

if [ $FAILED -eq 1 ]; then
    echo "❌ Type checking found issues (warnings only for now)"
    exit 0  # Warning-only mode, change to exit 1 when ready to enforce
else
    echo "✅ Type checking passed!"
fi
```

#### Script: format-check.sh

**File:** `scripts/ci/format-check.sh`

```bash
#!/usr/bin/env bash
# Check code formatting with ruff
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Checking code formatting..."

docker run --rm \
    -v "$PROJECT_ROOT:/workspace:ro" \
    -w /workspace \
    joustmania/ci-lint:latest \
    ruff format --check .

echo "✅ Formatting is correct!"
```

#### Script: lint-dockerfiles.sh

**File:** `scripts/ci/lint-dockerfiles.sh`

```bash
#!/usr/bin/env bash
# Lint all Dockerfiles with hadolint
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Linting Dockerfiles..."

# Find and lint all Dockerfiles
docker run --rm \
    -v "$PROJECT_ROOT:/workspace:ro" \
    -w /workspace \
    joustmania/ci-hadolint:latest \
    /bin/sh -c 'find . -name "Dockerfile" -type f -exec echo "Linting {}" \; -exec hadolint {} \;'

echo "✅ All Dockerfiles passed linting!"
```

#### Script: validate-protos.sh

**File:** `scripts/ci/validate-protos.sh`

```bash
#!/usr/bin/env bash
# Validate proto file generation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Validating proto generation..."

# Generate protos in Docker container
docker run --rm \
    -v "$PROJECT_ROOT:/workspace" \
    -w /workspace \
    joustmania/ci-proto:latest \
    bash proto/generate_proto.sh

# Check for uncommitted changes
cd "$PROJECT_ROOT"
if ! git diff --exit-code proto/; then
    echo "❌ Proto files are out of sync! Run 'make protos' and commit changes."
    exit 1
fi

# Verify bytecode compilation
if [ ! -d "proto/__pycache__" ]; then
    echo "❌ Proto bytecode not generated!"
    exit 1
fi

PYC_COUNT=$(find proto/__pycache__ -name "*.opt-2.pyc" | wc -l)
if [ "$PYC_COUNT" -lt 10 ]; then
    echo "❌ Expected at least 10 .opt-2.pyc files, found $PYC_COUNT"
    exit 1
fi

echo "✅ Proto files validated! Found $PYC_COUNT bytecode files"
```

#### Script: build-service.sh

**File:** `scripts/ci/build-service.sh`

```bash
#!/usr/bin/env bash
# Build a single service Docker image
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <service-name>"
    echo "Example: $0 controller_manager"
    exit 1
fi

SERVICE=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Building $SERVICE service..."

docker build \
    -f "$PROJECT_ROOT/services/$SERVICE/Dockerfile" \
    -t "joustmania/${SERVICE}-service:ci" \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    "$PROJECT_ROOT"

echo "✅ Built $SERVICE successfully!"
```

#### Script: build-all.sh

**File:** `scripts/ci/build-all.sh`

```bash
#!/usr/bin/env bash
# Build all service Docker images
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SERVICES=(
    "controller_manager"
    "game_coordinator"
    "settings"
    "supervisor"
    "menu"
    "audio"
    "webui"
)

echo "Building all services..."

for service in "${SERVICES[@]}"; do
    echo ""
    echo "========================================"
    echo "Building $service"
    echo "========================================"
    "$SCRIPT_DIR/build-service.sh" "$service"
done

echo ""
echo "✅ All services built successfully!"
```

#### Script: validate-packages.sh

**File:** `scripts/ci/validate-packages.sh`

```bash
#!/usr/bin/env bash
# Validate Python package installation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Validating Python packages..."

docker run --rm \
    -v "$PROJECT_ROOT:/workspace" \
    -w /workspace \
    joustmania/ci-proto:latest \
    bash -c '
        set -e
        echo "Installing workspace packages..."
        uv sync --all-packages

        echo "Testing proto imports..."
        uv run python -c "from proto import settings_pb2, controller_manager_pb2; print(\"✅ Proto imports work\")"

        echo "Checking for dependency conflicts..."
        uv pip check

        echo "✅ All packages validated!"
    '
```

### 3. Workflow: Main CI Pipeline

**File:** `.github/workflows/ci.yml`

```yaml
name: CI

on:
  pull_request:
    branches: [main, master, dev-refactor]
  push:
    branches: [main, master, dev-refactor]
  workflow_dispatch:

jobs:
  lint:
    name: Lint Python Code
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build lint tooling image
        run: docker build -t joustmania/ci-lint:latest tools/ci-lint/

      - name: Run linting
        run: bash scripts/ci/lint.sh

      - name: Check formatting
        run: bash scripts/ci/format-check.sh

  typecheck:
    name: Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build lint tooling image
        run: docker build -t joustmania/ci-lint:latest tools/ci-lint/

      - name: Run type checking
        run: bash scripts/ci/typecheck.sh

  lint-dockerfiles:
    name: Lint Dockerfiles
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build hadolint tooling image
        run: docker build -t joustmania/ci-hadolint:latest tools/ci-hadolint/

      - name: Lint Dockerfiles
        run: bash scripts/ci/lint-dockerfiles.sh

  validate-protos:
    name: Validate Proto Files
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build proto tooling image
        run: docker build -t joustmania/ci-proto:latest tools/ci-proto/

      - name: Validate protos
        run: bash scripts/ci/validate-protos.sh

  validate-packages:
    name: Validate Python Packages
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build proto tooling image
        run: docker build -t joustmania/ci-proto:latest tools/ci-proto/

      - name: Validate packages
        run: bash scripts/ci/validate-packages.sh

  docker-build:
    name: Build ${{ matrix.service }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        service:
          - controller_manager
          - game_coordinator
          - settings
          - supervisor
          - menu
          - audio
          - webui
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build service
        run: bash scripts/ci/build-service.sh ${{ matrix.service }}
```

**Key Features:**
- All jobs run scripts (same locally and in CI)
- Tool images built on-demand
- No dependency installation in workflow
- Simple, maintainable workflow file

### 4. Dev Container Setup

**Philosophy:** Make local development identical to CI environment using VS Code Dev Containers.

#### Main Dev Container

**File:** `.devcontainer/devcontainer.json`

```json
{
  "name": "JoustMania Development",
  "dockerComposeFile": "docker-compose.yml",
  "service": "dev",
  "workspaceFolder": "/workspace",

  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "charliermarsh.ruff",
        "ms-azuretools.vscode-docker",
        "redhat.vscode-yaml",
        "ms-vscode.makefile-tools"
      ],
      "settings": {
        "python.defaultInterpreterPath": "/usr/local/bin/python",
        "python.linting.enabled": true,
        "python.linting.ruffEnabled": true,
        "python.formatting.provider": "none",
        "[python]": {
          "editor.defaultFormatter": "charliermarsh.ruff",
          "editor.formatOnSave": true,
          "editor.codeActionsOnSave": {
            "source.organizeImports": true,
            "source.fixAll": true
          }
        },
        "files.watcherExclude": {
          "**/__pycache__/**": true,
          "**/proto/*_pb2.py": true,
          "**/proto/*_pb2_grpc.py": true
        }
      }
    }
  },

  "features": {
    "ghcr.io/devcontainers/features/docker-in-docker:2": {}
  },

  "postCreateCommand": "uv sync --all-packages && make protos",

  "remoteUser": "vscode"
}
```

#### Dev Container Docker Compose

**File:** `.devcontainer/docker-compose.yml`

```yaml
version: '3.8'

services:
  dev:
    build:
      context: ..
      dockerfile: .devcontainer/Dockerfile

    volumes:
      - ..:/workspace:cached
      - /var/run/docker.sock:/var/run/docker.sock  # Docker-in-Docker

    # Keep container running
    command: sleep infinity

    environment:
      - PYTHONPATH=/workspace
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317

    # Network with other services for integration testing
    networks:
      - joustmania

networks:
  joustmania:
    name: joustmania_default
    external: true
```

#### Dev Container Dockerfile

**File:** `.devcontainer/Dockerfile`

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    make \
    curl \
    ca-certificates \
    sudo \
    # Bluetooth development (for controller_manager work)
    libbluetooth-dev \
    libusb-dev \
    libdbus-1-dev \
    libglib2.0-dev \
    pkg-config \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv==0.5.11

# Install development tools
RUN pip install --no-cache-dir \
    ruff==0.8.4 \
    mypy==1.13.0 \
    types-PyYAML \
    types-requests \
    ipython \
    ipdb

# Create non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

USER $USERNAME

WORKDIR /workspace

# Install Docker CLI (for Docker-in-Docker)
RUN curl -fsSL https://get.docker.com | sudo sh

CMD ["/bin/bash"]
```

#### Dev Container Tasks

**File:** `.vscode/tasks.json`

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Lint Code",
      "type": "shell",
      "command": "bash scripts/ci/lint.sh",
      "group": "test",
      "presentation": {
        "reveal": "always",
        "panel": "new"
      }
    },
    {
      "label": "Format Code",
      "type": "shell",
      "command": "ruff format .",
      "group": "none",
      "presentation": {
        "reveal": "silent"
      }
    },
    {
      "label": "Type Check",
      "type": "shell",
      "command": "bash scripts/ci/typecheck.sh",
      "group": "test",
      "presentation": {
        "reveal": "always",
        "panel": "new"
      }
    },
    {
      "label": "Generate Protos",
      "type": "shell",
      "command": "make protos",
      "group": "build",
      "presentation": {
        "reveal": "always"
      }
    },
    {
      "label": "Build All Services",
      "type": "shell",
      "command": "bash scripts/ci/build-all.sh",
      "group": "build",
      "presentation": {
        "reveal": "always",
        "panel": "dedicated"
      }
    },
    {
      "label": "Run All CI Checks",
      "type": "shell",
      "command": "bash scripts/ci/lint.sh && bash scripts/ci/format-check.sh && bash scripts/ci/typecheck.sh && bash scripts/ci/lint-dockerfiles.sh",
      "group": {
        "kind": "test",
        "isDefault": true
      },
      "presentation": {
        "reveal": "always",
        "panel": "dedicated"
      }
    }
  ]
}
```

**Benefits of Dev Containers:**
- ✅ **One-click setup**: Open in VS Code, container builds automatically
- ✅ **Consistent environment**: Same Python, tools, dependencies as CI
- ✅ **Pre-configured**: Linting, formatting, type checking ready to go
- ✅ **Docker-in-Docker**: Can build service containers from within dev container
- ✅ **Integrated debugging**: VS Code debugger works with services
- ✅ **Task integration**: Run CI checks with keyboard shortcuts

### 5. Makefile Targets for CI Tools

**File:** `Makefile` (append to existing file)

```makefile
# ============================================================================
# CI/CD Targets (Phase 55)
# ============================================================================

.PHONY: ci-build-tools
ci-build-tools:
	@echo "Building CI tooling images..."
	@docker build -t joustmania/ci-lint:latest tools/ci-lint/
	@docker build -t joustmania/ci-hadolint:latest tools/ci-hadolint/
	@docker build -t joustmania/ci-proto:latest tools/ci-proto/
	@echo "✓ CI tools built"

.PHONY: lint
lint: ci-build-tools
	@bash scripts/ci/lint.sh

.PHONY: format
format:
	@echo "Formatting code with ruff..."
	@docker run --rm -v "$(PWD):/workspace" -w /workspace joustmania/ci-lint:latest ruff format .
	@echo "✓ Code formatted"

.PHONY: format-check
format-check: ci-build-tools
	@bash scripts/ci/format-check.sh

.PHONY: typecheck
typecheck: ci-build-tools
	@bash scripts/ci/typecheck.sh

.PHONY: lint-dockerfiles
lint-dockerfiles: ci-build-tools
	@bash scripts/ci/lint-dockerfiles.sh

.PHONY: validate-protos
validate-protos: ci-build-tools
	@bash scripts/ci/validate-protos.sh

.PHONY: validate-packages
validate-packages: ci-build-tools
	@bash scripts/ci/validate-packages.sh

.PHONY: build-service
build-service:
	@if [ -z "$(SERVICE)" ]; then \
		echo "Usage: make build-service SERVICE=<service-name>"; \
		echo "Example: make build-service SERVICE=controller_manager"; \
		exit 1; \
	fi
	@bash scripts/ci/build-service.sh $(SERVICE)

.PHONY: build-all-services
build-all-services:
	@bash scripts/ci/build-all.sh

.PHONY: ci-all
ci-all: lint format-check typecheck lint-dockerfiles validate-protos validate-packages
	@echo ""
	@echo "=========================================="
	@echo "✅ All CI checks passed!"
	@echo "=========================================="

.PHONY: ci-quick
ci-quick: lint format-check
	@echo ""
	@echo "✅ Quick CI checks passed!"

.PHONY: ci-help
ci-help:
	@echo "CI/CD Make Targets"
	@echo "=================="
	@echo ""
	@echo "Quality Checks:"
	@echo "  make lint              - Run Python linting (ruff)"
	@echo "  make format            - Format code with ruff"
	@echo "  make format-check      - Check code formatting"
	@echo "  make typecheck         - Run type checking (mypy)"
	@echo "  make lint-dockerfiles  - Lint all Dockerfiles"
	@echo ""
	@echo "Validation:"
	@echo "  make validate-protos   - Validate proto generation"
	@echo "  make validate-packages - Validate Python packages"
	@echo ""
	@echo "Building:"
	@echo "  make build-service SERVICE=<name>  - Build single service"
	@echo "  make build-all-services            - Build all services"
	@echo ""
	@echo "Combined:"
	@echo "  make ci-all    - Run all CI checks"
	@echo "  make ci-quick  - Run quick checks (lint + format)"
	@echo ""
	@echo "Setup:"
	@echo "  make ci-build-tools  - Build CI tooling images"
```

**Update help target:**

```makefile
.PHONY: help
help:
	@echo "JoustMania Build Targets"
	@echo "========================"
	@echo "  make protos          - Generate and compile protobuf files"
	@echo "  make clean-protos    - Remove generated protobuf files"
	@echo "  make docker-build    - Build all Docker images"
	@echo "  make docker-start    - Start Docker services"
	@echo "  make docker-stop     - Stop Docker services"
	@echo ""
	@echo "CI/CD Targets:"
	@echo "  make ci-help         - Show all CI/CD targets"
	@echo "  make ci-all          - Run all CI checks"
	@echo "  make lint            - Lint Python code"
	@echo "  make format          - Format code"
	@echo "  make typecheck       - Type check code"
```

**Usage Examples:**

```bash
# Run all CI checks (same as CI pipeline)
make ci-all

# Quick pre-commit checks
make ci-quick

# Format code before committing
make format

# Check specific things
make lint
make typecheck
make lint-dockerfiles

# Build single service
make build-service SERVICE=controller_manager

# Build all services
make build-all-services

# Validate proto files
make validate-protos
```

**Benefits:**
- ✅ **Simple commands**: `make lint` instead of long Docker commands
- ✅ **Auto-builds tools**: Targets ensure tooling images exist
- ✅ **Pre-commit workflow**: `make ci-quick` before committing
- ✅ **Discoverable**: `make help` and `make ci-help` show all options
- ✅ **Same locally and CI**: Scripts are identical

### 6. Status Badges

**Add to README.md:**

```markdown
# JoustMania

[![CI](https://github.com/YOUR_USERNAME/JoustMania/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/JoustMania/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Multi-player gaming system using PS Move controllers and Raspberry Pi.
```

### 4. Branch Protection Rules (GitHub Settings)

**Recommended Settings:**
- Require status checks before merging
- Require checks to pass:
  - `Python Linting (Ruff)`
  - `Dockerfile Linting (Hadolint)`
  - `Validate Proto Generation`
  - `Docker Build (all 7 matrix jobs)`
  - `Validate Python Packages`
- Require up-to-date branches before merging
- Type checking optional initially (warning-only)

## Configuration Files

### mypy Configuration

**File:** `pyproject.toml` (add section)

```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false  # Start permissive
check_untyped_defs = true      # Check even untyped functions
ignore_missing_imports = true  # Many libraries lack stubs

# Per-module configuration
[[tool.mypy.overrides]]
module = "proto.*"
ignore_errors = true  # Generated code

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

### Hadolint Configuration (Optional)

**File:** `.hadolint.yaml`

```yaml
# Hadolint configuration for Dockerfile linting
ignored:
  - DL3008  # Pin versions in apt-get (not always needed for base images)
  - DL3013  # Pin versions in pip (we use uv which handles this)

failure-threshold: error

trustedRegistries:
  - docker.io
  - python
```

## Testing the Workflow Locally

### Test Linting

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run linting
uv run ruff check . --output-format=github
uv run ruff format --check .
```

### Test Type Checking

```bash
uv pip install mypy types-PyYAML types-requests
uv run mypy services/controller_manager --check-untyped-defs
```

### Test Dockerfile Linting

```bash
# Install hadolint
wget -O /usr/local/bin/hadolint https://github.com/hadolint/hadolint/releases/download/v2.12.0/hadolint-Linux-x86_64
chmod +x /usr/local/bin/hadolint

# Lint all Dockerfiles
find services -name "Dockerfile" -exec hadolint {} \;
```

### Test Docker Builds

```bash
# Build all services
make docker-build

# Or individually
docker build -f services/controller_manager/Dockerfile -t test .
```

## Gradual Quality Improvement Strategy

### Phase 1: Warning Mode (Week 1)
- All jobs run but don't block merges
- Type checking reports issues but doesn't fail
- Gather baseline metrics

### Phase 2: Enforce Basics (Week 2)
- Ruff linting becomes required
- Dockerfile linting becomes required
- Proto validation becomes required
- Docker builds must succeed

### Phase 3: Tighten Standards (Week 3-4)
- Enable type checking failures
- Add more ruff rules
- Enforce formatting

### Phase 4: Full Quality Gates (Week 5+)
- All checks required before merge
- Add unit test requirements (Phase 56)
- Add integration test requirements

## Success Criteria

- ✅ GitHub Actions workflow runs on every PR
- ✅ All 6 jobs complete successfully on clean main branch
- ✅ Developers receive immediate feedback on PRs
- ✅ CI run time < 10 minutes (with caching)
- ✅ Status badges visible in README
- ✅ Branch protection enforces quality gates
- ✅ Zero false positives (jobs don't fail on valid code)

## Performance Considerations

### Caching Strategy

1. **UV Cache**: Cache `~/.cache/uv` for faster dependency installs
2. **Docker Layer Cache**: Use GitHub Actions cache for Docker builds
3. **Proto Cache**: No need to cache (fast generation)

### Parallelization

- All 6 jobs run in parallel (independent)
- Docker matrix builds 7 services in parallel
- Total CI time ≈ 5-8 minutes (vs 30+ minutes sequential)

## Future Enhancements (Post-Phase 55)

### Phase 56: Unit Testing in CI
- Add pytest jobs for all services
- Code coverage reporting
- Coverage thresholds

### Phase 57: Integration Testing
- Docker Compose-based tests
- gRPC contract testing
- End-to-end game simulation

### Phase 58: Deployment Pipeline
- Automatic Docker image publishing
- Semantic versioning
- Release automation

### Phase 59: Security Scanning
- Dependency vulnerability scanning (Dependabot)
- Docker image scanning (Trivy)
- SAST with CodeQL

## Files to Create/Modify

### New Files

**CI Tooling Docker Images:**
1. `tools/ci-lint/Dockerfile` - Ruff + mypy image
2. `tools/ci-lint/README.md` - Tool documentation
3. `tools/ci-hadolint/Dockerfile` - Hadolint image
4. `tools/ci-hadolint/README.md` - Tool documentation
5. `tools/ci-proto/Dockerfile` - Proto generation image
6. `tools/ci-proto/README.md` - Tool documentation

**CI Scripts:**
7. `scripts/ci/lint.sh` - Python linting script
8. `scripts/ci/format-check.sh` - Format checking script
9. `scripts/ci/typecheck.sh` - Type checking script
10. `scripts/ci/lint-dockerfiles.sh` - Dockerfile linting script
11. `scripts/ci/validate-protos.sh` - Proto validation script
12. `scripts/ci/build-service.sh` - Single service build script
13. `scripts/ci/build-all.sh` - All services build script
14. `scripts/ci/validate-packages.sh` - Package validation script
15. `scripts/ci/README.md` - Scripts documentation

**GitHub Actions:**
16. `.github/workflows/ci.yml` - Main CI pipeline

**Dev Container:**
17. `.devcontainer/devcontainer.json` - VS Code dev container config
18. `.devcontainer/docker-compose.yml` - Dev container compose file
19. `.devcontainer/Dockerfile` - Dev container image
20. `.vscode/tasks.json` - VS Code tasks for CI commands

**Configuration:**
21. `.hadolint.yaml` - Hadolint configuration (optional)
22. `.github/dependabot.yml` - Dependency updates (bonus)
23. `docs/CONTRIBUTING.md` - Developer guide

### Modified Files
1. `Makefile` - Add CI/CD targets
2. `pyproject.toml` - Add mypy configuration
3. `README.md` - Add status badges and dev container instructions
4. `.github/settings.yml` - Branch protection (via GitHub UI)

**Total:** 23 new files, 4 modified files

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CI runs too slow | Developer friction | Aggressive caching, parallelization |
| False positives | Bypassing checks | Start permissive, tighten gradually |
| Flaky tests | Lost trust in CI | No tests yet; add carefully in Phase 56 |
| GitHub Actions costs | Budget concerns | Use public repo (free); optimize runtime |

## Documentation

### Developer Guide Section

**File:** `docs/CONTRIBUTING.md` (to be created)

```markdown
## Continuous Integration

All pull requests must pass CI checks before merging:

1. **Python Linting**: Code must pass `ruff check` and `ruff format --check`
2. **Dockerfile Linting**: All Dockerfiles must pass hadolint validation
3. **Proto Validation**: Proto files must be up-to-date (run `make protos`)
4. **Docker Builds**: All 7 services must build successfully
5. **Package Validation**: All workspace packages must install correctly

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
```

## Timeline

| Day | Task |
|-----|------|
| 1 | Create CI tooling Docker images (ci-lint, ci-hadolint, ci-proto) |
| 1 | Create all 8 CI scripts in `scripts/ci/` |
| 1 | Add mypy configuration to `pyproject.toml` |
| 2 | Create `.github/workflows/ci.yml` workflow |
| 2 | Create `.hadolint.yaml` configuration |
| 2 | Add Makefile CI targets (lint, format, typecheck, etc.) |
| 3 | Test all scripts locally with Docker |
| 3 | Create dev container setup (`.devcontainer/`) |
| 3 | Create VS Code tasks (`.vscode/tasks.json`) |
| 4 | Test GitHub Actions workflow on feature branch |
| 4 | Fix any discovered issues |
| 5 | Add status badges to README |
| 5 | Create `docs/CONTRIBUTING.md` developer guide |
| 6 | Enable branch protection rules |
| 6 | Validate on multiple PRs |
| 7 | Monitor performance and optimize caching |
| 7 | Document any edge cases discovered |

**Estimated Total:** 6-8 hours spread over 1-2 weeks

## Dependencies

**External:**
- GitHub Actions (free for public repos)
- Docker Hub (for base images)

**GitHub Actions:**
- `actions/checkout@v4`
- `astral-sh/setup-uv@v4`
- `docker/setup-buildx-action@v3`
- `docker/build-push-action@v5`
- `hadolint/hadolint-action@v3.1.0`
- `github/codeql-action/upload-sarif@v3`

## Related Phases

- **Phase 47**: Protobuf precompilation (validated in CI)
- **Phase 56**: Unit testing (next step after CI)
- **Phase 57**: Integration testing
- **Phase 58**: Deployment automation

## Notes

- Start with **permissive settings** (warnings only) to avoid blocking development
- Gradually **tighten standards** as codebase improves
- Use **GitHub Actions cache** aggressively for performance
- **Matrix strategy** for parallel Docker builds is critical for speed
- **Status badges** provide visibility into CI health

---

**Phase Owner**: TBD
**Reviewers**: TBD
**Target Completion**: Q1 2026
