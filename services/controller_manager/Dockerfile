# Standalone Dockerfile for JoustMania Controller Manager Service
#
# Builds psmoveapi from source - no pre-built images needed
# Build time: ~10-15 minutes on Pi 5

# =============================================================================
# Stage 1: Build PS Move API from source
# =============================================================================
FROM python:3.11-slim AS psmove-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    pkg-config \
    libbluetooth-dev \
    libusb-dev \
    libusb-1.0-0-dev \
    libudev-dev \
    swig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Clone and build psmoveapi
RUN git clone --depth 1 https://github.com/thp/psmoveapi.git && \
    cd psmoveapi && \
    git submodule update --init --recursive

WORKDIR /build/psmoveapi/build

RUN cmake .. \
    -DPSMOVE_BUILD_CSHARP_BINDINGS=OFF \
    -DPSMOVE_BUILD_JAVA_BINDINGS=OFF \
    -DPSMOVE_BUILD_PROCESSING_BINDINGS=OFF \
    -DPSMOVE_BUILD_TRACKER=OFF \
    -DPSMOVE_BUILD_EXAMPLES=OFF \
    -DPSMOVE_BUILD_TESTS=OFF \
    -DPSMOVE_BUILD_OPENGL_EXAMPLES=OFF \
    -DPSMOVE_USE_PSEYE=OFF \
    && make -j$(nproc)

# =============================================================================
# Stage 2: Build Python dependencies
# =============================================================================
FROM python:3.11-slim AS python-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libbluetooth-dev \
    libusb-dev \
    libdbus-1-dev \
    libglib2.0-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency installation
RUN pip install uv

WORKDIR /app

# Copy workspace configuration
COPY pyproject.toml /app/

# Copy proto package
COPY proto/pyproject.toml /app/proto/
COPY proto/*.py /app/proto/

# Copy service dependencies
COPY services/controller_manager/pyproject.toml /app/services/controller_manager/

# Install dependencies
WORKDIR /app/services/controller_manager
RUN uv pip install --system -e .

# =============================================================================
# Stage 3: Runtime image
# =============================================================================
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libbluetooth3 \
    libusb-1.0-0 \
    libdbus-1-3 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from python-builder
COPY --from=python-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin

# Copy psmove Python bindings from psmove-builder
COPY --from=psmove-builder /build/psmoveapi/build/psmove.py /usr/local/lib/python3.11/site-packages/
COPY --from=psmove-builder /build/psmoveapi/build/_psmove.so /usr/local/lib/python3.11/site-packages/
COPY --from=psmove-builder /build/psmoveapi/build/libpsmoveapi.so /usr/local/lib/

# Update library cache
RUN ldconfig

# Copy application code
COPY pyproject.toml /app/
COPY proto/ /app/proto/
COPY lib/ /app/lib/
COPY services/controller_manager/ /app/services/controller_manager/

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=0

# Configure OpenTelemetry (disabled in lite mode)
ENV OTEL_SERVICE_NAME=controller-manager-service
ENV OTEL_SDK_DISABLED=true

# Expose gRPC port
EXPOSE 50052

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:50052'); channel.channel_ready()" || exit 1

# Run the server
CMD ["python", "services/controller_manager/server.py"]
