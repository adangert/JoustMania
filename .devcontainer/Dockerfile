FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    make \
    curl \
    ca-certificates \
    sudo \
    # Bluetooth development (for controller_manager work)
    libbluetooth-dev \
    libusb-dev \
    libdbus-1-dev \
    libglib2.0-dev \
    pkg-config \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv==0.5.11

# Install development tools
RUN pip install --no-cache-dir \
    ruff==0.8.4 \
    ty==0.0.11 \
    ipython \
    ipdb

# Create non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Install Docker CLI (for Docker-in-Docker)
RUN curl -fsSL https://get.docker.com -o get-docker.sh \
    && sh get-docker.sh \
    && rm get-docker.sh \
    && usermod -aG docker $USERNAME

USER $USERNAME

WORKDIR /workspace

CMD ["/bin/bash"]
