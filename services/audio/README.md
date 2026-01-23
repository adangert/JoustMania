# Audio Service

**Part of JoustMania Microservices Architecture**

## Overview

The Audio Service handles all sound and music playback for JoustMania. It manages game music with dynamic tempo control, sound effects, voice announcements, and audio mixing with priority levels.

## Quick Reference

| Property | Value |
|----------|-------|
| **Port** | 50056 |
| **Proto** | `proto/audio.proto` |
| **Container** | `joustmania-audio` |

## gRPC API

### PlaySound
Plays a one-shot sound effect.

```bash
grpcurl -plaintext -d '{"file_path": "sounds/death.wav", "volume": 1.0, "priority": "HIGH"}' \
  localhost:50056 joustmania.audio.AudioService/PlaySound
```

### PlayMusic
Plays background music with optional looping and tempo control.

```bash
grpcurl -plaintext -d '{"file_pattern": "music/game_*.wav", "loop": true, "tempo": 1.0}' \
  localhost:50056 joustmania.audio.AudioService/PlayMusic
```

### StopMusic
Stops currently playing music.

```bash
grpcurl -plaintext -d '{"track_id": "abc123"}' \
  localhost:50056 joustmania.audio.AudioService/StopMusic
```

### ChangeTempo
Dynamically changes music tempo (for game intensity).

```bash
grpcurl -plaintext -d '{"track_id": "abc123", "new_tempo": 1.5, "transition_duration": 2.0}' \
  localhost:50056 joustmania.audio.AudioService/ChangeTempo
```

### SetVolume
Sets master volume level.

```bash
grpcurl -plaintext -d '{"volume": 0.8}' \
  localhost:50056 joustmania.audio.AudioService/SetVolume
```

## Audio Priority

| Priority | Use Case |
|----------|----------|
| `LOW` | Ambient sounds, background effects |
| `MEDIUM` | Game events, menu sounds |
| `HIGH` | Player deaths, important events |
| `CRITICAL` | Voice announcements, system alerts |

## Sound Categories

| Category | Examples |
|----------|----------|
| **Game Music** | Background tracks with tempo control |
| **Sound Effects** | Death sounds, button clicks, transitions |
| **Voice** | Game mode announcements, sensitivity changes |
| **Alerts** | Low battery, weak signal warnings |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIO_PORT` | 50056 | gRPC service port |
| `AUDIO_ASSETS_DIR` | `/audio` | Path to audio files |
| `MOCK_MODE` | `false` | Silent mode for testing |

## Development

```bash
# Run locally
cd services/audio
python server.py

# Run tests
pytest tests/
```

## See Also

- [Architecture](../../docs/ARCHITECTURE.md) - System architecture
- [Proto Definition](../../proto/audio.proto) - Full API specification
- [LED Feedback](../../docs/led-feedback.md) - Audio + LED coordination
- [Development Guide](../../docs/DEVELOPMENT.md) - Development workflow
