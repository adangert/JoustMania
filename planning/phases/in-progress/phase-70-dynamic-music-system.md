# Phase 70: Dynamic Music System

## Overview

Implement the original JoustMania music system in the microservices architecture:
- Background music during lobby (quiet) and games (loud)
- Real-time tempo changes using scipy resampling
- Dynamic tempo oscillation based on game progression
- Tempo-linked sensitivity adjustments

## Background

The original JoustMania had a sophisticated music system:
1. **Lobby music**: Quiet background music while in menu
2. **Game music**: Louder music during gameplay
3. **Dynamic tempo**: Music alternates between slow (1.0x) and fast (1.3x)
4. **Game-linked timing**: Tempo changes more frequently as players die
5. **Gameplay effect**: When music is fast, sensitivity decreases (harder to kill)

The existing `piaudio.py` has the tempo control code (scipy.signal.resample) but it's not integrated into the gRPC audio service.

## Technical Design

### Constants (from original)

```python
# Tempo speeds
SLOW_MUSIC_SPEED = 1.0  # Normal playback
FAST_MUSIC_SPEED = 1.3  # 30% faster

# Transition duration
INTERVAL_CHANGE = 1.5  # Seconds to smoothly transition

# Normal game timing (seconds)
MIN_MUSIC_FAST_TIME = 4
MAX_MUSIC_FAST_TIME = 8
MIN_MUSIC_SLOW_TIME = 10
MAX_MUSIC_SLOW_TIME = 23

# End game timing (more frequent changes)
END_MIN_MUSIC_FAST_TIME = 6
END_MAX_MUSIC_FAST_TIME = 10
END_MIN_MUSIC_SLOW_TIME = 8
END_MAX_MUSIC_SLOW_TIME = 12

# Volume levels
LOBBY_VOLUME = 0.4
GAME_VOLUME = 0.7
```

### Architecture

```
Menu Service                    Audio Service (gRPC :50056)
┌─────────────┐                ┌─────────────────────────────┐
│ StartMenu() │───PlayMusic───▶│ MusicPlayer (piaudio-based) │
│             │   volume=0.4   │  - scipy.signal.resample    │
│ StopMenu()  │───StopMusic───▶│  - Separate audio process   │
└─────────────┘                │  - Real-time tempo control  │
                               └─────────────────────────────┘
Game Coordinator                          ▲
┌─────────────────┐                       │
│ BaseGameMode    │───PlayMusic───────────┤
│                 │   volume=0.7          │
│ _music_loop()   │───ChangeTempo─────────┤
│                 │   (oscillates 1.0↔1.3)│
│ check_music_    │                       │
│ speed()         │───SetVolume───────────┘
└─────────────────┘
```

### Implementation Tasks

#### Task 1: Audio Service - Integrate piaudio Music Class

Replace pygame.mixer for music with piaudio.py's Music class:

**File: `services/audio/server.py`**

1. Import and initialize piaudio Music alongside pygame for effects
2. Route `PlayMusic` RPC to piaudio Music class
3. Route `ChangeTempo` RPC to `music.change_ratio()` / `transition_ratio()`
4. Route `StopMusic` RPC to `music.stop_audio()`
5. Keep pygame.mixer for sound effects (works well)

```python
# Hybrid approach:
# - pygame.mixer for sound effects (8 channels, priority mixing)
# - piaudio.Music for background music (real-time tempo control)

class AudioManager:
    def __init__(self):
        # Sound effects via pygame
        pygame.mixer.init(44100, -16, 2, 4096)

        # Music via piaudio (separate process, tempo control)
        self.music = Music("game_music")
        self.music_playing = False
```

#### Task 2: Menu Service - Lobby Music

**File: `services/menu/server.py`**

1. Start lobby music when menu starts (in `StartMenu` or on first button monitor)
2. Stop lobby music when game starts (on `game_starting` event)
3. Restart lobby music when game ends (on `game_ended` event)

```python
async def _start_lobby_music(self):
    """Start quiet background music for lobby."""
    await self.audio_client.SetVolume(audio_pb2.SetVolumeRequest(volume=0.4))
    await self.audio_client.PlayMusic(audio_pb2.PlayMusicRequest(
        file_pattern="Menu/music/*.wav",
        loop=True,
        tempo=1.0,
    ))

async def _stop_lobby_music(self):
    """Stop lobby music when game starts."""
    await self.audio_client.StopMusic(audio_pb2.StopMusicRequest())
```

#### Task 3: Base Game Mode - Game Music & Tempo Logic

**File: `services/game_coordinator/games/base.py`**

1. Add music constants
2. Start game music in `_run_game()` after countdown
3. Add `_music_loop()` task that runs alongside `_game_loop()`
4. Implement `_check_music_speed()` logic
5. Link tempo to sensitivity via `_get_effective_sensitivity()`

```python
# Music constants
SLOW_MUSIC_SPEED = 1.0
FAST_MUSIC_SPEED = 1.3
INTERVAL_CHANGE = 1.5

class BaseGameMode:
    async def _start_game_music(self):
        """Start game music at higher volume."""
        await self._set_volume(0.7)
        await self.audio_client.PlayMusic(audio_pb2.PlayMusicRequest(
            file_pattern="Joust/music/*.wav",
            loop=True,
            tempo=1.0,
        ))
        self.music_speed = SLOW_MUSIC_SPEED
        self.speed_up = True
        self.change_time = self._get_change_time()

    async def _music_loop(self):
        """Background task to manage music tempo changes."""
        while self.running:
            await self._check_music_speed()
            await asyncio.sleep(0.05)  # 20Hz check rate

    def _get_change_time(self) -> float:
        """Calculate next tempo change time based on game progression."""
        # Interpolate between normal and end-game timing
        game_percent = min(1.0, self.dead_count / max(1, len(self.players) - 2))

        if self.speed_up:
            min_t = lerp(MIN_MUSIC_SLOW_TIME, END_MIN_MUSIC_SLOW_TIME, game_percent)
            max_t = lerp(MAX_MUSIC_SLOW_TIME, END_MAX_MUSIC_SLOW_TIME, game_percent)
        else:
            min_t = lerp(MIN_MUSIC_FAST_TIME, END_MIN_MUSIC_FAST_TIME, game_percent)
            max_t = lerp(MAX_MUSIC_FAST_TIME, END_MAX_MUSIC_FAST_TIME, game_percent)

        return time.time() + random.uniform(min_t, max_t)
```

#### Task 4: Tempo-Sensitivity Link

When music is fast, reduce sensitivity (make players harder to kill):

```python
def _get_effective_sensitivity(self) -> float:
    """Get sensitivity adjusted for music speed."""
    base_threshold = self.sensitivity.value[1]

    # When music is fast (1.3), increase threshold by ~30%
    # This makes players harder to kill during fast sections
    speed_factor = self.music_speed / SLOW_MUSIC_SPEED
    return base_threshold * speed_factor
```

### Proto Changes

No proto changes needed - `PlayMusic`, `StopMusic`, `ChangeTempo`, `SetVolume` already exist in `audio.proto`.

### File Changes Summary

| File | Changes |
|------|---------|
| `services/audio/server.py` | Integrate piaudio Music for tempo control |
| `services/audio/piaudio.py` | Minor fixes for gRPC integration |
| `services/menu/server.py` | Add lobby music start/stop |
| `services/game_coordinator/games/base.py` | Add music loop, tempo logic, sensitivity link |
| `lib/common.py` | Add `lerp()` function if not exists |

### Testing

1. **Unit test**: Audio service tempo changes
2. **Integration test**: Menu → lobby music → game → game music → tempo changes
3. **Manual test**: Verify music speeds up/slows down during gameplay
4. **Manual test**: Verify players are harder to kill when music is fast

### Rollout

1. Build pygame-builder image (already done in Phase 69)
2. Update audio service
3. Update menu service
4. Update game coordinator
5. Test in mock mode
6. Test with real controllers

## Dependencies

- Phase 29: Audio Integration (completed)
- Phase 69: Pygame builder image (completed)
- scipy, numpy, pydub packages in audio service

## Risks

1. **Audio process stability**: piaudio uses multiprocessing - ensure clean shutdown
2. **Latency**: Tempo changes should be smooth, not jarring
3. **Resource usage**: scipy resampling is CPU-intensive on Pi

## Implementation Status

### Completed Tasks

1. **Audio Service - MusicPlayer with Tempo Control** (`services/audio/music_player.py`)
   - Created new `MusicPlayer` class using scipy.signal.resample for real-time tempo changes
   - Runs audio playback in separate process (non-blocking)
   - `transition_ratio()` for smooth tempo transitions
   - `DummyMusicPlayer` for mock mode

2. **Audio Service - Server Integration** (`services/audio/server.py`)
   - Integrated `MusicPlayer` for background music
   - Kept pygame.mixer for sound effects (8 channels)
   - `PlayMusic` → MusicPlayer.load() + start()
   - `ChangeTempo` → MusicPlayer.transition_ratio()
   - `StopMusic` → MusicPlayer.stop()

3. **Menu Service - Lobby Music** (`services/menu/server.py`)
   - `_start_lobby_music()` - starts quiet (0.4 volume) menu music
   - `_stop_lobby_music()` - stops when game starts
   - Integrated into `StartMenu` RPC
   - Integrated into game event loop (stop on game_start, restart on game_end)

4. **Base Game Mode - Game Music & Tempo** (`services/game_coordinator/games/base.py`)
   - Added music constants (SLOW_MUSIC_SPEED=1.0, FAST_MUSIC_SPEED=1.3)
   - Added timing constants for tempo changes
   - `_start_game_music()` - starts louder (0.7 volume) game music
   - `_stop_game_music()` - stops on game end
   - `_music_loop()` - background task for tempo management
   - `_check_music_speed()` - oscillates tempo based on timing
   - `_get_music_change_time()` - calculates next change based on game progress

5. **Tempo-Sensitivity Link** (`services/game_coordinator/games/base.py`)
   - Modified `_process_controller_state()` to scale death threshold by music speed
   - When music is 1.3x, thresholds increase by 30% (harder to kill)

### Files Modified

| File | Changes |
|------|---------|
| `services/audio/pyproject.toml` | Added scipy, numpy, pydub, pyalsaaudio |
| `services/audio/Dockerfile` | Added libasound2-dev (build), ffmpeg (runtime) |
| `services/audio/music_player.py` | NEW: MusicPlayer with tempo control |
| `services/audio/server.py` | Integrated MusicPlayer for music |
| `services/menu/server.py` | Added lobby music start/stop |
| `services/game_coordinator/games/base.py` | Added music constants, tempo logic, sensitivity link |

## Success Criteria

- [x] Lobby has quiet background music
- [x] Games have louder background music
- [x] Music tempo oscillates between 1.0x and 1.3x
- [x] Tempo changes are smooth (1.5s transition)
- [x] Tempo changes more frequently as game progresses
- [x] Players are harder to kill when music is fast
- [x] Music stops cleanly on game end
- [ ] Works on Raspberry Pi without audio glitches (needs hardware testing)
