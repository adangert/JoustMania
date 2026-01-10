# JoustMania Scripts

Organized scripts for JoustMania cloud-native deployment.

---

## Directory Structure

```
scripts/
├── hardware/    # Hardware configuration scripts
├── testing/     # Test execution scripts
├── setup/       # Modular setup scripts
└── docker/      # Docker helper scripts
```

---

## Hardware Scripts

Located in `scripts/hardware/`

### reset_bluetooth_connections.sh

Resets Bluetooth connections and clears paired devices.

**Usage:**
```bash
scripts/hardware/reset_bluetooth_connections.sh
```

**Use when:** PS Move controllers won't pair or have connection issues.

---

### update_asound.sh

Configures ALSA audio settings for optimal PS Move controller performance.

**Usage:**
```bash
scripts/hardware/update_asound.sh
```

**Use when:** Audio output issues or after changing audio hardware.

---

### update_permissions.sh

Sets up device permissions for USB and Bluetooth access. Updates ownership of JoustMania directory to current user.

**Usage:**
```bash
scripts/hardware/update_permissions.sh
```

**Use when:** Permission errors accessing USB/Bluetooth devices, or after sudo operations.

---

## Testing Scripts

Located in `scripts/testing/`

### run_tests.sh

Executes the full test suite (unit + integration tests) using pytest.

**Usage:**
```bash
scripts/testing/run_tests.sh
```

**Requirements:**
- Python virtual environment activated
- Test dependencies installed: `pip install -r testing/requirements.txt`

---

### controller_util_test.sh

Tests controller utility functions.

**Usage:**
```bash
scripts/testing/controller_util_test.sh
```

---

### color_tests/

Directory containing color rendering tests for PS Move controllers:
- `color_combo_test.py` - Test color combinations
- `interactive_colortest.py` - Interactive color testing
- `quad_combo_test.py` - Quad color combinations
- `static_colortest.py` - Static color display

**Usage:**
```bash
cd scripts/testing/color_tests/
python interactive_colortest.py
```

---

## Setup Scripts

Located in `scripts/setup/`

### setup_host.sh

Installs system dependencies and configures the host environment.

**What it does:**
- Updates system packages (apt update/upgrade)
- Installs Python, build tools, and libraries
- Installs Docker
- Creates Python virtual environment
- Installs uv package manager
- Syncs Python dependencies
- Configures audio (ALSA)
- Configures Bluetooth (disables internal BT, sets ClassicBondedOnly=false)
- Installs supervisor configuration
- Fixes file permissions

**Usage:**
```bash
scripts/setup/setup_host.sh
```

**Requirements:**
- Raspberry Pi OS (or Debian-based Linux)
- Internet connection
- sudo privileges

**Duration:** ~10-15 minutes

---

### build_psmoveapi.sh

Builds and installs PS Move API from source.

**What it does:**
- Installs PS Move API build dependencies
- Clones PS Move API repository (specific tested commit)
- Builds with cmake (no tracker, no examples, Python bindings only)

**Usage:**
```bash
scripts/setup/build_psmoveapi.sh
```

**Requirements:**
- Build dependencies installed (done by setup_host.sh)
- 2-4 GB free disk space
- Internet connection

**Duration:** ~5-15 minutes (depending on Pi model)

---

## Docker Scripts

Located in `scripts/docker/`

Convenient helper scripts for Docker operations.

### build.sh

Builds all Docker images for the microservices stack in parallel.

**Usage:**
```bash
scripts/docker/build.sh
```

**Equivalent to:** `docker-compose build --parallel`

---

### start.sh

Starts the full Docker Compose stack with helpful output.

**Usage:**
```bash
scripts/docker/start.sh
```

**Output includes:**
- Jaeger UI URL (http://localhost:16686)
- Web UI URL (http://localhost:80)
- Prometheus metrics URL (http://localhost:8888/metrics)
- Service status

**Equivalent to:** `docker-compose up -d && docker-compose ps`

---

### stop.sh

Stops and cleans up the Docker stack.

**Usage:**
```bash
scripts/docker/stop.sh
```

**Equivalent to:** `docker-compose down`

---

### logs.sh

Follows logs for all services or a specific service.

**Usage:**
```bash
# Follow all services
scripts/docker/logs.sh

# Follow specific service
scripts/docker/logs.sh audio
scripts/docker/logs.sh controller-manager
scripts/docker/logs.sh game-coordinator
```

**Available services:**
- `settings`
- `controller-manager`
- `game-coordinator`
- `menu`
- `supervisor`
- `webui`
- `audio`
- `redis`
- `jaeger`
- `otel-collector`

**Exit:** Press Ctrl+C to stop following logs

---

## Legacy Scripts

Archived legacy scripts can be found in `legacy/scripts/`.

These are preserved for reference but are no longer used in the cloud-native architecture:

- `enable_ap.sh` / `disable_ap.sh` - WiFi access point (not needed)
- `joust.sh` / `webui.sh` / `kill_processes.sh` - Replaced by Docker Compose
- `disable_internal_bluetooth.sh` - Functionality moved to setup_host.sh

---

## Quick Start

### First-Time Setup

```bash
# Run full setup (interactive, requires reboot)
./setup.sh

# Or run individual steps:
scripts/setup/setup_host.sh
scripts/setup/build_psmoveapi.sh
```

### Daily Development

```bash
# Build images
scripts/docker/build.sh

# Start stack
scripts/docker/start.sh

# View logs
scripts/docker/logs.sh

# Stop stack
scripts/docker/stop.sh
```

### Testing

```bash
# Run test suite
scripts/testing/run_tests.sh

# Run color tests
cd scripts/testing/color_tests/
python interactive_colortest.py
```

### Hardware Maintenance

```bash
# Reset Bluetooth if controllers won't pair
scripts/hardware/reset_bluetooth_connections.sh

# Fix permissions if needed
scripts/hardware/update_permissions.sh
```

---

## Notes

- All scripts are designed to be run from the repository root directory
- Setup scripts require sudo privileges
- Docker scripts require Docker to be installed and user in docker group
- Testing scripts require Python virtual environment with dependencies installed
- Hardware scripts are Raspberry Pi / Linux specific

---

## Getting Help

For issues with specific scripts:
- Check the script's error output
- Review the log files (setup_host.log, setup_psmoveapi.log, etc.)
- Ensure prerequisites are met
- Check file permissions (`chmod +x` if needed)

For general JoustMania help, see the main README.md.
