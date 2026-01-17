"""
Prometheus metrics for Game Coordinator (Phase 38).

Tracks game state, player performance, audio playback, and game quality metrics.
"""

from prometheus_client import Counter, Gauge, Histogram

# Game state metrics
active_game = Gauge("game_active", "Whether a game is currently running (0=no, 1=yes)")

current_game_mode = Gauge(
    "game_current_mode",
    "Current game mode",
    ["mode"],  # 'ffa', 'teams_simple', 'teams_random', 'nonstop_joust', 'none'
)

game_duration_seconds = Gauge("game_duration_seconds", "Duration of current game in seconds")

games_started_total = Counter("games_started_total", "Total number of games started", ["mode"])

games_completed_total = Counter("games_completed_total", "Total number of games completed", ["mode"])

# Player metrics
active_players = Gauge("game_active_players", "Number of players currently in game")

players_alive = Gauge("game_players_alive", "Number of players currently alive")

player_deaths_total = Counter("game_player_deaths_total", "Total player deaths", ["mode", "serial"])

player_kills_total = Counter("game_player_kills_total", "Total player kills", ["mode", "serial"])

player_respawns_total = Counter("game_player_respawns_total", "Total player respawns (Nonstop Joust only)", ["serial"])

# Game performance metrics
frame_time_seconds = Histogram(
    "game_frame_time_seconds",
    "Game loop frame time",
    buckets=[0.010, 0.016, 0.020, 0.030, 0.050, 0.100, 0.200, 0.500],
)

frame_rate_hz = Gauge("game_frame_rate_hz", "Current game loop frame rate")

game_loop_lag_seconds = Histogram(
    "game_loop_lag_seconds",
    "Time between expected and actual frame",
    buckets=[0.001, 0.005, 0.010, 0.020, 0.050, 0.100, 0.200],
)

# Audio playback metrics (Phase 29)
audio_sounds_played_total = Counter(
    "audio_sounds_played_total",
    "Total sounds played",
    ["sound_type"],  # 'countdown', 'start', 'death', 'victory', 'respawn', 'join'
)

audio_playback_errors_total = Counter("audio_playback_errors_total", "Total audio playback errors")

# Game quality metrics
countdown_accuracy_seconds = Histogram(
    "game_countdown_accuracy_seconds",
    "Accuracy of countdown timing",
    buckets=[0.001, 0.005, 0.010, 0.020, 0.050, 0.100],
)

winner_announcement_delay_seconds = Histogram(
    "game_winner_announcement_delay_seconds",
    "Time from last death to winner announcement",
    buckets=[0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
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

# Runtime configuration metrics (Phase 43)
configured_update_frequency_hz = Gauge(
    "game_configured_update_frequency_hz", "Configured update frequency from runtime config"
)

actual_update_frequency_hz = Gauge(
    "game_actual_update_frequency_hz", "Actual measured update frequency during gameplay"
)

config_changes_total = Counter(
    "game_config_changes_total",
    "Total number of configuration changes",
    ["parameter"],  # 'update_frequency_hz', 'sensitivity_mode', etc.
)

game_loop_iterations_total = Counter("game_loop_iterations_total", "Total number of game loop iterations", ["mode"])

game_loop_latency_ms = Histogram(
    "game_loop_latency_ms",
    "Game loop iteration latency in milliseconds",
    ["mode"],
    buckets=[10, 20, 30, 40, 50, 75, 100, 150, 200, 300, 500],
)

# Adaptive controller filtering metrics (Phase 45)
filtered_controllers = Gauge("game_filtered_controllers", "Number of controllers currently filtered out (dead players)")

filter_updates_total = Counter(
    "game_filter_updates_total",
    "Total number of controller filter updates sent",
    ["game_mode"],  # Track per game mode
)

active_controllers = Gauge("game_active_controllers", "Number of controllers currently being monitored (alive players)")

# Controller analytics metrics (Phase XX - Analytics)
# Real-time gauges (updated every ~1 second during gameplay)
player_accel_magnitude = Gauge(
    "game_player_accel_magnitude",
    "Current acceleration magnitude for player (g-force)",
    ["serial"],
)

player_movement_zone = Gauge(
    "game_player_movement_zone",
    "Current movement zone (0=still, 1=active, 2=warning, 3=danger)",
    ["serial"],
)

player_peak_accel = Gauge(
    "game_player_peak_accel",
    "Peak acceleration magnitude for player in current game (g-force)",
    ["serial", "game_id"],
)

player_playstyle = Gauge(
    "game_player_playstyle",
    "Player playstyle classification (0=calm, 1=balanced, 2=active, 3=aggressive)",
    ["serial"],
)

# Counters (incremented on events)
near_death_events_total = Counter(
    "game_near_death_events_total",
    "Total near-death events (raw > threshold but EMA saved player)",
    ["serial", "game_mode"],
)

player_warnings_total = Counter(
    "game_player_warnings_total",
    "Total warning events triggered",
    ["serial", "game_mode"],
)

# Histogram for distribution analysis
accel_distribution = Histogram(
    "game_accel_distribution",
    "Distribution of acceleration magnitudes during gameplay",
    ["game_mode"],
    buckets=[0.5, 1.0, 1.1, 1.3, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0],
)

# Per-game summary metrics (set at end of game)
game_analytics_samples_total = Counter(
    "game_analytics_samples_total",
    "Total analytics samples recorded",
    ["game_mode"],
)

game_analytics_replay_bytes = Histogram(
    "game_analytics_replay_bytes",
    "Size of replay data stored in bytes",
    ["game_mode"],
    buckets=[10000, 50000, 100000, 200000, 500000, 1000000],
)
