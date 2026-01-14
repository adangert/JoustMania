"""
System Metrics Collector - Collects process-level metrics for Prometheus.

Provides async background collection of CPU, memory, and thread metrics
using psutil. Designed to be reusable across all services.

Usage:
    from lib.system_metrics import start_system_metrics_collector

    # In your async serve() function:
    async def serve():
        # Start collecting metrics (returns the task for optional cancellation)
        metrics_task = start_system_metrics_collector(
            cpu_gauge=my_cpu_gauge,
            memory_gauge=my_memory_gauge,
            threads_gauge=my_threads_gauge,
            interval=10.0,
        )

        # ... rest of server setup
"""

import asyncio
import logging

import psutil

logger = logging.getLogger(__name__)


async def collect_system_metrics(
    cpu_gauge,
    memory_gauge,
    threads_gauge,
    interval: float = 10.0,
):
    """
    Background task to collect system metrics periodically.

    Runs psutil calls in thread pool to avoid blocking the event loop.

    Args:
        cpu_gauge: Prometheus Gauge for CPU percentage
        memory_gauge: Prometheus Gauge for memory usage (MB)
        threads_gauge: Prometheus Gauge for thread count
        interval: Collection interval in seconds (default: 10.0)
    """
    process = psutil.Process()
    loop = asyncio.get_event_loop()

    while True:
        try:
            # Run blocking psutil calls in thread pool
            cpu_percent = await loop.run_in_executor(
                None, lambda: process.cpu_percent(interval=None)
            )
            mem_info = await loop.run_in_executor(None, process.memory_info)
            thread_count = await loop.run_in_executor(None, process.num_threads)

            cpu_gauge.set(cpu_percent)
            memory_gauge.set(mem_info.rss / 1024 / 1024)
            threads_gauge.set(thread_count)

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")

        await asyncio.sleep(interval)


def start_system_metrics_collector(
    cpu_gauge,
    memory_gauge,
    threads_gauge,
    interval: float = 10.0,
) -> asyncio.Task:
    """
    Start the system metrics collector as a background task.

    Args:
        cpu_gauge: Prometheus Gauge for CPU percentage
        memory_gauge: Prometheus Gauge for memory usage (MB)
        threads_gauge: Prometheus Gauge for thread count
        interval: Collection interval in seconds (default: 10.0)

    Returns:
        The asyncio Task (can be cancelled if needed)
    """
    return asyncio.create_task(
        collect_system_metrics(cpu_gauge, memory_gauge, threads_gauge, interval)
    )


def collect_system_metrics_sync(
    cpu_gauge,
    memory_gauge,
    threads_gauge,
    interval: float = 10.0,
):
    """
    Synchronous version of system metrics collection for threaded services.

    Runs in a loop, collecting metrics at the specified interval.
    Designed to run in a daemon thread.

    Args:
        cpu_gauge: Prometheus Gauge for CPU percentage
        memory_gauge: Prometheus Gauge for memory usage (MB)
        threads_gauge: Prometheus Gauge for thread count
        interval: Collection interval in seconds (default: 10.0)
    """
    import time

    process = psutil.Process()

    while True:
        try:
            cpu_gauge.set(process.cpu_percent(interval=None))
            memory_gauge.set(process.memory_info().rss / 1024 / 1024)
            threads_gauge.set(process.num_threads())
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")

        time.sleep(interval)


def start_system_metrics_collector_thread(
    cpu_gauge,
    memory_gauge,
    threads_gauge,
    interval: float = 10.0,
):
    """
    Start the system metrics collector as a background daemon thread.

    For use in synchronous/non-async services.

    Args:
        cpu_gauge: Prometheus Gauge for CPU percentage
        memory_gauge: Prometheus Gauge for memory usage (MB)
        threads_gauge: Prometheus Gauge for thread count
        interval: Collection interval in seconds (default: 10.0)

    Returns:
        The started Thread object
    """
    import threading

    thread = threading.Thread(
        target=collect_system_metrics_sync,
        args=(cpu_gauge, memory_gauge, threads_gauge, interval),
        daemon=True,
    )
    thread.start()
    return thread
