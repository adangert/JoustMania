FROM python:3.12-slim

# Install system dependencies (including build tools for packages with C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libasound2-dev \
    libdbus-1-dev \
    libglib2.0-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv==0.5.11

WORKDIR /workspace

# Default command
CMD ["/bin/bash"]
