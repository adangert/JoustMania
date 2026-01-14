# Multi-stage build for JoustMania Controller Manager Service
#
# Includes PS Move API built from source for real controller support.
# Build time: ~10-15 minutes on first build (psmoveapi compilation)

# =============================================================================
# Stage 1: Build PS Move API from source
# =============================================================================
FROM python:3.11-slim AS psmove-builder

# Install psmoveapi build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    pkg-config \
    libudev-dev \
    libbluetooth-dev \
    libusb-dev \
    libusb-1.0-0-dev \
    libdbus-1-dev \
    swig \
    && rm -rf /var/lib/apt/lists/*

# Clone and build psmoveapi (tested commit)
WORKDIR /build
RUN git clone --recursive https://github.com/thp/psmoveapi.git && \
    cd psmoveapi && \
    git checkout 8a1f8d035e9c82c5c134d848d9fbb4dd37a34b58

WORKDIR /build/psmoveapi/build
RUN cmake .. \
    -DPSMOVE_BUILD_CSHARP_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_EXAMPLES:BOOL=OFF \
    -DPSMOVE_BUILD_JAVA_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_OPENGL_EXAMPLES:BOOL=OFF \
    -DPSMOVE_BUILD_PROCESSING_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_TESTS:BOOL=OFF \
    -DPSMOVE_BUILD_TRACKER:BOOL=OFF \
    -DPSMOVE_USE_PSEYE:BOOL=OFF && \
    make -j$(nproc)

# =============================================================================
# Stage 2: Build Python dependencies
# =============================================================================
FROM python:3.11-slim AS python-builder

# Install build dependencies (including bluetooth libraries for PS Move)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    pkg-config \
    libbluetooth-dev \
    libusb-dev \
    libdbus-1-dev \
    libglib2.0-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy root pyproject.toml for workspace configuration
COPY pyproject.toml /app/

# Copy proto package (shared protocol buffer contracts)
COPY proto/pyproject.toml /app/proto/
COPY proto/*.py /app/proto/
COPY proto/__pycache__ /app/proto/__pycache__/

# Copy service dependencies
COPY services/controller_manager/pyproject.toml /app/services/controller_manager/

# Install uv package manager
RUN pip install --no-cache-dir uv==0.5.11

# Install dependencies using uv
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
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy installed packages from python-builder
COPY --from=python-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin

# Copy psmove Python bindings from psmove-builder
COPY --from=psmove-builder /build/psmoveapi/build/psmove.py /usr/local/lib/python3.11/site-packages/
COPY --from=psmove-builder /build/psmoveapi/build/_psmove.so /usr/local/lib/python3.11/site-packages/

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
