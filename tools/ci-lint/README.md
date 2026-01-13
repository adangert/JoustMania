# CI Lint Tooling

Docker image containing Python linting and type checking tools.

## Tools Included

- **ruff** 0.8.4 - Fast Python linter and formatter
- **ty** 0.0.11 - Astral type checker for Python

## Building

```bash
docker build -t joustmania/ci-lint:latest tools/ci-lint/
```

## Usage

### Linting

```bash
docker run --rm -v "$(pwd):/workspace" -w /workspace \
    joustmania/ci-lint:latest \
    ruff check . --output-format=github
```

### Formatting Check

```bash
docker run --rm -v "$(pwd):/workspace" -w /workspace \
    joustmania/ci-lint:latest \
    ruff format --check .
```

### Type Checking

```bash
docker run --rm -v "$(pwd):/workspace" -w /workspace \
    joustmania/ci-lint:latest \
    ty check services/controller_manager
```

## Integration

This image is used by:
- `scripts/ci/lint.sh`
- `scripts/ci/format-check.sh`
- `scripts/ci/typecheck.sh`
- GitHub Actions CI workflow
