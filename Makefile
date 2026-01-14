# JoustMania Build Targets
# Phase 47: Protobuf precompilation optimization

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
	@echo "Testing Targets:"
	@echo "  make test-help       - Show all testing targets"
	@echo "  make test            - Run all integration tests (recommended)"
	@echo "  make test-teams      - Run Teams test"
	@echo "  make test-mock-pause - Run with pause for Jaeger inspection"
	@echo ""
	@echo "CI/CD Targets:"
	@echo "  make ci-help         - Show all CI/CD targets"
	@echo "  make ci-all          - Run all CI checks"
	@echo "  make lint            - Lint Python code"
	@echo "  make format          - Format code"
	@echo "  make typecheck       - Type check code"

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

.PHONY: docker-build
docker-build:
	@bash scripts/docker/build.sh

.PHONY: docker-start
docker-start:
	@bash scripts/docker/start.sh

.PHONY: docker-stop
docker-stop:
	@bash scripts/docker/stop.sh

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

.PHONY: build-service
build-service:
	@if [ -z "$(SERVICE)" ]; then \
		echo "Usage: make build-service SERVICE=<service-name>"; \
		echo "Example: make build-service SERVICE=controller_manager"; \
		exit 1; \
	fi
	@echo "Building $(SERVICE) service..."
	@docker build \
		-f services/$(SERVICE)/Dockerfile \
		-t joustmania/$(SERVICE)-service:ci \
		--build-arg BUILDKIT_INLINE_CACHE=1 \
		.
	@echo "✅ Built $(SERVICE) successfully!"

.PHONY: build-all-services
build-all-services:
	@echo "Building all services..."
	@for service in $(SERVICES); do \
		echo ""; \
		echo "========================================"; \
		echo "Building $$service"; \
		echo "========================================"; \
		$(MAKE) build-service SERVICE=$$service; \
	done
	@echo ""
	@echo "✅ All services built successfully!"

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
