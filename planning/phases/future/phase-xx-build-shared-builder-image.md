# Phase 69: Shared Builder Base Image

> **Status**: Implemented
>
> **Prerequisites**: None (can be implemented anytime)
>
> **Impact**: Build time optimization, CI/CD improvement

## Overview

Extract common build dependencies into shared base images to speed up Docker builds across all JoustMania microservices. Includes both a general builder image and a specialized psmoveapi builder image.

## Motivation

Currently, each service Dockerfile repeats the same builder setup:

```dockerfile
# Repeated in every service Dockerfile
FROM python:3.11-slim AS builder
RUN apt-get update && apt-get install -y gcc ...
RUN pip install uv==0.5.11
```

This wastes:
- ~30 seconds per service for apt-get + pip
- CI/CD minutes on every build
- Developer time waiting for builds

With 7+ services, this adds up to **3-5 minutes of redundant work** per full build.

## Current State Analysis

### Common Dependencies Across Services

| Dependency | settings | controller-manager | game-coordinator | menu | webui | audio | supervisor |
|------------|----------|-------------------|------------------|------|-------|-------|------------|
| python:3.11-slim | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| gcc | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| uv | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| grpcio | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| grpcio-tools | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| opentelemetry-* | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

### Special Cases

- **controller-manager**: Also needs psmoveapi build stage (keep separate)
- **audio**: Needs SDL/pygame runtime libraries
- **webui**: Needs additional web dependencies

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Image Hierarchy                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────┐                                    │
│  │ python:3.11-slim    │  ← Upstream base                   │
│  └──────────┬──────────┘                                    │
│             │                                                │
│  ┌──────────▼──────────┐                                    │
│  │ joustmania/builder  │  ← Shared builder (this phase)     │
│  │ - gcc, build-essential                                    │
│  │ - uv package manager                                      │
│  │ - grpcio, grpcio-tools                                   │
│  │ - opentelemetry-*                                         │
│  │ - pytest, common dev tools                               │
│  └──────────┬──────────┘                                    │
│             │                                                │
│     ┌───────┼───────┬───────┬───────┐                       │
│     │       │       │       │       │                       │
│     ▼       ▼       ▼       ▼       ▼                       │
│ settings  menu   game-   webui  supervisor                  │
│                  coord                                       │
│                                                              │
│  ┌─────────────────────┐                                    │
│  │ joustmania/psmove-  │  ← Separate psmoveapi builder      │
│  │ builder             │    (already exists)                │
│  └──────────┬──────────┘                                    │
│             │                                                │
│             ▼                                                │
│     controller-manager                                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Implementation

### Directory Structure

```
images/
├── builder/
│   ├── Dockerfile          # Shared builder for Python services
│   └── requirements-common.txt
└── psmove-builder/
    └── Dockerfile          # PS Move API builder (10-15min compile)
```

### Shared Builder Dockerfile

```dockerfile
# images/builder/Dockerfile
#
# Shared builder base image for JoustMania services
# Build: docker build -t joustmania/builder:latest images/builder/
#

FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/adangert/JoustMania"
LABEL org.opencontainers.image.description="JoustMania shared builder image"

# Build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Package manager
RUN pip install --no-cache-dir uv==0.5.11

# Pre-install common Python dependencies
COPY requirements-common.txt /tmp/
RUN uv pip install --system --no-cache -r /tmp/requirements-common.txt

# Working directory convention
WORKDIR /app
```

### Common Requirements

```txt
# images/builder/requirements-common.txt
#
# Dependencies shared across most/all services
#

# gRPC
grpcio>=1.60.0
grpcio-tools>=1.60.0
grpcio-health-checking>=1.60.0

# OpenTelemetry
opentelemetry-api>=1.22.0
opentelemetry-sdk>=1.22.0
opentelemetry-exporter-otlp>=1.22.0
opentelemetry-instrumentation-grpc>=0.43b0

# Common utilities
pyyaml>=6.0
redis>=5.0.0
```

### Updated Service Dockerfile

```dockerfile
# services/settings/Dockerfile (simplified)
#
# Uses shared builder base image
#

# Build stage - uses pre-cached builder
FROM ghcr.io/adangert/joustmania-builder:latest AS builder

WORKDIR /app

# Copy workspace config
COPY pyproject.toml /app/
COPY proto/ /app/proto/
COPY services/settings/pyproject.toml /app/services/settings/

# Install service-specific dependencies only
WORKDIR /app/services/settings
RUN uv pip install --system -e .

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Copy from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY proto/ /app/proto/
COPY lib/ /app/lib/
COPY services/settings/ /app/services/settings/

# ... rest of Dockerfile
```

### CI/CD Integration

```yaml
# .github/workflows/build-builder.yml
name: Build Shared Builder Image

on:
  push:
    paths:
      - 'images/builder/**'
      - '.github/workflows/build-builder.yml'
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push builder image
        uses: docker/build-push-action@v5
        with:
          context: images/builder
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/joustmania-builder:latest
            ghcr.io/${{ github.repository_owner }}/joustmania-builder:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### Service Build Workflow Update

```yaml
# .github/workflows/build-services.yml
jobs:
  build-service:
    strategy:
      matrix:
        service: [settings, menu, game-coordinator, webui, supervisor, audio]

    steps:
      - name: Build service
        uses: docker/build-push-action@v5
        with:
          context: .
          file: services/${{ matrix.service }}/Dockerfile
          build-args: |
            BUILDER_IMAGE=ghcr.io/${{ github.repository_owner }}/joustmania-builder:latest
          # ... rest of config
```

## Build Time Comparison

### Before (Estimated)

| Step | Time | Repeated |
|------|------|----------|
| apt-get update | 10s | × 7 services |
| apt-get install gcc | 15s | × 7 services |
| pip install uv | 5s | × 7 services |
| uv install common deps | 20s | × 7 services |
| **Total redundant** | **~350s** | |

### After (Estimated)

| Step | Time | Frequency |
|------|------|-----------|
| Pull builder image | 5s | × 7 services (cached) |
| Service-specific deps | 5-10s | × 7 services |
| **Total** | **~70s** | |

**Savings: ~280 seconds (~5 minutes) per full build**

### Controller-Manager (with psmove-builder)

| Step | Before | After |
|------|--------|-------|
| psmoveapi compile | 10-15 min | 0 (pre-built) |
| Python deps | 30s | 5s |
| **Total** | **~15 min** | **~1-2 min** |

**Savings: ~13 minutes per controller-manager build**

## Tasks

- [x] Create `images/builder/` directory
- [x] Create shared builder Dockerfile
- [x] Extract common requirements to `requirements-common.txt`
- [x] Update settings Dockerfile to use builder
- [x] Update menu Dockerfile to use builder
- [x] Update game-coordinator Dockerfile to use builder
- [x] Update webui Dockerfile to use builder
- [x] Update supervisor Dockerfile to use builder
- [x] Update audio Dockerfile to use builder
- [x] Create `images/psmove-builder/` directory
- [x] Create psmove-builder Dockerfile (extracts psmoveapi build)
- [x] Update controller-manager to use both builder images
- [ ] Build and push builder images to registry
- [ ] Create GitHub Actions workflow for builder images
- [ ] Update service build workflows
- [ ] Document builder image maintenance
- [ ] Test full build pipeline

## Maintenance

### When to Update Builder Image

- Python version upgrade
- uv version upgrade
- New common dependency added
- Security patches for base image

### Versioning Strategy

```
ghcr.io/adangert/joustmania-builder:latest     ← Development
ghcr.io/adangert/joustmania-builder:v1.0.0     ← Pinned releases
ghcr.io/adangert/joustmania-builder:<sha>      ← CI traceability
```

## Risks

| Risk | Mitigation |
|------|------------|
| Builder image becomes stale | Automated weekly rebuilds |
| Cache invalidation issues | Pin versions, use SHA tags |
| Registry availability | Fallback to inline build |
| Version drift between services | Document builder version in service Dockerfile |

## Future Enhancements

- **Runtime base image**: Similar pattern for runtime (slim image with common libs)
- **Dev container**: Use builder as VS Code dev container base
- **Multi-arch**: Build for amd64 + arm64 (Raspberry Pi)

## References

- [Docker multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Docker build cache](https://docs.docker.com/build/cache/)
