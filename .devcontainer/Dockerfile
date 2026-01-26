FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gcc \
    git \
    # Bluetooth development (for controller_manager work)
    libbluetooth-dev \
    libdbus-1-dev \
    libglib2.0-dev \
    libusb-dev \
    make \
    pkg-config \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Install uv and development tools
RUN pip install --no-cache-dir \
    ruff==0.14.13 \
    ty==0.0.11 \
    uv==0.5.11

# Create non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid "$USER_GID" "$USERNAME" \
    && useradd --uid "$USER_UID" --gid "$USER_GID" -m "$USERNAME" \
    && echo "$USERNAME ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/"$USERNAME" \
    && chmod 0440 /etc/sudoers.d/"$USERNAME"

# Install Docker CLI (for Docker-in-Docker)
RUN curl -fsSL https://get.docker.com -o get-docker.sh \
    && sh get-docker.sh \
    && rm get-docker.sh \
    && usermod -aG docker "$USERNAME"

USER $USERNAME

WORKDIR /workspace

CMD ["/bin/bash"]
