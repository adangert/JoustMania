"""
Prometheus metrics for Menu Service (Phase 38).

Tracks system resources and gRPC request performance.
"""

from prometheus_client import Counter, Gauge, Histogram

# System metrics
process_cpu_percent = Gauge("process_cpu_percent", "Process CPU usage percentage")

process_memory_mb = Gauge("process_memory_mb", "Process memory usage in MB")

process_threads = Gauge("process_threads", "Number of active threads")

# gRPC metrics
grpc_requests_total = Counter("grpc_requests_total", "Total gRPC requests received", ["method", "status"])

grpc_request_duration_seconds = Histogram(
    "grpc_request_duration_seconds",
    "gRPC request duration",
    ["method"],
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0],
)
