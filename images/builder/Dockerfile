# JoustMania Shared Builder Image
#
# Pre-installs common build dependencies and Python packages to speed up
# service builds. Services extend from this image instead of python:3.11-slim.
#
# Build:
#   docker build -t joustmania/builder:latest images/builder/
#
# Usage in service Dockerfile:
#   FROM joustmania/builder:latest AS builder
#   ...
#
# Build time savings: ~30-60 seconds per service (more on slow hardware like Pi)

FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/adangert/JoustMania"
LABEL org.opencontainers.image.description="JoustMania shared builder base image"
LABEL org.opencontainers.image.title="joustmania-builder"

# Build dependencies needed by various Python packages
# - gcc, g++: Compile C/C++ extensions (grpcio, pygame, etc.)
# - build-essential: Common build tools
# - python3-dev: Python headers for C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager (fast Python package installer)
RUN pip install --no-cache-dir uv==0.5.11

# Pre-install common Python dependencies
# This is the key optimization - these packages are cached in the image
COPY requirements-common.txt /tmp/
RUN uv pip install --system --no-cache -r /tmp/requirements-common.txt && \
    rm /tmp/requirements-common.txt

# Set working directory convention
WORKDIR /app

# Verify installation
RUN python -c "import grpc; import opentelemetry; print('Builder image ready')"
