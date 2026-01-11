# Phase 45: Adaptive Controller Filtering via Bidirectional Streaming

**Status:** ✅ COMPLETED
**Priority:** HIGH
**Estimated Effort:** Medium (1-2 days) - ACTUAL: ~4 hours
**Depends On:** Phase 43 (Observability & Metrics)

## Goal

Reduce monitoring overhead during gameplay by dynamically filtering which controllers are polled and streamed based on player status (alive/dead). Use gRPC bidirectional streaming to enable seamless filter updates without stream restarts.

**Key Innovation**: As players die/are eliminated, stop monitoring their controllers - reducing bandwidth, CPU, and USB polling overhead progressively throughout the game.

## Motivation

### Problem Statement

**Current Architecture (Phase 43)**:
- `StreamGameplayData` polls **ALL** connected controllers every frame
- Dead/eliminated players' sensor data is still:
  - Polled from USB
  - Serialized to protobuf
  - Transmitted over gRPC
  - Received and parsed by game coordinator
  - Discarded at processing step (early-return for dead players)

**Inefficiency Example (25-player FFA)**:
```
Start:      25 controllers monitored (750 updates/sec at 30Hz)
Mid-game:   25 controllers monitored, 10 alive → 15 wasted
Late-game:  25 controllers monitored, 2 alive → 23 wasted (92% waste)
```

**Why Current Approach is Limited**:
- Filtering happens at consumer (game coordinator), not source (controller manager)
- Server-side streaming (`StreamGameplayData`) can't update filter mid-stream
- Would need to restart stream to change filter (10-20ms gaps, complex logic)

### Expected Benefits

**Network Bandwidth** (25 controllers at 30Hz):
- Baseline: 22 KB/s
- Mid-game (10 alive): 9 KB/s (-59%)
- Late-game (2 alive): 1.8 KB/s (-92%)

**CPU Usage**:
- Baseline: ~22% CPU (all 25 controllers)
- Mid-game (10 alive): ~15% CPU (-32%)
- Late-game (2 alive): ~5% CPU (-77%)

**USB Polling Reduction** (future enhancement):
- Skip USB reads for filtered controllers (additional ~10% CPU savings)

**Observability**:
- Metrics track filter effectiveness
- Validates optimization with real data (Phase 43 integration)
- A/B testable via OpenFeature (Phase 44 integration)

## Architecture

### Bidirectional Streaming Design

**Why Bidirectional?**

Current `StreamGameplayData` is server-side streaming only:
```protobuf
rpc StreamGameplayData(GameplayStreamRequest) returns (stream GameplayDataUpdate);
```

To change the filter mid-stream, you'd need to:
1. Cancel stream
2. Create new stream with updated filter
3. Handle 10-20ms gap and coordination complexity

**New Approach**: Bidirectional streaming allows client to send filter updates without restarting:
```protobuf
rpc StreamGameplayDataDynamic(stream GameplayStreamControl)
    returns (stream GameplayDataUpdate);
```

**Flow**:
```
Game Coordinator (client):
  ├─ Start bidirectional stream
  ├─ Send initial config (30Hz, all controllers)
  ├─ Receive gameplay data stream
  ├─ Player dies → Send filter update (remove dead controller)
  ├─ Receive filtered gameplay data (seamlessly)
  └─ No stream restart needed!

Controller Manager (server):
  ├─ Background task reads client messages (config/filter updates)
  ├─ Main task streams gameplay data
  ├─ Apply filter to controller iteration loop
  └─ Thread-safe filter updates (Python GIL)
```

### Proto Definition

**New messages** (`proto/controller_manager.proto`):

```protobuf
service ControllerManagerService {
  // Existing RPC (keep for backward compatibility)
  rpc StreamGameplayData(GameplayStreamRequest) returns (stream GameplayDataUpdate);

  // NEW: Bidirectional streaming with dynamic filtering
  rpc StreamGameplayDataDynamic(stream GameplayStreamControl)
      returns (stream GameplayDataUpdate);
}

// Control messages sent by client to update stream behavior
message GameplayStreamControl {
  oneof control {
    GameplayStreamConfig config = 1;      // Initial config
    FilterUpdate filter_update = 2;        // Mid-stream filter change
  }
}

message GameplayStreamConfig {
  int32 update_frequency_hz = 1;           // Game loop frequency
  repeated string serials = 2;             // Initial filter (empty = all)
}

message FilterUpdate {
  repeated string serials = 1;             // New filter list (empty = all)
}
```

**Design Notes**:
- Keep existing `StreamGameplayData` for backward compatibility
- Use `oneof` to support both initial config and filter updates
- Empty `serials` list means "stream all controllers"
- Extensible for future enhancements (can add Hz updates to `GameplayStreamControl`)

### Server Implementation

**File**: `services/controller_manager/server.py`

```python
async def StreamGameplayDataDynamic(
    self,
    request_iterator: AsyncIterator[controller_manager_pb2.GameplayStreamControl],
    context: grpc.ServicerContext
) -> AsyncIterator[controller_manager_pb2.GameplayDataUpdate]:
    """
    Stream gameplay data with dynamic filtering via bidirectional communication.

    Client can send filter updates at any time to adjust which controllers
    are being monitored without restarting the stream.
    """

    # Stream state (updated by client messages)
    current_hz = 30  # Default
    current_filter = None  # None = all controllers

    # Background task to read client updates
    async def read_client_updates():
        nonlocal current_hz, current_filter

        try:
            async for control_msg in request_iterator:
                if control_msg.HasField("config"):
                    # Initial configuration
                    current_hz = control_msg.config.update_frequency_hz
                    current_filter = (
                        set(control_msg.config.serials)
                        if control_msg.config.serials
                        else None
                    )
                    logger.info(
                        f"Stream configured: {current_hz}Hz, "
                        f"filter={len(current_filter) if current_filter else 'all'} controllers"
                    )

                elif control_msg.HasField("filter_update"):
                    # Mid-stream filter update
                    new_filter = (
                        set(control_msg.filter_update.serials)
                        if control_msg.filter_update.serials
                        else None
                    )

                    if new_filter != current_filter:
                        logger.info(
                            f"Filter updated: {len(current_filter or [])} → "
                            f"{len(new_filter or [])} controllers"
                        )
                        current_filter = new_filter

        except Exception as e:
            logger.error(f"Error reading client updates: {e}", exc_info=True)

    # Start background task to read updates
    update_task = asyncio.create_task(read_client_updates())

    try:
        # Stream gameplay data
        while not context.cancelled():
            gameplay_data = []

            # Build data for each controller (respecting filter)
            for serial, info in self.tracked_controllers.items():
                # Apply filter if present
                if current_filter is not None and serial not in current_filter:
                    continue  # Skip filtered controller

                # Build gameplay data (existing logic)
                full_state = self._build_or_get_cached_state(serial, info)

                gd = controller_manager_pb2.GameplayData(
                    serial=serial,
                    acceleration=controller_manager_pb2.Vector3D(
                        x=full_state.accel_x,
                        y=full_state.accel_y,
                        z=full_state.accel_z,
                    ),
                    gyroscope=controller_manager_pb2.Vector3D(
                        x=full_state.gyro_x,
                        y=full_state.gyro_y,
                        z=full_state.gyro_z,
                    ),
                    battery_percentage=full_state.battery_percentage,
                )
                gameplay_data.append(gd)

            # Send update
            yield controller_manager_pb2.GameplayDataUpdate(
                controllers=gameplay_data,
                timestamp=int(time.time() * 1000),
            )

            # Sleep based on current Hz
            await asyncio.sleep(1.0 / current_hz)

    finally:
        # Cleanup
        update_task.cancel()
        try:
            await update_task
        except asyncio.CancelledError:
            pass
```

**Key Design Points**:
- Background task reads client updates asynchronously
- Main loop streams data based on current filter state
- Thread-safe update of `current_filter` (Python GIL handles this)
- Graceful cleanup on stream end

### Client Implementation

**File**: `services/game_coordinator/games/base.py`

Update `_game_loop()` to use bidirectional streaming:

```python
async def _game_loop(self):
    """Game loop with dynamic controller filtering."""

    logger.info("Starting game loop with dynamic filtering...")

    try:
        from proto import controller_manager_pb2

        # Create player spans
        self._create_player_spans(None)

        # Get initial config
        config = get_config_manager().get_config()
        update_frequency_hz = config.update_frequency_hz

        # Create bidirectional stream
        stream = self.controller_client.StreamGameplayDataDynamic()

        # Send initial configuration
        initial_config = controller_manager_pb2.GameplayStreamControl(
            config=controller_manager_pb2.GameplayStreamConfig(
                update_frequency_hz=update_frequency_hz,
                serials=[],  # Start with all controllers
            )
        )
        await stream.write(initial_config)

        # Track current alive set for detecting changes
        last_alive_serials = set(p.serial for p in self.players.values() if p.alive)

        # Process gameplay updates
        async for gameplay_update in stream:
            if not self.running:
                break

            # Process each controller's data
            for gameplay_data in gameplay_update.controllers:
                await self._process_controller_state(gameplay_data)

            # Check if alive players changed (death/respawn)
            current_alive_serials = set(
                p.serial for p in self.players.values() if p.alive
            )

            if current_alive_serials != last_alive_serials:
                # Send filter update to server
                filter_msg = controller_manager_pb2.GameplayStreamControl(
                    filter_update=controller_manager_pb2.FilterUpdate(
                        serials=list(current_alive_serials)
                    )
                )
                await stream.write(filter_msg)

                logger.info(
                    f"Updated controller filter: {len(last_alive_serials)} → "
                    f"{len(current_alive_serials)} alive players"
                )

                last_alive_serials = current_alive_serials

            # Check win condition
            if self._check_win_condition():
                break

    except Exception as e:
        logger.error(f"Game loop error: {e}", exc_info=True)
        raise
```

**Key Design Points**:
- Use `stream.write()` to send filter updates
- Check for alive player changes each iteration
- Only send update when filter actually changes
- No stream restarts needed

## Implementation Plan

### Task 1: Proto Definition & Code Generation

**Status:** ✅ COMPLETED

**Files**:
- `proto/controller_manager.proto` - Add new messages and RPC
- `proto/controller_manager_pb2.py` - Generated
- `proto/controller_manager_pb2_grpc.py` - Generated

**Steps**:
1. Add `GameplayStreamControl`, `GameplayStreamConfig`, `FilterUpdate` messages
2. Add `StreamGameplayDataDynamic` RPC definition
3. Regenerate Python protobuf code: `python3 -m grpc_tools.protoc ...`
4. Verify generated code compiles

**Verification**: Import generated classes in Python REPL

### Task 2: Server Implementation (Controller Manager)

**Status:** ✅ COMPLETED

**File**: `services/controller_manager/server.py`

**Steps**:
1. Implement `StreamGameplayDataDynamic()` method
2. Add background task for reading client filter updates
3. Apply filter to controller iteration loop
4. Add logging for filter changes
5. Test with grpcurl/manual client

**Verification**: Use grpcurl to send filter updates, verify logs show changes

### Task 3: Client Implementation (Game Coordinator)

**Status:** ✅ COMPLETED

**File**: `services/game_coordinator/games/base.py`

**Steps**:
1. Update `_game_loop()` to use bidirectional streaming
2. Create bidirectional stream on game start
3. Send initial config message
4. Track alive player changes
5. Send filter updates on death/respawn
6. Handle stream errors gracefully

**Verification**: Start FFA game, check logs for filter updates as players die

### Task 4: Metrics & Monitoring

**Status:** ✅ COMPLETED

**Files**:
- `services/game_coordinator/metrics.py`
- `services/controller_manager/metrics.py` (if exists)

**New Metrics**:
```python
# Game Coordinator
filtered_controllers = Gauge(
    'game_filtered_controllers',
    'Number of controllers currently filtered out (dead players)'
)

filter_updates_total = Counter(
    'game_filter_updates_total',
    'Total number of controller filter updates sent',
    ['game_mode']
)

active_controllers = Gauge(
    'game_active_controllers',
    'Number of controllers currently being monitored (alive players)'
)

# Controller Manager
streamed_controllers = Histogram(
    'controller_streamed_per_frame',
    'Number of controllers streamed per frame',
    buckets=[1, 2, 5, 10, 15, 20, 25, 30]
)
```

**Verification**: Check Prometheus `/metrics` endpoint, view in Grafana

### Task 5: Testing & Validation

**Status:** ✅ COMPLETED

**Files**:
- `tests/integration/test_dynamic_filtering.py` (new)
- `tests/unit/test_controller_filtering.py` (new)

**Tests**:
1. Unit tests for filter logic
2. Integration tests with mock controllers
3. Manual testing with 25-controller setup
4. Performance benchmarking (compare bandwidth/CPU before and after)
5. Verify Nonstop Joust works (frequent filter changes)

**Verification**: All tests pass, metrics show expected reduction

## Special Considerations

### Nonstop Joust Mode

**Challenge**: Players respawn in Nonstop Joust, causing frequent filter changes.

**Options**:

1. **Disable filtering** for Nonstop (always stream all controllers)
   ```python
   if self.get_game_name() == "Nonstop Joust":
       serials = []  # All controllers
   else:
       serials = list(alive_serials)  # Only alive
   ```

2. **Debouncing** (wait N seconds before sending update)
   ```python
   if current_alive_serials != last_alive_serials:
       await asyncio.sleep(2.0)  # Batch multiple respawns
       await stream.write(filter_msg)
   ```

3. **Keep filtering** (respawns are still seconds apart)
   - Most practical approach
   - Filter updates on death, another on respawn
   - ~2-3 filter updates per player death/respawn cycle

**Recommendation**: Start with Option 3 (keep filtering), add Option 1 if metrics show too many updates.

### Backward Compatibility

- Keep existing `StreamGameplayData` RPC for backward compatibility
- Game modes can opt-in to dynamic filtering
- Old RPC continues working for games that don't need filtering
- Future: Once all game modes migrate, deprecate old RPC

### Error Handling

**Client disconnects**:
- Server's `read_client_updates()` task catches exception and logs
- Server continues streaming with last known filter
- Stream ends gracefully

**Server crashes**:
- Client's `async for` loop raises exception
- Client can retry connection or fall back to old RPC

**Filter update race conditions**:
- Python GIL ensures thread-safe filter updates
- Worst case: One frame uses old filter before updating
- Acceptable (deaths are not frame-perfect events)

## Performance Impact

### Scenario: 25-Player FFA on Raspberry Pi 5

**Baseline (current - no filtering)**:
- 25 controllers × 30Hz = 750 updates/sec
- 22 KB/s bandwidth
- ~22% CPU

**Mid-game (10 alive) with bidirectional filtering**:
- 10 controllers × 30Hz = 300 updates/sec (60% reduction)
- 9 KB/s bandwidth (-59%)
- ~15% CPU (-32%)

**Late-game (2 alive) with bidirectional filtering**:
- 2 controllers × 30Hz = 60 updates/sec (92% reduction)
- 1.8 KB/s bandwidth (-92%)
- ~5% CPU (-77%)

**Key Insights**:
- Filter effectiveness increases as game progresses
- Maximum benefit in late game (1v1 finals)
- No stream restart overhead (seamless transitions)

### Measurement Plan

**Before Phase 45**:
- Use Phase 43 tools to establish baseline (25 controllers, 30Hz)
- Record: CPU, bandwidth, latency, controller count

**During Phase 45**:
- Run same 25-controller game with filtering enabled
- Track `filtered_controllers`, `active_controllers`, `filter_updates_total` metrics
- Compare CPU/bandwidth reduction at mid-game and late-game

**Success Criteria**:
- ✅ 50%+ reduction in bandwidth/CPU at mid-game
- ✅ 80%+ reduction in bandwidth/CPU at late-game
- ✅ No stream interruptions (logs show seamless filter updates)
- ✅ All game modes work (including Nonstop Joust)

## Risks & Mitigations

### Risk 1: Bidirectional Stream Complexity

**Concern**: First bidirectional stream in codebase, new pattern

**Mitigation**:
- Start with thorough unit tests
- Keep old RPC for fallback
- Add extensive logging for debugging
- Document pattern for future use

### Risk 2: Filter Update Frequency (Nonstop)

**Concern**: Nonstop Joust could send many filter updates (death + respawn every 3-5 seconds)

**Mitigation**:
- Monitor `filter_updates_total` metric
- Add debouncing if needed
- Can disable for Nonstop if problematic

### Risk 3: gRPC Python Bidirectional Quirks

**Concern**: Python gRPC bidirectional streaming has subtle edge cases

**Mitigation**:
- Test extensively with async iteration
- Handle `CancelledError` and `RpcError` gracefully
- Use `asyncio.create_task()` pattern from gRPC docs

### Risk 4: Synchronization Between Reader and Writer

**Concern**: Client reading responses while also writing updates could deadlock

**Mitigation**:
- Use separate async tasks (reader in `async for`, writer in check logic)
- Don't `await` writes for long periods
- gRPC handles async coordination internally

## Testing Strategy

### Unit Tests

**Test 1: Filter application**
```python
def test_filter_applies_correctly():
    # Create request with filter
    control_msg = GameplayStreamControl(
        config=GameplayStreamConfig(
            update_frequency_hz=30,
            serials=["controller_1", "controller_2"]
        )
    )
    # Verify only filtered controllers in response
```

**Test 2: Filter updates**
```python
async def test_filter_update_changes_output():
    # Start stream with all controllers
    # Send filter update for subset
    # Verify next frame only contains subset
```

**Test 3: Empty filter means all**
```python
def test_empty_filter_streams_all():
    # Send config with serials=[]
    # Verify all controllers in response
```

### Integration Tests

**Test 4: End-to-end filtering**
```python
async def test_dynamic_filtering_on_death():
    # Start game with 4 mock controllers
    # Kill 1 player
    # Verify filter update sent
    # Verify only 3 controllers streaming
```

**Test 5: Nonstop mode (respawns)**
```python
async def test_nonstop_respawn_filtering():
    # Start Nonstop game with 4 players
    # Kill 1 player → filter update (3 alive)
    # Respawn same player → filter update (4 alive)
    # Verify multiple filter updates work correctly
```

### Performance Tests

**Test 6: Measure bandwidth reduction**
```python
async def test_bandwidth_reduction():
    # Start game with 25 controllers
    bandwidth_before = measure_bandwidth()
    # Kill 15 players (10 alive)
    bandwidth_after = measure_bandwidth()
    # Expect ~60% reduction
    assert bandwidth_after < bandwidth_before * 0.5
```

**Test 7: Measure CPU reduction**
```python
async def test_cpu_reduction():
    # Start game with 25 controllers
    cpu_before = measure_cpu()
    # Kill 20 players (5 alive)
    cpu_after = measure_cpu()
    # Expect ~40% reduction
    assert cpu_after < cpu_before * 0.7
```

## Success Criteria

**Functional Requirements**:
- ✅ Bidirectional stream successfully filters controllers mid-game
- ✅ Filter updates sent on player death/respawn
- ✅ All game modes work (FFA, Teams, Random Teams, Nonstop Joust)
- ✅ No stream interruptions or gaps
- ✅ Backward compatible (old RPC still works)

**Performance Requirements**:
- ✅ 50%+ reduction in bandwidth/CPU at mid-game (10 alive)
- ✅ 80%+ reduction in bandwidth/CPU at late-game (2 alive)
- ✅ Filter updates < 5ms latency
- ✅ Zero disconnects during filter updates

**Observability Requirements**:
- ✅ Metrics track filtered vs active controllers
- ✅ Logs show filter update events
- ✅ Grafana dashboard visualizes filtering effectiveness
- ✅ Performance impact measurable (Phase 43 integration)

## Future Enhancements (Not in Scope)

**Phase 46+: Dynamic Hz via OpenFeature**
- Use same bidirectional stream to update Hz mid-game
- Feature flag targeting based on alive_players
- Combine with controller filtering for multiplicative benefits

**Phase 47+: Advanced Optimizations**
- Skip USB polling for filtered controllers (server-side)
- Predictive filtering (pre-filter before death confirmation)
- Per-player streaming (individual streams per controller)

## Dependencies

**Requires**:
- Phase 43: Observability & Metrics (for measurement and validation)

**Enables**:
- Phase 44: OpenFeature Integration (A/B test filtering effectiveness)
- Phase 46+: Dynamic Hz (reuse bidirectional stream mechanism)
- Production optimization based on real data

## Notes

**Why This Matters**:
- Real performance impact: 60-92% reduction in monitoring overhead
- Scales with game progression (more benefit as game advances)
- First bidirectional stream in codebase (pattern for future features)
- Observable and measurable (integrates with Phase 43 tools)

**Design Philosophy**:
- "Filter at source, not destination" - move filtering from consumer to producer
- "Seamless over efficient" - no stream restarts, smooth transitions
- "Observable over assumed" - metrics prove optimization works
- "Extensible over optimized" - bidirectional stream enables future enhancements
