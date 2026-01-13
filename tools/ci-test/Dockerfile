# Test Runner Image for JoustMania
# Provides consistent test environment with uv and pytest
FROM python:3.12-slim

# Install system dependencies for testcontainers and Docker SDK
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI for testcontainers
RUN curl -fsSL https://get.docker.com | sh

# Install uv for fast Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Verify uv installation
RUN uv --version

WORKDIR /workspace

# Default command shows help
CMD ["uv", "--help"]
