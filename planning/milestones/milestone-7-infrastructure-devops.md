# Milestone 7: Infrastructure & DevOps

**Status:** Complete
**Phases:** 15, 55, 75

## Summary

CI/CD pipeline with GitHub Actions, Docker optimization, and container registry integration for automated builds and deployments.

## Background

JoustMania runs on Raspberry Pi (ARM64) and development machines (AMD64), requiring:
- Multi-architecture Docker builds
- Automated testing and linting
- Container registry for deployment
- Optimized build times

## Implementation

### GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
on: [push, pull_request]

jobs:
  lint:
    # Ruff linting and formatting check

  test:
    # pytest with coverage

  build:
    # Multi-arch Docker builds
    platforms: linux/amd64,linux/arm64

  push:
    # Push to GHCR on main branch
    if: github.ref == 'refs/heads/master'
```

### Docker Optimization

**Multi-stage builds** for smaller images:
```dockerfile
# Stage 1: Build dependencies
FROM python:3.11-slim as builder
RUN pip wheel -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim
COPY --from=builder /wheels /wheels
RUN pip install /wheels/*.whl
```

**Layer caching** for faster rebuilds:
- Dependencies cached separately from code
- Protobuf compilation cached
- Build args for cache busting

### Container Registry

Images published to GitHub Container Registry:
```
ghcr.io/joustmania/controller-manager:latest
ghcr.io/joustmania/game-coordinator:latest
ghcr.io/joustmania/settings:latest
ghcr.io/joustmania/menu:latest
ghcr.io/joustmania/supervisor:latest
ghcr.io/joustmania/audio:latest
ghcr.io/joustmania/webui:latest
```

### Builder Images

Pre-built base images with common dependencies:
```
ghcr.io/joustmania/builder-base:latest    # Python + common deps
ghcr.io/joustmania/builder-psmove:latest  # + psmoveapi
```

### Deployment

```bash
# Pull latest images
docker-compose pull

# Deploy with zero downtime
docker-compose up -d --remove-orphans
```

## Files Changed

- `.github/workflows/ci.yml` - CI/CD pipeline
- `Dockerfile.*` - Per-service Dockerfiles
- `docker-compose.yml` - Service orchestration
- `docker-compose.override.yml` - Development overrides

## Commits

Key commits (see `git log --grep="CI\|docker\|GHCR"` for complete list):

- `71e6c55` feat(ci): Add build sections to docker-compose and gate service push on tests
- `f73ea3e` fix(ci): Add multi-platform builds for ARM64 support
- `5d8bd63` feat(ci): Push service images to GHCR and add pull support
- `c490178` feat(ci): Publish builder images to GHCR (Phase 75)
- `a59a6d2` fix(docker): Enable controller hot-plug support

## Related Phases

- Phase 15: Docker Compose optimization
- Phase 55: GitHub Actions CI/CD
- Phase 75: GHCR builder images
