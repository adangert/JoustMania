# Multi-stage build for JoustMania Web UI Service
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

# Copy proto package (shared protocol buffer contracts)
COPY proto/pyproject.toml /app/proto/
COPY proto/*.py /app/proto/

# Copy service dependencies
COPY services/webui/pyproject.toml /app/services/webui/

# Install uv package manager
RUN pip install --no-cache-dir uv==0.5.11

# Install dependencies using uv
WORKDIR /app/services/webui
RUN uv pip install --system -e .

# Runtime stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app/pyproject.toml /app/
COPY core/ /app/core/
COPY utils/ /app/utils/
COPY proto/ /app/proto/
# Includes templates/ and static/
COPY services/webui/ /app/services/webui/

# Set Python path
ENV PYTHONPATH=/app

# Configure OpenTelemetry
ENV OTEL_SERVICE_NAME=webui-service
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
ENV OTEL_TRACES_EXPORTER=otlp
ENV OTEL_METRICS_EXPORTER=none
ENV OTEL_LOGS_EXPORTER=none

# Configure service endpoints
ENV SETTINGS_SERVICE=settings:50051
ENV CONTROLLER_MANAGER_SERVICE=controller-manager:50052
ENV MENU_SERVICE=menu:50054
ENV SUPERVISOR_SERVICE=supervisor:50055

# Expose HTTP port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:80/').read()" || exit 1

# Run the server
CMD ["python", "services/webui/server.py"]
