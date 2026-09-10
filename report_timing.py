"""Bounded, shared measurements of application report arrival timing."""
import ctypes
import math
import multiprocessing
import time


class ReportTiming:
    def __init__(self, controllers, capacity=2048, window_s=10.0):
        self.capacity = capacity
        self.window_s = window_s
        self.timestamps = multiprocessing.RawArray(ctypes.c_double, controllers * capacity)
        self.counts = multiprocessing.RawArray(ctypes.c_ulonglong, controllers)
        self.locks = [multiprocessing.Lock() for _ in range(controllers)]

    def reset(self, index):
        with self.locks[index]:
            self.counts[index] = 0

    def record(self, index, now=None):
        now = time.monotonic() if now is None else now
        with self.locks[index]:
            count = self.counts[index]
            self.timestamps[index * self.capacity + count % self.capacity] = now
            self.counts[index] = count + 1

    def snapshot(self, index, now=None):
        with self.locks[index]:
            count = self.counts[index]
            size = min(count, self.capacity)
            start = index * self.capacity
            values = list(self.timestamps[start:start + size])
        # Take 'now' after copying, so a concurrent new report cannot appear
        # to have arrived in the future relative to the snapshot clock.
        now = time.monotonic() if now is None else now
        if count > self.capacity:
            offset = count % self.capacity
            values = values[offset:] + values[:offset]
        cutoff = now - self.window_s
        gaps = sorted((end - begin) * 1000 for begin, end in zip(values, values[1:])
                      if end >= cutoff)
        def percentile(fraction):
            return round(gaps[math.ceil(fraction * len(gaps)) - 1], 2) if gaps else None
        return {
            'source': 'application',
            'window_s': self.window_s,
            'sample_count': len(gaps),
            'p95_ms': percentile(0.95),
            'p99_ms': percentile(0.99),
            'max_ms': round(gaps[-1], 2) if gaps else None,
            'last_report_age_ms': round(max(0, now - values[-1]) * 1000, 2) if values else None,
            'gaps_over_50ms': sum(gap > 50 for gap in gaps),
            'gaps_over_100ms': sum(gap > 100 for gap in gaps),
            'sample_limited': count > self.capacity and values[0] >= cutoff,
        }
