# CI Hadolint Tooling

Docker image for linting Dockerfiles with hadolint.

## Tools Included

- **hadolint** v2.12.0 - Dockerfile linter

## Building

```bash
docker build -t joustmania/ci-hadolint:latest tools/ci-hadolint/
```

## Usage

### Lint Single Dockerfile

```bash
docker run --rm -v "$(pwd):/workspace" -w /workspace \
    joustmania/ci-hadolint:latest \
    services/controller_manager/Dockerfile
```

### Lint All Dockerfiles

```bash
docker run --rm -v "$(pwd):/workspace" -w /workspace \
    joustmania/ci-hadolint:latest \
    /bin/sh -c 'find . -name "Dockerfile" -type f -exec hadolint {} \;'
```

## Integration

This image is used by:
- `scripts/ci/lint-dockerfiles.sh`
- GitHub Actions CI workflow

## Configuration

Hadolint configuration is in `.hadolint.yaml` at the project root.
