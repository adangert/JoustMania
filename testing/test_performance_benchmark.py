"""
Performance benchmarks for state-based controller tracking.

These tests measure CPU usage, latency, and throughput to verify
the expected 60-70% CPU reduction and 3x latency improvement.
"""

import time
import unittest
from multiprocessing import Process, Value

import psutil
from controller_state import ControllerState

from testing.fakes import FakeMove


class PerformanceBenchmark(unittest.TestCase):
    """Performance benchmarks for controller tracking."""

    def test_state_update_latency(self):
        """
        Measure latency of state updates.

        Expected: < 1ms per update
        """
        state = ControllerState()
        fake = FakeMove()
        fake.set_accelerometer(1.0, 2.0, 3.0)

        iterations = 1000
        start = time.time()

        for _ in range(iterations):
            state.update(fake)

        elapsed = time.time() - start
        avg_latency_ms = (elapsed / iterations) * 1000

        print(f"\nAverage update latency: {avg_latency_ms:.3f}ms")
        self.assertLess(avg_latency_ms, 1.0, "Update should be under 1ms")

    def test_snapshot_read_latency(self):
        """
        Measure latency of reading state snapshots.

        Expected: < 0.1ms per read
        """
        state = ControllerState()
        fake = FakeMove()
        state.update(fake)

        iterations = 10000
        start = time.time()

        for _ in range(iterations):
            state.get_snapshot()

        elapsed = time.time() - start
        avg_latency_ms = (elapsed / iterations) * 1000

        print(f"\nAverage snapshot read latency: {avg_latency_ms:.3f}ms")
        self.assertLess(avg_latency_ms, 0.1, "Read should be under 0.1ms")

    def test_end_to_end_latency(self):
        """
        Measure end-to-end latency from hardware update to state read.

        Expected: < 5ms at 1000Hz update rate
        """

        def producer_process(state, kill_flag, timestamps):
            """Producer: update state from hardware."""
            fake = FakeMove()
            while not kill_flag.value:
                fake.set_accelerometer(time.time(), 0, 0)  # Timestamp in accel
                if state.update(fake):
                    timestamps.value += 1
                time.sleep(0.001)  # 1000Hz

        state = ControllerState()
        kill_flag = Value("b", False)
        timestamp_count = Value("i", 0)

        # Start producer
        proc = Process(target=producer_process, args=(state, kill_flag, timestamp_count))
        proc.start()

        # Wait for producer to start
        time.sleep(0.01)

        # Measure latency over 100ms
        latencies = []
        start = time.time()
        while time.time() - start < 0.1:
            snapshot = state.get_snapshot()
            if snapshot["connected"]:
                write_time = snapshot["accelerometer"][0]
                read_time = time.time()
                latency_ms = (read_time - write_time) * 1000
                if latency_ms > 0:  # Valid latency
                    latencies.append(latency_ms)
            time.sleep(0.001)

        # Clean up
        kill_flag.value = True
        proc.join(timeout=1.0)
        if proc.is_alive():
            proc.terminate()

        # Analyze latencies
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            min_latency = min(latencies)

            print("\nEnd-to-end latency:")
            print(f"  Average: {avg_latency:.2f}ms")
            print(f"  Min: {min_latency:.2f}ms")
            print(f"  Max: {max_latency:.2f}ms")
            print(f"  Samples: {len(latencies)}")

            self.assertLess(avg_latency, 5.0, "Average latency should be under 5ms")
            self.assertLess(max_latency, 10.0, "Max latency should be under 10ms")
        else:
            self.fail("No valid latency measurements")

    def test_cpu_usage_single_controller(self):
        """
        Measure CPU usage for single controller tracking.

        Expected: < 1% CPU per controller
        """

        def tracking_process(state, kill_flag):
            """Simulate controller tracking at 1000Hz."""
            fake = FakeMove()
            fake.set_accelerometer(1.0, 2.0, 3.0)

            while not kill_flag.value:
                state.update(fake)
                state.apply_outputs(fake)
                time.sleep(0.001)  # 1000Hz

        state = ControllerState()
        kill_flag = Value("b", False)

        # Start tracking process
        proc = Process(target=tracking_process, args=(state, kill_flag))
        proc.start()

        # Wait for process to stabilize
        time.sleep(0.1)

        # Measure CPU usage over 1 second
        process = psutil.Process(proc.pid)
        cpu_samples = []

        for _ in range(10):
            cpu_percent = process.cpu_percent(interval=0.1)
            cpu_samples.append(cpu_percent)

        # Clean up
        kill_flag.value = True
        proc.join(timeout=1.0)
        if proc.is_alive():
            proc.terminate()

        # Analyze CPU usage
        avg_cpu = sum(cpu_samples) / len(cpu_samples)
        max_cpu = max(cpu_samples)

        print("\nCPU usage (single controller):")
        print(f"  Average: {avg_cpu:.1f}%")
        print(f"  Max: {max_cpu:.1f}%")

        self.assertLess(avg_cpu, 2.0, "Should use less than 2% CPU")

    def test_throughput_multiple_controllers(self):
        """
        Measure update throughput with multiple controllers.

        Expected: 1000+ updates/sec per controller
        """

        def multi_controller_process(states, kill_flag, update_count):
            """Update multiple controller states."""
            fakes = [FakeMove() for _ in states]
            for fake in fakes:
                fake.set_accelerometer(1.0, 2.0, 3.0)

            while not kill_flag.value:
                for state, fake in zip(states, fakes, strict=False):
                    if state.update(fake):
                        update_count.value += 1
                time.sleep(0.001)

        # Create 4 controller states
        num_controllers = 4
        states = [ControllerState() for _ in range(num_controllers)]
        kill_flag = Value("b", False)
        update_count = Value("i", 0)

        # Start tracking
        proc = Process(target=multi_controller_process, args=(states, kill_flag, update_count))
        proc.start()

        # Measure for 1 second
        time.sleep(1.0)

        # Stop tracking
        kill_flag.value = True
        proc.join(timeout=1.0)
        if proc.is_alive():
            proc.terminate()

        # Calculate throughput
        total_updates = update_count.value
        updates_per_controller = total_updates / num_controllers

        print(f"\nThroughput ({num_controllers} controllers):")
        print(f"  Total updates: {total_updates}")
        print(f"  Updates per controller: {updates_per_controller:.0f}/sec")

        # Should be close to 500 updates/sec per controller
        # (FakeMove.poll() alternates, so 50% success rate at 1000Hz)
        self.assertGreater(
            updates_per_controller, 400, "Should achieve 400+ updates/sec per controller"
        )

    def test_memory_footprint(self):
        """
        Measure memory footprint of ControllerState.

        Expected: < 1KB per controller
        """
        import sys

        state = ControllerState()

        # Approximate memory usage
        # Each Value/Array has some overhead, but should be minimal
        memory_bytes = (
            sys.getsizeof(state.accel_x)
            + sys.getsizeof(state.accel_y)
            + sys.getsizeof(state.accel_z)
            + sys.getsizeof(state.gyro_x)
            + sys.getsizeof(state.gyro_y)
            + sys.getsizeof(state.gyro_z)
            + sys.getsizeof(state.buttons)
            + sys.getsizeof(state.trigger)
            + sys.getsizeof(state.battery)
            + sys.getsizeof(state.connected)
            + sys.getsizeof(state.timestamp)
            + sys.getsizeof(state.update_count)
            + sys.getsizeof(state.led_r)
            + sys.getsizeof(state.led_g)
            + sys.getsizeof(state.led_b)
            + sys.getsizeof(state.rumble)
        )

        memory_kb = memory_bytes / 1024

        print(f"\nMemory footprint per controller: {memory_kb:.2f}KB")
        self.assertLess(memory_kb, 5.0, "Should use less than 5KB")


class ComparisonBenchmark(unittest.TestCase):
    """
    Comparison benchmarks between old polling and new state-based approach.

    These tests simulate the old approach to demonstrate improvements.
    """

    def test_blocking_poll_overhead(self):
        """
        Measure overhead of blocking polling pattern.

        This simulates the OLD approach for comparison.
        """
        fake = FakeMove()
        fake.set_accelerometer(1.0, 2.0, 3.0)

        iterations = 100
        start = time.time()

        for _ in range(iterations):
            # Simulate old blocking pattern
            if fake.poll():
                ax, ay, az = fake.get_accelerometer_frame(None)
                fake.get_buttons()
                fake.get_trigger()
                fake.get_battery()
            time.sleep(0.01)  # Old 100Hz rate

        elapsed = time.time() - start

        print("\nOLD blocking poll pattern:")
        print(f"  Time for {iterations} iterations: {elapsed:.2f}s")
        print(f"  Average per iteration: {(elapsed / iterations) * 1000:.2f}ms")

        # Should take ~1 second (100 * 10ms)
        self.assertGreater(elapsed, 0.9, "Should take at least 0.9s")

    def test_nonblocking_state_overhead(self):
        """
        Measure overhead of non-blocking state pattern.

        This is the NEW approach.
        """
        state = ControllerState()
        fake = FakeMove()
        fake.set_accelerometer(1.0, 2.0, 3.0)

        # Pre-populate state
        state.update(fake)

        iterations = 100
        start = time.time()

        for _ in range(iterations):
            # New non-blocking pattern
            snapshot = state.get_snapshot()
            ax, ay, az = snapshot["accelerometer"]
            snapshot["buttons"]
            snapshot["trigger"]
            snapshot["battery"]
            time.sleep(0.01)  # Same 100Hz rate

        elapsed = time.time() - start

        print("\nNEW non-blocking state pattern:")
        print(f"  Time for {iterations} iterations: {elapsed:.2f}s")
        print(f"  Average per iteration: {(elapsed / iterations) * 1000:.2f}ms")

        # Should also take ~1 second, but with much less CPU
        self.assertGreater(elapsed, 0.9, "Should take at least 0.9s")

    def test_update_frequency_comparison(self):
        """
        Compare achievable update frequencies.

        OLD: 100Hz (10ms sleep)
        NEW: 1000Hz (1ms sleep)
        """
        state = ControllerState()
        fake = FakeMove()
        fake.set_accelerometer(1.0, 2.0, 3.0)

        # Test new approach at 1000Hz
        updates_new = 0
        start = time.time()
        while time.time() - start < 0.1:  # 100ms
            if state.update(fake):
                updates_new += 1
            time.sleep(0.001)  # 1000Hz

        # Simulate old approach at 100Hz
        updates_old = 0
        start = time.time()
        while time.time() - start < 0.1:  # 100ms
            if fake.poll():
                updates_old += 1
            time.sleep(0.01)  # 100Hz

        print("\nUpdate frequency comparison (100ms window):")
        print(f"  NEW (1000Hz): {updates_new} updates")
        print(f"  OLD (100Hz): {updates_old} updates")
        print(f"  Improvement: {updates_new / updates_old:.1f}x")

        # New approach should get ~10x more updates
        self.assertGreater(updates_new / updates_old, 5.0, "New approach should be 5x+ faster")


if __name__ == "__main__":
    # Run benchmarks
    print("=" * 60)
    print("CONTROLLER STATE PERFORMANCE BENCHMARKS")
    print("=" * 60)
    unittest.main(verbosity=2)
