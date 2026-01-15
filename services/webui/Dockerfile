# Multi-stage build for JoustMania Web UI Service
#
# Uses shared builder image for faster builds (Phase 69)
# Build the builder first: docker build -t joustmania/builder:latest images/builder/

# Builder image - override with --build-arg BUILDER_IMAGE=...
# Using pre-built builder image

# Build stage - uses pre-cached builder with common dependencies
FROM joustmania/builder:latest AS builder

WORKDIR /app

# Copy workspace configuration
COPY pyproject.toml /app/

# Copy proto package (shared protocol buffer contracts)
COPY proto/pyproject.toml /app/proto/
COPY proto/*.py /app/proto/
COPY proto/__pycache__/ /app/proto/__pycache__/

# Copy service dependencies
COPY services/webui/pyproject.toml /app/services/webui/

# Install service-specific dependencies (flask, wtforms, etc.)
WORKDIR /app/services/webui
RUN uv pip install --system -e .

# Runtime stage - slim image without build tools
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app/pyproject.toml /app/
COPY proto/ /app/proto/
COPY lib/ /app/lib/
# Includes templates/ and static/
COPY services/webui/ /app/services/webui/

# Set Python path
ENV PYTHONPATH=/app
# Ensure Python uses bytecode cache for faster imports (Phase 47)
ENV PYTHONDONTWRITEBYTECODE=0

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

# Expose Prometheus metrics port (Phase 38)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:80/').read()" || exit 1

# Run the server
CMD ["python", "services/webui/server.py"]
