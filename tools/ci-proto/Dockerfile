FROM python:3.12-slim

# Install system dependencies (including build tools for packages with C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    pkg-config \
    libasound2-dev \
    libdbus-1-dev \
    libglib2.0-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv==0.5.11

WORKDIR /workspace

# Default command
CMD ["/bin/bash"]
