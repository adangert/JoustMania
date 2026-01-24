# Docker Workflow Guide

## Overview

JoustMania uses Docker and Docker Compose for containerized deployment. All images use canonical GHCR (GitHub Container Registry) names for consistency.

## Quick Reference

### Docker Compose Commands (Direct)

```bash
# Start services
docker compose up -d

# Build and start
docker compose up -d --build

# Pull from GHCR and start
docker compose pull
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f
docker compose logs -f settings  # specific service

# List services
docker compose ps
```

### Make Targets (Convenience)

```bash
# Start in mock mode (no hardware)
make up-mock

# Build base images (one-time)
make builders

# Run tests
make test
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
IMAGE_TAG=dev-refactor docker compose pull
IMAGE_TAG=dev-refactor docker compose up -d
```

### BUILDER_IMAGE / PSMOVE_BUILDER_IMAGE

Override builder images (used by CI):

```bash
BUILDER_IMAGE=ghcr.io/.../builder:sha123 docker compose build
```

## Workflows

### Developer Quick Start

**First time setup:**

```bash
# Clone repository
git clone https://github.com/WatchMeJoustMyFlags/JoustMania.git
cd JoustMania

# Option 1: Pull prebuilt images (fast)
docker compose pull
docker compose up -d

# Option 2: Build locally (tests your changes)
docker compose up -d --build
```

**Daily development:**

```bash
# Make code changes
vim services/settings/server.py

# Rebuild and restart
docker compose up -d --build

# View logs
docker compose logs -f settings
```

### Testing Workflow

```bash
# Run all integration tests
make test

# Run unit tests (fast)
make test-unit

# Run specific test
make test TEST=test_ffa

# Debug with Jaeger (pauses before teardown)
make test-debug

# Test with prebuilt GHCR images
make test-pulled
IMAGE_TAG=dev-refactor make test-pulled
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

## Troubleshooting

### "Image not found" when pulling

**Problem:** `docker compose pull` fails with "not found"

**Solutions:**
1. Check if images exist in GHCR: https://github.com/orgs/WatchMeJoustMyFlags/packages
2. Authenticate if images are private (see above)
3. Build locally instead: `docker compose up -d --build`

### Builder images not found during build

**Problem:** Service build fails with "builder image not found"

**Solution:** Build or pull builder images:

```bash
# Build locally
make builders

# Or pull from GHCR
docker pull ghcr.io/watchmejoustmyflags/joustmania/builder:latest
docker pull ghcr.io/watchmejoustmyflags/joustmania/psmove-builder:latest
```

### .venv permission issues

**Problem:** Tests fail with permission denied on .venv-test

**Solution:** The Makefile handles this automatically. If it persists:

```bash
sudo rm -rf .venv-test
make test
```

### Old images taking up space

```bash
# Prune unused images
docker image prune

# Remove all JoustMania images
docker images | grep joustmania | awk '{print $1":"$2}' | xargs docker rmi
```

## Summary

Docker Compose is the primary interface for running JoustMania:

| Task | Command |
|------|---------|
| Start services | `docker compose up -d` |
| Build and start | `docker compose up -d --build` |
| Pull from GHCR | `docker compose pull` |
| Stop services | `docker compose down` |
| View logs | `docker compose logs -f` |
| Mock mode | `make up-mock` |
| Run tests | `make test` |

The Makefile provides shortcuts for common development tasks (testing, linting, mock mode) but most Docker operations should use docker compose directly.
