# Phase 60: Menu Audio Feedback

**Status:** ✅ COMPLETE
**Priority:** MEDIUM
**Estimated Effort:** Medium (1-2 days)

## Goal

Restore the original JoustMania audio experience by integrating the menu service with the audio service for voice announcements and sound effects.

## Motivation

JoustMania is often used headless (no monitor). The original system provided voice feedback for:
- Game mode selection
- Sensitivity changes
- Instructions toggle
- Admin options

Currently the menu service only provides LED feedback. Adding audio makes the system usable without looking at controllers.

## Audio Assets Available

The voice assets already exist in `services/audio/assets/Menu/`:

### Sensitivity
- `sounds/slow_sensitivity.wav`
- `sounds/mid_sensitivity.wav`
- `sounds/fast_sensitivity.wav`

### Instructions Toggle
- `vox/{voice}/instructions_on.wav`
- `vox/{voice}/instructions_off.wav`

### Game Mode Announcements
- `vox/{voice}/menu Joust Teams.wav`
- `vox/{voice}/menu Joust Random Teams.wav`
- (Need to verify/create for all game modes)

### Admin Options
- `vox/{voice}/adminop_random_team_size.wav`
- `vox/{voice}/adminop_traitor_team_size.wav`
- `vox/{voice}/medium.wav`

### Voice Actors
- `aaron` - Male voice
- `ivy` - Female voice

## Architecture Decision: Menu vs Game Coordinator

### Menu Service Responsibilities
- Game mode selection announcements
- Admin mode voice feedback (sensitivity, instructions, team count)
- Lobby sounds (connection, ready confirmation)

### Game Coordinator Responsibilities
- Pre-game instructions ("In Joust Teams, you will be assigned to a team...")
- Wait for instructions to complete before starting game
- Game-specific audio during play

**Rationale:** Game coordinator already has audio integration and owns the game lifecycle. Instructions are game-specific content that belongs with game execution, not menu selection.

## Tasks

### Task 1: Add Audio Service Integration to Menu

**Files:** `services/menu/server.py`

Add audio channel and helper method:

```python
def __init__(self):
    # ... existing channels ...

    # Audio service channel (Phase 60)
    audio_host = os.getenv("AUDIO_HOST", "audio")
    audio_port = os.getenv("AUDIO_PORT", "50057")
    self.audio_channel = grpc.aio.insecure_channel(f"{audio_host}:{audio_port}")

    # Voice actor setting (aaron or ivy)
    self.voice_actor = "aaron"  # TODO: Get from settings

async def _play_sound(self, file_path: str, volume: float = 0.8, wait: bool = False):
    """Play a sound via the audio service."""
    try:
        from proto import audio_pb2, audio_pb2_grpc
        stub = audio_pb2_grpc.AudioServiceStub(self.audio_channel)
        await stub.PlaySound(audio_pb2.PlaySoundRequest(
            file_path=file_path,
            volume=volume,
            priority=audio_pb2.AudioPriority.HIGH
        ))
    except Exception as e:
        logger.warning(f"Could not play sound {file_path}: {e}")

async def _play_voice(self, voice_file: str, volume: float = 0.8):
    """Play a voice announcement."""
    path = f"/app/assets/Menu/vox/{self.voice_actor}/{voice_file}"
    await self._play_sound(path, volume)
```

### Task 2: Game Mode Selection Audio

**Files:** `services/menu/server.py`

Play announcement when game mode changes:

```python
# In _handle_select_press after changing selection:
GAME_MODE_VOICE = {
    "JoustFFA": "menu Joust FFA.wav",      # May need to create
    "JoustTeams": "menu Joust Teams.wav",
    "Tournament": "menu Tournament.wav",    # May need to create
    "Werewolf": "menu Werewolf.wav",        # May need to create
    "NonstopJoust": "menu Nonstop.wav",     # May need to create
}

voice_file = GAME_MODE_VOICE.get(self.current_selection)
if voice_file:
    await self._play_voice(voice_file)
```

### Task 3: Admin Mode Sensitivity Audio

**Files:** `services/menu/server.py`

Play sensitivity announcement in `_handle_admin_sensitivity`:

```python
SENSITIVITY_SOUNDS = {
    0: "slow_sensitivity.wav",   # Slow
    1: "mid_sensitivity.wav",    # Medium
    2: "fast_sensitivity.wav",   # Fast
}

# After changing sensitivity:
sound_file = SENSITIVITY_SOUNDS.get(new_sens)
if sound_file:
    await self._play_sound(f"/app/assets/Menu/sounds/{sound_file}")
```

### Task 4: Admin Mode Instructions Toggle Audio

**Files:** `services/menu/server.py`

Play announcement in `_handle_admin_instructions`:

```python
# After toggling instructions:
voice_file = "instructions_on.wav" if new_value == "true" else "instructions_off.wav"
await self._play_voice(voice_file)
```

### Task 5: Admin Mode Team Count Audio

**Files:** `services/menu/server.py`

Announce team count changes:

```python
# After changing num_teams:
# Could use TTS or pre-recorded "2 teams", "3 teams", etc.
# For now, just play a confirmation sound
await self._play_sound("/app/assets/Commander/sounds/buttonselect.wav")
```

### Task 6: Lobby Connection/Ready Sounds

**Files:** `services/menu/server.py`

Add sounds for lobby events:

```python
# In _update_lobby_feedback when controller first connects:
if is_new_connection:
    await self._play_sound("/app/assets/Joust/sounds/join.wav", volume=0.5)

# When controller becomes ready:
if newly_ready:
    await self._play_sound("/app/assets/Joust/sounds/beep_loud.wav", volume=0.6)
```

### Task 7: Voice Actor Setting

**Files:** `services/menu/server.py`

Get voice actor from settings service:

```python
async def _get_voice_actor(self) -> str:
    """Get configured voice actor from settings."""
    try:
        from proto import settings_pb2, settings_pb2_grpc
        stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)
        response = await stub.GetSetting(
            settings_pb2.GetSettingRequest(key="voice_actor")
        )
        if response.value in ("aaron", "ivy"):
            return response.value
    except Exception:
        pass
    return "aaron"  # Default
```

### Task 8: Update docker-compose

**Files:** `docker-compose.yml`

Add audio service dependency to menu:

```yaml
menu:
  depends_on:
    - audio
    - settings
    - controller-manager
  environment:
    - AUDIO_HOST=audio
    - AUDIO_PORT=50057
```

### Task 9: Game Coordinator Pre-Game Instructions

**Files:** `services/game_coordinator/server.py`

Ensure game coordinator plays instructions before starting game:

```python
async def _start_game(self, game_name: str, controllers: list):
    """Start a game with optional pre-game instructions."""

    # Check if instructions are enabled
    instructions_enabled = await self._get_setting("show_instructions") == "true"

    if instructions_enabled:
        # Play game-specific instructions
        instruction_file = GAME_INSTRUCTIONS.get(game_name)
        if instruction_file:
            voice = await self._get_setting("voice_actor") or "aaron"
            await self._play_and_wait(f"/app/assets/Menu/vox/{voice}/{instruction_file}")

    # Now start the actual game
    await self._initialize_game(game_name, controllers)

GAME_INSTRUCTIONS = {
    "JoustFFA": "FFA-instructions.wav",
    "JoustTeams": "Teams-instructions.wav",
    "Tournament": "Tournament-instructions.wav",
    "Werewolf": "werewolf-instructions.wav",
    "NonstopJoust": None,  # No instructions for nonstop
}
```

### Task 10: Verify/Create Missing Voice Assets

**Files:** `services/audio/assets/Menu/vox/`

Audit and document which voice files exist vs needed:

| Game Mode | Voice File | Status |
|-----------|------------|--------|
| JoustFFA | menu Joust FFA.wav | ❓ Check |
| JoustTeams | menu Joust Teams.wav | ✅ Exists |
| Tournament | menu Tournament.wav | ❓ Check |
| Werewolf | menu Werewolf.wav | ❓ Check |
| NonstopJoust | menu Nonstop.wav | ❓ Check |

### Task 11: Update LED Feedback Documentation

**Files:** `docs/led-feedback.md`, `services/menu/README.md`

Add audio feedback section documenting what sounds play when.

## Testing

### Manual Testing Checklist

- [ ] Game mode change plays voice announcement
- [ ] Sensitivity change plays appropriate sound
- [ ] Instructions toggle plays on/off announcement
- [ ] Controller connect plays join sound
- [ ] Controller ready plays beep
- [ ] Game start plays instructions (if enabled)
- [ ] Voice actor setting switches between aaron/ivy

### Integration Tests

- [ ] Menu service connects to audio service
- [ ] Audio plays without blocking menu operation
- [ ] Graceful handling when audio service unavailable

## Success Criteria

- ✅ Game mode selection has voice announcement
- ✅ Admin sensitivity has voice feedback
- ✅ Admin instructions toggle has voice feedback
- ✅ Lobby has connection/ready sounds
- ✅ Voice actor is configurable
- ✅ Game instructions play before game start
- ✅ Documentation updated

## Dependencies

- Phase 59 (Menu Service Polish) - ✅ Complete
- Audio service operational

## Performance Considerations

- Audio calls are fire-and-forget (don't block menu operation)
- Exception handling ensures menu works if audio unavailable
- Rate limiting on lobby sounds to prevent spam

## Future Enhancements

- Add admin mode entry/exit sound
- Add game start countdown sounds
- Add "all players ready" announcement
- TTS for dynamic announcements (team counts, player names)

## Notes

- Voice assets already exist for most scenarios
- Two voice actors available (aaron, ivy)
- Audio service uses pygame for playback
- Menu should not wait for audio (fire-and-forget)
- Game coordinator should wait for instructions before starting
