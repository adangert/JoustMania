# Dockerfile Linting

This project uses [hadolint](https://github.com/hadolint/hadolint) to lint Dockerfiles for best practices and common mistakes.

## Quick Start

### Local Usage

Lint all Dockerfiles in the project:

```bash
./tools/lint-dockerfiles.sh
```

Lint specific directories:

```bash
./tools/lint-dockerfiles.sh services/game_coordinator/
```

### CI Usage

The lint script can be run in CI mode for stricter checks:

```bash
CI=true ./tools/lint-dockerfiles.sh
```

## Configuration

Hadolint rules are configured in `.hadolint.yaml`. Currently ignored rules:

- **DL3008**: Pin versions in apt-get install (we prefer latest security updates from Debian stable)
- **DL3013**: Pin versions in pip install (major packages are pinned, type stubs can float)
- **DL3049**: Missing labels (will be added in a future phase)
- **DL3059**: Multiple consecutive RUN instructions (we prefer readability)
- **SC2261**: ShellCheck false positive for multiline RUN commands

## Common Issues and Fixes

### Issue: `FROM python:3.11-slim as builder`

**Error**: Inconsistent casing - use uppercase `AS`

**Fix**:
```dockerfile
FROM python:3.11-slim AS builder
```

### Issue: Unpinned pip packages

**Error**: `DL3013: Pin versions in pip`

**Fix**:
```dockerfile
# Before
RUN pip install flask requests

# After
RUN pip install flask==3.0.0 requests==2.31.0
```

### Issue: Unpinned apt-get packages

**Status**: Currently ignored via config

If you need to pin apt-get versions:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc=4:12.2.0-3 \
    && rm -rf /var/lib/apt/lists/*
```

## Adding Linting to CI/CD

### GitHub Actions

```yaml
name: Lint Dockerfiles

on: [push, pull_request]

jobs:
  lint-dockerfiles:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Lint Dockerfiles
        run: CI=true ./tools/lint-dockerfiles.sh
```

### GitLab CI

```yaml
lint-dockerfiles:
  image: docker:latest
  services:
    - docker:dind
  script:
    - CI=true ./tools/lint-dockerfiles.sh
```

## Best Practices

1. **Always use uppercase for Dockerfile keywords**: `FROM`, `RUN`, `COPY`, `AS`, etc.
2. **Pin major dependencies**: Python packages, base images
3. **Use multi-stage builds**: Reduce final image size
4. **Minimize layers**: Combine RUN commands where appropriate
5. **Clean up apt cache**: `rm -rf /var/lib/apt/lists/*` after `apt-get`
6. **Use `.dockerignore`**: Exclude unnecessary files from build context
7. **Leverage build cache**: Order commands from least to most frequently changing

## Resources

- [Hadolint Documentation](https://github.com/hadolint/hadolint)
- [Dockerfile Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [ShellCheck Wiki](https://github.com/koalaman/shellcheck/wiki)
