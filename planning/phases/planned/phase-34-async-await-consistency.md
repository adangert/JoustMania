# Phase 34: Async/Await Consistency

**Status:** ⚡ PLANNED
**Priority:** LOW - Technical correctness

## Goal
Fix sync/async mixing and use proper async patterns throughout

## Motivation
- Some services mix sync and async gRPC calls
- Settings loads use synchronous calls in async functions
- Event queues use threading.Queue instead of asyncio.Queue
- Blocking operations in async contexts cause performance issues

## Tasks

**1. Settings Service - Async Streams**
- [ ] Convert SubscribeToChanges to async stream
  - [ ] Use `asyncio.Queue` instead of `queue.Queue`
  - [ ] Use `async def` and `await`
  - **Files:** `services/settings/server.py:533-565`

```python
async def SubscribeToChanges(self, request, context):
    """Stream setting change events (async)."""
    subscriber_id = f"settings_sub_{time.time()}"
    event_queue = asyncio.Queue(maxsize=100)

    async with self.event_lock:
        self.event_subscribers[subscriber_id] = event_queue

    try:
        while not context.cancelled():
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                yield event
            except asyncio.TimeoutError:
                continue
    finally:
        async with self.event_lock:
            del self.event_subscribers[subscriber_id]
```

**2. Game Modes - Async Settings Loads**
- [ ] Use async gRPC stubs for Settings service
  - [ ] Create async channel: `grpc.aio.insecure_channel`
  - [ ] Await Settings calls: `await self.settings_client.GetSettings(...)`
  - [ ] Add timeout: `asyncio.wait_for(..., timeout=2.0)`
  - **Files:** `services/game_coordinator/games/ffa.py:93-117`, `teams.py:128-152`, `random_teams.py:158-182`

```python
async def _load_settings(self):
    """Fetch game settings from Settings service (async)."""
    try:
        response = await asyncio.wait_for(
            self.settings_client.GetSettings(settings_pb2.GetSettingsRequest()),
            timeout=2.0
        )
        # ... process settings
    except asyncio.TimeoutError:
        logger.error("Settings service timeout")
        # Use defaults
```

**3. Event Publishing - Async Queues**
- [ ] Replace `queue.Queue` with `asyncio.Queue`
  - [ ] GameCoordinator event subscribers
  - [ ] Menu event subscribers
  - [ ] Settings event subscribers
  - **Files:** `services/game_coordinator/server.py:508-519`, `services/menu/server.py:328-339`, `services/settings/server.py:378-395`

```python
async def _publish_event(self, event_type: str, data: Dict[str, str]):
    """Publish event to all subscribers (async)."""
    event = game_coordinator_pb2.GameEvent(
        event_type=event_type,
        data=data,
        timestamp=int(time.time() * 1000)
    )

    async with self.event_lock:
        for sub_id, event_queue in self.event_subscribers.items():
            try:
                await event_queue.put(event)
            except asyncio.QueueFull:
                logger.warning(f"Event queue full for subscriber {sub_id}")
```

**4. File I/O - Use aiofiles**
- [ ] Replace synchronous file operations with async
  - [ ] Settings service YAML save/load
  - [ ] Use `aiofiles` library
  - **Files:** `services/settings/server.py:212-280`

```python
import aiofiles
import yaml

async def _save_settings_to_file(self):
    """Save current settings to YAML file (async)."""
    async with aiofiles.open(self.settings_file, 'w') as f:
        await f.write(yaml.dump(dict(self.settings)))
```

**5. Context Manager Consistency**
- [ ] Use async context managers throughout
  - [ ] `async with` for locks instead of `with`
  - [ ] `async with` for file operations
  - [ ] `async with` for gRPC channels
  - **Files:** All services

```python
async with self.lock:
    # Critical section
    pass
```

## Expected Improvements
- No blocking operations in async contexts
- Better concurrency (proper async patterns)
- Consistent code style
- Easier to reason about execution flow

## Success Criteria
- No `queue.Queue` usage (all `asyncio.Queue`)
- No synchronous file I/O in async functions
- All locks use `async with`
- mypy async checks pass
- No warnings about unawaited coroutines
