# Multi-stage build for JoustMania Audio Service
#
# Uses pre-built pygame from pygame-builder image for faster builds
# Build the pygame builder first: docker build -t joustmania/pygame-builder:latest images/pygame-builder/
#
# Phase 70: Added scipy, numpy, pydub, pyalsaaudio for tempo control
# Phase 75: Builder images can be overridden for CI/CD
# --build-arg BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/builder:latest
# --build-arg PYGAME_BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/pygame-builder:latest

# Builder images - override with --build-arg for CI/CD
ARG BUILDER_IMAGE=joustmania/builder:latest
ARG PYGAME_BUILDER_IMAGE=joustmania/pygame-builder:latest

# Pygame builder - pre-compiled pygame with SDL2 support
FROM ${PYGAME_BUILDER_IMAGE} AS pygame-builder

# Build stage - uses pre-cached builder with common dependencies
FROM ${BUILDER_IMAGE} AS builder

# Install ALSA dev libraries for pyalsaaudio compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy workspace configuration
COPY pyproject.toml /app/

# Copy proto package (shared protocol buffer contracts)
COPY proto/pyproject.toml /app/proto/
COPY proto/*.py /app/proto/
RUN python -m compileall -q proto/

# Copy service dependencies
COPY services/audio/pyproject.toml /app/services/audio/

# Install proto package from local workspace
WORKDIR /app/proto
RUN pip install --no-cache-dir -e .

# Install service-specific dependencies EXCEPT pygame (comes from pygame-builder)
WORKDIR /app/services/audio
RUN pip install --no-cache-dir \
    grpcio>=1.70.0 \
    grpcio-health-checking>=1.70.0 \
    opentelemetry-distro>=0.49b0 \
    opentelemetry-exporter-otlp>=1.28.0 \
    opentelemetry-instrumentation-grpc>=0.49b0 \
    prometheus-client>=0.19.0 \
    psutil>=5.9.0 \
    scipy>=1.11.0 \
    numpy>=1.24.0 \
    pydub>=0.25.0 \
    pyalsaaudio>=0.11.0

# Runtime stage - slim image without build tools
FROM python:3.11-slim

# Install runtime dependencies for SDL audio and tempo control
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsdl2-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libasound2 \
    alsa-utils \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder (everything except pygame)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy pre-compiled pygame from pygame-builder
COPY --from=pygame-builder /pygame /usr/local/lib/python3.11/site-packages/pygame

# Copy application code
COPY proto/ /app/proto/
COPY lib/ /app/lib/
COPY services/audio/ /app/services/audio/

# Set Python path
ENV PYTHONPATH=/app
# Ensure Python uses bytecode cache for faster imports (Phase 47)
ENV PYTHONDONTWRITEBYTECODE=0

# Configure OpenTelemetry
ENV OTEL_SERVICE_NAME=audio-service
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
ENV OTEL_TRACES_EXPORTER=otlp
ENV OTEL_METRICS_EXPORTER=none
ENV OTEL_LOGS_EXPORTER=none

# Expose gRPC port
EXPOSE 50056

# Expose Prometheus metrics port (Phase 38)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:50056'); channel.channel_ready()" || exit 1

# Run the server
CMD ["python", "services/audio/server.py"]
