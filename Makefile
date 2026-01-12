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
