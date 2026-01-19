FROM python:3.12-slim

# Install linting and type checking tools
RUN pip install --no-cache-dir \
    ruff==0.8.4 \
    ty==0.0.11

WORKDIR /workspace

# Default command shows help
CMD ["ruff", "--help"]
