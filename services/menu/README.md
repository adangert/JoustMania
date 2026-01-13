# Menu Service

**Part of JoustMania Microservices Architecture**

## Overview

The Menu Service manages the game selection menu and lobby experience. It handles:

- Game mode selection (JoustFFA, JoustTeams, Tournament, Werewolf, NonstopJoust)
- Controller lobby state (connected/ready detection)
- LED feedback based on game mode and player ready state
- Admin mode for in-game configuration
- Event streaming for UI updates

## Quick Reference

| Property | Value |
|----------|-------|
| **gRPC Port** | 50054 |
| **Metrics Port** | 8000 |
| **Proto Definition** | `proto/menu.proto` |
| **Health Check** | gRPC health protocol |

## gRPC API

### StartMenu

Starts the menu and begins controller monitoring.

```protobuf
rpc StartMenu(StartMenuRequest) returns (StartMenuResponse);
```

**Response:**
- `success`: Whether the menu started successfully
- `error`: Error message if failed (e.g., "Menu already running")

### StopMenu

Stops the menu and clears all lobby state.

```protobuf
rpc StopMenu(StopMenuRequest) returns (StopMenuResponse);
```

### GetMenuStatus

Returns current menu state.

```protobuf
rpc GetMenuStatus(GetMenuStatusRequest) returns (GetMenuStatusResponse);
```

**Response:**
- `state`: STOPPED (0), RUNNING (1), or GAME_STARTING (2)
- `current_selection`: Currently selected game mode
- `ready_controller_count`: Number of controllers that have pressed trigger

### ProcessInput

Process menu input from controllers or web UI.

```protobuf
rpc ProcessInput(ProcessInputRequest) returns (ProcessInputResponse);
```

**Input Types:**

| Type | Data | Description |
|------|------|-------------|
| `button_press` | `{button: "trigger"}` | Start game with current selection |
| `button_press` | `{button: "select"}` | Cycle to next game mode |
| `web_command` | `{command: "start_game"}` | Start game from web UI |
| `reset_menu` | `{}` | Cancel GAME_STARTING state, return to RUNNING |

### StreamMenuEvents

Stream real-time menu events.

```protobuf
rpc StreamMenuEvents(StreamMenuEventsRequest) returns (stream MenuEvent);
```

**Event Types:**

| Event | Data | Description |
|-------|------|-------------|
| `menu_started` | `{}` | Menu has started |
| `menu_stopped` | `{}` | Menu has stopped |
| `selection_changed` | `{game_name, source?, serial?}` | Game mode changed |
| `game_requested` | `{game_name, source?, serial?}` | Game start requested |
| `game_start_cancelled` | `{}` | Game start was cancelled |
| `admin_action` | `{action, ...}` | Admin mode action taken |

## Lobby Feedback

Controllers receive LED feedback based on their state and the selected game mode:

### Game Mode Colors

| Game Mode | Color | RGB |
|-----------|-------|-----|
| JoustFFA | Orange | (255, 140, 0) |
| JoustTeams | Blue | (0, 100, 255) |
| Tournament | Purple | (150, 0, 255) |
| Werewolf | Green | (0, 255, 100) |
| NonstopJoust | Pink | (255, 50, 120) |

### Controller States

| State | LED Behavior |
|-------|--------------|
| Just Connected | Green flash (300ms), then dim game color |
| Connected (not ready) | Dim game color (~50% brightness) |
| Ready (trigger pressed) | Bright game color (100% brightness) |
| Admin Mode | White |

### Auto-Start

When all connected controllers are ready (trigger pressed) and there are at least 2 controllers, the game automatically starts.

## Admin Mode

Enter admin mode by pressing all 4 face buttons (Cross + Circle + Square + Triangle) simultaneously.

### Controls

| Button | Action |
|--------|--------|
| Move | Cycle through settings (num_teams, force_all_start) |
| Trigger | Increase current setting value |
| Cross | Decrease current setting value |
| Circle | Cycle sensitivity (Slow/Medium/Fast) |
| Triangle | Show battery levels on all controllers |
| Square | Toggle instruction display |
| PS | Exit admin mode |

### Timeout

Admin mode automatically exits after 60 seconds of inactivity.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `CONTROLLER_MANAGER_HOST` | `controller-manager` | Controller manager hostname |
| `CONTROLLER_MANAGER_PORT` | `50052` | Controller manager port |
| `SETTINGS_HOST` | `settings` | Settings service hostname |
| `SETTINGS_PORT` | `50051` | Settings service port |
| `GAME_COORDINATOR_HOST` | `game-coordinator` | Game coordinator hostname |
| `GAME_COORDINATOR_PORT` | `50053` | Game coordinator port |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OpenTelemetry endpoint |
| `OTEL_SERVICE_NAME` | `menu-service` | Service name for tracing |

## Metrics

Prometheus metrics are exposed at `http://localhost:8000/metrics`.

### gRPC Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `grpc_requests_total` | Counter | method, status | Total gRPC requests |
| `grpc_request_duration_seconds` | Histogram | method | Request duration |

### Button Monitoring Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `menu_button_frames_processed_total` | Counter | - | Controller state frames processed |
| `menu_button_presses_total` | Counter | button, action | Button presses detected |
| `menu_lobby_updates_total` | Counter | - | LED updates sent |

### System Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `process_cpu_percent` | Gauge | CPU usage percentage |
| `process_memory_mb` | Gauge | Memory usage in MB |
| `process_threads` | Gauge | Active thread count |

## Testing

```bash
# Run unit tests
cd services/menu
pytest tests/

# Test with grpcurl
grpcurl -plaintext localhost:50054 list
grpcurl -plaintext localhost:50054 joustmania.menu.MenuService/GetMenuStatus
```

## Dependencies

- **controller-manager**: Streams controller states, sets LED colors
- **settings**: Gets/updates game configuration
- **game-coordinator**: Receives game start requests

## Development

See [DEVELOPMENT.md](../../docs/DEVELOPMENT.md) for development workflow.
