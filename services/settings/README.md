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

## Settings Schema

All available settings with their types, defaults, and validation rules:

### Game Settings

| Key | Type | Default | Range/Values | Description |
|-----|------|---------|--------------|-------------|
| `sensitivity` | int | `2` | 0-4 | Movement sensitivity (0=ultra slow, 4=ultra fast) |
| `instructions` | bool | `true` | true/false | Play voice instructions before games |
| `num_teams` | int | `2` | 2-6 | Number of teams for team games |
| `force_all_start` | bool | `false` | true/false | Start with all controllers (vs only ready ones) |
| `nonstop_time_limit` | int | `0` | 0-3600 | Time limit for Nonstop Joust in seconds (0=no limit) |
| `random_teams` | bool | `true` | true/false | Randomize team assignments (vs sequential) |

### Menu Settings

| Key | Type | Default | Values | Description |
|-----|------|---------|--------|-------------|
| `current_game` | str | `"JoustFFA"` | See game modes | Currently selected game mode |
| `menu_voice` | str | `"ivy"` | "ivy", "aaron" | Voice pack for announcements |
| `play_audio` | bool | `true` | true/false | Enable/disable all audio |
| `random_modes` | list | See below | Game mode names | Modes included in random selection |

### Sensitivity Levels

| Value | Name | Description |
|-------|------|-------------|
| 0 | Ultra Slow | Most sensitive - easiest to die |
| 1 | Slow | High sensitivity |
| 2 | Medium | Default balanced setting |
| 3 | Fast | Low sensitivity |
| 4 | Ultra Fast | Least sensitive - hardest to die |

### Valid Game Modes

```
JoustFFA, JoustTeams, JoustRandomTeams, Werewolf, Traitor,
Zombies, Commander, Swapper, FightClub, Tournament, NonstopJoust, Ninja
```

### Default Random Modes

```yaml
random_modes:
  - JoustFFA
  - JoustRandomTeams
  - Werewolf
  - Nonstop
```

## Configuration File

Settings are persisted in `joustsettings.yaml` at the project root.

### Example Configuration

```yaml
# JoustMania Settings
sensitivity: 2
instructions: true
num_teams: 2
force_all_start: false
nonstop_time_limit: 0
menu_voice: ivy
random_modes:
  - JoustFFA
  - JoustRandomTeams
  - Werewolf
  - Nonstop
```

### File Location

| Environment | Path |
|-------------|------|
| Docker | `/app/joustsettings.yaml` (mounted volume) |
| Local | `./joustsettings.yaml` (project root) |

## Architecture

```
┌─────────────────┐
│  Settings       │◄──── GetSettings/UpdateSetting
│  Service        │
│  (port 50051)   │────► SettingChangeEvent (stream)
└────────┬────────┘
         │
         ▼
   joustsettings.yaml
```

### How It Works

1. **Startup**: Service loads `joustsettings.yaml`, validates against schema, applies defaults
2. **Read**: `GetSettings`/`GetSetting` return current in-memory values
3. **Write**: `UpdateSetting` validates value, updates memory, persists to YAML
4. **Subscribe**: `SubscribeToChanges` streams real-time change events to clients

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
