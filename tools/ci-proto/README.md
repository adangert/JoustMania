# CI Proto Tooling

Docker image for protobuf generation and Python package validation.

## Tools Included

- **Python** 3.11
- **uv** 0.5.11 - Fast Python package manager
- **git** - For detecting proto file changes

## Building

```bash
docker build -t joustmania/ci-proto:latest tools/ci-proto/
```

## Usage

### Generate Proto Files

```bash
docker run --rm -v "$(pwd):/workspace" -w /workspace \
    joustmania/ci-proto:latest \
    bash proto/generate_proto.sh
```

### Validate Python Packages

```bash
docker run --rm -v "$(pwd):/workspace" -w /workspace \
    joustmania/ci-proto:latest \
    bash -c 'uv sync --all-packages && uv pip check'
```

## Integration

This image is used by:
- `scripts/ci/validate-protos.sh`
- `scripts/ci/validate-packages.sh`
- GitHub Actions CI workflow
