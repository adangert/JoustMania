# Settings Service

**Part of JoustMania Microservices Architecture**

## Overview

The Settings Service provides centralized configuration management for all JoustMania services. It stores game settings, sensitivity configurations, and other runtime parameters that need to be shared across services.

## Quick Reference

| Property | Value |
|----------|-------|
| **Port** | 50051 |
| **Proto** | `proto/settings.proto` |
| **Container** | `joustmania-settings` |

## gRPC API

### GetSettings
Retrieves all settings as key-value pairs.

```bash
grpcurl -plaintext localhost:50051 joustmania.settings.SettingsService/GetSettings
```

### GetSetting
Retrieves a specific setting by key.

```bash
grpcurl -plaintext -d '{"key": "sensitivity"}' \
  localhost:50051 joustmania.settings.SettingsService/GetSetting
```

### UpdateSetting
Updates a setting value.

```bash
grpcurl -plaintext -d '{"key": "sensitivity", "value": "fast", "source": "admin"}' \
  localhost:50051 joustmania.settings.SettingsService/UpdateSetting
```

### SubscribeToChanges
Streams setting change events (server-side streaming).

```bash
grpcurl -plaintext -d '{"keys": ["sensitivity"]}' \
  localhost:50051 joustmania.settings.SettingsService/SubscribeToChanges
```

## Common Settings

| Key | Values | Description |
|-----|--------|-------------|
| `sensitivity` | `slow`, `medium`, `fast` | Motion sensitivity threshold |
| `instructions` | `true`, `false` | Whether to show game instructions |
| `teams` | `2`, `3`, `4` | Number of teams for team games |
| `game_mode` | Game mode name | Currently selected game mode |

## Architecture

```
┌─────────────────┐
│  Settings       │◄──── GetSettings/UpdateSetting
│  Service        │
│  (port 50051)   │────► SettingChangeEvent (stream)
└────────┬────────┘
         │
         ▼
    Redis (persistence)
```

## Development

```bash
# Run locally
cd services/settings
python server.py

# Run tests
pytest tests/
```

## See Also

- [Architecture](../../docs/ARCHITECTURE.md) - System architecture
- [Proto Definition](../../proto/settings.proto) - Full API specification
- [Development Guide](../../docs/DEVELOPMENT.md) - Development workflow
