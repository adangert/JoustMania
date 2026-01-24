# Docker Workflow Guide

## Overview

JoustMania uses Docker and Docker Compose for containerized deployment. All images use canonical GHCR (GitHub Container Registry) names for consistency across development, testing, and CI/CD environments.

## Quick Reference

### Start Services (Flexible)

```bash
# Start with existing images (default)
make up

# Build and start
make up BUILD=1
# or
make up-build

# Pull from GHCR and start  
make up PULL=1
# or
make up-pull
```

### Build Images

```bash
# Build all service images
make images

# Build builder images (optional, one-time, or Docker pulls automatically)
make builders
```

### Integration Testing

```bash
# Test with locally built images (default)
make test

# Test with prebuilt GHCR images
make test-with-pulled

# Test with specific image tag
IMAGE_TAG=dev-refactor make test-with-pulled
```

## Image Names

All JoustMania images use the canonical GHCR registry path:

```
ghcr.io/watchmejoustmyflags/joustmania/<service>:<tag>
```

### Builder Images

- `ghcr.io/watchmejoustmyflags/joustmania/builder:latest`
- `ghcr.io/watchmejoustmyflags/joustmania/psmove-builder:latest`

### Service Images

- `ghcr.io/watchmejoustmyflags/joustmania/settings-service:latest`
- `ghcr.io/watchmejoustmyflags/joustmania/controller-manager-service:latest`
- `ghcr.io/watchmejoustmyflags/joustmania/game-coordinator-service:latest`
- `ghcr.io/watchmejoustmyflags/joustmania/menu-service:latest`
- `ghcr.io/watchmejoustmyflags/joustmania/supervisor-service:latest`
- `ghcr.io/watchmejoustmyflags/joustmania/webui-service:latest`
- `ghcr.io/watchmejoustmyflags/joustmania/audio-service:latest`
- `ghcr.io/watchmejoustmyflags/joustmania/connect-proxy:latest`
- `ghcr.io/watchmejoustmyflags/joustmania/dashboard:latest`

## Environment Variables

### IMAGE_TAG

Controls which image tag to use. Defaults to `latest`.

```bash
# Use dev-refactor branch images
IMAGE_TAG=dev-refactor docker compose up -d

# Or with Makefile
IMAGE_TAG=dev-refactor make up-from-ghcr
```

### USE_PREBUILT_IMAGES

For integration tests only. Controls whether to build or pull images.

```bash
# Pull images for testing (faster, tests published code)
USE_PREBUILT_IMAGES=true make test

# Build images for testing (slower, tests current code)
make test  # default behavior
```

## Workflows

### Developer Quick Start

**First time setup:**

```bash
# Clone repository
git clone https://github.com/WatchMeJoustMyFlags/JoustMania.git
cd JoustMania

# Option 1: Pull prebuilt images (fast)
make up PULL=1

# Option 2: Build locally (tests your changes)
make up BUILD=1
```

**Daily development:**

```bash
# Make code changes
vim services/settings/server.py

# Rebuild and restart
make up BUILD=1

# View logs
make logs
```

### Testing Workflow

**Test current code:**

```bash
# Build and test current code
make test

# Test specific game mode
make test-ffa

# Test with Jaeger inspection
make test-mock-pause
```

**Test published images:**

```bash
# Test images from GHCR (faster, no build)
make test-with-pulled

# Test specific version
IMAGE_TAG=dev-refactor make test-with-pulled
```

### CI/CD Workflow

The CI workflow automatically:

1. Builds builder images with commit SHA tag
2. Builds each service separately for isolation
3. Tags images with both commit SHA and branch name
4. Pushes to GHCR for caching and deployment

**Environment variables used in CI:**

- `IMAGE_TAG`: Set to `${{ github.sha }}` for versioning
- `BUILDER_IMAGE`: Points to builder image with same commit SHA
- `PSMOVE_BUILDER_IMAGE`: Points to psmove-builder with same commit SHA

The CI workflow is **fully compatible** with the canonical GHCR names and requires no changes.

## Migration from Old Names

### What Changed

**Before:**
- Images used `IMAGE_PREFIX` variable with default `joustmania/`
- Different naming in dev vs CI environments
- Required environment variables to pull from GHCR
- Separate `make images` then `make up` workflow

**After:**
- All images use canonical GHCR names
- Consistent naming everywhere
- Simple `docker compose pull` works out of the box
- `make up` builds automatically with `--build` flag
- `make up-pull` for pulling from GHCR
- `IMAGE_TAG` controls version

### Breaking Changes

**None for CI/CD** - CI already used GHCR names via `IMAGE_PREFIX`

**For local development:**

Old workflow:
```bash
make builders
make images
make up
```

New workflow (flexible):
```bash
make up           # Start with existing images
make up BUILD=1   # Build and start
make up PULL=1    # Pull and start
```

### Cleanup Old Images

After switching to canonical names, you may have old images:

```bash
# List old joustmania/* images
docker images | grep "^joustmania/"

# Remove old images (optional)
docker images | grep "^joustmania/" | awk '{print $1":"$2}' | xargs docker rmi
```

Local builds will now create images with GHCR names automatically.

## GHCR Authentication

### Public Images

If images are public, no authentication is needed:

```bash
docker compose pull  # Just works
```

### Private Images

For private repositories, authenticate once:

```bash
# Create GitHub Personal Access Token with read:packages scope
# Visit: https://github.com/settings/tokens/new

# Authenticate
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

### CI/CD Authentication

GitHub Actions automatically authenticates to GHCR using `GITHUB_TOKEN`. No additional setup needed.

## Advanced Usage

### Building Specific Services

```bash
# Build individual service
make image-settings
make image-controller-manager

# Or use docker compose
docker compose build settings
docker compose build controller-manager
```

### Custom Tags

```bash
# Build with custom tag
docker compose build
docker compose push  # if you have push access

# Tag for release
docker tag ghcr.io/watchmejoustmyflags/joustmania/settings-service:latest \
           ghcr.io/watchmejoustmyflags/joustmania/settings-service:v1.0.0
```

### Multi-Platform Builds

```bash
# Build for multiple architectures (requires buildx)
docker buildx build --platform linux/amd64,linux/arm64 \
  -t ghcr.io/watchmejoustmyflags/joustmania/settings-service:latest \
  -f services/settings/Dockerfile .
```

## Troubleshooting

### "Image not found" when pulling

**Problem:** `docker compose pull` fails with "not found"

**Solutions:**
1. Check if images exist in GHCR: https://github.com/orgs/WatchMeJoustMyFlags/packages
2. Authenticate if images are private (see GHCR Authentication above)
3. Build locally instead: `make images && make up`

### Builder images not found during build

**Problem:** Service build fails with "builder image not found"

**Solution:** Docker should automatically pull builder images. If it fails:

```bash
# Build builder images locally
make builders

# Or pull specific version manually
docker pull ghcr.io/watchmejoustmyflags/joustmania/builder:latest
docker pull ghcr.io/watchmejoustmyflags/joustmania/psmove-builder:latest
```

### Integration tests fail to start

**Problem:** Tests fail with "cannot build image"

**Solutions:**
1. Ensure Docker daemon is running
2. Build images first: `make images`
3. Or use prebuilt: `USE_PREBUILT_IMAGES=true make test`

### Old images taking up space

**Problem:** Disk space consumed by old `joustmania/*` images

**Solution:** Clean up old images:

```bash
# List all JoustMania images
docker images | grep joustmania

# Remove old local images
docker images | grep "^joustmania/" | awk '{print $1":"$2}' | xargs docker rmi

# Prune unused images
docker image prune
```

## Summary

The canonical GHCR naming and flexible `make up` command simplify everything:

✅ **One command, multiple modes** - `make up` with BUILD=1 or PULL=1  
✅ **Quick start:** `make up PULL=1` pulls and starts from GHCR  
✅ **Development:** `make up BUILD=1` builds and starts  
✅ **CI/CD:** No changes needed, already using GHCR  
✅ **Consistency:** Same image names everywhere  

Most common workflows:
- **First time:** `make up PULL=1` (fast start with published images)
- **Development:** `make up BUILD=1` (build your changes)
- **Restart:** `make up` (use existing images)

For most users, the change is transparent - everything just works with simpler, more flexible commands.
