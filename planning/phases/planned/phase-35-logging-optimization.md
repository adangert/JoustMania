# Phase 35: Logging Optimization

**Status:** 🔍 PLANNED
**Priority:** MEDIUM

## Goal
Reduce logging overhead and improve log quality by cleaning up excessive logging

## Motivation
- High-frequency DEBUG logs running at INFO level
- 200-300 log lines/minute during gameplay (excessive)
- Controller state updates logged every 16.7ms (60 Hz)
- Button press events logged individually (spam)
- Logs are noisy - hard to find important events
- ~5% CPU wasted on unnecessary string formatting and I/O

## Current Issues

**Excessive Logging Examples:**

```python
# Controller Manager - logs every 16.7ms
logger.info(f"Controller {serial} state: buttons={buttons}, accel={accel}")  # 480 logs/sec

# Game Coordinator - logs every frame
logger.info(f"Processing frame for {len(players)} players")  # 60 logs/sec

# Menu - logs every button check
logger.info(f"Checking button state for {serial}")  # 120+ logs/sec

# Settings - logs every setting read
logger.info(f"Getting setting: {key}")  # 50+ logs/sec
```

**Impact:**
- Log volume: 200-300 lines/minute (16,000-18,000 lines/hour)
- CPU overhead: ~5% (string formatting, I/O)
- Log files: 10-15 MB/hour
- Signal-to-noise ratio: Poor (hard to find important events)

## Tasks

### 1. Audit and Cleanup Logger Levels
- [ ] Controller Manager - reduce high-frequency logs
  - [ ] `logger.info("Controller state...")` → `logger.debug()`
  - [ ] `logger.info("Button pressed...")` → `logger.debug()`
  - [ ] `logger.info("Battery level...")` → `logger.debug()` (unless low)
  - [ ] Keep INFO for: controller paired, removed, connection lost
  - **Files:** `services/controller_manager/server.py`

- [ ] Game Coordinator - reduce game loop logs
  - [ ] `logger.info("Processing frame...")` → `logger.debug()`
  - [ ] `logger.info("Player state...")` → `logger.debug()`
  - [ ] Keep INFO for: game start, game end, player death, victory
  - **Files:** `services/game_coordinator/games/*.py`

- [ ] Menu - reduce button check logs
  - [ ] `logger.info("Checking button...")` → `logger.debug()`
  - [ ] `logger.info("Button state...")` → `logger.debug()`
  - [ ] Keep INFO for: game selected, admin mode entered
  - **Files:** `services/menu/server.py`

- [ ] Settings - reduce setting access logs
  - [ ] `logger.info("Getting setting...")` → `logger.debug()`
  - [ ] `logger.info("Setting value...")` → `logger.debug()`
  - [ ] Keep INFO for: setting changed, settings saved to file
  - **Files:** `services/settings/server.py`

- [ ] All services - reduce gRPC call logs
  - [ ] `logger.info("gRPC call received...")` → `logger.debug()`
  - [ ] `logger.info("Creating channel...")` → `logger.debug()`
  - [ ] Keep INFO for: service startup, shutdown, errors

### 2. Define INFO Level Standards
- [ ] Document what should be INFO level
  - **Lifecycle events:** Service startup, shutdown, restart
  - **User actions:** Game selected, game started, admin mode entered
  - **Significant events:** Player death, victory, controller paired/removed
  - **Configuration:** Settings changed, files saved
  - **Errors and warnings:** All errors at WARNING or ERROR level

- [ ] Document what should be DEBUG level
  - **High-frequency updates:** Controller state, game ticks, button checks
  - **Internal operations:** gRPC calls, cache hits, queue operations
  - **Detailed state:** Player positions, acceleration values, battery levels
  - **Performance metrics:** Frame times, processing durations

### 3. Add Environment Variable Controls
- [ ] Add global log level control
  - [ ] Environment variable: `LOG_LEVEL` (DEBUG, INFO, WARNING, ERROR)
  - [ ] Default: INFO in production, DEBUG in development
  - [ ] Apply to all services
  - **Files:** All service `server.py` files

```python
import os
import logging

def setup_logging(service_name: str):
    """Configure logging for service."""
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(levelname)s - %(name)s - %(message)s'
    )

    logger = logging.getLogger(service_name)
    logger.setLevel(log_level)
    return logger
```

- [ ] Add per-service log level overrides
  - [ ] `SETTINGS_LOG_LEVEL` for settings service
  - [ ] `CONTROLLER_LOG_LEVEL` for controller-manager
  - [ ] `GAME_LOG_LEVEL` for game-coordinator
  - [ ] `MENU_LOG_LEVEL` for menu
  - [ ] Pattern: `{SERVICE_NAME}_LOG_LEVEL`

```python
def setup_logging(service_name: str):
    """Configure logging with per-service override."""
    # Global default
    global_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    # Per-service override
    service_key = f"{service_name.upper().replace('-', '_')}_LOG_LEVEL"
    log_level = os.getenv(service_key, global_level)

    # ...
```

### 4. Optimize Log Formatting
- [ ] Remove unnecessary timestamps
  - [ ] Docker logs / journald already add timestamps
  - [ ] Simplify format for high-frequency logs
  - [ ] Keep structured logging for critical events

```python
# BEFORE (complex format with redundant timestamp)
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s:%(lineno)d - %(message)s'
)

# AFTER (simplified format)
logging.basicConfig(
    format='%(levelname)s - %(name)s - %(message)s'
)
```

- [ ] Add structured logging for critical events
  - [ ] Use JSON format for machine-parseable logs
  - [ ] Include context: game_id, controller_serial, etc.
  - [ ] Only for INFO+ level logs

```python
import json

def log_event(logger, level, event_type, **context):
    """Log structured event."""
    log_data = {
        'event': event_type,
        **context
    }
    logger.log(level, json.dumps(log_data))

# Usage
log_event(logger, logging.INFO, 'game_started',
          game_id=game_id, players=player_count, mode=game_mode)
```

### 5. Add Log Sampling for High-Frequency Events
- [ ] Sample high-frequency logs if needed
  - [ ] Log every Nth occurrence instead of every occurrence
  - [ ] Example: Log controller state every 60 frames (1 Hz) instead of every frame (60 Hz)
  - **Files:** High-frequency logging locations

```python
class RateLimitedLogger:
    """Logger that only logs every Nth call."""

    def __init__(self, logger, rate_limit_n=60):
        self.logger = logger
        self.rate_limit_n = rate_limit_n
        self.call_count = 0

    def debug_sampled(self, message, *args):
        """Log at DEBUG level, but only every Nth call."""
        self.call_count += 1
        if self.call_count % self.rate_limit_n == 0:
            self.logger.debug(message, *args)

# Usage - log controller state once per second instead of 60 times
rate_limited_logger = RateLimitedLogger(logger, rate_limit_n=60)
rate_limited_logger.debug_sampled("Controller state: %s", state)
```

### 6. Documentation
- [ ] Create logging guidelines document
  - [ ] When to use each log level
  - [ ] How to set log levels via environment variables
  - [ ] Examples of good vs bad logging
  - **Files:** `docs/LOGGING_GUIDELINES.md` (new)

- [ ] Update service README files
  - [ ] Document log level environment variables
  - [ ] Document per-service overrides
  - [ ] Add troubleshooting section

## Expected Improvements

**Log Volume:**
- Before: 200-300 lines/minute (18,000 lines/hour)
- After: 20-40 lines/minute (2,400 lines/hour)
- Reduction: -80-90%

**CPU Usage:**
- Before: ~5% on logging (string formatting, I/O)
- After: ~1% on logging
- Reduction: -4% overall CPU

**Log Quality:**
- Signal-to-noise ratio: Dramatically improved
- Important events easy to find
- Debugging easier with DEBUG level when needed
- Production logs clean and actionable

**Disk Usage:**
- Before: 10-15 MB/hour log files
- After: 1-2 MB/hour log files
- Reduction: -85-90%

## Success Criteria

- ✅ INFO level logs readable and actionable
- ✅ No DEBUG logs in production (LOG_LEVEL=INFO)
- ✅ Log volume < 100 lines/minute during gameplay
- ✅ Critical events always logged at INFO/WARNING
- ✅ Can enable DEBUG logging via environment variable
- ✅ CPU overhead < 1%
- ✅ Logs useful for troubleshooting without noise

## Configuration Examples

**Development:**
```bash
export LOG_LEVEL=DEBUG  # See all logs
```

**Production:**
```bash
export LOG_LEVEL=INFO  # Only important events
```

**Debugging specific service:**
```bash
export LOG_LEVEL=INFO
export CONTROLLER_LOG_LEVEL=DEBUG  # Only debug controller-manager
```

## Dependencies

- None - can be implemented anytime
- Independent of Phase 18 and Phase 27
- Complements other optimization phases

## Testing

- [ ] Verify log volume reduction in production mode
- [ ] Test DEBUG mode still shows all logs
- [ ] Test per-service overrides work
- [ ] Ensure critical events still logged
- [ ] Measure CPU impact of logging
- [ ] Review logs for quality and usefulness
