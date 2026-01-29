# JoustMania Architecture

## Service Overview

| Service | Port | Role |
|---------|------|------|
| Settings | 50051 | Configuration management, persists to `joustsettings.yaml` |
| Controller Manager | 50052 | PS Move hardware, button events, motion streaming |
| Game Coordinator | 50053 | Game lifecycle, death detection, scoring |
| Menu | 50054 | Lobby, game selection, ready state, admin mode |
| Audio | 50056 | Sound effects, music, voice announcements |

## Data Flow

### Game Start Sequence

```
Menu (lobby)
  │ monitors button events via StreamButtonEvents
  │
  ├─ Controllers connect → dim LED (game color)
  ├─ Trigger pressed → READY state, bright LED
  │
  ▼ All ready (≥2 players)
Menu → GameCoordinator.StreamGameEvents(start_config)
  │
  ▼
GameCoordinator
  ├─ Creates game instance
  ├─ Subscribes to StreamGameplayData (motion)
  ├─ Emits "game_started" event
  │
  ▼
Menu receives confirmation
  ├─ Clears ready state
  ├─ Stops button monitor
  │
  ▼
Game runs (60Hz motion processing)
  ├─ Detects deaths (movement threshold)
  ├─ Sends LED effects (warning, death, winner)
  ├─ Plays sounds via Audio service
  │
  ▼
Game ends → "game_ended" event → Menu restarts lobby
```

### Streaming Patterns

**Bidirectional streams** (primary communication):
- `StreamButtonEvents`: Button events ↔ LED commands
- `StreamGameplayData`: Motion data ↔ Game effects

**Server streams**:
- `StreamGameEvents`: Game lifecycle events
- `StreamMenuEvents`: Menu state changes
- `SubscribeToChanges`: Settings change notifications

## Key Concepts

### Controller States (Menu)

```
DISCONNECTED → CONNECTED (dim LED) → READY (bright LED)
                    ↓                      ↓
               ADMIN MODE (white LED, 60s timeout)
```

### Game States

```
IDLE → STARTING → RUNNING → ENDING → ENDED
```

### Motion Processing

- Hardware polls at 1000Hz
- Streams to game at 60Hz (active) or 10Hz (idle)
- Game uses EMA filter for smoothing
- Death threshold varies by sensitivity setting (0-4)

## Service Dependencies

```
Settings ← foundational (no deps)
Audio ← foundational (no deps)
Controller Manager ← Settings
Game Coordinator ← Settings, Controller Manager, Audio
Menu ← Settings, Controller Manager, Game Coordinator, Audio
```
