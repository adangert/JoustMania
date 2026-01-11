# Phase 29: Audio Integration

**Status:** 🔊 PLANNED
**Priority:** MEDIUM - Enhances game experience

## Goal
Add sound effects to all game modes for complete feedback loop

## Motivation
- All game modes have TODOs for audio integration
- Death/victory events lack audio feedback
- Countdown has no audio cues
- Audio service exists but isn't fully utilized

## Tasks

**1. FFA Game Audio**
- [ ] Add death explosion sound
  - [ ] Call Audio service when player dies
  - [ ] Sound: "explosion.wav"
  - [ ] Priority: HIGH (interrupts other sounds)
  - **Files:** `services/game_coordinator/games/ffa.py:384`

- [ ] Add victory sound
  - [ ] Call Audio service when player wins
  - [ ] Sound: "victory.wav"
  - [ ] Play for all players
  - **Files:** `services/game_coordinator/games/ffa.py:428`

- [ ] Add countdown audio
  - [ ] Tick sound at 3, 2, 1
  - [ ] Start sound at 0
  - **Files:** `services/game_coordinator/games/ffa.py:166-170`

**2. Teams Game Audio**
- [ ] Add death explosion sound
  - **Files:** `services/game_coordinator/games/teams.py:426`

- [ ] Add victory sound
  - **Files:** `services/game_coordinator/games/teams.py:496`

- [ ] Add countdown audio
  - **Files:** `services/game_coordinator/games/teams.py:212`

**3. Random Teams Game Audio**
- [ ] Add death explosion sound
  - **Files:** `services/game_coordinator/games/random_teams.py:495`

- [ ] Add victory sound
  - **Files:** `services/game_coordinator/games/random_teams.py:565`

- [ ] Add countdown audio
  - **Files:** `services/game_coordinator/games/random_teams.py:281`

**4. Nonstop Joust Audio**
- [ ] Add respawn countdown ticks
  - [ ] 3-second countdown with beeps
  - [ ] Different pitch for each second
  - **Files:** `services/game_coordinator/games/nonstop_joust.py:400-420`

- [ ] Add spawn protection sound
  - [ ] Hum/shield sound during invulnerability
  - [ ] Stops when protection expires

**5. Audio Assets**
- [ ] Verify required sounds exist in `audio/` directory
  - [ ] explosion.wav
  - [ ] victory.wav
  - [ ] countdown_3.wav, countdown_2.wav, countdown_1.wav, countdown_go.wav
  - [ ] respawn.wav
  - [ ] shield.wav

## Implementation Pattern

```python
async def _play_sound(self, sound_name: str, priority: int = 5):
    """Play sound via Audio service."""
    from services.audio import audio_pb2

    request = audio_pb2.PlaySoundRequest(
        sound_name=sound_name,
        priority=priority
    )
    await self.audio_client.PlaySound(request)
```

## Expected Improvements
- Complete sensory feedback (visual + audio + haptic)
- Better game atmosphere
- Clear audio cues for game state changes
- Matches original JoustMania experience

## Success Criteria
- All death events play explosion sound
- Victory plays celebration sound
- Countdown has audio cues (3, 2, 1, GO)
- Respawn countdown has audio
- Audio doesn't lag or stutter on RPi
