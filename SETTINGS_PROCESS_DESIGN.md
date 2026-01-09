# Settings Process - Design Document

**Date:** 2026-01-09
**Purpose:** Extract settings management into dedicated process
**Status:** Design Proposal (Phase 3 of Microservices Architecture)

---

## Problem Statement

`piparty.py` currently manages settings directly, mixing concerns:
- Settings initialization and validation
- File I/O (load/save YAML)
- WebUI integration for settings updates
- Settings distribution to all processes

This makes settings management scattered and hard to monitor.

---

## Proposed Solution

Create a **Settings Process** that centralizes all settings operations with a pub/sub pattern for change notifications.

### Architecture

**Settings Process as Separate Process**
- Runs as independent process
- Owns the settings file (single source of truth)
- Provides request/response for settings queries
- Publishes change events when settings update
- Coordinates between WebUI, Menu, and other processes

---

## Settings Process Responsibilities

### Core Responsibilities

**Settings Lifecycle:**
- Load settings from YAML file on startup
- Validate settings against schema
- Provide default values for missing settings
- Save settings to YAML file on updates

**Settings Queries:**
- Get all settings
- Get individual setting by key
- List available settings

**Settings Updates:**
- Update individual setting
- Validate update before applying
- Save to file atomically
- Notify all subscribers of changes

**Pub/Sub:**
- Allow processes to subscribe to setting changes
- Publish events when settings change
- Support wildcard subscriptions (e.g., "sensitivity.*")

---

## Proposed Architecture

### Process Structure

```
Settings Process
   │
   ├─→ Load settings from joustsettings.yaml
   ├─→ Validate against schema
   ├─→ Listen for IPC commands
   │   - get_settings
   │   - get_setting
   │   - update_setting
   │   - subscribe
   │   - unsubscribe
   │
   ├─→ Process updates
   │   - Validate new value
   │   - Update in-memory settings
   │   - Save to YAML file
   │   - Publish change event
   │
   └─→ Publish to subscribers
       - Send setting_changed event
       - Include old and new values
```

### Integration with Other Processes

```
WebUI Process
    ↓ IPC: update_setting
Settings Process
    ↓ Validates and saves
    ↓ Publishes: setting_changed event
    ↓
    ├─→ Menu Process (subscribed)
    ├─→ ControllerManager Process (subscribed)
    ├─→ GameCoordinator Process (subscribed)
    └─→ WebUI Process (subscribed for confirmation)
```

### Settings Cache Pattern

**Architecture Decision:**

To minimize IPC overhead while maintaining Settings process as source of truth, we use a **cache pattern**:

1. **Settings Process** = Authoritative source
   - Owns the YAML file
   - Validates all updates
   - Publishes change events

2. **piparty.py (Menu Process)** = Cache Layer
   - Subscribes to all setting changes (pattern='*')
   - Maintains `ns.settings` as synchronized cache
   - Updates cache immediately upon receiving events
   - Provides IPC helper methods for updates

3. **Other Processes** = Cache Consumers
   - Read from `ns.settings` (fast, no IPC)
   - No stale data (piparty updates immediately)
   - Only piparty writes to settings (via Settings process)

**Benefits:**
- Fast local reads (no IPC latency)
- Settings process is still source of truth
- No stale data (event-driven updates)
- Less IPC traffic

**Example:**
```python
# ControllerManager reads from cache
sensitivity = self.ns.settings.get('sensitivity', 2)

# GameCoordinator reads from cache
if self.ns.settings.get('enforce_minimum', True):
    # Check minimum players

# piparty updates via Settings process
response = self.send_settings_command('update_setting', {
    'key': 'sensitivity',
    'value': 3
})

# piparty receives event and updates cache
event = self.settings_event_queue.get()
self.ns.settings[event['data']['key']] = event['data']['new_value']
```

---

## Class Design

```python
class SettingsProcess(Process):
    """
    Settings management running as separate process.

    Responsibilities:
    - Load/save settings from/to YAML
    - Validate settings updates
    - Provide query interface via IPC
    - Publish change events (pub/sub)
    """

    def __init__(self, command_queue, response_queue, event_queue, settings_file):
        """Initialize Settings process."""

    def run(self):
        """Main process loop."""

    # Settings Lifecycle
    def load_settings(self) -> dict:
        """Load settings from YAML file."""

    def save_settings(self):
        """Save current settings to YAML file."""

    def initialize_defaults(self) -> dict:
        """Get default settings."""

    def validate_settings(self, settings: dict) -> tuple[bool, str]:
        """Validate settings dict against schema."""

    # Settings Queries
    def get_all_settings(self) -> dict:
        """Get all current settings."""

    def get_setting(self, key: str):
        """Get individual setting value."""

    # Settings Updates
    def update_setting(self, key: str, value) -> bool:
        """Update a setting value."""

    def validate_setting_update(self, key: str, value) -> tuple[bool, str]:
        """Validate a setting update."""

    # Pub/Sub
    def subscribe(self, subscriber_queue, pattern: str = "*"):
        """Subscribe to setting changes."""

    def unsubscribe(self, subscriber_queue):
        """Unsubscribe from setting changes."""

    def publish_change(self, key: str, old_value, new_value):
        """Publish setting change to all subscribers."""

    # IPC Handlers
    def handle_get_settings(self) -> dict:
        """Handle get_settings command."""

    def handle_get_setting(self, params: dict) -> dict:
        """Handle get_setting command."""

    def handle_update_setting(self, params: dict) -> dict:
        """Handle update_setting command."""

    def handle_subscribe(self, params: dict) -> dict:
        """Handle subscribe command."""

    def handle_unsubscribe(self, params: dict) -> dict:
        """Handle unsubscribe command."""
```

---

## IPC Protocol

### Request/Response (Command Queue)

**Commands:**

1. **`get_settings`** - Get all settings
   ```python
   command = {'command': 'get_settings'}
   response = {
       'status': 'success',
       'data': {
           'settings': {
               'sensitivity': 2,
               'play_instructions': True,
               # ... all settings
           }
       }
   }
   ```

2. **`get_setting`** - Get individual setting
   ```python
   command = {'command': 'get_setting', 'params': {'key': 'sensitivity'}}
   response = {
       'status': 'success',
       'data': {'key': 'sensitivity', 'value': 2}
   }
   ```

3. **`update_setting`** - Update a setting
   ```python
   command = {
       'command': 'update_setting',
       'params': {'key': 'sensitivity', 'value': 3}
   }
   response = {
       'status': 'success',
       'data': {
           'key': 'sensitivity',
           'old_value': 2,
           'new_value': 3
       }
   }
   ```

4. **`subscribe`** - Subscribe to setting changes
   ```python
   command = {
       'command': 'subscribe',
       'params': {
           'pattern': '*',  # or 'sensitivity' or 'random_*'
           'event_queue': <queue reference>
       }
   }
   response = {
       'status': 'success',
       'data': {'subscription_id': 'uuid-1234'}
   }
   ```

5. **`unsubscribe`** - Unsubscribe
   ```python
   command = {
       'command': 'unsubscribe',
       'params': {'subscription_id': 'uuid-1234'}
   }
   response = {'status': 'success'}
   ```

### Event Publication (Event Queues)

**Event: `setting_changed`**

```python
event = {
    'event': 'setting_changed',
    'data': {
        'key': 'sensitivity',
        'old_value': 2,
        'new_value': 3,
        'source': 'webui'  # who triggered the change
    },
    'timestamp': 1234567890.123
}
```

---

## Settings Schema

```python
SETTINGS_SCHEMA = {
    'sensitivity': {
        'type': 'int',
        'min': 0,
        'max': 4,
        'default': Sensitivity.MID.value,
        'description': 'Controller sensitivity (0=ultra slow, 4=ultra fast)'
    },
    'play_instructions': {
        'type': 'bool',
        'default': True,
        'description': 'Play voice instructions before games'
    },
    'random_modes': {
        'type': 'list',
        'item_type': 'str',
        'allowed_values': [g.name for g in Games if g != Games.JoustTeams and g != Games.Random],
        'default': ['JoustFFA', 'JoustRandomTeams', 'Werewolf', 'Swapper'],
        'description': 'Game modes included in random selection'
    },
    'current_game': {
        'type': 'str',
        'allowed_values': [g.name for g in Games],
        'default': 'JoustFFA',
        'description': 'Currently selected game mode'
    },
    'play_audio': {
        'type': 'bool',
        'default': True,
        'immutable': True,  # Cannot be changed
        'description': 'Enable audio playback'
    },
    'menu_voice': {
        'type': 'str',
        'allowed_values': ['ivy', 'en', 'es', 'fr', 'de'],
        'default': 'ivy',
        'description': 'Voice pack for menu announcements'
    },
    'move_can_be_admin': {
        'type': 'bool',
        'default': True,
        'immutable': True,
        'description': 'Allow controllers to become admin'
    },
    'enforce_minimum': {
        'type': 'bool',
        'default': True,
        'immutable': True,
        'description': 'Enforce minimum player requirements'
    },
    'red_on_kill': {
        'type': 'bool',
        'default': True,
        'description': 'Flash red when killed'
    },
    'random_teams': {
        'type': 'bool',
        'default': True,
        'description': 'Randomize team assignments'
    },
    'color_lock': {
        'type': 'bool',
        'default': False,
        'description': 'Lock team colors'
    },
    'random_team_size': {
        'type': 'int',
        'min': 2,
        'max': 6,
        'default': 4,
        'description': 'Size of random teams'
    },
    'force_all_start': {
        'type': 'bool',
        'default': False,
        'description': 'Start game with all controllers (even not ready)'
    },
    'color_lock_choices': {
        'type': 'dict',
        'default': {
            2: ['Magenta', 'Green'],
            3: ['Orange', 'Turquoise', 'Purple'],
            4: ['Yellow', 'Green', 'Blue', 'Purple']
        },
        'description': 'Color choices for locked teams'
    }
}
```

---

## Key Features

### 1. Atomic File Updates

```python
def save_settings(self):
    """Save settings atomically (write to temp, then rename)."""
    temp_file = self.settings_file + '.tmp'

    with open(temp_file, 'w') as f:
        yaml.dump(self.settings, f)

    # Atomic rename
    os.replace(temp_file, self.settings_file)

    # Set permissions
    if platform == "linux":
        os.chmod(self.settings_file, 0o666)
```

### 2. Validation Before Update

```python
def update_setting(self, key: str, value) -> bool:
    """Update setting with validation."""
    # Validate key exists
    if key not in SETTINGS_SCHEMA:
        return False, f"Unknown setting: {key}"

    schema = SETTINGS_SCHEMA[key]

    # Check if immutable
    if schema.get('immutable', False):
        return False, f"Setting {key} cannot be changed"

    # Validate type
    if not isinstance(value, schema['type']):
        return False, f"Invalid type for {key}"

    # Validate range/values
    if 'min' in schema and value < schema['min']:
        return False, f"{key} below minimum"
    if 'max' in schema and value > schema['max']:
        return False, f"{key} above maximum"
    if 'allowed_values' in schema and value not in schema['allowed_values']:
        return False, f"{key} not in allowed values"

    # Update
    old_value = self.settings[key]
    self.settings[key] = value

    # Save
    self.save_settings()

    # Publish
    self.publish_change(key, old_value, value)

    return True, "Success"
```

### 3. Pub/Sub Pattern

```python
def subscribe(self, event_queue, pattern: str = "*"):
    """Subscribe to setting changes."""
    subscription_id = str(uuid.uuid4())
    self.subscribers[subscription_id] = {
        'queue': event_queue,
        'pattern': pattern
    }
    return subscription_id

def publish_change(self, key: str, old_value, new_value):
    """Publish change to matching subscribers."""
    event = {
        'event': 'setting_changed',
        'data': {
            'key': key,
            'old_value': old_value,
            'new_value': new_value
        },
        'timestamp': time.time()
    }

    for sub_id, subscriber in self.subscribers.items():
        pattern = subscriber['pattern']

        # Check if pattern matches
        if pattern == "*" or pattern == key or fnmatch.fnmatch(key, pattern):
            try:
                subscriber['queue'].put_nowait(event)
            except:
                logger.warning(f"Failed to send event to subscriber {sub_id}")
```

---

## Integration with Menu

### Startup

```python
# piparty.py Menu.__init__()
if self.use_settings_process:
    logger.info("Starting Settings process")
    self.settings_cmd_queue = Queue()
    self.settings_resp_queue = Queue()
    self.settings_event_queue = Queue()

    self.settings_proc = SettingsProcess(
        command_queue=self.settings_cmd_queue,
        response_queue=self.settings_resp_queue,
        event_queue=self.settings_event_queue,
        settings_file=common.SETTINGSFILE
    )
    self.settings_proc.start()

    # Subscribe to setting changes
    response = self.send_settings_command('subscribe', {
        'pattern': '*',
        'event_queue': self.settings_event_queue
    })

    # Get initial settings
    response = self.send_settings_command('get_settings')
    if response['status'] == 'success':
        self.ns.settings = response['data']['settings']
```

### Settings Updates

```python
# piparty.py Menu.update_setting()
def update_setting(self, key, val):
    if self.use_settings_process:
        # Update via Settings process
        response = self.send_settings_command('update_setting', {
            'key': key,
            'value': val
        })

        if response['status'] == 'success':
            # Update will come via event subscription
            logger.info(f"Setting {key} updated successfully")
        else:
            logger.error(f"Failed to update setting: {response.get('error')}")
    else:
        # Legacy path
        temp_settings = self.ns.settings
        temp_settings[key] = val
        self.ns.settings = temp_settings
        self.update_settings_file()
```

### Checking for Setting Changes

```python
# piparty.py Menu.game_loop()
def game_loop(self):
    while True:
        # ... existing loop code

        self.check_setting_events()  # Check for setting changes

        # ... rest of loop

def check_setting_events(self):
    """Check for setting change events."""
    if not self.use_settings_process:
        return

    try:
        while not self.settings_event_queue.empty():
            event = self.settings_event_queue.get_nowait()

            if event['event'] == 'setting_changed':
                key = event['data']['key']
                new_value = event['data']['new_value']

                # Update local settings
                temp_settings = self.ns.settings
                temp_settings[key] = new_value
                self.ns.settings = temp_settings

                logger.info(f"Setting changed: {key} = {new_value}")

                # React to specific settings
                if key == 'sensitivity':
                    self.update_controller_sensitivity(new_value)
                elif key == 'current_game':
                    self.game_mode = Games[new_value]
    except Exception as e:
        logger.error(f"Error checking setting events: {e}", exc_info=True)
```

---

## Benefits

### 1. Single Source of Truth
- ✅ One process owns settings
- ✅ All updates go through validation
- ✅ Atomic file writes (no corruption)

### 2. Pub/Sub Pattern
- ✅ Processes subscribe to changes they care about
- ✅ No polling required
- ✅ Instant propagation of changes

### 3. Validation
- ✅ Schema-based validation
- ✅ Type checking
- ✅ Range checking
- ✅ Immutable settings protection

### 4. Monitoring
- ✅ Can log all setting changes
- ✅ Can track who changed what
- ✅ Can add metrics (settings changes per minute, etc.)

### 5. Testing
- ✅ Can test settings logic independently
- ✅ Can mock settings for other tests
- ✅ Can verify validation rules

---

## Migration Strategy

### Step 1: Create Settings Process Alongside
- Create `settings_process.py` with full implementation
- Keep existing settings code in piparty.py
- Test Settings process independently

### Step 2: Dual Mode (Feature Flag)
```python
self.use_settings_process = True  # Feature flag
```
- If enabled, use Settings process
- If disabled, use legacy settings
- Test both paths work

### Step 3: Migrate Other Processes
- Update ControllerManager to subscribe to settings
- Update GameCoordinator to subscribe to settings
- Update WebUI to use Settings process

### Step 4: Cut Over
- Make Settings process the default
- Remove legacy settings code from piparty.py

### Step 5: Cleanup
- Remove feature flag
- Final testing
- Documentation

---

## Timeline Estimate

- **Design & Review:** 1 hour (this document) ✅
- **Implementation:** 4-6 hours
  - Core Settings process: 2 hours
  - Validation and schema: 1 hour
  - Pub/sub implementation: 1 hour
  - Integration with Menu: 1 hour
  - Integration with other processes: 1 hour
- **Testing & Validation:** 2-3 hours
- **Total:** 7-10 hours (1 day of focused work)

---

## Success Criteria

### Implementation
- [ ] Settings process starts successfully
- [ ] Can load settings from YAML
- [ ] Can save settings to YAML atomically
- [ ] Validation works correctly
- [ ] Pub/sub delivers events to subscribers
- [ ] IPC commands work

### Testing
- [ ] Unit tests for validation
- [ ] Integration test for IPC
- [ ] Test pub/sub delivery
- [ ] Test all settings can be updated

### Documentation
- [ ] Settings API documented
- [ ] Schema documented
- [ ] Integration guide
- [ ] Migration guide

---

## Next Steps

**For Implementation:**
1. Review and approve this design
2. Create `settings_process.py` skeleton
3. Implement Settings class with validation
4. Implement pub/sub mechanism
5. Integrate with Menu
6. Test incrementally

**For Discussion:**
- Should we add settings history (audit log)?
- Should we support settings hot-reload (watch file)?
- Should we add settings presets (profiles)?

---

## Open Questions

**Q: How do processes get initial settings on startup?**
A: Each process sends `get_settings` command on startup and subscribes to changes.

**Q: What if Settings process crashes?**
A: Settings are persisted to file. On restart, reload from file. Other processes can cache settings locally and continue with last known values.

**Q: How to handle settings that affect multiple processes?**
A: Settings process publishes to all subscribers. Each process reacts to settings it cares about.

**Q: Should WebUI go through Settings process or update ns.settings directly?**
A: WebUI should use Settings process for consistency and validation.

---

## Approval

**Design by:** Claude Sonnet 4.5
**Date:** 2026-01-09
**Status:** Awaiting Review

Once approved, we can proceed with implementation of Phase 3.
