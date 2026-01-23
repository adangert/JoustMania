#!/usr/bin/env python3
"""
Multi-Hub Performance Monitor for 25-controller setup.

Tracks per-controller metrics to identify:
- Which USB hub/dongle has issues
- Latency distribution across hubs
- Bandwidth usage per hub
- CPU and system load

Run during gameplay to validate distributed hub setup.
"""

import asyncio
import os
import sys
import time
from collections import defaultdict

import grpc
import psutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from proto import controller_manager_pb2, controller_manager_pb2_grpc


class MultiHubPerformanceMonitor:
    def __init__(self):
        # Controller tracking
        self.controller_updates = defaultdict(int)  # {serial: update_count}
        self.controller_last_seen = {}  # {serial: timestamp}
        self.controller_gaps = defaultdict(list)  # {serial: [gap_ms, ...]}

        # Hub grouping (user will configure dongle→hub mapping)
        self.hub_assignments = {}  # {serial: hub_name}

        # Performance metrics
        self.total_updates = 0
        self.total_bytes = 0
        self.start_time = None
        self.update_intervals = []
        self.last_update_time = None

        # System metrics
        self.cpu_samples = []
        self.memory_samples = []

    def assign_controller_to_hub(self, serial, hub_name):
        """Assign a controller serial to a hub name for tracking."""
        self.hub_assignments[serial] = hub_name

    def auto_assign_hubs(self, controllers):
        """Auto-assign controllers to hubs based on serial prefixes."""
        # Example: Assume serials follow pattern, or user can configure
        # For now, assign by controller number
        sorted_serials = sorted([c.serial for c in controllers])

        for idx, serial in enumerate(sorted_serials):
            if idx < 15:
                self.hub_assignments[serial] = "Hub 1 (USB 3.0 Port 1)"
            else:
                self.hub_assignments[serial] = "Hub 2 (USB 3.0 Port 2)"

    def record_update(self, controllers, timestamp):
        """Record update and calculate metrics."""
        now = time.time()

        if self.start_time is None:
            self.start_time = now
            self.auto_assign_hubs(controllers)

        # Update interval tracking
        if self.last_update_time:
            interval_ms = (now - self.last_update_time) * 1000
            self.update_intervals.append(interval_ms)
        self.last_update_time = now

        # Per-controller tracking
        for controller in controllers:
            serial = controller.serial
            self.controller_updates[serial] += 1

            # Track gaps between updates for this controller
            if serial in self.controller_last_seen:
                gap_ms = (now - self.controller_last_seen[serial]) * 1000
                self.controller_gaps[serial].append(gap_ms)

            self.controller_last_seen[serial] = now

        self.total_updates += 1

        # System metrics
        self.cpu_samples.append(psutil.cpu_percent(interval=0))
        self.memory_samples.append(psutil.virtual_memory().percent)

    def get_hub_stats(self):
        """Calculate per-hub statistics."""
        hub_stats = defaultdict(
            lambda: {
                "controllers": [],
                "total_updates": 0,
                "avg_gap_ms": 0,
                "max_gap_ms": 0,
                "missing_updates": 0,
            }
        )

        for serial, hub_name in self.hub_assignments.items():
            hub_stats[hub_name]["controllers"].append(serial)
            hub_stats[hub_name]["total_updates"] += self.controller_updates.get(serial, 0)

            if serial in self.controller_gaps and self.controller_gaps[serial]:
                gaps = self.controller_gaps[serial]
                hub_stats[hub_name]["avg_gap_ms"] += sum(gaps) / len(gaps)
                hub_stats[hub_name]["max_gap_ms"] = max(
                    hub_stats[hub_name]["max_gap_ms"], max(gaps)
                )

                # Count missing updates (gaps >100ms)
                hub_stats[hub_name]["missing_updates"] += sum(1 for g in gaps if g > 100)

        # Average the avg_gap_ms across controllers
        for hub_name, stats in hub_stats.items():
            if stats["controllers"]:
                stats["avg_gap_ms"] /= len(stats["controllers"])

        return hub_stats

    def print_live_status(self, elapsed):
        """Print live status during monitoring."""
        controllers_seen = len(self.controller_updates)
        updates_per_sec = self.total_updates / elapsed if elapsed > 0 else 0

        avg_cpu = (
            sum(self.cpu_samples[-10:]) / len(self.cpu_samples[-10:]) if self.cpu_samples else 0
        )

        print(
            f"[{int(elapsed):3d}s] "
            f"Controllers: {controllers_seen:2d} | "
            f"Updates/s: {updates_per_sec:6.1f} | "
            f"CPU: {avg_cpu:5.1f}% | "
            f"Avg Interval: {sum(self.update_intervals[-30:]) / len(self.update_intervals[-30:]):.1f}ms"
            if self.update_intervals
            else "[Waiting...]"
        )

    def print_summary(self):
        """Print comprehensive performance summary."""
        elapsed = time.time() - self.start_time

        print("\n" + "=" * 70)
        print("📊 MULTI-HUB PERFORMANCE SUMMARY")
        print("=" * 70)

        # Overall metrics
        print("\n⏱️  OVERALL PERFORMANCE:")
        print(f"   Duration: {elapsed:.1f}s")
        print(f"   Total updates: {self.total_updates}")
        print(f"   Average update rate: {self.total_updates / elapsed:.1f} updates/sec")
        print(f"   Controllers tracked: {len(self.controller_updates)}")

        if self.update_intervals:
            avg_interval = sum(self.update_intervals) / len(self.update_intervals)
            max_interval = max(self.update_intervals)
            min_interval = min(self.update_intervals)
            print(
                f"   Update interval: {avg_interval:.1f}ms avg (min: {min_interval:.1f}ms, max: {max_interval:.1f}ms)"
            )

        # System metrics
        if self.cpu_samples:
            avg_cpu = sum(self.cpu_samples) / len(self.cpu_samples)
            max_cpu = max(self.cpu_samples)
            print("\n💻 SYSTEM LOAD:")
            print(f"   CPU: {avg_cpu:.1f}% avg, {max_cpu:.1f}% max")

        if self.memory_samples:
            avg_mem = sum(self.memory_samples) / len(self.memory_samples)
            print(f"   Memory: {avg_mem:.1f}%")

        # Per-hub breakdown
        hub_stats = self.get_hub_stats()
        print("\n🔌 PER-HUB BREAKDOWN:")

        for hub_name, stats in sorted(hub_stats.items()):
            print(f"\n   {hub_name}:")
            print(f"      Controllers: {len(stats['controllers'])}")
            print(f"      Total updates: {stats['total_updates']}")
            print(f"      Avg gap: {stats['avg_gap_ms']:.1f}ms")
            print(f"      Max gap: {stats['max_gap_ms']:.1f}ms")

            if stats["missing_updates"] > 0:
                print(f"      ⚠️  Missing updates (>100ms): {stats['missing_updates']}")
            else:
                print("      ✅ No missing updates")

        # Per-controller details (top 5 worst)
        print("\n🎮 CONTROLLER DETAILS (Top 5 highest gaps):")

        controller_avg_gaps = {}
        for serial, gaps in self.controller_gaps.items():
            if gaps:
                controller_avg_gaps[serial] = sum(gaps) / len(gaps)

        top_worst = sorted(controller_avg_gaps.items(), key=lambda x: x[1], reverse=True)[:5]

        for serial, avg_gap in top_worst:
            hub_name = self.hub_assignments.get(serial, "Unknown")
            max_gap = max(self.controller_gaps[serial])
            updates = self.controller_updates[serial]
            print(f"   {serial} ({hub_name})")
            print(f"      Updates: {updates}, Avg gap: {avg_gap:.1f}ms, Max gap: {max_gap:.1f}ms")

        # Health assessment
        print("\n🏥 HEALTH ASSESSMENT:")

        total_missing = sum(stats["missing_updates"] for stats in hub_stats.values())
        max_gap_overall = max(stats["max_gap_ms"] for stats in hub_stats.values())

        if total_missing == 0 and max_gap_overall < 100:
            print("   ✅ EXCELLENT - All hubs performing optimally")
        elif total_missing < 10 and max_gap_overall < 150:
            print("   🟢 GOOD - Minor variations, acceptable performance")
        elif total_missing < 50 and max_gap_overall < 200:
            print("   🟡 FAIR - Some gaps detected, monitor closely")
        else:
            print("   🔴 POOR - Significant gaps, investigate USB hub setup")

        # Recommendations
        print("\n💡 RECOMMENDATIONS:")

        if max_gap_overall > 150:
            print("   ⚠️  High latency detected - check USB hub connections")

        if total_missing > 20:
            print("   ⚠️  Many missing updates - consider distributing controllers across more hubs")

        if self.cpu_samples and max(self.cpu_samples) > 60:
            print("   ⚠️  High CPU usage - consider lowering update frequency")

        # Bandwidth estimation
        bytes_per_update = 60  # Approximate size of GameplayData
        bandwidth = (self.total_updates * bytes_per_update) / elapsed / 1024  # KB/s
        print("\n📡 BANDWIDTH:")
        print(f"   Estimated: {bandwidth:.2f} KB/s")
        print(f"   Per hub: {bandwidth / len(hub_stats):.2f} KB/s avg")


async def monitor_performance(frequency_hz: int, duration_sec: int):
    """Monitor multi-hub performance."""
    grpc_host = os.getenv("CONTROLLER_MANAGER_HOST", "localhost:50052")
    channel = grpc.aio.insecure_channel(grpc_host)
    stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    monitor = MultiHubPerformanceMonitor()

    print(f"🔍 Monitoring multi-hub performance at {frequency_hz}Hz for {duration_sec} seconds")
    print("   Press Ctrl+C to stop early\n")

    start_time = time.time()
    last_print = 0

    # Create bidirectional stream
    stream = stub.StreamGameplayData()

    # Send initial configuration
    config_msg = controller_manager_pb2.GameplayStreamControl(
        config=controller_manager_pb2.GameplayStreamConfig(
            update_frequency_hz=frequency_hz,
        )
    )
    await stream.write(config_msg)

    try:
        async for update in stream:
            monitor.record_update(update.controllers, update.timestamp)

            elapsed = time.time() - start_time

            # Print status every 5 seconds
            if int(elapsed) >= last_print + 5:
                monitor.print_live_status(elapsed)
                last_print = int(elapsed)

            if elapsed >= duration_sec:
                break

    except KeyboardInterrupt:
        print("\n⏹️  Monitoring stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await channel.close()
        monitor.print_summary()


async def main():
    print("🎮 JoustMania Multi-Hub Performance Monitor")
    print("=" * 70)
    print("For 25-controller setup with multiple powered USB 2.0 hubs")
    print("=" * 70 + "\n")

    # Monitor at current 30Hz setting
    await monitor_performance(frequency_hz=30, duration_sec=120)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Monitoring cancelled")
