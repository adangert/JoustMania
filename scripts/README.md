# JoustMania Scripts

Scripts for JoustMania deployment and hardware configuration.

**Note:** Most development tasks (linting, testing, building) are handled via Makefile targets.
See `make help` for available commands.

---

## Directory Structure

```
scripts/
├── ci/          # CI validation scripts (complex multi-step)
├── docker/      # Docker helper scripts
├── hardware/    # Hardware configuration scripts (Pi-specific)
├── planning/    # Phase workflow utilities
├── setup/       # Host system setup scripts (Pi-specific)
└── testing/     # Manual testing utilities
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Run tests | `make test` |
| Lint code | `make lint` |
| Format code | `make format` |
| Build services | `make build-all-services` |
| Start Docker stack | `make docker-start` |
| Stop Docker stack | `make docker-stop` |
| All CI checks | `make ci-all` |

---

## Hardware Scripts

Located in `scripts/hardware/` - Raspberry Pi specific.

### reset_bluetooth_connections.sh

Resets Bluetooth connections and clears paired devices.

```bash
scripts/hardware/reset_bluetooth_connections.sh
```

**Use when:** PS Move controllers won't pair or have connection issues.

### update_asound.sh

Configures ALSA audio settings for Pi 4/5 audio output.

```bash
scripts/hardware/update_asound.sh
```

**Use when:** Audio output issues or after changing audio hardware.

### update_permissions.sh

Sets ownership of JoustMania directory to current user.

```bash
scripts/hardware/update_permissions.sh
```

**Use when:** Permission errors after sudo operations.

---

## Setup Scripts

Located in `scripts/setup/` - For initial Raspberry Pi setup.

### setup_host.sh

Installs system dependencies and configures the host environment.

**What it does:**
- Updates system packages
- Installs Python, Docker, build tools
- Creates Python virtual environment
- Configures audio (ALSA) and Bluetooth
- Installs supervisor configuration

```bash
scripts/setup/setup_host.sh
```

**Duration:** ~10-15 minutes

### build_psmoveapi.sh

Builds PS Move API from source.

```bash
scripts/setup/build_psmoveapi.sh
```

**Duration:** ~5-15 minutes (depending on Pi model)

### install_autostart.sh / uninstall_autostart.sh

Install/remove systemd service for autostart on boot.

```bash
sudo scripts/setup/install_autostart.sh
sudo scripts/setup/uninstall_autostart.sh
```

---

## Planning Scripts

Located in `scripts/planning/` - Phase workflow utilities.

```bash
./scripts/planning/phase-status.sh           # Show phase status
./scripts/planning/phase-start.sh <number>   # Start a planned phase
./scripts/planning/phase-complete.sh <number> # Mark phase complete
```

---

## CI Scripts

Located in `scripts/ci/` - Complex validation scripts.

Most CI operations are inlined in the Makefile. These scripts handle
operations too complex for Make syntax:

- `validate-protos.sh` - Proto generation + git diff + bytecode verification
- `validate-packages.sh` - Multi-step uv package validation

```bash
make validate-protos    # Recommended way to run
make validate-packages
```

---

## Testing Utilities

Located in `scripts/testing/` - Manual testing tools.

### color_tests/

Python utilities for manual PS Move controller color testing:

```bash
cd scripts/testing/color_tests/
python interactive_colortest.py
```

### Other utilities

- `simulate_game.py` - Game simulation for testing
- `test-mock.py` / `test-mock-with-pause.py` - Mock environment testing

**For automated tests, use:** `make test`

---

## First-Time Setup (Raspberry Pi)

```bash
# 1. Run host setup
scripts/setup/setup_host.sh

# 2. Build PS Move API
scripts/setup/build_psmoveapi.sh

# 3. (Optional) Enable autostart
sudo scripts/setup/install_autostart.sh
```

---

## Notes

- Setup and hardware scripts are Raspberry Pi / Linux specific
- Most development tasks should use Makefile targets
- Docker scripts require Docker installed and user in docker group
- All scripts should be run from repository root
