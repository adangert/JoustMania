# Multi-stage build for JoustMania Game Coordinator Service
#
# Uses shared builder image for faster builds (Phase 69)
# Build the builder first: docker build -t joustmania/builder:latest images/builder/

# Builder image - override with --build-arg BUILDER_IMAGE=...
ARG BUILDER_IMAGE=joustmania/builder:latest

# Build stage - uses pre-cached builder with common dependencies
FROM ${BUILDER_IMAGE} AS builder

WORKDIR /app

# Copy workspace configuration
COPY pyproject.toml /app/

# Copy proto package (shared protocol buffer contracts)
COPY proto/pyproject.toml /app/proto/
COPY proto/*.py /app/proto/
COPY proto/__pycache__/ /app/proto/__pycache__/

# Copy service dependencies
COPY services/game_coordinator/pyproject.toml /app/services/game_coordinator/

# Install service-specific dependencies only (common deps already in builder)
WORKDIR /app/services/game_coordinator
RUN uv pip install --system -e .

# Runtime stage - slim image without build tools
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app/pyproject.toml /app/
COPY proto/ /app/proto/
COPY lib/ /app/lib/
COPY services/game_coordinator/ /app/services/game_coordinator/

# Set Python path
ENV PYTHONPATH=/app
# Ensure Python uses bytecode cache for faster imports (Phase 47)
ENV PYTHONDONTWRITEBYTECODE=0

# Configure OpenTelemetry
ENV OTEL_SERVICE_NAME=game-coordinator-service
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
ENV OTEL_TRACES_EXPORTER=otlp
ENV OTEL_METRICS_EXPORTER=none
ENV OTEL_LOGS_EXPORTER=none

# Expose gRPC port
EXPOSE 50053

# Expose Prometheus metrics port (Phase 38)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:50053'); channel.channel_ready()" || exit 1

# Run the server
CMD ["python", "services/game_coordinator/server.py"]
