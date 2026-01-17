# Phase 75: Publish Builder Images to GHCR

**Status**: Planned
**Priority**: High (blocks CI pipeline)

## Problem

1. CI pipeline is failing because builder images aren't available in GitHub Actions
2. Local deployment requires running `make builders` first (~15min on Pi)
3. Builder images are only available locally, not in a registry

## Proposed Solution

Publish builder images to GitHub Container Registry (ghcr.io):

- `ghcr.io/watchmejoustmyflags/joustmania/builder:latest`
- `ghcr.io/watchmejoustmyflags/joustmania/psmove-builder:latest`
- `ghcr.io/watchmejoustmyflags/joustmania/pygame-builder:latest`

### Tagging Strategy

- `latest` - Most recent build from main/master
- `<commit-sha>` - Specific commit for reproducibility
- `<branch>-latest` - Latest from specific branch (e.g., `dev-refactor-latest`)

## Implementation Steps

### 1. Update GitHub Actions Workflow

Add a job to build and push builder images:

```yaml
build-builders:
  runs-on: ubuntu-latest
  permissions:
    contents: read
    packages: write
  steps:
    - uses: actions/checkout@v4
    - name: Login to GHCR
      uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    - name: Build and push builder
      uses: docker/build-push-action@v5
      with:
        context: images/builder
        push: true
        tags: |
          ghcr.io/${{ github.repository }}/builder:latest
          ghcr.io/${{ github.repository }}/builder:${{ github.sha }}
```

### 2. Update Service Dockerfiles

Change FROM statements to use GHCR:

```dockerfile
# Before
FROM joustmania/builder:latest AS builder

# After
ARG BUILDER_IMAGE=ghcr.io/watchmejoustmyflags/joustmania/builder:latest
FROM ${BUILDER_IMAGE} AS builder
```

### 3. Update docker-compose.yml

Reference GHCR images for services, or build locally with proper tags.

### 4. Update Makefile

- Remove local builder build requirement for `make images`
- Add `make push-builders` for publishing new builder versions
- Keep `make builders` for local development

## Benefits

1. **CI works** - GitHub Actions can pull builder images from GHCR
2. **Faster Pi deployment** - Just `docker compose up`, no builder build needed
3. **Reproducible builds** - Pin to specific commit SHA if needed
4. **Simpler workflow** - Remove `make builders` prerequisite

## Notes

- GHCR is free for public repositories
- Images are automatically linked to the repository
- Need to ensure `packages: write` permission in workflow
