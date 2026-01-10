# JoustMania Process Architecture - Microservices Design

**Date:** 2026-01-09
**Vision:** Modular, observable, microservices-style process architecture
**Goal:** Clear separation of concerns, each process handles subset of logic

---

## Vision: Process-Based Microservices Architecture

Instead of a monolithic main process, JoustMania should be composed of independent processes that communicate via well-defined interfaces. Each process:

- ✅ Has a **single clear responsibility**
- ✅ Runs **independently** (can restart without affecting others)
- ✅ Communicates via **explicit IPC** (queues, pipes, shared memory)
- ✅ Can be **observed independently** (OpenTelemetry per process)
- ✅ Can be **swapped/upgraded** without full system restart
- ✅ Easier to **reason about** (subset of logic per process)

---

## Current Architecture (Before Refactoring)

```
┌─────────────────────────────────────────────────────────┐
│                   Main Process (piparty.py)             │
│  - Menu logic                                           │
│  - Game coordination                                    │
│  - Controller management                                │
│  - Settings                                             │
│  - Everything mixed together (1,242 lines)              │
└────────────┬────────────────────────────────────────────┘
             │
             ├─► Web Server Process (webui.py)
             ├─► Audio Process (piaudio.py) x4
             └─► Controller Processes (controller_process.py) x N
```

**Problems:**
- 💥 Main process does too much
- 💥 Hard to reason about
- 💥 Can't restart components independently
- 💥 Poor observability boundaries
- 💥 Tight coupling

---

## Target Architecture (Process-Based Microservices)

```
┌──────────────────────────────────────────────────────────────┐
│                    Process Supervisor                        │
│  - Starts all processes                                      │
│  - Monitors health                                           │
│  - Restarts on failure                                       │
│  - Minimal logic (~100 lines)                                │
└──────┬───────────────────────────────────────────────────────┘
       │
       ├─► Menu Process (menu_process.py)
       │   - Menu loop and UI
       │   - Game selection
       │   - Start game triggers
       │   - Talks to: ControllerManager, GameCoordinator
       │
       ├─► ControllerManager Process (controller_manager.py)
       │   - Discover/pair controllers
       │   - Spawn controller processes
       │   - Monitor controller health
       │   - Query interface for ready controllers
       │   - Talks to: Controller processes, Menu
       │
       ├─► GameCoordinator Process (game_coordinator.py)
       │   - Initialize games
       │   - Monitor game state
       │   - End game logic
       │   - Talks to: Controller processes, Menu
       │
       ├─► Settings Process (settings_process.py)
       │   - Load/save settings
       │   - Provide settings to other processes
       │   - Update on web UI changes
       │   - Talks to: WebUI, Menu
       │
       ├─► Web Server Process (webui.py)
       │   - Admin interface
       │   - Status display
       │   - Talks to: Settings, ControllerManager, Menu
       │
       ├─► Audio Manager Process (audio_manager.py)
       │   - Manage audio processes
       │   - Music tempo control
       │   - Talks to: GameCoordinator
       │   └─► Audio Worker Processes x4
       │
       └─► Controller Processes (controller_process.py) x N
           - Hardware polling (1000Hz)
           - State management
           - Talks to: ControllerManager (reports health)
```

---

## Process Breakdown

### 1. Process Supervisor (~100 lines)

**Responsibility:** Start, monitor, and restart processes

```python
class ProcessSupervisor:
    """
    Minimal supervisor that starts and monitors all processes.
    """
    def start_all_processes(self):
        """Start all service processes."""

    def monitor_health(self):
        """Check process health, restart if needed."""

    def shutdown_all(self):
        """Graceful shutdown of all processes."""
```

**Why:**
- Single point of initialization
- Automatic restart on failure
- Clean shutdown coordination

---

### 2. ControllerManager Process (~400 lines)

**Responsibility:** Controller lifecycle and health monitoring

```python
class ControllerManagerProcess(Process):
    """
    Manages all Move controllers as separate process.

    Responsibilities:
    - Discover and pair controllers
    - Spawn controller processes
    - Monitor controller health
    - Provide query interface (IPC)
    """

    def run(self):
        """Main loop: discover, pair, monitor."""

    def discover_controllers(self):
        """Check for new USB/BT controllers."""

    def pair_controller(self, move):
        """Spawn tracking process for controller."""

    def monitor_health(self):
        """Check controller process health."""

    def handle_ipc_request(self, request):
        """
        Handle requests from other processes:
        - get_ready_controllers()
        - get_controller_count()
        - get_controller_state(serial)
        """
```

**IPC Interface:**
- **Input:** Command queue (get ready controllers, pair new, etc.)
- **Output:** Response queue (controller lists, state info)
- **Shared Memory:** ControllerState instances (already have this!)

**Benefits:**
- ✅ Isolated controller logic
- ✅ Can restart without affecting menu/game
- ✅ Independent observability
- ✅ Health monitoring in one place

---

### 3. Menu Process (~300 lines)

**Responsibility:** Menu UI and game selection

```python
class MenuProcess(Process):
    """
    Menu interface and game selection.

    Responsibilities:
    - Menu loop
    - Display controller colors
    - Process admin controls
    - Trigger game start
    """

    def run(self):
        """Main menu loop."""

    def update_controller_colors(self):
        """Update LED colors for menu."""

    def check_start_conditions(self):
        """Check if ready to start game."""

    def request_game_start(self, game_mode):
        """Request GameCoordinator to start game."""
```

**IPC Interface:**
- **To ControllerManager:** Get ready controllers, get count
- **To GameCoordinator:** Start game, get game status
- **To Settings:** Get/set settings

**Benefits:**
- ✅ Focused on UI/UX
- ✅ No controller management complexity
- ✅ Easy to modify menu behavior

---

### 4. GameCoordinator Process (~400 lines)

**Responsibility:** Game lifecycle and monitoring

```python
class GameCoordinatorProcess(Process):
    """
    Coordinates game initialization and monitoring.

    Responsibilities:
    - Initialize game instances
    - Monitor game state
    - Detect end conditions
    - Coordinate with controllers
    """

    def run(self):
        """Main coordination loop."""

    def start_game(self, game_mode, controllers):
        """Initialize and start game."""

    def monitor_game_state(self):
        """Check for end conditions."""

    def end_game(self, winner):
        """Handle game end logic."""
```

**IPC Interface:**
- **From Menu:** Start game request
- **To ControllerManager:** Set game mode, get controller states
- **To Menu:** Game ended event

**Benefits:**
- ✅ Game logic isolated
- ✅ Can experiment with different game engines
- ✅ Clean separation from menu

---

### 5. Settings Process (~200 lines)

**Responsibility:** Settings persistence and distribution

```python
class SettingsProcess(Process):
    """
    Manages settings for all processes.

    Responsibilities:
    - Load/save settings
    - Provide settings via IPC
    - Watch for web UI updates
    """

    def run(self):
        """Main settings loop."""

    def load_settings(self):
        """Load from joustsettings.yaml."""

    def save_settings(self):
        """Save to joustsettings.yaml."""

    def handle_setting_request(self, request):
        """Return setting value."""

    def handle_setting_update(self, key, value):
        """Update setting, notify subscribers."""
```

**IPC Interface:**
- **Pub/Sub:** Notify processes of setting changes
- **Request/Response:** Get setting values

**Benefits:**
- ✅ Single source of truth
- ✅ Atomic updates
- ✅ Easy to add validation

---

### 6. Controller Process (Already Exists) (~150 lines)

**Responsibility:** Hardware polling and state management

```python
def state_based_track_move(...):
    """
    Poll hardware at 1000Hz, update shared state.
    Report health to ControllerManager.
    """
```

**Current:** Already a separate process per controller ✅

**Enhancements:**
- Add health reporting to ControllerManager
- Add metrics for observability

---

## Inter-Process Communication (IPC) Design

### Option 1: Multiprocessing Queues (Recommended)

```python
# Command/Response Pattern
controller_manager_cmd = Queue()
controller_manager_resp = Queue()

# Menu → ControllerManager
controller_manager_cmd.put({
    'command': 'get_ready_controllers',
    'params': {'force_all': False}
})
response = controller_manager_resp.get(timeout=1.0)
# {'controllers': ['serial1', 'serial2', ...]}
```

**Pros:**
- ✅ Simple, built-in
- ✅ Type-safe with Python dicts
- ✅ Easy to debug

**Cons:**
- ⚠️ Serialization overhead
- ⚠️ No built-in service discovery

---

### Option 2: Shared Memory + Semaphores

```python
# Use existing ControllerState pattern
# Add command/response shared memory

class IPCChannel:
    def __init__(self):
        self.command = Value('i', 0)  # Command ID
        self.data = Array('c', 1024)  # Command data
        self.ready = Value('b', False)  # Response ready
```

**Pros:**
- ✅ Very fast (no serialization)
- ✅ Already using this pattern

**Cons:**
- ⚠️ More complex
- ⚠️ Fixed size buffers

---

### Option 3: Named Pipes

```python
# Unix domain sockets
import socket

controller_manager_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
controller_manager_socket.bind('/tmp/joustmania_controller_manager.sock')
```

**Pros:**
- ✅ Standard IPC mechanism
- ✅ Can use across processes not parent/child

**Cons:**
- ⚠️ More boilerplate
- ⚠️ Platform-specific

---

**Recommendation:** Start with **Queues** (Option 1), upgrade to **Shared Memory** (Option 2) for hot paths if needed.

---

## IPC Message Protocol

### Standard Message Format

```python
# Command Message
{
    'command': 'get_ready_controllers',
    'params': {
        'force_all': False
    },
    'request_id': 'uuid-1234',  # For tracking
    'timestamp': 1234567890.123
}

# Response Message
{
    'status': 'success',  # or 'error'
    'data': {
        'controllers': ['serial1', 'serial2']
    },
    'request_id': 'uuid-1234',
    'timestamp': 1234567890.456
}

# Event Message (Pub/Sub)
{
    'event': 'controller_connected',
    'data': {
        'serial': 'serial1',
        'battery': 80
    },
    'timestamp': 1234567890.789
}
```

---

## Implementation Phases

### Phase 1: Extract ControllerManager Process ✅

**Goal:** Move controller management to separate process

**Tasks:**
1. Create `controller_manager.py` with process class
2. Implement IPC queues for commands/responses
3. Move controller lifecycle logic
4. Update Menu to use IPC instead of direct calls
5. Test controller pairing/removal via IPC

**Time:** 4-6 hours

---

### Phase 2: Extract GameCoordinator Process

**Goal:** Move game logic to separate process

**Tasks:**
1. Create `game_coordinator.py` with process class
2. Implement IPC for start_game/end_game
3. Move game initialization logic
4. Update Menu to use IPC
5. Test game start/end flow

**Time:** 4-6 hours

---

### Phase 3: Extract Settings Process

**Goal:** Centralize settings management

**Tasks:**
1. Create `settings_process.py`
2. Implement pub/sub for setting changes
3. Move settings load/save logic
4. Update all processes to request settings
5. Test settings updates

**Time:** 2-3 hours

---

### Phase 4: Create Process Supervisor

**Goal:** Unified process management

**Tasks:**
1. Create `process_supervisor.py`
2. Move process startup logic
3. Add health monitoring
4. Add restart logic
5. Test supervisor

**Time:** 3-4 hours

---

### Phase 5: Extract Menu Process

**Goal:** Menu as separate process

**Tasks:**
1. Create `menu_process.py`
2. Menu loop using IPC
3. Test menu → coordinator → controllers flow
4. Integration testing

**Time:** 4-5 hours

---

### Phase 6: Observability Integration

**Goal:** OpenTelemetry per process

**Tasks:**
1. Add OTel spans to each process
2. Add process-level metrics
3. Add IPC tracing
4. Create monitoring dashboard

**Time:** 4-6 hours

---

## Benefits of Process Architecture

### Development & Maintenance
- ✅ **Easier to Understand** - Each process has ~200-400 lines
- ✅ **Easier to Test** - Mock IPC interfaces
- ✅ **Easier to Debug** - Isolate to single process
- ✅ **Easier to Modify** - Change one process without affecting others

### Reliability
- ✅ **Fault Isolation** - Process crash doesn't kill system
- ✅ **Automatic Restart** - Supervisor restarts failed processes
- ✅ **Graceful Degradation** - System continues with reduced functionality

### Performance
- ✅ **True Parallelism** - No GIL limitations
- ✅ **Resource Isolation** - CPU/memory per process
- ✅ **Independent Optimization** - Tune each process separately

### Observability
- ✅ **Per-Process Metrics** - CPU, memory, latency per service
- ✅ **IPC Tracing** - See message flow between processes
- ✅ **Health Monitoring** - Detect and restart unhealthy processes
- ✅ **Clear Boundaries** - Easy to instrument

### Experimentation
- ✅ **Swap Implementations** - Try different controller strategies
- ✅ **A/B Testing** - Run two versions side by side
- ✅ **Feature Flags** - Enable/disable process features
- ✅ **Hot Reload** - Update process without full restart

---

## Migration Strategy

### Step 1: ControllerManager Process (Start Here)
- Highest value, clearest boundaries
- Already have state-based foundation
- Can test in isolation

### Step 2: GameCoordinator Process
- Second highest value
- Clear interface with Menu
- Enables game experimentation

### Step 3: Settings Process
- Relatively simple
- Enables pub/sub pattern
- Good learning ground

### Step 4: Process Supervisor
- Ties everything together
- Enables health monitoring
- Production-ready

### Step 5: Menu Process
- Most complex (many dependencies)
- Do last when other processes stable
- Completes architecture

### Step 6: Observability Enhancement
- Add metrics, tracing
- Create dashboards
- Document patterns

---

## Risk Assessment

### Low Risk ✅
- ControllerManager extraction (clear boundaries)
- Settings process (simple, read-heavy)
- IPC with queues (well-understood)

### Medium Risk ⚠️
- GameCoordinator extraction (complex game logic)
- Menu process extraction (many touch points)
- Process supervision (critical path)

### High Risk 🔴
- IPC performance (might need optimization)
- Deadlock scenarios (careful with multiple queues)
- State synchronization (need clear ownership)

### Mitigation
- ✅ **Feature Flags** - Can rollback to monolithic
- ✅ **Incremental Migration** - One process at a time
- ✅ **Extensive Testing** - IPC integration tests
- ✅ **Monitoring** - Detect issues early

---

## Success Criteria

### Architecture
- [ ] All major components as separate processes
- [ ] Clear IPC interfaces documented
- [ ] Process supervisor managing lifecycle
- [ ] Health monitoring in place

### Code Quality
- [ ] Each process < 500 lines
- [ ] Well-defined IPC protocol
- [ ] No circular dependencies
- [ ] Comprehensive tests

### Functionality
- [ ] All features work as before
- [ ] No performance regression
- [ ] Graceful failure handling
- [ ] Auto-restart on crash

### Observability
- [ ] Per-process metrics
- [ ] IPC tracing
- [ ] Health dashboards
- [ ] Clear error messages

---

## Timeline Estimate

- **Phase 1 (ControllerManager):** 4-6 hours
- **Phase 2 (GameCoordinator):** 4-6 hours
- **Phase 3 (Settings):** 2-3 hours
- **Phase 4 (Supervisor):** 3-4 hours
- **Phase 5 (Menu):** 4-5 hours
- **Phase 6 (Observability):** 4-6 hours

**Total:** 21-30 hours (3-4 days focused work)

---

## Next Steps

**Immediate:**
1. ✅ Review this architecture design
2. ⚠️ Start with ControllerManager process
3. ⚠️ Implement IPC queues
4. ⚠️ Test controller lifecycle via IPC

**This Week:**
- Complete ControllerManager process
- Test with real controllers
- Document IPC protocol

**Next Week:**
- Extract GameCoordinator
- Add process supervisor
- Integration testing

---

## Questions for Discussion

1. **Scope:** Do all phases now, or ControllerManager first then evaluate?
2. **IPC:** Start with Queues or jump to Shared Memory?
3. **Testing:** Should we test state-based tracking first before this refactor?
4. **Timeline:** Is 3-4 days reasonable for your goals?

---

This architecture aligns perfectly with your microservices vision and makes JoustMania much more modular and observable! Ready to start implementing?
