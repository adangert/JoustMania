# Menu Service Architecture Refactor Plan

## Current State

After dead code removal, `server.py` is ~1610 lines with mixed responsibilities:
- gRPC request handlers
- Button monitoring loops
- LED control
- Audio control
- Settings management
- Controller state handling
- Admin mode integration

## Proposed Architecture

### Core Principle: State-Based Controller Handling

Each controller exists in one of three states:
- **Connected**: Newly connected, not ready (dim LED)
- **Ready**: Trigger pressed, waiting to play (bright LED)
- **Admin**: In admin mode (white LED, special commands)

Each state has its own handler that processes only relevant button events.

### Directory Structure

```
services/menu/
├── server.py              # Thin gRPC servicer - delegates to components
├── state_manager.py       # ControllerStateManager - tracks all controller state
├── admin_mode.py          # AdminModeHandler (already exists)
├── handlers/
│   ├── __init__.py
│   ├── base.py            # Protocol/base for handlers
│   ├── connected.py       # ConnectedControllerHandler
│   └── ready.py           # ReadyControllerHandler
└── utils/
    ├── __init__.py
    ├── led.py             # LedController - LED color management
    ├── audio.py           # AudioHelper - sound/voice/music
    └── settings.py        # SettingsHelper - settings load/save
```

### Component Responsibilities

#### 1. MenuServicer (server.py) - ~300 lines
- gRPC handlers only: StartMenu, StopMenu, GetMenuStatus, ProcessInput, StreamMenuEvents
- Lifecycle management (start/stop monitors)
- Delegates button events to StateManager
- Owns event_subscribers and publish_event

#### 2. ControllerStateManager (state_manager.py) - ~200 lines
Central coordinator for controller states:
```python
class ControllerStateManager:
    def __init__(self, handlers: dict[str, ControllerHandler], utils: MenuUtils):
        self.handlers = handlers  # {"connected": ..., "ready": ..., "admin": ...}
        self.controller_states: dict[str, str] = {}  # {serial: state_name}
        self.connected_controllers: set[str] = set()
        self.ready_controllers: set[str] = set()

    async def handle_button_event(self, serial: str, button: str):
        state = self.controller_states.get(serial, "connected")
        await self.handlers[state].handle_button(serial, button)

    def transition_to(self, serial: str, new_state: str):
        old_state = self.controller_states.get(serial, "connected")
        self.controller_states[serial] = new_state
        # Update sets, notify handlers, etc.
```

#### 3. ControllerHandler Protocol (handlers/base.py)
```python
class ControllerHandler(Protocol):
    async def handle_button(self, serial: str, button: str) -> None: ...
    async def on_enter(self, serial: str) -> None: ...
    async def on_exit(self, serial: str) -> None: ...
    def handles_button(self, button: str) -> bool: ...
```

#### 4. ConnectedControllerHandler (handlers/connected.py) - ~100 lines
Handles controllers that are connected but not ready:
- **Trigger**: Transition to "ready" state
- **Move**: Cycle game modes
- **Admin combo**: Transition to "admin" state

#### 5. ReadyControllerHandler (handlers/ready.py) - ~100 lines
Handles controllers that are ready to play:
- **Move**: Transition back to "connected" (un-ready)
- **Trigger**: Start game if all ready
- **Admin combo**: Transition to "admin" state

#### 6. AdminModeHandler (admin_mode.py) - Already exists
Handles admin mode commands. Already extracted!

#### 7. Utility Classes (utils/)

**LedController** - ~150 lines
```python
class LedController:
    def __init__(self, controller_channel, game_mode_colors: dict):
        self.channel = controller_channel
        self.colors = game_mode_colors
        self.button_stream_queue = None

    async def set_connected_color(self, serial: str, game_mode: str): ...
    async def set_ready_color(self, serial: str, game_mode: str): ...
    async def set_admin_color(self, serial: str): ...
    async def send_base_color(self, serial: str, color: tuple): ...
    async def send_game_effect(self, serial: str, effect: int): ...
```

**AudioHelper** - ~100 lines
```python
class AudioHelper:
    def __init__(self, audio_channel, voice_actor: str = "ivy"):
        self.channel = audio_channel
        self.voice_actor = voice_actor

    async def play_sound(self, sound: Sound, volume: float = 0.8): ...
    async def play_voice(self, sound: Sound, volume: float = 0.9): ...
    async def start_lobby_music(self): ...
    async def stop_lobby_music(self): ...
```

**SettingsHelper** - ~80 lines
```python
class SettingsHelper:
    def __init__(self, settings_channel):
        self.channel = settings_channel

    async def load_voice_actor(self) -> str: ...
    async def load_current_game(self) -> str: ...
    async def save_current_game(self, game: str): ...
    async def get_setting(self, key: str) -> str: ...
    async def set_setting(self, key: str, value: str): ...
```

### Data Flow

```
Button Event
    │
    ▼
MenuServicer._button_event_loop()
    │
    ▼
ControllerStateManager.handle_button_event(serial, button)
    │
    ├─ controller_states[serial] == "connected"
    │       │
    │       ▼
    │   ConnectedControllerHandler.handle_button(serial, button)
    │       │
    │       └─ May call: state_manager.transition_to(serial, "ready")
    │
    ├─ controller_states[serial] == "ready"
    │       │
    │       ▼
    │   ReadyControllerHandler.handle_button(serial, button)
    │       │
    │       └─ May call: state_manager.start_game()
    │
    └─ controller_states[serial] == "admin"
            │
            ▼
        AdminModeHandler.handle_button_event(serial, button)
```

### Benefits

1. **Single Responsibility**: Each handler does one thing
2. **Open/Closed**: Add new states without modifying existing handlers
3. **Testability**: Test each handler in isolation with mock utils
4. **Maintainability**: ~100-200 line files instead of 1600+
5. **Dependency Injection**: Utils passed via constructor

### Implementation Order

1. **Phase 1: Extract Utilities** (Low risk)
   - Create utils/led.py - extract LED control methods
   - Create utils/audio.py - extract audio methods
   - Create utils/settings.py - extract settings methods
   - Wire utilities into MenuServicer via constructor

2. **Phase 2: Create State Manager** (Medium risk)
   - Create state_manager.py with state tracking
   - Move connected_controllers, ready_controllers to StateManager
   - Keep button handling in MenuServicer temporarily

3. **Phase 3: Extract Connected Handler** (Medium risk)
   - Create handlers/connected.py
   - Move trigger/move handling for connected state
   - Wire into StateManager

4. **Phase 4: Extract Ready Handler** (Medium risk)
   - Create handlers/ready.py
   - Move game start logic
   - Wire into StateManager

5. **Phase 5: Integrate Admin Handler** (Low risk)
   - AdminModeHandler already exists
   - Just wire it into StateManager

6. **Phase 6: Simplify MenuServicer** (Low risk)
   - Remove migrated code
   - MenuServicer becomes thin delegation layer

### Testing Strategy

Each phase should:
1. Not break existing functionality
2. Add unit tests for new components
3. Run integration tests after each phase

### Estimated Impact

| Component | Current Lines | After Refactor |
|-----------|--------------|----------------|
| server.py | 1610 | ~300 |
| state_manager.py | 0 | ~200 |
| handlers/connected.py | 0 | ~100 |
| handlers/ready.py | 0 | ~100 |
| utils/led.py | 0 | ~150 |
| utils/audio.py | 0 | ~100 |
| utils/settings.py | 0 | ~80 |
| admin_mode.py | ~400 | ~400 |
| **Total** | **2010** | **~1430** |

The total line count may decrease slightly due to reduced duplication, but more importantly the code will be organized into focused, testable modules.
