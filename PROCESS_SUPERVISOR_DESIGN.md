# Process Supervisor - Design Document

**Date:** 2026-01-09
**Purpose:** Unified process management and health monitoring
**Status:** Design Proposal (Phase 4 of Microservices Architecture)

---

## Problem Statement

`piparty.py` currently manages all microservice processes manually:
- Starts each process individually in `__init__()`
- No health monitoring after startup
- Manual shutdown coordination in `shutdown()`
- No automatic restart on failure
- No centralized status visibility

This creates:
- **Fragile startup** - If one process fails to start, others may continue
- **Silent failures** - Processes can crash without detection
- **Complex shutdown** - Must manually stop each process
- **Poor observability** - No unified view of process health

---

## Proposed Solution

Create a **Process Supervisor** that manages all microservice processes with health monitoring and automatic recovery.

### Architecture

**ProcessSupervisor as Manager Class**
- Lives in piparty.py (not a separate process)
- Manages lifecycle of all microservice processes
- Monitors health via periodic pings
- Automatically restarts failed processes
- Coordinates startup and shutdown
- Provides status queries

**Why not a separate process?**
- Supervisor needs to monitor and restart processes
- If supervisor is a process, what monitors the supervisor?
- Better to have supervisor as part of main process (piparty.py)
- Reduces complexity (no supervisor IPC needed)

---

## Process Supervisor Responsibilities

### Process Lifecycle Management

**Startup:**
1. Start processes in dependency order:
   - Settings (no dependencies)
   - ControllerManager (depends on Settings)
   - GameCoordinator (depends on ControllerManager, Settings)
2. Wait for each process to initialize
3. Verify initial health check
4. Register process in tracking registry

**Shutdown:**
1. Stop processes in reverse dependency order:
   - GameCoordinator first
   - ControllerManager second
   - Settings last
2. Send graceful shutdown command
3. Wait for clean exit (timeout)
4. Force terminate if needed

### Health Monitoring

**Periodic Health Checks:**
- Ping each process every 5 seconds
- Check if process is still alive (`is_alive()`)
- Optional: IPC health check (send ping command)
- Track last successful health check time

**Failure Detection:**
- Process crashes (no longer alive)
- Process hung (doesn't respond to ping)
- Process error (reports unhealthy status)

**Automatic Recovery:**
- Detect failure within 5 seconds
- Log failure details
- Attempt restart (up to 3 times)
- If restart fails repeatedly, disable process and alert
- Preserve state where possible

### Status Queries

**Process Status Info:**
- Process name and PID
- Status: starting, running, stopping, stopped, failed
- Uptime
- Restart count
- Last health check time
- Last error (if any)

---

## Proposed Architecture

### Class Design

```python
class ProcessInfo:
    """Information about a managed process."""
    def __init__(self, name: str, process: Process, ...):
        self.name = name
        self.process = process
        self.status = ProcessStatus.STARTING
        self.start_time = time.time()
        self.last_health_check = time.time()
        self.restart_count = 0
        self.last_error = None

class ProcessSupervisor:
    """
    Manages lifecycle and health of all microservice processes.

    Responsibilities:
    - Start processes in dependency order
    - Monitor process health
    - Restart failed processes
    - Coordinate graceful shutdown
    - Provide status queries
    """

    def __init__(self, piparty_instance):
        self.piparty = piparty_instance
        self.processes: Dict[str, ProcessInfo] = {}
        self.running = False
        self.monitor_thread = None

    # Lifecycle
    def start_all_processes(self):
        """Start all microservice processes in dependency order."""

    def stop_all_processes(self):
        """Stop all processes in reverse dependency order."""

    def start_process(self, name: str, factory_func, dependencies: List[str] = None):
        """Start a single process with dependency checking."""

    def stop_process(self, name: str, timeout: float = 5.0):
        """Stop a single process gracefully."""

    # Health Monitoring
    def start_monitoring(self):
        """Start health monitoring thread."""

    def stop_monitoring(self):
        """Stop health monitoring thread."""

    def monitor_loop(self):
        """Continuous health monitoring loop."""

    def check_process_health(self, name: str) -> bool:
        """Check if process is healthy."""

    def restart_process(self, name: str):
        """Restart a failed process."""

    # Status Queries
    def get_status(self) -> Dict[str, ProcessInfo]:
        """Get status of all managed processes."""

    def get_process_status(self, name: str) -> ProcessInfo:
        """Get status of specific process."""

    def is_all_healthy(self) -> bool:
        """Check if all processes are healthy."""
```

---

## Process Registry

### Process Definitions

```python
PROCESS_REGISTRY = {
    'Settings': {
        'factory': create_settings_process,
        'dependencies': [],
        'restart_on_failure': True,
        'max_restarts': 3,
        'health_check_interval': 5.0,
        'critical': True  # System cannot function without this
    },
    'ControllerManager': {
        'factory': create_controller_manager_process,
        'dependencies': ['Settings'],
        'restart_on_failure': True,
        'max_restarts': 3,
        'health_check_interval': 5.0,
        'critical': True
    },
    'GameCoordinator': {
        'factory': create_game_coordinator_process,
        'dependencies': ['Settings', 'ControllerManager'],
        'restart_on_failure': True,
        'max_restarts': 3,
        'health_check_interval': 5.0,
        'critical': False  # Can operate without games
    }
}
```

---

## Startup Sequence

### Ordered Startup

```python
def start_all_processes(self):
    """
    Start processes in dependency order.

    Order:
    1. Settings (no dependencies)
    2. ControllerManager (depends on Settings)
    3. GameCoordinator (depends on ControllerManager, Settings)
    """

    # Start Settings
    logger.info("Starting Settings process...")
    self.start_process('Settings')
    self.wait_for_process_ready('Settings', timeout=5.0)

    # Start ControllerManager
    logger.info("Starting ControllerManager process...")
    self.start_process('ControllerManager')
    self.wait_for_process_ready('ControllerManager', timeout=5.0)

    # Start GameCoordinator
    logger.info("Starting GameCoordinator process...")
    self.start_process('GameCoordinator')
    self.wait_for_process_ready('GameCoordinator', timeout=5.0)

    logger.info("All processes started successfully")

    # Start health monitoring
    self.start_monitoring()
```

### Process Ready Check

```python
def wait_for_process_ready(self, name: str, timeout: float = 5.0):
    """
    Wait for process to be ready.

    Checks:
    1. Process is alive
    2. Process responds to ping (optional)
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        proc_info = self.processes[name]

        if not proc_info.process.is_alive():
            raise ProcessError(f"{name} process died during startup")

        # Optional: Send IPC ping
        if self.ping_process(name):
            proc_info.status = ProcessStatus.RUNNING
            return True

        time.sleep(0.1)

    raise ProcessError(f"{name} process did not become ready within {timeout}s")
```

---

## Health Monitoring

### Monitoring Thread

```python
def monitor_loop(self):
    """
    Continuous health monitoring loop.

    Runs in separate thread, checks all processes periodically.
    """
    logger.info("Health monitoring started")

    while self.running:
        try:
            for name, proc_info in list(self.processes.items()):
                # Skip if process is not supposed to be running
                if proc_info.status not in [ProcessStatus.RUNNING, ProcessStatus.STARTING]:
                    continue

                # Check if process is alive
                if not proc_info.process.is_alive():
                    logger.error(f"{name} process died unexpectedly")
                    self.handle_process_failure(name)
                    continue

                # Optional: Send IPC health check
                if not self.check_process_health(name):
                    logger.warning(f"{name} process not responding to health check")
                    self.handle_process_failure(name)

                # Update last health check time
                proc_info.last_health_check = time.time()

        except Exception as e:
            logger.error(f"Error in health monitoring: {e}", exc_info=True)

        # Sleep between checks
        time.sleep(5.0)

    logger.info("Health monitoring stopped")
```

### Failure Handling

```python
def handle_process_failure(self, name: str):
    """
    Handle process failure.

    Strategy:
    1. Log failure details
    2. Check restart count
    3. If under max_restarts, restart process
    4. If over limit, mark as failed and alert
    """
    proc_info = self.processes[name]

    # Update status
    proc_info.status = ProcessStatus.FAILED
    proc_info.restart_count += 1

    # Log failure
    logger.error(f"{name} process failed (restart count: {proc_info.restart_count})")

    # Check if we should restart
    config = PROCESS_REGISTRY[name]
    if not config['restart_on_failure']:
        logger.info(f"{name} restart disabled, not restarting")
        return

    if proc_info.restart_count > config['max_restarts']:
        logger.error(f"{name} exceeded max restarts ({config['max_restarts']}), giving up")
        if config['critical']:
            logger.critical(f"Critical process {name} failed permanently!")
        return

    # Attempt restart
    logger.info(f"Attempting to restart {name}...")
    try:
        self.restart_process(name)
        logger.info(f"{name} restarted successfully")
    except Exception as e:
        logger.error(f"Failed to restart {name}: {e}", exc_info=True)
        proc_info.last_error = str(e)
```

---

## Shutdown Sequence

### Graceful Shutdown

```python
def stop_all_processes(self):
    """
    Stop all processes in reverse dependency order.

    Order:
    1. GameCoordinator (depends on others)
    2. ControllerManager (depends on Settings)
    3. Settings (no dependencies)
    """

    logger.info("Stopping all processes...")

    # Stop health monitoring first
    self.stop_monitoring()

    # Stop in reverse order
    self.stop_process('GameCoordinator', timeout=5.0)
    self.stop_process('ControllerManager', timeout=5.0)
    self.stop_process('Settings', timeout=5.0)

    logger.info("All processes stopped")

def stop_process(self, name: str, timeout: float = 5.0):
    """
    Stop a process gracefully.

    Steps:
    1. Send shutdown command via IPC
    2. Wait for process to exit (timeout)
    3. If still alive, terminate forcefully
    """
    if name not in self.processes:
        return

    proc_info = self.processes[name]

    if not proc_info.process.is_alive():
        logger.info(f"{name} already stopped")
        proc_info.status = ProcessStatus.STOPPED
        return

    logger.info(f"Stopping {name} process...")
    proc_info.status = ProcessStatus.STOPPING

    # Send shutdown command
    try:
        self.piparty.send_shutdown_to_process(name)
    except:
        pass

    # Wait for clean exit
    proc_info.process.join(timeout=timeout)

    # Force terminate if needed
    if proc_info.process.is_alive():
        logger.warning(f"{name} didn't stop gracefully, terminating")
        proc_info.process.terminate()
        proc_info.process.join(timeout=2.0)

    proc_info.status = ProcessStatus.STOPPED
    logger.info(f"{name} stopped")
```

---

## Integration with piparty.py

### Modified Initialization

```python
class Menu:
    def __init__(self):
        # Feature flags
        self.use_process_supervisor = True

        # Create supervisor
        if self.use_process_supervisor:
            self.supervisor = ProcessSupervisor(self)

            # Start all processes via supervisor
            self.supervisor.start_all_processes()
        else:
            # Legacy: Start processes manually
            self.start_settings_process()
            self.start_controller_manager()
            self.start_game_coordinator()
```

### Modified Shutdown

```python
def shutdown(self):
    """Graceful shutdown."""
    logger.info("Shutting down JoustMania...")

    if self.use_process_supervisor:
        # Use supervisor for coordinated shutdown
        self.supervisor.stop_all_processes()
    else:
        # Legacy: Stop manually
        self.stop_game_coordinator()
        self.stop_controller_manager()
        self.stop_settings()

    logger.info("Shutdown complete")
```

### Status Queries

```python
def get_system_status(self):
    """Get status of all processes."""
    if self.use_process_supervisor:
        return self.supervisor.get_status()
    else:
        # Legacy: Manual status check
        return self.check_processes_manually()
```

---

## Health Check Protocol

### Optional IPC Health Check

If processes support health checks:

```python
def check_process_health(self, name: str) -> bool:
    """
    Send health check ping to process.

    Returns:
        True if process responds, False otherwise
    """
    try:
        # Send ping command
        response = self.piparty.send_command_to_process(
            name, 'ping', timeout=1.0
        )

        return response['status'] == 'success'
    except:
        return False
```

Each process can implement a simple ping handler:

```python
# In Settings/ControllerManager/GameCoordinator
def handle_ping(self, params: dict) -> dict:
    """Handle health check ping."""
    return {
        'status': 'success',
        'data': {
            'healthy': True,
            'uptime': time.time() - self.start_time
        }
    }
```

---

## Benefits

### 1. Unified Process Management
- ✅ Single point of control for all processes
- ✅ Consistent startup/shutdown
- ✅ Dependency-aware ordering
- ✅ Simplified error handling

### 2. Automatic Recovery
- ✅ Failed processes restarted automatically
- ✅ Reduces manual intervention
- ✅ Configurable restart policies
- ✅ Better uptime

### 3. Observability
- ✅ Centralized status visibility
- ✅ Process health metrics
- ✅ Restart counts and errors
- ✅ Easy integration with monitoring

### 4. Robustness
- ✅ Graceful degradation (non-critical processes can fail)
- ✅ Prevents cascade failures
- ✅ Better startup error handling
- ✅ Coordinated shutdown

---

## Implementation Challenges

### Challenge 1: Restart State Preservation

**Problem:** When restarting a process, how do we preserve state?

**Solution:** Depends on process type:
- **Settings:** State is in YAML file (automatically reloaded)
- **ControllerManager:** Controllers are rediscovered automatically
- **GameCoordinator:** If game in progress, state is lost (acceptable)

### Challenge 2: Dependency Cascades

**Problem:** If Settings fails, should we restart ControllerManager too?

**Solution:**
- Restart Settings first
- Check if dependents are still healthy
- If dependents use cached data (like ns.settings), they may continue working
- Only restart dependents if they actually fail

### Challenge 3: Monitoring Overhead

**Problem:** Health checks add IPC overhead.

**Solution:**
- Use simple `is_alive()` checks (no IPC)
- Optional IPC ping for deeper health checks
- Configurable health check intervals (default 5s)
- Keep monitoring lightweight

---

## Migration Strategy

### Step 1: Create ProcessSupervisor Class
- Implement ProcessSupervisor in new file
- Add ProcessInfo and ProcessStatus classes
- No integration yet, just core functionality

### Step 2: Integrate with piparty.py (Feature Flag)
```python
self.use_process_supervisor = True  # Feature flag
```
- If enabled, use ProcessSupervisor
- If disabled, use legacy startup/shutdown
- Test both paths work

### Step 3: Add Health Monitoring
- Start monitoring thread after processes start
- Log health check results
- Don't restart yet, just observe

### Step 4: Enable Automatic Restart
- Add restart logic
- Test failure scenarios
- Tune restart policies

### Step 5: Cleanup
- Remove legacy startup/shutdown code
- Remove feature flag
- Update documentation

---

## Testing Strategy

### Unit Tests
- ProcessSupervisor startup/shutdown
- Dependency ordering
- Status tracking
- Restart logic

### Integration Tests
- Start all processes
- Kill a process, verify restart
- Verify shutdown order
- Test startup failures

### Manual Tests
- Kill process manually, observe restart
- Check system status
- Verify graceful shutdown
- Test max restart limit

---

## Success Criteria

### Implementation
- [ ] ProcessSupervisor class created
- [ ] Dependency-aware startup
- [ ] Graceful shutdown
- [ ] Health monitoring thread
- [ ] Automatic restart on failure
- [ ] Status queries
- [ ] Integration with piparty.py

### Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual failure recovery verified
- [ ] Startup/shutdown tested

### Documentation
- [ ] Design document (this file)
- [ ] API documentation
- [ ] Integration guide
- [ ] Migration notes

---

## Next Steps

**For Implementation:**
1. Create `process_supervisor.py` with ProcessSupervisor class
2. Add process factory functions
3. Integrate with piparty.py behind feature flag
4. Test startup/shutdown
5. Add health monitoring
6. Test restart scenarios

**For Discussion:**
- Should health checks use IPC or just `is_alive()`?
- What's the right restart delay?
- Should we add process metrics (CPU, memory)?
- How to handle cascading failures?

---

## Approval

**Design by:** Claude Sonnet 4.5
**Date:** 2026-01-09
**Status:** Awaiting Implementation

Once approved, we can proceed with implementation.
