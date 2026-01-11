# Phase 32: Settings Cleanup

**Status:** 🧹 PLANNED
**Priority:** LOW - Reduces confusion

## Goal
Remove unused settings and validate used ones

## Motivation
- Settings service defines many unused settings
- WebUI allows changing settings that games ignore
- Confusing for users when settings have no effect
- Increases code maintenance burden

## Tasks

**1. Audit Settings Usage**
- [ ] Scan all game modes for settings.get() calls
- [ ] Identify which settings are actually used
- [ ] Document which game modes use which settings
- **Files:** All game mode files

**Currently Used Settings:**
```
sensitivity: Used by all games (FFA, Teams, RandomTeams, Nonstop)
num_teams: Used by Teams, RandomTeams
force_all_start: Used by GameCoordinator
instructions: Referenced but not fully implemented
```

**Unused Settings (Found in Analysis):**
```
random_modes: Loaded but never checked
color_lock: Defined but not implemented
random_teams: Boolean flag, not used
menu_voice: Not implemented
enforce_minimum: Immutable, never checked
red_on_kill: Not referenced in any game mode
```

**2. Remove Unused Settings**
- [ ] Remove from settings schema
  - **Files:** `services/settings/server.py:119-193`

- [ ] Remove from WebUI forms
  - **Files:** `services/webui/server.py:115-145`

- [ ] Remove from default settings
  - **Files:** `joustsettings.yaml`

**3. Add Settings Validation**
- [ ] Validate num_teams range [2-6]
- [ ] Validate sensitivity range [0-2]
- [ ] Validate force_all_start is boolean
- [ ] Return error on invalid values
- **Files:** `services/settings/server.py:350-390`

**4. Document Settings**
- [ ] Create settings reference in docs/
- [ ] Document each setting's purpose
- [ ] Document which game modes use which settings
- [ ] Document valid value ranges

**5. Settings Migration**
- [ ] Add migration script for old joustsettings.yaml
- [ ] Remove deprecated keys
- [ ] Set defaults for new required keys
- **Files:** `scripts/settings/migrate_settings.py` (new)

## Expected Improvements
- Cleaner settings UI
- Less confusion about what settings do
- Reduced code complexity
- Better validation and error messages

## Success Criteria
- Only used settings in schema
- All settings have validation
- WebUI shows only functional settings
- Migration script handles old configs
