# Audio Service

The Audio Service manages all sound playback in JoustMania, including game music with dynamic tempo control, sound effects, and voice announcements.

## Hardware Requirements

### Raspberry Pi 5

The Pi 5 has no 3.5mm headphone jack. You need a **USB audio adapter** for sound output.

Recommended: Any USB sound card with 3.5mm output (cheap ones work fine).

### Raspberry Pi 4 and Earlier

Built-in 3.5mm audio jack works out of the box. USB audio adapters also work if you prefer.

### HDMI Audio

HDMI audio output is supported but not recommended for portable/party setups where a monitor may not be available.

## Features

### Sound Effects

- 8 simultaneous sound channels with priority-based mixing
- Priority levels: LOW, MEDIUM, HIGH, CRITICAL
- When channels are full, lower priority sounds are evicted
- Fire-and-forget playback (non-blocking)

### Background Music

- Looping background music with random track selection
- Glob pattern support (e.g., `Joust/music/*.wav` plays a random track)
- One music track at a time

### Dynamic Tempo Control (Linux Only)

The signature JoustMania feature - music speeds up and slows down during gameplay:

- Normal speed: 1.0x
- Fast speed: 1.3x (30% faster)
- Smooth transitions over 1.5 seconds
- Tempo affects death sensitivity thresholds (faster music = harder to die)

This creates the classic JoustMania tension where slow music means careful movement, and fast music lets players move more freely.

**Note:** Tempo control requires Linux with ALSA. On other platforms, music plays at fixed speed.

### Voice Announcements

Two voice actors available:
- **aaron** - Male voice
- **ivy** - Female voice

Voice selection is configured in Settings (admin mode or settings service).

### Volume Control

- Master volume affects all audio (0.0 to 1.0)
- Game music typically plays at 0.7 volume
- Individual sound effects can have per-sound volume

## Audio File Formats

**Recommended:** WAV files (44.1 kHz, 16-bit, stereo)

**Supported with conversion overhead:** MP3, FLAC, OGG (converted via pydub)

For best performance, use WAV files. Other formats require runtime conversion which adds latency.

## Asset Structure

Audio files are organized by game mode:

```
services/audio/assets/
├── Joust/
│   ├── music/          # Background music tracks
│   │   ├── track1.wav
│   │   └── ...
│   ├── sounds/         # Sound effects
│   │   ├── Explosion34.wav
│   │   ├── beep_loud.wav
│   │   └── ...
│   └── voice/
│       ├── aaron/      # Aaron's voice files
│       └── ivy/        # Ivy's voice files
├── Menu/
│   ├── music/
│   ├── sounds/
│   └── voice/
├── Commander/
├── Zombie/
└── ...
```

## Custom Music

To add custom music:

1. Place WAV files in the appropriate `music/` folder
2. Files are selected randomly when the game starts
3. Restart the audio service to pick up new files

Example: Add custom Joust music to `services/audio/assets/Joust/music/`

**Supported formats:** WAV (recommended), MP3, FLAC, OGG

**Requirements:**
- 44.1 kHz sample rate (or will be resampled)
- Stereo or mono
- Any bit depth (converted to 16-bit)

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIO_ASSETS_DIR` | `services/audio/assets` | Path to audio files |
| `MOCK_MODE` | `false` | Silent mode for testing |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

### Settings Service

- **Voice actor:** Selectable via admin mode or settings API
- **Play audio:** Can be disabled entirely via settings
- **Volume:** Controlled per-game by the game coordinator

## Limitations

### Platform Support

| Feature | Linux | Windows/Mac |
|---------|-------|-------------|
| Sound effects | Yes | Yes |
| Background music | Yes | Yes |
| Dynamic tempo | Yes | No (fixed speed) |

Full features require Linux with ALSA audio backend.

### Technical Constraints

- Maximum 8 simultaneous sounds (pygame mixer limit)
- One music track at a time (no layered music)
- No crossfading between tracks
- No audio ducking (music doesn't lower for voice)
- No text-to-speech (all voice files are pre-recorded)
- No microphone/input support (output only)
- No audio device selection (uses system default)

### Tempo Control Constraints

- Range limited to 0.5x - 2.0x speed
- Real-time resampling uses CPU (scipy)
- No pitch correction (tempo change affects pitch slightly)

## Troubleshooting

### No Sound Output

1. Check audio device is connected (USB adapter for Pi 5)
2. Verify ALSA can see the device: `aplay -l`
3. Check audio service logs: `docker compose logs audio`
4. Ensure `play_audio` setting is enabled

### Choppy or Stuttering Audio

1. Check CPU usage during tempo transitions
2. Use WAV files instead of MP3/FLAC (avoids conversion overhead)
3. Reduce number of simultaneous sound effects

### Wrong Audio Device

The service uses the system default audio device. To change:

1. List devices: `aplay -l`
2. Set default in `/etc/asound.conf` or `~/.asoundrc`:
   ```
   defaults.pcm.card 1
   defaults.ctl.card 1
   ```
   (Replace `1` with your device number)

## API Reference

The audio service exposes a gRPC API on port 50056:

| RPC | Description |
|-----|-------------|
| `PlaySound` | Play a one-shot sound effect |
| `PlayMusic` | Start looping background music |
| `StopMusic` | Stop current music track |
| `ChangeTempo` | Change music playback speed |
| `SetVolume` | Set master volume |
| `GetStatus` | Get current playback status |

See `proto/audio.proto` for full API definition.
