# Multi-stage build for JoustMania Game Coordinator Service
#
# Uses shared builder image for faster builds (Phase 69)
# Build the builder first: docker build -t ghcr.io/watchmejoustmyflags/joustmania/builder:latest images/builder/
#
# Phase 75: Builder image can be overridden for CI/CD
# --build-arg BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/builder:dev-refactor

# Builder image - override with --build-arg BUILDER_IMAGE=...
ARG BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/builder:latest


# Build stage - uses pre-cached builder with common dependencies
FROM ${BUILDER_IMAGE} AS builder

WORKDIR /app

# Copy workspace configuration
COPY pyproject.toml /app/

# Copy proto package (shared protocol buffer contracts)
COPY proto/pyproject.toml /app/proto/
COPY proto/*.py /app/proto/
RUN python -m compileall -q proto/

# Copy lib package (shared utilities)
COPY lib/pyproject.toml /app/lib/
COPY lib/*.py /app/lib/
RUN python -m compileall -q lib/

# Copy service dependencies
COPY services/game_coordinator/pyproject.toml /app/services/game_coordinator/

# Install workspace packages and service dependencies
WORKDIR /app
RUN uv pip install --system -e proto/ -e lib/ -e services/game_coordinator/

# Runtime stage - distroless image for minimal size and attack surface
FROM gcr.io/distroless/python3-debian12

WORKDIR /app

# Copy grpc-health-probe for health checks
# Copy grpc-health-probe from official multi-arch image
COPY --from=ghcr.io/grpc-ecosystem/grpc-health-probe:v0.4.38 /ko-app/grpc-health-probe /bin/grpc_health_probe

# Copy installed packages from builder to distroless stdlib location
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/lib/python3.11/
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app/pyproject.toml /app/
COPY proto/ /app/proto/
COPY lib/ /app/lib/
COPY services/game_coordinator/ /app/services/game_coordinator/

# Set Python path for application code
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

# Health check using grpc-health-probe (proper gRPC health checking)
HEALTHCHECK --interval=2s --timeout=2s --start-period=1s --retries=3 \
    CMD ["/bin/grpc_health_probe", "-addr=:50053"]

# Run the server (distroless has python as entrypoint)
CMD ["services/game_coordinator/server.py"]
