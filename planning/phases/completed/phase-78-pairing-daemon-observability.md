# Phase 78: Pairing Daemon Observability

## Overview

Rewrite the PS Move pairing daemon from Bash to Python to enable full observability with Prometheus metrics and OpenTelemetry tracing, consistent with other JoustMania services.

## Problem Statement

The original Bash-based pairing daemon (Phase 65) works but lacks observability:
1. No metrics for monitoring pairing success/failure rates
2. No tracing for debugging "controller won't connect" issues
3. No visibility into pairing duration or calibration time
4. Inconsistent with the observability stack used by other services

## Solution

Rewrite the daemon in Python with:
- Prometheus metrics exposed on port 8002
- OpenTelemetry tracing sent to the OTLP collector
- Same pairing logic as the Bash version
- Virtual environment for dependency isolation (PEP 668 compliance)

## Benefits

- **Full observability**: Metrics and traces like other JoustMania services
- **Debugging**: Trace spans show exactly where pairing fails
- **Monitoring**: Grafana dashboards can show pairing success rates
- **Histograms**: Track pairing and calibration duration distributions
- **Consistency**: Same observability patterns as containerized services

## Metrics Exposed

| Metric | Type | Description |
|--------|------|-------------|
| `psmove_pairing_attempts_total` | Counter | Total pairing attempts |
| `psmove_pairing_success_total` | Counter | Successful pairings |
| `psmove_pairing_failed_total` | Counter | Failed pairings |
| `psmove_pairing_polls_total` | Counter | Total polling cycles |
| `psmove_pairing_usb_controllers` | Gauge | Currently connected USB controllers |
| `psmove_pairing_duration_seconds` | Histogram | Time to complete pairing |
| `psmove_pairing_calibration_duration_seconds` | Histogram | Time to calibrate controller |

## Tracing Spans

- `poll_cycle` - Each polling iteration
- `process_controller` - Processing a detected controller
- `pair_controller` - Running `psmove pair`
- `trust_device` - Running `bluetoothctl trust`
- `calibrate_controller` - Running `psmove calibrate`

## Implementation

### Files Created

**`scripts/pairing-daemon/psmove_pairing_daemon.py`**
```python
# Main daemon with:
# - PairingDaemon class
# - Prometheus metrics (counters, gauges, histograms)
# - OpenTelemetry tracing
# - Same logic as Bash version
```

**`scripts/pairing-daemon/requirements.txt`**
```
prometheus-client>=0.17.0
opentelemetry-api>=1.20.0
opentelemetry-sdk>=1.20.0
opentelemetry-exporter-otlp-proto-grpc>=1.20.0
```

### Files Modified

**`scripts/pairing-daemon/psmove-pairing.service`**
- Changed ExecStart to use venv Python
- Added METRICS_PORT and OTEL_EXPORTER_OTLP_ENDPOINT environment variables

**`scripts/pairing-daemon/install.sh`**
- Creates virtual environment at `/opt/joustmania/scripts/pairing-daemon/venv`
- Installs Python dependencies in venv
- Copies Python daemon to install directory

**`services/prometheus/prometheus.yml`**
- Added `psmove-pairing` scrape job targeting `host.docker.internal:8002`

**`docker-compose.yml`**
- Added `extra_hosts: host.docker.internal:host-gateway` to prometheus service
- Exposed port 4317 on otel-collector for host services to send traces

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Host System                              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │           psmove-pairing-daemon (Python)                 │    │
│  │  - Polls for USB controllers                             │    │
│  │  - Pairs via psmove/bluetoothctl                         │    │
│  │  - Exposes metrics on :8002                              │    │
│  │  - Sends traces to localhost:4317                        │    │
│  └──────────────┬──────────────────────┬───────────────────┘    │
│                 │                      │                         │
│                 ▼                      ▼                         │
│          :8002/metrics          :4317 (OTLP)                    │
└─────────────────┬──────────────────────┬────────────────────────┘
                  │                      │
    ┌─────────────┴──────────┐    ┌──────┴─────────┐
    │      Prometheus        │    │  OTEL Collector │
    │  (scrapes via          │    │  (receives via  │
    │   host.docker.internal)│    │   exposed 4317) │
    └────────────────────────┘    └─────────────────┘
```

## Installation

```bash
# Install the daemon
sudo ./scripts/pairing-daemon/install.sh

# Check status
sudo systemctl status psmove-pairing

# View logs
journalctl -u psmove-pairing -f

# Check metrics
curl http://localhost:8002/metrics | grep psmove_
```

## Verification

1. **Metrics endpoint**: `curl http://localhost:8002/metrics`
2. **Prometheus scrape**: Check http://localhost:9090/targets for `psmove-pairing` (UP)
3. **Query metrics**: `psmove_pairing_polls_total` in Prometheus
4. **Jaeger traces**: Search for service `psmove-pairing` at http://localhost:16686
5. **Pairing test**: Plug in USB controller, verify metrics increment and spans appear

## Tasks

- [x] Create Python pairing daemon with metrics and tracing
- [x] Create requirements.txt for Python dependencies
- [x] Update systemd service to use Python daemon
- [x] Update install.sh to use virtual environment (PEP 668)
- [x] Add pairing daemon to Prometheus scrape config
- [x] Expose OTLP port 4317 for host services
- [x] Add extra_hosts to prometheus for host access

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POLL_INTERVAL` | 10 | Seconds between USB polls |
| `DEBUG` | 0 | Set to 1 for verbose logging |
| `METRICS_PORT` | 8002 | Prometheus metrics port |
| `PSMOVE_PATH` | auto-detect | Path to psmove binary |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | http://localhost:4317 | OTLP collector endpoint |

## Dependencies

- Python 3 with venv support (`python3-venv` package)
- psmoveapi installed on host
- BlueZ/bluetoothctl available
- Docker services running (for trace collection)

## Notes

- The Bash daemon is kept for backward compatibility but not used
- Virtual environment required due to PEP 668 on modern Debian/Raspberry Pi OS
- Metrics port 8002 chosen to avoid conflicts with other services (8000, 8001)
- Traces are only collected when Docker stack is running (otel-collector available)
