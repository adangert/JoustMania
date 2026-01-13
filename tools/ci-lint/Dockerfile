FROM python:3.11-slim

# Install linting and type checking tools
RUN pip install --no-cache-dir \
    ruff==0.8.4 \
    mypy==1.13.0 \
    types-PyYAML==6.0.12.20240917 \
    types-requests==2.32.0.20241016

WORKDIR /workspace

# Default command shows help
CMD ["ruff", "--help"]
