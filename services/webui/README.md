# WebUI Service

**Part of JoustMania Microservices Architecture**

## Overview

The WebUI Service provides a browser-based interface for JoustMania administration. It's a Flask application that acts as a gRPC client to communicate with backend microservices, offering game configuration, controller status monitoring, and system administration.

## Quick Reference

| Property | Value |
|----------|-------|
| **Port** | 80 (HTTP) |
| **Framework** | Flask |
| **Container** | `joustmania-webui` |

## Features

### Controller Status
- View all connected controllers
- Monitor battery levels
- Check Bluetooth signal strength (RSSI)
- See controller colors and team assignments

### Game Configuration
- Select game modes
- Configure sensitivity settings
- Set team options
- Toggle instructions on/off

### System Administration
- View service health status
- Monitor system metrics
- Access game settings

## Web Pages

| Path | Description |
|------|-------------|
| `/` | Main dashboard |
| `/battery` | Controller battery and signal status |
| `/settings` | Game configuration |
| `/admin` | System administration |

## Architecture

```
┌─────────────────┐
│    Browser      │
│  (HTTP/HTML)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    WebUI        │
│   (Flask)       │
│  port 80        │
└────────┬────────┘
         │ gRPC
         ├──► Settings (50051)
         ├──► Controller Manager (50052)
         ├──► Menu (50054)
         └──► Supervisor (50055)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `production` | Flask environment |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `SETTINGS_HOST` | `settings` | Settings service hostname |
| `CONTROLLER_MANAGER_HOST` | `controller-manager` | Controller manager hostname |
| `MENU_HOST` | `menu` | Menu service hostname |
| `SUPERVISOR_HOST` | `supervisor` | Supervisor service hostname |

## Development

```bash
# Run locally
cd services/webui
flask run --port 5000

# Run tests
pytest tests/
```

## Template Structure

```
templates/
├── base.html          # Base template with navigation
├── index.html         # Dashboard
├── battery.html       # Controller status
├── settings.html      # Game configuration
└── admin.html         # System administration
```

## See Also

- [Architecture](../../docs/ARCHITECTURE.md) - System architecture
- [Controller Connectivity](../../docs/CONTROLLER_CONNECTIVITY.md) - Signal monitoring
- [Development Guide](../../docs/DEVELOPMENT.md) - Development workflow
