# Phase 28: Admin Mode Completion

**Status:** ✅ PLANNED
**Priority:** MEDIUM - Makes Phase 23 fully functional

## Goal
Complete admin mode implementation with actual settings persistence

## Motivation
- Phase 23 implemented visual feedback but not actual functionality
- Sensitivity cycling shows blue pulse but doesn't change game sensitivity
- Instruction toggle shows purple pulse but doesn't affect audio playback
- Users have no way to adjust settings without WebUI

## Tasks

**1. Sensitivity Persistence**
- [ ] Connect sensitivity admin handler to Settings service
  - [ ] Track current sensitivity state (0=slow, 1=medium, 2=fast)
  - [ ] Call Settings.UpdateSetting("sensitivity", value)
  - [ ] Provide visual feedback with color codes:
    - Slow: Blue (0, 0, 255)
    - Medium: Green (0, 255, 0)
    - Fast: Red (255, 0, 0)
  - **Files:** `services/menu/server.py:648-659`

```python
async def _handle_admin_sensitivity(self, serial: str):
    # Get current sensitivity
    get_req = settings_pb2.GetSettingRequest(key="sensitivity")
    response = await self.settings_stub.GetSetting(get_req)
    current = int(response.value) if response.value else 1

    # Cycle: 0 (slow) → 1 (medium) → 2 (fast) → 0
    new_value = str((current + 1) % 3)

    # Update setting
    update_req = settings_pb2.UpdateSettingRequest(
        key="sensitivity",
        value=new_value,
        source="admin_mode"
    )
    await self.settings_stub.UpdateSetting(update_req)

    # Visual feedback (color by sensitivity level)
    colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0)]
    # ... show color
```

**2. Instruction Toggle Persistence**
- [ ] Connect instruction handler to Settings service
  - [ ] Track instruction state (true/false)
  - [ ] Call Settings.UpdateSetting("instructions", value)
  - [ ] Provide visual feedback:
    - Enabled: Green (0, 255, 0)
    - Disabled: Red (255, 0, 0)
  - **Files:** `services/menu/server.py:719-757`

**3. Admin Mode State Indicator**
- [ ] Show admin mode status on controller
  - [ ] Periodic pulse in admin mode (every 5 seconds)
  - [ ] Shows current option color
  - [ ] Exit shows white fade-out effect
  - **Files:** `services/menu/server.py:530-570`

**4. Settings Validation**
- [ ] Validate settings before updating
  - [ ] Ensure num_teams in range [2, 6]
  - [ ] Ensure sensitivity in range [0, 2]
  - [ ] Ensure force_all_start is "true" or "false"
  - [ ] Return error on invalid values

**5. Documentation**
- [ ] Update README with actual functionality
  - [ ] Document that settings persist across games
  - [ ] Document sensitivity levels (slow/medium/fast)
  - [ ] Document visual feedback colors

## Expected Improvements
- Admin mode actually functional
- Settings changes visible in WebUI
- Sensitivity affects ongoing games
- Instructions can be toggled during events

## Success Criteria
- Sensitivity cycling updates Settings service
- New sensitivity applies to next game
- Instruction toggle affects audio playback
- Settings persist to joustsettings.yaml
- Visual feedback matches actual state
