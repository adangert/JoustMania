# Multi-stage build for JoustMania Game Coordinator Service
#
# Uses shared builder image for faster builds (Phase 69)
# Build the builder first: docker build -t joustmania/builder:latest images/builder/
#
# Phase 75: Builder image can be overridden for CI/CD
# --build-arg BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/builder:latest

# Builder image - override with --build-arg BUILDER_IMAGE=...
ARG BUILDER_IMAGE=joustmania/builder:latest

# Download grpc-health-probe for health checks
FROM busybox:1.36 AS healthprobe
ARG GRPC_HEALTH_PROBE_VERSION=v0.4.25
RUN wget -qO/grpc_health_probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 && \
    chmod +x /grpc_health_probe

# Build stage - uses pre-cached builder with common dependencies
FROM ${BUILDER_IMAGE} AS builder

WORKDIR /app

# Copy workspace configuration
COPY pyproject.toml /app/

# Copy proto package (shared protocol buffer contracts)
COPY proto/pyproject.toml /app/proto/
COPY proto/*.py /app/proto/
RUN python -m compileall -q proto/

# Copy service dependencies
COPY services/game_coordinator/pyproject.toml /app/services/game_coordinator/

# Install service-specific dependencies only (common deps already in builder)
WORKDIR /app/services/game_coordinator
RUN uv pip install --system -e .

# Runtime stage - distroless image for minimal size and attack surface
FROM gcr.io/distroless/python3-debian12

WORKDIR /app

# Copy grpc-health-probe for health checks
COPY --from=healthprobe /grpc_health_probe /bin/grpc_health_probe

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
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["/bin/grpc_health_probe", "-addr=:50053"]

# Run the server (distroless has python as entrypoint)
CMD ["services/game_coordinator/server.py"]
