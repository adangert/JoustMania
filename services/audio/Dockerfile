# Multi-stage build for JoustMania Audio Service
#
# Phase 80: Migrated to distroless with miniaudio (replaces pygame)
# - miniaudio for sound effects (requires libmvec from glibc)
# - resampy for tempo control (replaces scipy)
# - pyalsaaudio for ALSA music output
#
# Issue #79: Fixed libmvec.so.1 missing error by copying glibc math libs
#
# Phase 75: Builder images can be overridden for CI/CD
# --build-arg BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/builder:latest

# Builder image - override with --build-arg for CI/CD
ARG BUILDER_IMAGE=joustmania/builder:latest

# =============================================================================
# Stage 0: Extract shared libraries for distroless
# =============================================================================
FROM debian:bookworm-slim AS system-libs
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /extra-libs \
    && if [ "$TARGETARCH" = "arm64" ]; then \
         LIB_DIR=/usr/lib/aarch64-linux-gnu; \
       else \
         LIB_DIR=/usr/lib/x86_64-linux-gnu; \
       fi \
    && cp $LIB_DIR/libasound.so* /extra-libs/ \
    && cp $LIB_DIR/libmvec.so* /extra-libs/ 2>/dev/null || true \
    && cp /lib/*-linux-gnu/libmvec.so* /extra-libs/ 2>/dev/null || true

# =============================================================================
# Stage 2: Build Python dependencies
# =============================================================================
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

# Install service-specific dependencies (miniaudio + resampy instead of pygame + scipy)
WORKDIR /app/services/audio
RUN uv pip install --system -e .

# =============================================================================
# Stage 3: Runtime image - distroless for minimal size
# =============================================================================
FROM gcr.io/distroless/python3-debian12

WORKDIR /app

# Copy grpc-health-probe binary
# Copy grpc-health-probe from official multi-arch image
COPY --from=ghcr.io/grpc-ecosystem/grpc-health-probe:v0.4.38 /ko-app/grpc-health-probe /bin/grpc_health_probe

# Copy system shared libraries (ALSA + glibc math/vector libs for miniaudio)
COPY --from=system-libs /extra-libs/ /usr/lib/

# Copy installed packages from builder to distroless stdlib location
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/lib/python3.11/

# Copy application code (assets mounted as volume in docker-compose)
COPY --from=builder /app/pyproject.toml /app/
COPY proto/ /app/proto/
COPY lib/ /app/lib/
COPY services/audio/*.py /app/services/audio/
COPY services/audio/tests/ /app/services/audio/tests/

# Set Python path for application code
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

# Health check using grpc-health-probe
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["/bin/grpc_health_probe", "-addr=:50056"]

# Run the server
CMD ["services/audio/server.py"]
