"""
Prometheus metrics for Controller Manager (Phase 38).

Tracks controller health, input latency, stream performance, and cache efficiency.
"""

from prometheus_client import Counter, Gauge, Histogram

# Controller health metrics
controller_battery_level = Gauge(
    'controller_battery_level',
    'Controller battery level (0-5)',
    ['serial']
)

controller_connected = Gauge(
    'controller_connected',
    'Controller connection status (0=disconnected, 1=connected)',
    ['serial']
)

controller_disconnect_total = Counter(
    'controller_disconnect_total',
    'Total number of controller disconnects',
    ['serial']
)

controller_reconnect_total = Counter(
    'controller_reconnect_total',
    'Total number of controller reconnects',
    ['serial']
)

active_controllers = Gauge(
    'active_controllers_total',
    'Number of currently active controllers'
)

# Input latency metrics
controller_input_lag_seconds = Histogram(
    'controller_input_lag_seconds',
    'Time from button press to gRPC transmission',
    ['serial'],
    buckets=[0.001, 0.005, 0.010, 0.016, 0.020, 0.030, 0.050, 0.100, 0.200]
)

controller_state_update_hz = Gauge(
    'controller_state_update_hz',
    'Controller state update frequency',
    ['serial']
)

# Stream metrics
active_streams = Gauge(
    'controller_streams_active',
    'Number of active controller state streams'
)

stream_updates_total = Counter(
    'controller_stream_updates_total',
    'Total controller state updates sent',
    ['stream_type']  # 'legacy', 'button_events', 'gameplay_data'
)

button_events_total = Counter(
    'controller_button_events_total',
    'Total button events generated',
    ['serial', 'button', 'action']  # action: 'press' or 'release'
)

# Cache metrics (Phase 18 validation)
state_cache_hits_total = Counter(
    'controller_state_cache_hits_total',
    'Number of state cache hits (no rebuild needed)'
)

state_cache_misses_total = Counter(
    'controller_state_cache_misses_total',
    'Number of state cache misses (rebuild required)'
)

object_pool_utilization = Gauge(
    'controller_object_pool_utilization',
    'Object pool utilization percentage',
    ['pool_type']  # 'controller_state' or 'vector3'
)

# System metrics
process_cpu_percent = Gauge(
    'process_cpu_percent',
    'Process CPU usage percentage'
)

process_memory_mb = Gauge(
    'process_memory_mb',
    'Process memory usage in MB'
)

process_threads = Gauge(
    'process_threads',
    'Number of active threads'
)

# gRPC metrics
grpc_requests_total = Counter(
    'grpc_requests_total',
    'Total gRPC requests received',
    ['method', 'status']
)

grpc_request_duration_seconds = Histogram(
    'grpc_request_duration_seconds',
    'gRPC request duration',
    ['method'],
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0]
)
