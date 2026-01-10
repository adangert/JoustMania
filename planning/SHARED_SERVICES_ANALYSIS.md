# Shared Services Analysis: Colors & Audio

**Date:** 2026-01-10
**Question:** Should colors and audio be their own microservices?

---

## Decision Framework: Service vs Library

### When to make something a **MICROSERVICE:**

✅ Has **state** that needs central management
✅ Accesses **hardware** or external systems
✅ Has **side effects** (I/O, hardware, network)
✅ Multiple services need to **coordinate** access
✅ Needs to **scale independently**
✅ Has complex **business logic**
✅ Owns a **data store**

### When to keep something as a **LIBRARY:**

✅ Pure **utility functions** (stateless)
✅ Simple **data transformations**
✅ Just **constants** or configuration
✅ No external dependencies
✅ Pure **computation**, no I/O

---

## Analysis: Colors

### Current Implementation

**File:** `utils/colors.py` (120 lines)

**What it does:**
- Defines color constants (RGB tuples)
- Enum of team colors (Pink, Magenta, Orange, Yellow, etc.)
- Pure functions: `generate_team_colors(num_teams)`, `hsv2rgb()`, `darken_color()`
- No state, no hardware, no side effects

**Example usage:**
```python
from utils import colors

# Get team colors for 3 teams
team_colors = colors.generate_team_colors(num_teams=3)
# Returns: [Colors.Orange, Colors.Turquoise, Colors.Purple]

# Use color constant
controller.set_color(colors.Colors.Red)
```

### Who Uses Colors?

**Current usage in services:**
- ✅ **WebUI** - Display team color options in settings
- ✅ **Settings** - Store color_lock_choices configuration
- ✅ **ControllerManager** - Set LED colors on PS Move controllers
- ✅ **GameCoordinator** - Assign team colors to players
- ✅ **Menu** - Display controller colors in menu

**Total:** 5 out of 6 services use colors

### If Colors Were a Service

**Architecture:**
```
ColorService (port 50056)
└─ RPCs:
   - GetTeamColors(num_teams) -> [RGB]
   - GetColorByName(name) -> RGB
   - GenerateRandomColors(count) -> [RGB]
```

**What would happen:**

```python
# Before (library):
team_colors = colors.generate_team_colors(3)  # Instant, local
# [Colors.Orange, Colors.Turquoise, Colors.Purple]

# After (service):
client = ColorServiceClient('colors:50056')
response = client.GetTeamColors(num_teams=3)  # Network call!
team_colors = response.colors
# Same result, but with network latency
```

### Pros of Color Service

- ❓ Centralized color palette management?
  - **Reality:** Colors are static constants, not dynamic
- ❓ Can update colors without rebuilding services?
  - **Reality:** Colors rarely change, not a real need
- ❓ Enforce color consistency?
  - **Reality:** Shared library already does this

### Cons of Color Service

- ❌ **Network overhead** for simple data lookup (RGB tuple)
- ❌ **Latency** - Every color lookup requires gRPC call
- ❌ **Complexity** - Additional service to deploy, monitor, debug
- ❌ **No state to manage** - It's just constants and pure functions
- ❌ **Single point of failure** - If color service is down, all services break
- ❌ **Overkill** - Making a service for `(255, 0, 0)` is excessive

### Decision: Colors

## ❌ **DO NOT** make Colors a service

**Rationale:**
1. **Pure library** - No state, no hardware, just constants and math
2. **No coordination needed** - Services don't need to coordinate color access
3. **Adds complexity for zero benefit** - Network calls for RGB tuples is wasteful
4. **Violates YAGNI** - You Ain't Gonna Need It (centralized color management)

**Keep as:** Shared library in `utils/colors.py`

**Services import it:**
```python
from utils import colors

# Use directly, no network calls
team_colors = colors.generate_team_colors(3)
```

---

## Analysis: Audio

### Current Implementation

**File:** `utils/piaudio.py` (281 lines)

**What it does:**
- Plays audio files (music, sound effects)
- Uses **alsaaudio** (Linux ALSA hardware access)
- Uses **pygame mixer** (audio playback)
- Spawns separate **processes** for background music loops
- Real-time **audio resampling** for tempo changes
- Has **state**: currently playing track, volume, tempo

**Example usage:**
```python
from piaudio import Audio

# Play sound effect
Audio('audio/Zombie/sounds/pistol.wav').start_effect()

# Play background music with tempo control
music = Music('audio/Joust/music/*.wav')
music.start()
music.change_ratio(1.5)  # Speed up by 50%
```

### Who Uses Audio?

**Current usage:**
- ✅ **GameCoordinator** - Game music, sound effects, death sounds, victory music
- ✅ **Menu** - Menu background music, button sounds
- ❓ **WebUI** - Potentially notification sounds?

**In Docker containers:**
- Each container has its own filesystem
- Audio hardware (`/dev/snd/`) is on host
- Multiple containers accessing audio hardware = **conflicts**

### The Docker Audio Problem

**Challenge:** Audio hardware is a **shared resource**

**Current (non-Docker) approach:**
- Each process spawns its own audio subprocess
- Works because all processes share same host audio device
- No coordination needed (pygame mixer handles mixing)

**Docker approach (current):**
```
Container 1 (GameCoordinator)
  └─ Tries to access /dev/snd/... ❌ Conflict!

Container 2 (Menu)
  └─ Tries to access /dev/snd/... ❌ Conflict!
```

**Problems:**
1. **Device conflicts** - Multiple containers can't access audio device simultaneously
2. **Requires privileged mode** - Need to mount `/dev/snd/` into each container
3. **No coordination** - Menu music plays OVER game music (audio chaos!)
4. **Resource waste** - Each container loads audio libraries, samples

### If Audio Were a Service

**Architecture:**
```
AudioService (port 50056)
  - Owns audio hardware (/dev/snd/)
  - Privileged container (audio device access)
  - Manages audio playback queue
  - Handles mixing and prioritization

RPCs:
  - PlaySound(file, volume, priority) -> ok
  - PlayMusic(file, loop, tempo) -> track_id
  - StopMusic(track_id) -> ok
  - SetVolume(level) -> ok
  - ChangeTempo(track_id, tempo) -> ok
  - GetStatus() -> {playing, track, volume}
```

**docker-compose.yml:**
```yaml
audio:
  build:
    context: .
    dockerfile: services/audio/Dockerfile
  privileged: true  # For audio device access
  devices:
    - /dev/snd:/dev/snd  # Audio hardware
  volumes:
    - ./audio:/app/audio  # Audio files
  environment:
    - OTEL_SERVICE_NAME=audio-service
  networks:
    - joustmania
```

**Usage from other services:**
```python
# GameCoordinator
audio_client = AudioClient('audio:50056')
audio_client.PlaySound('audio/Joust/sounds/death.wav', volume=0.8, priority=HIGH)
music_id = audio_client.PlayMusic('audio/Joust/music/*.wav', loop=True, tempo=1.0)

# Later: Speed up music
audio_client.ChangeTempo(music_id, tempo=1.5)

# Menu (lower priority)
audio_client.PlayMusic('audio/Menu/music.wav', loop=True, priority=LOW)
```

### Pros of Audio Service

- ✅ **Centralized hardware access** - Only one container needs audio device
- ✅ **Proper mixing** - Service coordinates music + sound effects
- ✅ **Priority management** - Game sounds can interrupt menu sounds
- ✅ **Smooth transitions** - Fade menu music when game starts
- ✅ **Resource efficiency** - Audio libraries loaded once
- ✅ **Better isolation** - GameCoordinator doesn't need privileged mode for audio
- ✅ **Queue management** - Handle concurrent audio requests properly
- ✅ **State management** - Single source of truth for "what's playing"

### Cons of Audio Service

- ⚠️ **Network latency** - Small delay when triggering sounds (acceptable for game audio)
- ⚠️ **Additional service** - More complexity (but necessary for Docker)
- ⚠️ **Single point of failure** - If audio service fails, no sounds (acceptable)

### Decision: Audio

## ✅ **YES** - Make Audio a microservice

**Rationale:**
1. **Hardware access** - Audio device is shared resource, needs coordination
2. **Has state** - Currently playing track, volume, tempo
3. **Prevents conflicts** - Multiple containers can't share audio device
4. **Better architecture** - Clean separation: one service owns audio hardware
5. **Necessary for Docker** - Without it, audio won't work properly in containers
6. **Enables features** - Priority-based mixing, smooth transitions, volume management

**Recommended:** Create `AudioService` (7th microservice)

---

## Comparison Table

| Aspect | Colors | Audio |
|--------|--------|-------|
| **Type** | Constants + pure functions | Hardware I/O + state |
| **State** | None | Yes (playing track, volume) |
| **Hardware** | No | Yes (audio device) |
| **Side effects** | No | Yes (plays sounds) |
| **Coordination needed** | No | Yes (prevent conflicts) |
| **Used by** | 5 services | 2+ services |
| **In Docker** | Works fine as library | **Needs coordination** |
| **Verdict** | ❌ Keep as library | ✅ Make a service |

---

## Recommended Architecture

### Colors: Shared Library

```
utils/
  colors.py  # Imported by all services

services/
  settings/
    server.py
    # imports: from utils import colors

  game_coordinator/
    server.py
    # imports: from utils import colors

  # etc.
```

**Dockerfile (all services):**
```dockerfile
COPY utils/ /app/utils/
```

**No network calls, no overhead, simple.**

---

### Audio: Dedicated Service

```
services/
  audio/
    server.py           # gRPC audio service
    audio.proto         # Audio service protobuf
    playback.py         # Audio playback logic (from piaudio.py)
    mixer.py            # Audio mixing/prioritization
    Dockerfile
    pyproject.toml
```

**audio.proto:**
```protobuf
service AudioService {
  // Play a sound effect (one-shot)
  rpc PlaySound(PlaySoundRequest) returns (PlaySoundResponse);

  // Play background music (looping)
  rpc PlayMusic(PlayMusicRequest) returns (PlayMusicResponse);

  // Stop music track
  rpc StopMusic(StopMusicRequest) returns (StopMusicResponse);

  // Change music tempo (real-time speed adjustment)
  rpc ChangeTempo(ChangeTempoRequest) returns (ChangeTempoResponse);

  // Set master volume
  rpc SetVolume(SetVolumeRequest) returns (SetVolumeResponse);

  // Get current playback status
  rpc GetStatus(GetStatusRequest) returns (GetStatusResponse);
}

enum AudioPriority {
  LOW = 0;      // Menu music
  MEDIUM = 1;   // Game music
  HIGH = 2;     // Sound effects
  CRITICAL = 3; // Victory/death sounds
}

message PlaySoundRequest {
  string file_path = 1;      // e.g. "audio/Joust/sounds/death.wav"
  float volume = 2;          // 0.0 to 1.0
  AudioPriority priority = 3;
}

message PlayMusicRequest {
  string file_pattern = 1;   // e.g. "audio/Joust/music/*.wav"
  bool loop = 2;
  float tempo = 3;           // 1.0 = normal speed
  AudioPriority priority = 4;
}

message PlayMusicResponse {
  string track_id = 1;       // UUID for this music track
  bool success = 2;
  string error = 3;
}

message ChangeTempo Request {
  string track_id = 1;
  float new_tempo = 2;       // New playback speed
  float transition_duration = 3;  // Seconds to transition
}

message GetStatusResponse {
  string current_track = 1;
  bool is_playing = 2;
  float volume = 3;
  float tempo = 4;
  repeated string queued_sounds = 5;
}
```

**docker-compose.yml:**
```yaml
services:
  audio:
    build:
      context: .
      dockerfile: services/audio/Dockerfile
    container_name: joustmania-audio
    privileged: true  # For /dev/snd access
    devices:
      - /dev/snd:/dev/snd  # Audio hardware
    volumes:
      - ./audio:/app/audio:ro  # Audio files (read-only)
    ports:
      - "50056:50056"
    environment:
      - OTEL_SERVICE_NAME=audio-service
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
    depends_on:
      otel-collector:
        condition: service_healthy
    networks:
      - joustmania
    restart: unless-stopped
```

**Benefits:**
- 🎵 Only AudioService needs privileged mode
- 🎵 GameCoordinator can be unprivileged (better security)
- 🎵 Menu and Game music properly coordinated
- 🎵 Smooth transitions between menu ↔ game
- 🎵 Sound effect prioritization works correctly
- 🎵 Single audio device owner (no conflicts)

---

## Updated Microservices Architecture

### After adding AudioService: 7 services total

1. **Settings** (port 50051) - Settings management
2. **ControllerManager** (port 50052) - Controller I/O + pairing (privileged)
3. **GameCoordinator** (port 50053) - Game logic + coordination
4. **Menu** (port 50054) - Menu UI + navigation
5. **Supervisor** (port 50055) - Health monitoring
6. **WebUI** (port 80) - Web interface
7. **Audio** (port 50056) ✅ NEW - Audio playback + mixing (privileged)

### Privileged Services (need hardware access)

- ✅ **ControllerManager** - USB + Bluetooth (pairing)
- ✅ **Audio** - Audio device (`/dev/snd/`)

### Standard Services (unprivileged)

- ✅ Settings, GameCoordinator, Menu, Supervisor, WebUI

---

## Implementation Plan for AudioService

### Step 1: Define Audio Service

**Create:** `services/audio/audio.proto`

```protobuf
syntax = "proto3";
package joustmania.audio;

service AudioService {
  rpc PlaySound(PlaySoundRequest) returns (PlaySoundResponse);
  rpc PlayMusic(PlayMusicRequest) returns (PlayMusicResponse);
  rpc StopMusic(StopMusicRequest) returns (StopMusicResponse);
  rpc ChangeTempo(ChangeTempoRequest) returns (ChangeTempoResponse);
  rpc SetVolume(SetVolumeRequest) returns (SetVolumeResponse);
  rpc GetStatus(GetStatusRequest) returns (GetStatusResponse);
}

// [Full protobuf definition above]
```

### Step 2: Implement Audio Server

**Create:** `services/audio/server.py`

- Import playback logic from `piaudio.py`
- Implement gRPC servicer
- Manage audio queue with priority
- Handle concurrent requests
- OpenTelemetry instrumentation

### Step 3: Move Audio Code

```bash
# Move audio implementation
mkdir -p services/audio
cp utils/piaudio.py services/audio/playback.py
# Refactor playback.py to be service-friendly
```

### Step 4: Create Dockerfile

**Create:** `services/audio/Dockerfile`

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/audio/pyproject.toml /app/services/audio/
RUN pip install -e services/audio/

COPY services/audio/ /app/services/audio/
COPY audio/ /app/audio/

ENV PYTHONPATH=/app
ENV OTEL_SERVICE_NAME=audio-service

EXPOSE 50056
CMD ["python", "services/audio/server.py"]
```

### Step 5: Update docker-compose.yml

Add audio service (shown above)

### Step 6: Update GameCoordinator & Menu

Replace direct audio imports with gRPC client:

```python
# OLD (direct import)
from piaudio import Audio
Audio('audio/Joust/sounds/death.wav').start_effect()

# NEW (gRPC client)
from core.grpc_clients import AudioClient
audio = AudioClient('audio:50056')
audio.play_sound('audio/Joust/sounds/death.wav', volume=0.8, priority=HIGH)
```

### Step 7: Test

1. Start services: `docker-compose up --build`
2. Verify audio service starts
3. Test sound playback from GameCoordinator
4. Test music playback from Menu
5. Test transitions (menu → game music changeover)
6. Check Jaeger traces for audio RPCs

---

## Summary

### Colors: Keep as Library ❌ No Service

**Why:**
- Pure functions, no state
- No hardware access
- Just constants and math
- Network overhead for no benefit

### Audio: Make a Service ✅ New Service

**Why:**
- Hardware resource (audio device)
- Has state (playing track, volume)
- Needs coordination (prevent conflicts)
- Essential for Docker deployment
- Enables better UX (mixing, priorities, transitions)

---

## Next Steps

**For Phase 9 Implementation:**

1. ✅ **Keep colors as library** in `utils/colors.py`
2. ✅ **Create AudioService** as 7th microservice
3. Update GameCoordinator games to use AudioClient
4. Update Menu to use AudioClient
5. Remove direct piaudio imports
6. Test audio playback in containerized environment

**Priority:** Add AudioService to Phase 9 plan

Does this make sense? Should we proceed with creating the AudioService?
