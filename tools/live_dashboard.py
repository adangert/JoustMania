#!/usr/bin/env python3
"""
Live Performance Dashboard for JoustMania (Phase 43)

Real-time visual monitoring for observability talks/demos.
Shows:
- Current Hz and latency
- CPU usage
- Controllers per hub
- Bandwidth usage
- Live graphs (ASCII art)
- Configuration changes

Usage:
    python3 live_dashboard.py [--hz 30] [--duration 300]
"""

import asyncio
import time
import sys
import os
from collections import deque
from datetime import datetime

import grpc
import psutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from proto import controller_manager_pb2, controller_manager_pb2_grpc


class LiveDashboard:
    """Real-time ASCII dashboard for performance monitoring."""

    def __init__(self, max_history=60):
        self.max_history = max_history

        # Time series data (last N seconds)
        self.update_intervals = deque(maxlen=max_history)
        self.cpu_usage = deque(maxlen=max_history)
        self.controller_counts = deque(maxlen=max_history)
        self.bandwidth_per_sec = deque(maxlen=max_history)

        # Current state
        self.current_hz = 0
        self.current_latency = 0
        self.current_controllers = 0
        self.total_updates = 0
        self.total_bytes = 0
        self.start_time = time.time()

        # Hub tracking
        self.hub_assignments = {}  # {serial: hub_name}
        self.hub_controller_counts = {}  # {hub_name: count}

    def update(self, controllers, update_size_bytes):
        """Update dashboard with new data."""
        now = time.time()
        elapsed = now - self.start_time

        # Update metrics
        self.total_updates += 1
        self.total_bytes += update_size_bytes
        self.current_controllers = len(controllers)

        # Time series
        if self.total_updates > 1:
            interval = elapsed / self.total_updates * 1000  # avg ms between updates
            self.update_intervals.append(interval)
            self.current_latency = interval

        self.cpu_usage.append(psutil.cpu_percent(interval=0))
        self.controller_counts.append(len(controllers))
        self.bandwidth_per_sec.append(update_size_bytes / (elapsed if elapsed > 0 else 1))

        # Calculate current Hz
        if self.total_updates > 1 and elapsed > 0:
            self.current_hz = self.total_updates / elapsed

        # Update hub assignments
        self._update_hub_tracking(controllers)

    def _update_hub_tracking(self, controllers):
        """Track which controllers belong to which hub."""
        # Auto-assign based on serial if not already assigned
        sorted_serials = sorted([c.serial for c in controllers], key=lambda s: s)

        for idx, serial in enumerate(sorted_serials):
            if serial not in self.hub_assignments:
                # Assign to hubs (first 15 to Hub 1, rest to Hub 2)
                if idx < 15:
                    self.hub_assignments[serial] = "Hub 1"
                else:
                    self.hub_assignments[serial] = "Hub 2"

        # Count controllers per hub
        self.hub_controller_counts = {}
        for serial in sorted_serials:
            hub = self.hub_assignments.get(serial, "Unknown")
            self.hub_controller_counts[hub] = self.hub_controller_counts.get(hub, 0) + 1

    def render(self):
        """Render the dashboard to terminal."""
        elapsed = time.time() - self.start_time

        # Clear screen (ANSI escape code)
        print("\033[2J\033[H", end="")

        # Header
        print("=" * 80)
        print("🎮 JOUSTMANIA LIVE PERFORMANCE DASHBOARD (Phase 43)".center(80))
        print("=" * 80)
        print(f"⏱️  Runtime: {int(elapsed)}s | Updates: {self.total_updates} | "
              f"Timestamp: {datetime.now().strftime('%H:%M:%S')}")
        print()

        # Core metrics (big numbers)
        print("📊 CURRENT PERFORMANCE")
        print("-" * 80)
        print(f"  Frequency:    {self.current_hz:6.1f} Hz")
        print(f"  Latency:      {self.current_latency:6.1f} ms (avg interval)")
        print(f"  Controllers:  {self.current_controllers:3d}")
        print(f"  CPU Usage:    {self.cpu_usage[-1] if self.cpu_usage else 0:6.1f}%")
        print(f"  Bandwidth:    {self.total_bytes / elapsed / 1024 if elapsed > 0 else 0:6.2f} KB/s")
        print()

        # Hub breakdown
        print("🔌 USB HUB BREAKDOWN")
        print("-" * 80)
        for hub_name in sorted(self.hub_controller_counts.keys()):
            count = self.hub_controller_counts[hub_name]
            bar = "█" * (count // 2)
            print(f"  {hub_name:15s}: {count:2d} controllers {bar}")
        print()

        # Mini graphs (ASCII art)
        print("📈 CPU USAGE (last 60s)")
        print("-" * 80)
        self._render_graph(self.cpu_usage, max_value=100, height=5, label="%")
        print()

        print("📈 LATENCY (ms, last 60s)")
        print("-" * 80)
        self._render_graph(self.update_intervals, max_value=100, height=5, label="ms")
        print()

        # Status indicators
        print("🚦 HEALTH STATUS")
        print("-" * 80)

        # Latency status
        avg_latency = sum(self.update_intervals) / len(self.update_intervals) if self.update_intervals else 0
        if avg_latency < 40:
            latency_status = "✅ EXCELLENT (<40ms)"
        elif avg_latency < 60:
            latency_status = "🟢 GOOD (40-60ms)"
        elif avg_latency < 100:
            latency_status = "🟡 FAIR (60-100ms)"
        else:
            latency_status = "🔴 POOR (>100ms)"
        print(f"  Latency:      {latency_status}")

        # CPU status
        avg_cpu = sum(self.cpu_usage) / len(self.cpu_usage) if self.cpu_usage else 0
        if avg_cpu < 30:
            cpu_status = "✅ EXCELLENT (<30%)"
        elif avg_cpu < 50:
            cpu_status = "🟢 GOOD (30-50%)"
        elif avg_cpu < 70:
            cpu_status = "🟡 FAIR (50-70%)"
        else:
            cpu_status = "🔴 HIGH (>70%)"
        print(f"  CPU Load:     {cpu_status}")

        # Controller count status
        if self.current_controllers >= 20:
            controller_status = "✅ FULL SCALE (20+ controllers)"
        elif self.current_controllers >= 10:
            controller_status = "🟢 MULTI-CONTROLLER (10-20)"
        elif self.current_controllers >= 4:
            controller_status = "🟡 TESTING (4-10)"
        else:
            controller_status = "🟠 LIMITED (<4 controllers)"
        print(f"  Controllers:  {controller_status}")

        print()
        print("=" * 80)
        print("Press Ctrl+C to stop monitoring".center(80))
        print("=" * 80)

    def _render_graph(self, data, max_value=100, height=5, label=""):
        """Render ASCII bar graph."""
        if not data:
            print("  [No data yet]")
            return

        # Normalize data to height
        normalized = [min(int(v / max_value * height), height) for v in data]

        # Render from top to bottom
        for row in range(height, 0, -1):
            line = f"{row * max_value / height:5.0f}{label:3s} │"
            for val in normalized:
                if val >= row:
                    line += "█"
                else:
                    line += " "
            print(line)

        # X-axis
        print("       └" + "─" * len(normalized))
        print(f"        {len(data)} samples (last {len(data)}s)")


async def run_dashboard(frequency_hz: int, duration_sec: int = 300):
    """Run live dashboard."""
    channel = grpc.aio.insecure_channel("localhost:50051")
    stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    request = controller_manager_pb2.GameplayStreamRequest(update_frequency_hz=frequency_hz)
    dashboard = LiveDashboard(max_history=60)

    print(f"🚀 Starting live dashboard at {frequency_hz}Hz...")
    print(f"   Connect to game coordinator and start a game to see metrics\n")

    start_time = time.time()
    last_render = 0

    try:
        async for update in stub.StreamGameplayData(request):
            # Calculate update size
            update_size = len(update.SerializeToString())

            # Update dashboard
            dashboard.update(update.controllers, update_size)

            # Render every second
            elapsed = time.time() - start_time
            if elapsed >= last_render + 1:
                dashboard.render()
                last_render = elapsed

            if elapsed >= duration_sec:
                break

    except KeyboardInterrupt:
        print("\n\n⏹️  Dashboard stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await channel.close()
        print("\n✅ Dashboard session complete")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="JoustMania Live Performance Dashboard")
    parser.add_argument("--hz", type=int, default=30, help="Streaming frequency (default: 30)")
    parser.add_argument("--duration", type=int, default=300, help="Duration in seconds (default: 300)")

    args = parser.parse_args()

    try:
        asyncio.run(run_dashboard(args.hz, args.duration))
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


if __name__ == "__main__":
    main()
