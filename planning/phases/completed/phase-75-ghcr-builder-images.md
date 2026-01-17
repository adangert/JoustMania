# Phase 75: Publish Builder Images to GHCR

**Status**: Completed
**Priority**: High (blocks CI pipeline)

## Problem

1. CI pipeline is failing because builder images aren't available in GitHub Actions
2. Local deployment requires running `make builders` first (~15min on Pi)
3. Builder images are only available locally, not in a registry

## Solution Implemented

### 1. Updated CI Workflow (`.github/workflows/ci.yml`)

Added `build-builders` job that:
- Builds all three builder images in parallel (matrix strategy)
- Pushes to GHCR with multiple tags:
  - `<commit-sha>` - for reproducibility
  - `<branch>` - for branch-specific builds
  - `latest` - for default branch only
- Uses GitHub Actions cache for faster rebuilds

Service build jobs now:
- Depend on `build-builders` job
- Pass builder image locations via build args
- Pull from GHCR instead of requiring local builds

### 2. Updated Service Dockerfiles

All service Dockerfiles now accept builder image ARGs:

```dockerfile
# Example: services/settings/Dockerfile
ARG BUILDER_IMAGE=joustmania/builder:latest
FROM ${BUILDER_IMAGE} AS builder
```

Services using specialized builders:
- `controller_manager`: BUILDER_IMAGE + PSMOVE_BUILDER_IMAGE
- `audio`: BUILDER_IMAGE + PYGAME_BUILDER_IMAGE
- Others: BUILDER_IMAGE only

### 3. Added Makefile Targets

```makefile
# Build single service with optional builder overrides
make build-service SERVICE=settings

# Build with GHCR images (CI mode)
make build-service SERVICE=settings \
  BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/builder:abc123

# Build all services
make build-all-services
```

## GHCR Image URLs

- `ghcr.io/watchmejoustmyflags/joustmania/builder:<tag>`
- `ghcr.io/watchmejoustmyflags/joustmania/psmove-builder:<tag>`
- `ghcr.io/watchmejoustmyflags/joustmania/pygame-builder:<tag>`

## Benefits Achieved

1. **CI now works** - GitHub Actions pulls builder images from GHCR
2. **Local dev unchanged** - Default ARGs still use local `joustmania/*` images
3. **Reproducible builds** - Pin to specific commit SHA if needed
4. **Faster CI** - GitHub Actions cache speeds up builder rebuilds

## Files Changed

- `.github/workflows/ci.yml` - Added build-builders job, updated docker-build
- `Makefile` - Added build-service, build-all-services targets
- `services/*/Dockerfile` - Added ARG for builder images (all 7 services)
