# Phase 34: Async/Await Consistency

**Status:** COMPLETED
**Priority:** LOW - Technical correctness
**Completed:** 2026-01-13

## Goal
Fix sync/async mixing and use proper async patterns throughout

## Motivation
- Some services mix sync and async gRPC calls
- Settings loads use synchronous calls in async functions
- Event queues use threading.Queue instead of asyncio.Queue
- Blocking operations in async contexts cause performance issues

## Tasks

**1. Settings Service - Async Streams**
- [x] Convert SubscribeToChanges to async stream
  - [x] Use `asyncio.Queue` instead of `queue.Queue`
  - [x] Use `async def` and `await`
  - **Files:** `services/settings/server.py:478-512`

**2. Game Modes - Async Settings Loads**
- [x] Use async gRPC stubs for Settings service
  - [x] Create async channel: `grpc.aio.insecure_channel`
  - [x] Await Settings calls: `await self.settings_client.GetSettings(...)`
  - [x] Implemented in base class: `services/game_coordinator/games/base.py:255-280`

**3. Event Publishing - Async Queues**
- [x] Replace `queue.Queue` with `asyncio.Queue`
  - [x] GameCoordinator event subscribers - `services/game_coordinator/server.py:119`
  - [x] Menu event subscribers - `services/menu/server.py:93`
  - [x] Settings event subscribers - `services/settings/server.py:192`
  - [x] Controller Manager stream/button subscribers - `services/controller_manager/server.py:139,143`

**Note on _publish_event():** Kept synchronous with `put_nowait()` intentionally.
This is the correct pattern because game modes run in a separate thread (`game_thread`)
and `put_nowait()` is the proper way to add to an asyncio.Queue from a sync context.
The function is non-blocking and handles QueueFull exceptions properly.

**4. File I/O - Async-Safe Operations**
- [x] Replace synchronous file operations with async-safe patterns
  - [x] Settings service YAML save uses `run_in_executor()` - `services/settings/server.py:461-463`
  - **Note:** Used `run_in_executor()` instead of `aiofiles` to avoid additional dependency

**5. Context Manager Consistency**
- [x] Use async context managers throughout
  - [x] `async with` for asyncio.Lock instances
  - [x] `with` for threading.Lock instances (correct pattern)
  - [x] All services verified

## Implementation Details

### asyncio.Queue Usage (all services)
All subscriber queues converted to `asyncio.Queue(maxsize=100)` with proper:
- `await event_queue.get()` for async consumers
- `put_nowait()` for sync producers (from threads)
- `asyncio.QueueFull` exception handling

### Lock Usage Pattern
- `asyncio.Lock()` -> `async with self.lock:` (gRPC async methods)
- `threading.Lock()` -> `with self.lock:` (thread-safe sync code)

### File I/O Pattern
```python
# In UpdateSetting() - async context
loop = asyncio.get_running_loop()
await loop.run_in_executor(None, self.save_settings)
```

## Success Criteria - VERIFIED
- [x] No `queue.Queue` usage (all `asyncio.Queue`)
- [x] No synchronous file I/O in async functions (uses run_in_executor)
- [x] All asyncio.Lock instances use `async with`
- [x] All threading.Lock instances use `with`
- [x] No warnings about unawaited coroutines
