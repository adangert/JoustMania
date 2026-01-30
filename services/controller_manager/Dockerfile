# Multi-stage build for JoustMania Controller Manager Service
#
# Uses pre-built psmoveapi image for faster builds (Phase 69)
# Build the images first:
#   docker build -t ghcr.io/watchmejoustmyflags/joustmania/psmove-builder:latest images/psmove-builder/
#   docker build -t ghcr.io/watchmejoustmyflags/joustmania/builder:latest images/builder/
#
# Phase 75: Builder images can be overridden for CI/CD
# --build-arg BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/builder:dev-refactor
# --build-arg PSMOVE_BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/psmove-builder:dev-refactor
#
# Build time: ~1-2 minutes (vs 10-15 minutes without pre-built psmoveapi)

# Builder images - override with --build-arg for CI/CD
ARG BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/builder:latest
ARG PSMOVE_BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/psmove-builder:latest

# =============================================================================
# Stage 1: PS Move API - use pre-built image
# =============================================================================
FROM ${PSMOVE_BUILDER_IMAGE} AS psmove-builder

# =============================================================================
# Stage 2: Build Python dependencies
# =============================================================================
FROM ${BUILDER_IMAGE} AS python-builder

# Install additional bluetooth build dependencies (not in common builder)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libbluetooth-dev \
    libdbus-1-dev \
    libglib2.0-dev \
    libusb-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

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
COPY services/controller_manager/pyproject.toml /app/services/controller_manager/

# Install workspace packages and service dependencies
WORKDIR /app
RUN uv pip install --system -e proto/ -e lib/ -e services/controller_manager/

# =============================================================================
# Stage 3: Runtime image
# =============================================================================
FROM python:3.11-slim

# Install runtime dependencies (bluetooth for PS Move controllers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    libbluetooth3 \
    libdbus-1-3 \
    libglib2.0-0 \
    libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from python-builder
COPY --from=python-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin

# Copy psmove Python bindings from pre-built psmove-builder
COPY --from=psmove-builder /psmove/psmove.py /usr/local/lib/python3.11/site-packages/
COPY --from=psmove-builder /psmove/_psmove.so /usr/local/lib/python3.11/site-packages/
COPY --from=psmove-builder /psmove/libpsmoveapi.so /usr/local/lib/

# Update library cache so _psmove.so can find libpsmoveapi.so
RUN ldconfig

# Copy grpc-health-probe binary
# Copy grpc-health-probe from official multi-arch image
COPY --from=ghcr.io/grpc-ecosystem/grpc-health-probe:v0.4.38 /ko-app/grpc-health-probe /bin/grpc_health_probe

# Copy application code
COPY --from=python-builder /app/pyproject.toml /app/
COPY proto/ /app/proto/
COPY lib/ /app/lib/
COPY services/controller_manager/ /app/services/controller_manager/

# Set Python path
ENV PYTHONPATH=/app
# Ensure Python uses bytecode cache for faster imports (Phase 47)
ENV PYTHONDONTWRITEBYTECODE=0

# Configure OpenTelemetry
ENV OTEL_SERVICE_NAME=controller-manager-service
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
ENV OTEL_TRACES_EXPORTER=otlp
ENV OTEL_METRICS_EXPORTER=none
ENV OTEL_LOGS_EXPORTER=none

# Expose gRPC port
EXPOSE 50052

# Expose Prometheus metrics port (Phase 38)
EXPOSE 8000

# Note: Controller manager needs privileged access for bluetooth
# Run with: docker run --privileged or docker-compose privileged: true

# Health check using grpc-health-probe
HEALTHCHECK --interval=2s --timeout=2s --start-period=1s --retries=3 \
    CMD ["/bin/grpc_health_probe", "-addr=:50052"]

# Run the server
CMD ["python", "services/controller_manager/server.py"]
