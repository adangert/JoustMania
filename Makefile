# JoustMania Build Targets
# Phase 47: Protobuf precompilation optimization
# Phase 69: Shared builder images

.PHONY: help
help:
	@echo "JoustMania Build Targets"
	@echo "========================"
	@echo ""
	@echo "Quick Start:"
	@echo "  make up              - Build images and start all services"
	@echo "  make down            - Stop all services"
	@echo "  make logs            - Follow service logs"
	@echo "  make restart         - Restart all services"
	@echo ""
	@echo "Build:"
	@echo "  make images          - Build all service images"
	@echo "  make builders        - Build base images (run once, ~15min on Pi)"
	@echo ""
	@echo "Individual Services:"
	@echo "  make image-settings  - Build settings service image"
	@echo "  make image-audio     - Build audio service image"
	@echo "  (etc. for all services)"
	@echo ""
	@echo "Protos:"
	@echo "  make protos          - Generate protobuf files"
	@echo "  make clean-protos    - Remove generated protos"
	@echo ""
	@echo "Testing:  make test-help"
	@echo "CI/CD:    make ci-help"

.PHONY: protos
protos:
	@echo "Generating and compiling protobuf files..."
	@bash proto/generate_proto.sh
	@echo "✓ Done! Protobuf files are ready with optimized bytecode."

.PHONY: clean-protos
clean-protos:
	@echo "Cleaning generated protobuf files..."
	@rm -f proto/*_pb2.py proto/*_pb2_grpc.py
	@rm -rf proto/__pycache__
	@echo "✓ Done! Protobuf files cleaned."

# ============================================================================
# Docker Compose Commands
# ============================================================================

.PHONY: up
up: images
	@echo "Starting JoustMania stack..."
	@docker compose up -d
	@echo ""
	@echo "=========================================="
	@echo "JoustMania is running!"
	@echo "=========================================="
	@echo "  Web UI:     http://localhost:80"
	@echo "  Jaeger:     http://localhost:16686"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Grafana:    http://localhost:3000"

.PHONY: down
down:
	@echo "Stopping JoustMania stack..."
	@docker compose down

.PHONY: logs
logs:
	@docker compose logs -f

.PHONY: restart
restart: down up

.PHONY: ps
ps:
	@docker compose ps

# ============================================================================
# Builder Images (Phase 69)
# ============================================================================
# These images cache common dependencies to speed up service builds.
# Build once, then service builds will be much faster.

# Marker files to track when builders were last built
BUILDER_MARKER := .builder-built
PSMOVE_BUILDER_MARKER := .psmove-builder-built

.PHONY: builder
builder: $(BUILDER_MARKER)

$(BUILDER_MARKER): images/builder/Dockerfile images/builder/requirements-common.txt
	@echo "Building shared Python builder image..."
	@docker build -t joustmania/builder:latest images/builder/
	@touch $(BUILDER_MARKER)
	@echo "✓ Builder image ready"

.PHONY: psmove-builder
psmove-builder: $(PSMOVE_BUILDER_MARKER)

$(PSMOVE_BUILDER_MARKER): images/psmove-builder/Dockerfile
	@echo "Building psmoveapi builder image (this takes 10-15 minutes on Pi)..."
	@docker build -t joustmania/psmove-builder:latest images/psmove-builder/
	@touch $(PSMOVE_BUILDER_MARKER)
	@echo "✓ PS Move builder image ready"

.PHONY: builders
builders: builder psmove-builder
	@echo ""
	@echo "✓ All builder images ready!"

.PHONY: builder-force
builder-force:
	@echo "Force rebuilding shared Python builder image..."
	@docker build --no-cache -t joustmania/builder:latest images/builder/
	@touch $(BUILDER_MARKER)
	@echo "✓ Builder image rebuilt"

.PHONY: psmove-builder-force
psmove-builder-force:
	@echo "Force rebuilding psmoveapi builder image..."
	@docker build --no-cache -t joustmania/psmove-builder:latest images/psmove-builder/
	@touch $(PSMOVE_BUILDER_MARKER)
	@echo "✓ PS Move builder image rebuilt"

.PHONY: clean-builders
clean-builders:
	@echo "Removing builder marker files..."
	@rm -f $(BUILDER_MARKER) $(PSMOVE_BUILDER_MARKER)
	@echo "✓ Builder markers cleaned (images still exist)"

# ============================================================================
# Service Images
# ============================================================================
# Build service images using the shared builder images.
# Each service image is tagged as joustmania/<service>-service:latest

# Individual service image targets
.PHONY: image-settings
image-settings: builders
	@echo "Building settings service..."
	@docker build -f services/settings/Dockerfile \
		-t joustmania/settings-service:latest \
		--build-arg BUILDER_IMAGE=joustmania/builder:latest .
	@echo "✓ settings-service:latest built"

.PHONY: image-controller-manager
image-controller-manager: builders
	@echo "Building controller-manager service..."
	@docker build -f services/controller_manager/Dockerfile \
		-t joustmania/controller-manager-service:latest \
		--build-arg BUILDER_IMAGE=joustmania/builder:latest \
		--build-arg PSMOVE_BUILDER_IMAGE=joustmania/psmove-builder:latest .
	@echo "✓ controller-manager-service:latest built"

.PHONY: image-game-coordinator
image-game-coordinator: builders
	@echo "Building game-coordinator service..."
	@docker build -f services/game_coordinator/Dockerfile \
		-t joustmania/game-coordinator-service:latest \
		--build-arg BUILDER_IMAGE=joustmania/builder:latest .
	@echo "✓ game-coordinator-service:latest built"

.PHONY: image-menu
image-menu: builders
	@echo "Building menu service..."
	@docker build -f services/menu/Dockerfile \
		-t joustmania/menu-service:latest \
		--build-arg BUILDER_IMAGE=joustmania/builder:latest .
	@echo "✓ menu-service:latest built"

.PHONY: image-supervisor
image-supervisor: builders
	@echo "Building supervisor service..."
	@docker build -f services/supervisor/Dockerfile \
		-t joustmania/supervisor-service:latest \
		--build-arg BUILDER_IMAGE=joustmania/builder:latest .
	@echo "✓ supervisor-service:latest built"

.PHONY: image-webui
image-webui: builders
	@echo "Building webui service..."
	@docker build -f services/webui/Dockerfile \
		-t joustmania/webui-service:latest \
		--build-arg BUILDER_IMAGE=joustmania/builder:latest .
	@echo "✓ webui-service:latest built"

.PHONY: image-audio
image-audio: builders
	@echo "Building audio service..."
	@docker build -f services/audio/Dockerfile \
		-t joustmania/audio-service:latest \
		--build-arg BUILDER_IMAGE=joustmania/builder:latest .
	@echo "✓ audio-service:latest built"

# Build all service images
.PHONY: images
images: image-settings image-controller-manager image-game-coordinator image-menu image-supervisor image-webui image-audio
	@echo ""
	@echo "✓ All service images built!"

# ============================================================================
# CI/CD Targets (Phase 55)
# ============================================================================

# Services list for build targets
SERVICES := controller_manager game_coordinator settings supervisor menu audio webui

.PHONY: ci-build-tools
ci-build-tools:
	@echo "Building CI tooling images..."
	@docker build -t joustmania/ci-lint:latest tools/ci-lint/
	@docker build -t joustmania/ci-hadolint:latest tools/ci-hadolint/
	@docker build -t joustmania/ci-proto:latest tools/ci-proto/
	@echo "✓ CI tools built"

.PHONY: lint
lint: ci-build-tools
	@echo "Running ruff linting..."
	@docker run --rm \
		-v "$(PWD):/workspace:ro" \
		-w /workspace \
		-e RUFF_CACHE_DIR=/tmp/ruff-cache \
		joustmania/ci-lint:latest \
		ruff check . --output-format=github
	@echo "✅ Linting passed!"

.PHONY: format
format: ci-build-tools
	@echo "Formatting code with ruff..."
	@docker run --rm \
		-v "$(PWD):/workspace" \
		-w /workspace \
		-e RUFF_CACHE_DIR=/tmp/ruff-cache \
		joustmania/ci-lint:latest \
		ruff format .
	@echo "✓ Code formatted"

.PHONY: format-check
format-check: ci-build-tools
	@echo "Checking code formatting..."
	@docker run --rm \
		-v "$(PWD):/workspace:ro" \
		-w /workspace \
		-e RUFF_CACHE_DIR=/tmp/ruff-cache \
		joustmania/ci-lint:latest \
		ruff format --check .
	@echo "✅ Formatting is correct!"

.PHONY: typecheck
typecheck: ci-build-tools
	@echo "Running ty type checking..."
	@for service in $(SERVICES); do \
		echo "Checking services/$$service..."; \
		docker run --rm \
			-v "$(PWD):/workspace:ro" \
			-w /workspace \
			joustmania/ci-lint:latest \
			ty check "services/$$service" || true; \
	done
	@echo "✅ Type checking complete (warnings only)"

.PHONY: lint-dockerfiles
lint-dockerfiles: ci-build-tools
	@echo "Linting Dockerfiles..."
	@docker run --rm \
		--entrypoint /bin/sh \
		-v "$(PWD):/workspace:ro" \
		-w /workspace \
		joustmania/ci-hadolint:latest \
		-c 'find . -name "Dockerfile" -type f -exec echo "Linting {}" \; -exec hadolint {} \;'
	@echo "✅ All Dockerfiles passed linting!"

.PHONY: validate-protos
validate-protos: ci-build-tools
	@bash scripts/ci/validate-protos.sh

.PHONY: validate-packages
validate-packages: ci-build-tools
	@bash scripts/ci/validate-packages.sh

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

.PHONY: ci-integration
ci-integration: ci-build-test
	@echo "Running integration tests for CI..."
	@docker run --rm \
		-v "$(PWD):/workspace" \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-w /workspace \
		-e DOCKER_HOST=unix:///var/run/docker.sock \
		joustmania/ci-test:latest \
		uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py -v
	@echo "✅ Integration tests passed!"

.PHONY: ci-help
ci-help:
	@echo "CI/CD Make Targets"
	@echo "=================="
	@echo ""
	@echo "Quality Checks:"
	@echo "  make lint              - Run Python linting (ruff)"
	@echo "  make format            - Format code with ruff"
	@echo "  make format-check      - Check code formatting"
	@echo "  make typecheck         - Run type checking (ty)"
	@echo "  make lint-dockerfiles  - Lint all Dockerfiles"
	@echo ""
	@echo "Validation:"
	@echo "  make validate-protos   - Validate proto generation"
	@echo "  make validate-packages - Validate Python packages"
	@echo ""
	@echo "Testing:"
	@echo "  make ci-integration    - Run integration tests in CI"
	@echo ""
	@echo "Building:"
	@echo "  make build-service SERVICE=<name>  - Build single service"
	@echo "  make build-all-services            - Build all services"
	@echo ""
	@echo "Combined:"
	@echo "  make ci-all    - Run all CI checks (no integration tests)"
	@echo "  make ci-quick  - Run quick checks (lint + format)"
	@echo ""
	@echo "Setup:"
	@echo "  make ci-build-tools  - Build CI tooling images"

# ============================================================================
# Testing Targets
# ============================================================================

.PHONY: ci-build-test
ci-build-test:
	@echo "Building test runner image..."
	@docker build -t joustmania/ci-test:latest tools/ci-test/
	@echo "✓ Test runner image built"

.PHONY: test
test:
	@echo "Running integration tests with mock environment (fresh venv)..."
	@rm -rf .venv-test 2>/dev/null || true
	@UV_PROJECT_ENVIRONMENT=.venv-test uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py -v

.PHONY: test-docker
test-docker: ci-build-test
	@echo "Running integration tests in Docker..."
	@docker run --rm \
		-v "$(PWD):/workspace" \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-w /workspace \
		-e DOCKER_HOST=unix:///var/run/docker.sock \
		joustmania/ci-test:latest \
		uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py -v

.PHONY: test-mock-pause
test-mock-pause:
	@echo "Running integration tests with pause (for Jaeger inspection)..."
	@echo "Note: Tests will pause before teardown. Press Enter to continue."
	@echo ""
	@rm -rf .venv-test 2>/dev/null || true
	@PAUSE_BEFORE_TEARDOWN=1 UV_PROJECT_ENVIRONMENT=.venv-test uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py -v -s

.PHONY: test-mock-pause-docker
test-mock-pause-docker: ci-build-test
	@echo "Running integration tests in Docker with pause (for Jaeger inspection)..."
	@echo "Note: Tests will pause before teardown. Press Enter in test output to continue."
	@docker run --rm -it \
		-v "$(PWD):/workspace" \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-w /workspace \
		-e DOCKER_HOST=unix:///var/run/docker.sock \
		-e PAUSE_BEFORE_TEARDOWN=1 \
		joustmania/ci-test:latest \
		uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py -v -s

.PHONY: test-ffa
test-ffa:
	@echo "Running FFA integration test (fresh venv)..."
	@rm -rf .venv-test 2>/dev/null || true
	@UV_PROJECT_ENVIRONMENT=.venv-test uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py::test_ffa_game_with_mock_controllers -v

.PHONY: test-ffa-docker
test-ffa-docker: ci-build-test
	@echo "Running FFA integration test in Docker..."
	@docker run --rm \
		-v "$(PWD):/workspace" \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-w /workspace \
		-e DOCKER_HOST=unix:///var/run/docker.sock \
		joustmania/ci-test:latest \
		uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py::test_ffa_game_with_mock_controllers -v

.PHONY: test-teams
test-teams:
	@echo "Running Teams integration test (fresh venv)..."
	@rm -rf .venv-test 2>/dev/null || true
	@UV_PROJECT_ENVIRONMENT=.venv-test uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py::test_teams_game_with_mock_controllers -v

.PHONY: test-teams-docker
test-teams-docker: ci-build-test
	@echo "Running Teams integration test in Docker..."
	@docker run --rm \
		-v "$(PWD):/workspace" \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-w /workspace \
		-e DOCKER_HOST=unix:///var/run/docker.sock \
		joustmania/ci-test:latest \
		uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py::test_teams_game_with_mock_controllers -v

.PHONY: test-random-teams
test-random-teams:
	@echo "Running Random Teams integration test (fresh venv)..."
	@rm -rf .venv-test 2>/dev/null || true
	@UV_PROJECT_ENVIRONMENT=.venv-test uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py::test_random_teams_game_with_mock_controllers -v

.PHONY: test-random-teams-docker
test-random-teams-docker: ci-build-test
	@echo "Running Random Teams integration test in Docker..."
	@docker run --rm \
		-v "$(PWD):/workspace" \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-w /workspace \
		-e DOCKER_HOST=unix:///var/run/docker.sock \
		joustmania/ci-test:latest \
		uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py::test_random_teams_game_with_mock_controllers -v

.PHONY: test-watch
test-watch:
	@echo "Running tests in watch mode (re-runs on file changes)..."
	@uv run --package joustmania-integration-tests pytest tests/integration/test_mock_environment.py -v --looponfail

.PHONY: test-help
test-help:
	@echo "Testing Make Targets"
	@echo "===================="
	@echo ""
	@echo "Run Tests (Local - Recommended):"
	@echo "  make test                - Run all integration tests"
	@echo "  make test-mock-pause     - Run with pause before teardown (for Jaeger)"
	@echo "  make test-ffa            - Run FFA integration test only"
	@echo "  make test-teams          - Run Teams integration test only"
	@echo "  make test-random-teams   - Run Random Teams integration test only"
	@echo ""
	@echo "Run Tests (Docker):"
	@echo "  make test-docker             - Run all tests in Docker container"
	@echo "  make test-mock-pause-docker  - Run with pause in Docker (for Jaeger)"
	@echo "  make test-ffa-docker         - Run FFA test in Docker"
	@echo "  make test-teams-docker       - Run Teams test in Docker"
	@echo "  make test-random-teams-docker - Run Random Teams test in Docker"
	@echo ""
	@echo "Development:"
	@echo "  make test-watch       - Run tests in watch mode (re-runs on changes)"
	@echo ""
	@echo "Setup:"
	@echo "  make ci-build-test    - Build test runner Docker image"
	@echo ""
	@echo "Notes:"
	@echo "  - Local tests use fresh venv (.venv-test) - no permission issues"
	@echo "  - Docker tests may have TTY issues with pause mode - use local for Jaeger"
	@echo "  - For Jaeger inspection: make test-mock-pause"
	@echo "  - Requirements: uv installed (local tests) or Docker (Docker tests)"
