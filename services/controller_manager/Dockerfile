# Multi-stage build for JoustMania Controller Manager Service
#
# Uses pre-built psmoveapi image for faster builds (Phase 69)
# Build the images first:
#   docker build -t joustmania/psmove-builder:latest images/psmove-builder/
#   docker build -t joustmania/builder:latest images/builder/
#
# Phase 75: Builder images can be overridden for CI/CD
# --build-arg BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/builder:latest
# --build-arg PSMOVE_BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/psmove-builder:latest
#
# Build time: ~1-2 minutes (vs 10-15 minutes without pre-built psmoveapi)

# Builder images - override with --build-arg for CI/CD
ARG BUILDER_IMAGE=joustmania/builder:latest
ARG PSMOVE_BUILDER_IMAGE=joustmania/psmove-builder:latest

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
    pkg-config \
    libbluetooth-dev \
    libusb-dev \
    libdbus-1-dev \
    libglib2.0-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy workspace configuration
COPY pyproject.toml /app/

# Copy proto package (shared protocol buffer contracts)
COPY proto/pyproject.toml /app/proto/
COPY proto/*.py /app/proto/
COPY proto/__pycache__/ /app/proto/__pycache__/

# Copy service dependencies
COPY services/controller_manager/pyproject.toml /app/services/controller_manager/

# Install service-specific dependencies
WORKDIR /app/services/controller_manager
RUN uv pip install --system -e .

# =============================================================================
# Stage 3: Runtime image
# =============================================================================
FROM python:3.11-slim

# Install runtime dependencies (bluetooth for PS Move controllers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libbluetooth3 \
    libusb-1.0-0 \
    libdbus-1-3 \
    libglib2.0-0 \
    bluez \
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

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:50052'); channel.channel_ready()" || exit 1

# Run the server
CMD ["python", "services/controller_manager/server.py"]
