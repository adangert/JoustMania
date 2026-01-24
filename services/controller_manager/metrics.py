"""
OTEL Push Metrics for Controller Manager (Issue #104).

Tracks controller health, input latency, stream performance, and cache efficiency.
Uses OTLP push at 100ms intervals for real-time dashboard updates.
"""

from lib.otel_metrics import Counter, Gauge, Histogram

# Controller health metrics
controller_battery_level = Gauge("controller_battery_level", "Controller battery level (0-5)", ["serial"])

controller_connected = Gauge(
    "controller_connected", "Controller connection status (0=disconnected, 1=connected)", ["serial"]
)

# Controller LED color metrics (Phase 75: Per-player insights)
controller_color_r = Gauge("controller_color_r", "Controller LED red component (0-255)", ["serial"])
controller_color_g = Gauge("controller_color_g", "Controller LED green component (0-255)", ["serial"])
controller_color_b = Gauge("controller_color_b", "Controller LED blue component (0-255)", ["serial"])

# Controller info metric (Phase 75: Per-player insights)
# This is an "info" style metric - always 1, with useful labels for joins
controller_info = Gauge(
    "controller_info",
    "Controller information (always 1, use labels for joins)",
    ["serial", "name"],
)

# Combined LED color as hex integer (Phase 75: Per-player insights)
# Value is (R << 16) | (G << 8) | B, e.g., 0xFF0000 for red
controller_color_hex = Gauge(
    "controller_color_hex",
    "Controller LED color as hex integer (R<<16 | G<<8 | B)",
    ["serial"],
)

controller_disconnect_total = Counter(
    "controller_disconnect_total", "Total number of controller disconnects", ["serial"]
)

controller_reconnect_total = Counter("controller_reconnect_total", "Total number of controller reconnects", ["serial"])

# Connection strength metrics (Phase 48)
controller_rssi_dbm = Gauge(
    "controller_rssi_dbm",
    "Controller Bluetooth signal strength in dBm (-100 to 0, 0 = USB/unavailable)",
    ["serial"],
)

controller_weak_signal_warnings_total = Counter(
    "controller_weak_signal_warnings_total",
    "Total number of weak signal warnings displayed",
    ["serial"],
)

active_controllers = Gauge("active_controllers_total", "Number of currently active controllers")

# Input latency metrics
controller_input_lag_seconds = Histogram(
    "controller_input_lag_seconds",
    "Time from button press to gRPC transmission",
    ["serial"],
    buckets=[0.001, 0.005, 0.010, 0.016, 0.020, 0.030, 0.050, 0.100, 0.200],
)

controller_state_update_hz = Gauge("controller_state_update_hz", "Controller state update frequency", ["serial"])

# Stream metrics
active_streams = Gauge("controller_streams_active", "Number of active controller state streams")

stream_updates_total = Counter(
    "controller_stream_updates_total",
    "Total controller state updates sent",
    ["stream_type"],  # 'legacy', 'button_events', 'gameplay_data'
)

button_events_total = Counter(
    "controller_button_events_total",
    "Total button events generated",
    ["serial", "button", "action"],  # action: 'press' or 'release'
)

# Cache metrics (Phase 18 validation)
state_cache_hits_total = Counter("controller_state_cache_hits_total", "Number of state cache hits (no rebuild needed)")

state_cache_misses_total = Counter(
    "controller_state_cache_misses_total", "Number of state cache misses (rebuild required)"
)

object_pool_utilization = Gauge(
    "controller_object_pool_utilization",
    "Object pool utilization percentage",
    ["pool_type"],  # 'controller_state' or 'vector3'
)

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

# Adaptive controller filtering metrics (Phase 45)
streamed_controllers = Histogram(
    "controller_streamed_per_frame",
    "Number of controllers streamed per frame",
    buckets=[1, 2, 5, 10, 15, 20, 25, 30],
)

# Stream-based feedback commands (Phase 46)
stream_commands_total = Counter(
    "controller_stream_commands_total",
    "Total feedback commands received via stream",
    ["command_type"],  # 'color', 'effect', 'vibration'
)

# Discovery polling metrics (Phase 56: Event-driven spans)
discovery_checks_total = Counter(
    "controller_discovery_checks_total",
    "Total number of controller discovery checks performed",
)

discovery_check_duration_seconds = Histogram(
    "controller_discovery_check_duration_seconds",
    "Duration of controller discovery checks",
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500],
)

battery_checks_total = Counter(
    "controller_battery_checks_total",
    "Total number of battery level checks performed",
)

battery_check_duration_seconds = Histogram(
    "controller_battery_check_duration_seconds",
    "Duration of battery checks",
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100],
)

rssi_checks_total = Counter(
    "controller_rssi_checks_total",
    "Total number of RSSI signal checks performed",
)

rssi_check_duration_seconds = Histogram(
    "controller_rssi_check_duration_seconds",
    "Duration of RSSI checks",
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100],
)

# Parallel polling metrics (Phase 62)
poll_batch_duration_seconds = Histogram(
    "controller_poll_batch_duration_seconds",
    "Duration to poll all controllers in parallel",
    buckets=[0.001, 0.003, 0.005, 0.010, 0.016, 0.025, 0.050, 0.100],
)

poll_batch_size = Histogram(
    "controller_poll_batch_size",
    "Number of controllers polled per batch",
    buckets=[1, 2, 4, 8, 12, 16, 20, 24],
)

# Adaptive polling metrics (Quick Win optimization)
adaptive_polling_active_controllers = Gauge(
    "controller_adaptive_polling_active",
    "Number of controllers being polled at active rate (60Hz)",
)

adaptive_polling_idle_controllers = Gauge(
    "controller_adaptive_polling_idle",
    "Number of controllers being polled at idle rate (10Hz)",
)

adaptive_polling_skipped_total = Counter(
    "controller_adaptive_polling_skipped_total",
    "Total number of poll cycles skipped due to adaptive rate limiting",
)

# LED batch update metrics (Phase 72 optimization)
led_batch_updates_total = Counter(
    "controller_led_batch_updates_total",
    "Total number of LED batch update cycles",
)

led_controllers_updated_per_batch = Histogram(
    "controller_led_controllers_updated_per_batch",
    "Number of controllers with LEDs updated per batch cycle",
    buckets=[0, 1, 2, 4, 8, 12, 16, 20, 24],
)
