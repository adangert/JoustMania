# Phase 26: Critical Performance Fixes

**Status:** 🔥 PLANNED
**Priority:** HIGH - CRITICAL for Raspberry Pi deployment

## Goal
Fix performance bottlenecks that will cause issues on resource-constrained hardware

## Motivation
- gRPC channel creation on every button press causes connection pool exhaustion
- No resource limits means services can crash entire system
- Missing compression wastes bandwidth on controller state streams
- These issues are invisible on development machines but critical on RPi

## Tasks

**1. gRPC Channel Pooling (CRITICAL)**
- [ ] Menu service: Create persistent channels in `__init__()`
  - [ ] `self.controller_channel` - reuse for all controller operations
  - [ ] `self.settings_channel` - reuse for all settings operations
  - [ ] Update all admin mode methods to use instance channels
  - [ ] Add channel cleanup in `shutdown()` method
  - **Files:** `services/menu/server.py:557, 666, 707, 765, 810, 971`

- [ ] Game Coordinator: Audit channel creation patterns
  - [ ] Ensure channels created once per game instance
  - [ ] Reuse stubs across game lifecycle
  - **Files:** `services/game_coordinator/games/ffa.py`, `teams.py`, `random_teams.py`

- [ ] WebUI: Add channel cleanup on shutdown
  - [ ] Close `self.settings_channel` in destructor
  - [ ] Close other service channels
  - **Files:** `services/webui/server.py:179-196`

**2. Docker Resource Limits**
- [ ] Add resource limits to `docker-compose.yml`
  - [ ] game-coordinator: 512M memory, 0.5 CPU
  - [ ] controller-manager: 256M memory, 0.3 CPU
  - [ ] audio: 256M memory, 0.3 CPU
  - [ ] menu: 128M memory, 0.2 CPU
  - [ ] settings: 64M memory, 0.1 CPU
  - [ ] supervisor: 64M memory, 0.1 CPU
  - [ ] webui: 128M memory, 0.2 CPU
  - [ ] otel-collector: 256M memory, 0.3 CPU
  - **Files:** `docker-compose.yml`, `docker-compose.mock.yml`

- [ ] Add health check timeouts and retries
  - [ ] Adjust health check intervals for slower RPi
  - [ ] Add memory/CPU monitoring to Supervisor

**3. gRPC Compression**
- [ ] Enable gRPC compression in channel options
  - [ ] Add `('grpc.default_compression_algorithm', grpc.Compression.Gzip)`
  - [ ] Test bandwidth reduction with controller streams
  - **Files:** All services with `channel_options` definitions

**4. Stream Optimization**
- [ ] Controller state streaming: Send delta updates
  - [ ] Track previous state per controller
  - [ ] Only send changed fields
  - [ ] Reduce message size by 60-80%
  - **Files:** `services/controller_manager/server.py:304-314`

## Expected Improvements
- 90% reduction in channel creation overhead
- Prevents OOM crashes on RPi (resource limits)
- 50% reduction in network bandwidth (compression + deltas)
- Predictable memory usage per service

## Success Criteria
- No new gRPC channels created during gameplay
- Services respect memory limits (no OOM kills)
- Controller stream bandwidth < 10KB/sec
- System stable for 8+ hour gaming sessions
