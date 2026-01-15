# PS Move Pairing Daemon

Automatic PS Move controller pairing for JoustMania on Raspberry Pi.

## Overview

This daemon runs on the host system and automatically pairs PS Move controllers when connected via USB. It handles:

- Detecting USB-connected controllers
- Writing the host Bluetooth MAC to the controller
- Trusting the device in BlueZ
- Restarting Bluetooth to recognize new devices

## Installation

```bash
sudo ./install.sh
```

This copies the daemon script to `/usr/local/bin/` and installs/enables the systemd service.

## Usage

### Pairing a Controller

1. Plug in PS Move via USB
2. Wait for LED feedback:
   - **Yellow** = Pairing in progress
   - **White flash (3x)** = Success
   - **Red flash (3x)** = Error
3. Unplug USB cable
4. Press PS button to connect via Bluetooth

### Service Commands

```bash
# Check status
systemctl status psmove-pairing

# View logs (live)
journalctl -u psmove-pairing -f

# View recent logs
journalctl -u psmove-pairing -n 50

# Restart daemon
sudo systemctl restart psmove-pairing

# Stop daemon
sudo systemctl stop psmove-pairing

# Start daemon
sudo systemctl start psmove-pairing
```

## Uninstallation

```bash
sudo ./uninstall.sh
```

## Configuration

The daemon polls every 30 seconds by default. To change this, edit the service file:

```bash
sudo systemctl edit psmove-pairing
```

Add:
```ini
[Service]
Environment=POLL_INTERVAL=15
```

## Files

| File | Purpose |
|------|---------|
| `psmove-pairing-daemon.sh` | Main daemon script |
| `psmove-pairing.service` | systemd unit file |
| `install.sh` | Installation script |
| `uninstall.sh` | Removal script |

## Requirements

- psmoveapi (`psmove` CLI)
- BlueZ (`bluetoothctl`)
- systemd

## Troubleshooting

**Daemon not detecting controller:**
```bash
# Check USB device
lsusb | grep Sony

# Check daemon logs
journalctl -u psmove-pairing -f
```

**Pairing succeeds but Bluetooth won't connect:**
```bash
# Check ClassicBondedOnly setting
grep ClassicBondedOnly /etc/bluetooth/input.conf
# Must be: ClassicBondedOnly=false

# Restart Bluetooth
sudo systemctl restart bluetooth
```

See `docs/hardware-setup-guide.md` for detailed troubleshooting.
