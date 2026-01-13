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
format: ci-build-tools
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
