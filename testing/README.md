# JoustMania Testing Suite

This directory contains unit tests, integration tests, and performance benchmarks for the state-based controller tracking architecture.

## Test Files

### `test_controller_state.py`
Unit tests for the `ControllerState` and `ControllerStateManager` classes.

**Tests:**
- Initial state validation
- State updates from controllers
- LED and rumble control
- Freshness checking
- Multi-process shared memory
- State manager operations

**Expected Results:**
- All tests should pass
- Multi-process tests verify shared memory works correctly
- Freshness tests validate staleness detection

### `test_performance_benchmark.py`
Performance benchmarks comparing old and new architectures.

**Benchmarks:**
- State update latency (target: < 1ms)
- Snapshot read latency (target: < 0.1ms)
- End-to-end latency (target: < 5ms average)
- CPU usage per controller (target: < 2%)
- Update throughput (target: 1000+ updates/sec)
- Memory footprint (target: < 5KB per controller)

**Comparison Tests:**
- Blocking poll overhead (old approach)
- Non-blocking state overhead (new approach)
- Update frequency comparison (should show 5-10x improvement)

### `fakes.py`
Mock implementations for testing without real hardware.

**Classes:**
- `FakeMove`: Mock PS Move controller

## Running Tests

### Quick Run (All Tests)
```bash
./run_tests.sh
```

### Run Specific Test File
```bash
# Unit tests only
python3 -m pytest testing/test_controller_state.py -v

# Benchmarks only
python3 -m pytest testing/test_performance_benchmark.py -v -s
```

### Run Specific Test
```bash
python3 -m pytest testing/test_controller_state.py::TestControllerState::test_update_from_controller -v
```

## Dependencies

Tests require:
- `pytest` - Test framework
- `psutil` - CPU monitoring (for benchmarks)

Install with:
```bash
pip3 install pytest psutil
```

## Expected Performance Improvements

### CPU Usage
**OLD (Blocking Polling):**
- 2-3% CPU per controller
- 8 controllers = 16-24% total

**NEW (State-Based):**
- < 1% CPU per controller
- 8 controllers = 4-8% total
- **60-70% reduction**

### Latency
**OLD (Blocking Polling):**
- 100Hz update rate (10ms intervals)
- p95 latency: 15-25ms

**NEW (State-Based):**
- 1000Hz update rate (1ms intervals)
- p95 latency: 5-10ms
- **3x improvement**

### Memory
- ControllerState: < 5KB per controller
- Minimal overhead vs old approach

## Interpreting Results

### Unit Test Results
All unit tests should **PASS**. If any fail:
1. Check for import errors (missing dependencies)
2. Verify FakeMove implementation is correct
3. Check multiprocessing compatibility on your platform

### Benchmark Results
Benchmark output shows actual measurements:

```
Average update latency: 0.234ms  ✓ (target: < 1ms)
Average snapshot read latency: 0.012ms  ✓ (target: < 0.1ms)
End-to-end latency: 3.45ms  ✓ (target: < 5ms)
CPU usage: 0.8%  ✓ (target: < 2%)
```

**What to look for:**
- Update latency under 1ms
- Read latency under 0.1ms
- End-to-end latency under 5ms (average)
- CPU usage under 2% per controller
- Update frequency 5-10x higher than old approach

**Platform Differences:**
- Raspberry Pi may show higher absolute values but similar relative improvements
- Development machines (x86) will show lower latencies
- Focus on the **ratio** of improvement, not absolute numbers

## Troubleshooting

### Tests Fail with Import Errors
```bash
# Install missing dependencies
pip3 install pytest psutil
```

### Multiprocessing Tests Hang
This can happen on some platforms. Try:
```bash
# Skip multiprocess tests
python3 -m pytest testing/test_controller_state.py -v -k "not multiprocess"
```

### Benchmark Results Seem Wrong
- Close other applications (CPU monitoring needs clean environment)
- Run benchmarks multiple times for consistency
- Check if running on Raspberry Pi (expect higher latencies)

## Integration with CI/CD

These tests can be integrated into continuous integration:

```yaml
# Example GitHub Actions workflow
- name: Run Tests
  run: |
    pip3 install pytest psutil
    pytest testing/test_controller_state.py -v
    pytest testing/test_performance_benchmark.py -v
```

## Future Tests

Planned additions:
- Integration tests with real Move controllers
- Stress tests (24-hour continuous operation)
- Memory leak detection tests
- Multi-controller coordination tests
- OpenTelemetry instrumentation tests

## Test Coverage

Current coverage:
- ✓ ControllerState core functionality
- ✓ ControllerStateManager operations
- ✓ Multi-process shared memory
- ✓ Performance benchmarks
- ✓ Comparison with old approach
- ⚠ Integration with real hardware (requires manual testing)
- ⚠ Game loop integration (pending implementation)

## Questions?

If tests fail or results are unexpected:
1. Check the test output for specific error messages
2. Review ARCHITECTURE_ANALYSIS.md for design details
3. Verify your Python version (3.7+ required for multiprocessing features)
4. Try running tests individually to isolate issues
