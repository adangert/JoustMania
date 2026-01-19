# Milestone 6: Audio System

**Status:** Complete
**Phases:** 29, 70

## Summary

Dedicated audio microservice with priority-based sound mixing and real-time tempo control for dynamic game music.

## Background

Audio is critical for JoustMania gameplay:
- Music sets the pace and tension
- Sound effects provide feedback
- Voice announcements guide players

## Implementation

### Audio Architecture

```
┌─────────────────────────────────────────────┐
│              Audio Service                   │
│  ┌─────────────┐    ┌───────────────────┐   │
│  │   Pygame    │    │   MusicPlayer     │   │
│  │   Mixer     │    │  (scipy resample) │   │
│  │ (8 channels)│    │                   │   │
│  └─────────────┘    └───────────────────┘   │
│        ↑                     ↑              │
│   Sound Effects         Background Music    │
└─────────────────────────────────────────────┘
```

### Sound Effect System

Priority-based mixing with 8 simultaneous channels:

| Priority | Usage | Examples |
|----------|-------|----------|
| 1 (Low) | Ambient | Background sounds |
| 2 (Medium) | Gameplay | Warnings, movements |
| 3 (High) | Events | Deaths, wins |
| 4 (Critical) | System | Countdown, announcements |

### Dynamic Music System

Music tempo changes based on game state:

```python
# Tempo speeds up as players are eliminated
alive_ratio = alive_players / total_players
tempo = 1.0 + (1.0 - alive_ratio) * 0.5  # 1.0x to 1.5x

# Real-time resampling via scipy
await audio_client.ChangeTempo(tempo=1.3)
```

### Voice Announcements

Two voice options (configurable in settings):
- **Ivy** - Female voice (default)
- **Aaron** - Male voice

Voice files in: `services/audio/assets/Joust/vox/{voice}/`

### gRPC Interface

```protobuf
service AudioService {
  rpc PlaySound(PlaySoundRequest) returns (PlaySoundResponse);
  rpc PlayMusic(PlayMusicRequest) returns (PlayMusicResponse);
  rpc StopMusic(StopMusicRequest) returns (StopMusicResponse);
  rpc ChangeTempo(ChangeTempoRequest) returns (ChangeTempoResponse);
  rpc SetVolume(SetVolumeRequest) returns (SetVolumeResponse);
}
```

## Files Changed

- `services/audio/server.py` - gRPC servicer
- `services/audio/music_player.py` - Tempo-controlled playback
- `services/audio/assets/` - Sound files
- `proto/audio.proto` - Service definition

## Commits

See git history for complete list.

## Related Phases

- Phase 29: Audio integration
- Phase 70: Dynamic music system
