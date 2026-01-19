# Supervisor Service

**Part of JoustMania Microservices Architecture**

## Overview

The Supervisor Service orchestrates game lifecycle by subscribing to Menu events and starting games via the GameCoordinator. It acts as a bridge between the Menu UI and game execution.

## Quick Reference

| Property | Value |
|----------|-------|
| **Port** | 50055 (health only) |
| **Container** | `joustmania-supervisor` |
| **Type** | Orchestrator (gRPC client) |

## Architecture

The Supervisor is a **pure gRPC client** - it consumes other services but doesn't expose any RPCs itself. It only maintains a health service for Kubernetes liveness/readiness probes.

```
┌─────────────────────────────────────────────────────────────┐
│                    Supervisor Orchestrator                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   Menu ──StreamMenuEvents──▶ Supervisor ──StartGame──▶ Game  │
│                                                              │
│   Subscribes to:           Calls:                           │
│   - game_requested event   - GameCoordinator.StartGame      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Game Flow

1. **Menu** receives controller ready signals and emits `game_requested` event
2. **Supervisor** receives the event via `StreamMenuEvents`
3. **Supervisor** extracts controller list and game mode from event data
4. **Supervisor** calls `GameCoordinator.StartGame` with players
5. **GameCoordinator** starts the game and manages lifecycle

### Trace Propagation

The Supervisor propagates distributed tracing context between services:

```
Menu (game_requested event with trace context)
    └── Supervisor (orchestrate_game_start span)
        └── GameCoordinator (StartGame span)
            └── Game (game_lifecycle span)
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GRPC_PORT` | `50055` | gRPC health server port |
| `PROMETHEUS_PORT` | `8000` | Prometheus metrics port |
| `MENU_SERVICE` | `menu:50054` | Menu service address |
| `GAME_COORDINATOR_SERVICE` | `game-coordinator:50053` | GameCoordinator address |
| `LOG_LEVEL` | `INFO` | Logging level |

## Health Service

The Supervisor exposes only the standard gRPC Health service for container orchestration:

```bash
# Check health
grpcurl -plaintext localhost:50055 grpc.health.v1.Health/Check
```

## Development

```bash
# Run locally
cd services/supervisor
python server.py

# Run tests
pytest tests/
```

## See Also

- [Architecture](../../docs/ARCHITECTURE.md) - System architecture
- [Menu Service](../menu/README.md) - Event source
- [GameCoordinator](../game_coordinator/README.md) - Game execution
