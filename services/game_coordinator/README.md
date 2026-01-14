# Game Coordinator Service

**Part of JoustMania Microservices Architecture**

## Overview

The Game Coordinator Service manages the game lifecycle and orchestrates gameplay across all connected controllers. It handles game mode selection, player management, death detection, scoring, and game state transitions.

## Quick Reference

| Property | Value |
|----------|-------|
| **Port** | 50053 |
| **Proto** | `proto/game_coordinator.proto` |
| **Container** | `joustmania-game-coordinator` |

## gRPC API

### StartGame
Starts a new game with specified mode and players.

```bash
grpcurl -plaintext -d '{"game_name": "JoustFFA", "settings": {"sensitivity": "medium"}}' \
  localhost:50053 joustmania.game_coordinator.GameCoordinatorService/StartGame
```

### GetGameStatus
Gets current game state, players, and elapsed time.

```bash
grpcurl -plaintext localhost:50053 \
  joustmania.game_coordinator.GameCoordinatorService/GetGameStatus
```

### ForceEndGame
Forces the current game to end.

```bash
grpcurl -plaintext -d '{"reason": "admin_requested"}' \
  localhost:50053 joustmania.game_coordinator.GameCoordinatorService/ForceEndGame
```

### StreamGameEvents
Streams real-time game events (deaths, scoring, etc.).

```bash
grpcurl -plaintext localhost:50053 \
  joustmania.game_coordinator.GameCoordinatorService/StreamGameEvents
```

## Game States

| State | Description |
|-------|-------------|
| `IDLE` | No game running, waiting for start |
| `STARTING` | Game initializing, countdown in progress |
| `RUNNING` | Game in progress |
| `ENDING` | Game finishing, determining winner |
| `ENDED` | Game complete, showing results |

## Supported Game Modes

| Mode | Description |
|------|-------------|
| `JoustFFA` | Free-for-all joust - last player standing wins |
| `JoustTeams` | Team-based joust |
| `JoustRandomTeams` | Random team assignment |
| `Werewolves` | Hidden role deduction game |
| `Zombies` | Infection-style game |
| `Commander` | Protect your commander |
| `Swapper` | Role-swapping variant |
| `Tournament` | Bracket-style elimination |
| `NonStop` | Continuous respawn mode |
| `Ninja` | Stealth-based gameplay |
| `Random` | Randomly selected mode |

## Architecture

```
┌──────────────────────┐
│   Menu Service       │──── StartGame request
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐     ┌─────────────────┐
│  Game Coordinator    │◄────│ Controller Mgr  │
│  (port 50053)        │     │ (motion data)   │
└──────────┬───────────┘     └─────────────────┘
           │
           ├──► Audio Service (sounds/music)
           ├──► Settings Service (sensitivity)
           └──► Controller Mgr (LED feedback)
```

## Distributed Tracing

The Game Coordinator creates comprehensive traces for:
- Per-player lifecycle spans
- Per-team spans (team games)
- Death detection events
- Game phase transitions

View traces in Jaeger: `http://localhost:16686`

## Development

```bash
# Run locally
cd services/game_coordinator
python server.py

# Run tests
pytest tests/
```

## See Also

- [Architecture](../../docs/ARCHITECTURE.md) - System architecture
- [Proto Definition](../../proto/game_coordinator.proto) - Full API specification
- [Distributed Tracing](./DISTRIBUTED_TRACING.md) - Tracing implementation
- [Development Guide](../../docs/DEVELOPMENT.md) - Development workflow
