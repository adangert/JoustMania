# Multi-stage build for JoustMania Settings Service
# Build stage
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy root pyproject.toml for workspace configuration
COPY pyproject.toml /app/

# Copy service dependencies
COPY services/settings/pyproject.toml /app/services/settings/

# Install uv package manager
RUN pip install --no-cache-dir uv

# Install dependencies using uv
WORKDIR /app/services/settings
RUN uv pip install --system -e .

# Runtime stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app/pyproject.toml /app/
COPY core/ /app/core/
COPY utils/ /app/utils/
COPY services/settings/ /app/services/settings/

# Set Python path
ENV PYTHONPATH=/app

# Configure OpenTelemetry
ENV OTEL_SERVICE_NAME=settings-service
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
ENV OTEL_TRACES_EXPORTER=otlp
ENV OTEL_METRICS_EXPORTER=none
ENV OTEL_LOGS_EXPORTER=none

# Expose gRPC port
EXPOSE 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:50051'); channel.channel_ready()" || exit 1

# Run the server
CMD ["python", "services/settings/server.py"]
