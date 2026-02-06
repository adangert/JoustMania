# PS Move Pairing Daemon

Automatic PS Move controller pairing and Bluetooth monitoring for JoustMania on Raspberry Pi.

## Overview

This daemon runs on the host system and provides:

- **USB Pairing**: Automatically pairs PS Move controllers when connected via USB
- **Bluetooth Monitoring**: Tracks connected controllers, signal strength (RSSI), and connection status
- **Observability**: Prometheus metrics and OpenTelemetry tracing

## Installation

```bash
sudo ./install.sh
```

This installs Python dependencies, copies the daemon to `/usr/local/bin/`, and enables the systemd service.

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
```

## Configuration

Environment variables (set via systemd override):

| Variable | Default | Description |
|----------|---------|-------------|
| `POLL_INTERVAL` | `10` | Seconds between USB polling |
| `BT_MONITOR_INTERVAL` | `5` | Seconds between Bluetooth monitoring |
| `DEBUG` | `0` | Set to `1` for verbose logging |
| `METRICS_PORT` | `8002` | Prometheus metrics port |
| `PSMOVE_PATH` | auto-detect | Path to psmove binary |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP collector endpoint |

To override:
```bash
sudo systemctl edit psmove-pairing
```

Add:
```ini
[Service]
Environment=POLL_INTERVAL=15
Environment=BT_MONITOR_INTERVAL=3
Environment=DEBUG=1
```

## Prometheus Metrics

Access metrics at `http://localhost:8002/metrics`

### Pairing Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `psmove_pairing_attempts_total` | Counter | Total pairing attempts |
| `psmove_pairing_success_total` | Counter | Successful pairings |
| `psmove_pairing_failed_total` | Counter | Failed pairings |
| `psmove_pairing_usb_controllers` | Gauge | Currently connected USB controllers |
| `psmove_pairing_duration_seconds` | Histogram | Time to complete pairing |

### Bluetooth Monitoring Metrics (Host HCI Layer)

These metrics measure the raw Bluetooth HCI layer on the host, distinct from
`controller_*` metrics in controller-manager which measure the application layer.

| Metric | Labels | Description |
|--------|--------|-------------|
| `bluetooth_device_rssi_dbm` | `serial`, `hci_adapter` | Signal strength in dBm |
| `bluetooth_device_connected` | `serial`, `hci_adapter` | HCI connection status (1=connected) |
| `bluetooth_device_last_seen_timestamp` | `serial`, `hci_adapter` | Unix timestamp when last seen |
| `bluetooth_adapter_connections` | `hci_adapter` | Controllers per adapter |

### Example Grafana Queries

```promql
# RSSI over time per controller (host Bluetooth layer)
bluetooth_device_rssi_dbm

# Controllers per adapter
bluetooth_adapter_connections

# Time since last seen at HCI layer (staleness detection)
time() - bluetooth_device_last_seen_timestamp

# Compare HCI vs application layer connection status
# (useful for debugging connection issues)
bluetooth_device_connected == 1 and controller_connected == 0
```

## Files

| File | Purpose |
|------|---------|
| `psmove_pairing_daemon.py` | Main entry point |
| `psmove_pairing/` | Package directory |
| `psmove_pairing/config.py` | Configuration and constants |
| `psmove_pairing/metrics.py` | Prometheus metrics definitions |
| `psmove_pairing/telemetry.py` | OpenTelemetry initialization |
| `psmove_pairing/utils.py` | Utility functions |
| `psmove_pairing/usb_pairing.py` | USB pairing logic |
| `psmove_pairing/bluetooth_monitor.py` | Bluetooth monitoring |
| `psmove_pairing/adapter_manager.py` | Bluetooth adapter load balancing |
| `psmove_pairing/daemon.py` | Main daemon class |
| `psmove-pairing.service` | systemd unit file |
| `install.sh` | Installation script |
| `uninstall.sh` | Removal script |
| `pyproject.toml` | Python dependencies |
| `tests/` | Unit tests |

## Requirements

- Python 3.11+
- psmoveapi (`psmove` CLI)
- BlueZ (`bluetoothctl`, `hciconfig`, `hcitool`)
- systemd

## Uninstallation

```bash
sudo ./uninstall.sh
```

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

**No RSSI data:**
```bash
# Verify hcitool works
hcitool con   # List connections
hcitool rssi <MAC_ADDRESS>   # Get RSSI for connected device
```

See `docs/hardware-setup-guide.md` for detailed troubleshooting.
