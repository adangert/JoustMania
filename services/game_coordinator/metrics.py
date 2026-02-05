"""
OTEL Push Metrics for Game Coordinator (Issue #103).

Tracks game state, player performance, audio playback, and game quality metrics.
Uses OTLP push at 100ms intervals for real-time dashboard updates.
"""

from contextlib import suppress

from lib.otel_metrics import Counter, Gauge, Histogram

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

# Music tempo metric (Phase 70)
music_tempo = Gauge(
    "game_music_tempo",
    "Current music playback speed (1.0=slow, 1.3=fast, 0=no game)",
)

# Sensitivity and threshold metrics (Phase 80)
game_sensitivity = Gauge(
    "game_sensitivity",
    "Current game sensitivity level (0=ultra_slow, 1=slow, 2=medium, 3=fast, 4=ultra_fast)",
)

effective_warning_threshold = Gauge(
    "game_effective_warning_threshold",
    "Current effective warning threshold after LERP (g-force)",
)

effective_death_threshold = Gauge(
    "game_effective_death_threshold",
    "Current effective death threshold after LERP (g-force)",
)

# Runtime metrics (Phase 43)
actual_update_frequency_hz = Gauge(
    "game_actual_update_frequency_hz", "Actual measured update frequency during gameplay"
)

config_changes_total = Counter(
    "game_config_changes_total",
    "Total number of configuration changes",
    ["parameter"],  # 'sensitivity_mode', 'update_frequency_hz', etc.
)

# Feature flag metrics (Phase 44)
flag_evaluations_total = Counter(
    "game_flag_evaluations_total",
    "Total number of feature flag evaluations",
    ["flag_key"],  # 'update_frequency_hz', 'sensitivity_mode', etc.
)

flag_configuration_changes_total = Counter(
    "game_flag_configuration_changes_total",
    "Total number of PROVIDER_CONFIGURATION_CHANGED events received",
)

current_update_frequency_hz = Gauge(
    "game_current_update_frequency_hz",
    "Current configured update frequency from feature flags (Hz)",
)

# Frame consistency metrics (Issue #183)
game_loop_frame_consistency_percent = Gauge(
    "game_loop_frame_consistency_percent",
    "Percentage of frames within target timing (within 50% of target frame time)",
)

game_loop_jitter_ms = Gauge(
    "game_loop_jitter_ms",
    "Standard deviation of frame times in milliseconds",
)

game_loop_frames_dropped_total = Counter(
    "game_loop_frames_dropped_total",
    "Total number of frames that exceeded 2x the target frame time",
    ["mode"],
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

player_alive = Gauge(
    "game_player_alive",
    "Player alive status (1=alive, 0=dead)",
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


def clear_player_analytics(serial: str, game_id: str = "") -> None:
    """
    Clear analytics metrics for a player (e.g., when they die or game ends).

    This removes the gauge labels so they no longer appear in dashboards,
    rather than showing stale data.
    """
    with suppress(KeyError, ValueError):
        player_accel_magnitude.remove(serial)

    with suppress(KeyError, ValueError):
        player_movement_zone.remove(serial)

    with suppress(KeyError, ValueError):
        player_playstyle.remove(serial)

    with suppress(KeyError, ValueError):
        player_alive.remove(serial)

    # peak_accel has both serial and game_id labels
    if game_id:
        with suppress(KeyError, ValueError):
            player_peak_accel.remove(serial, game_id)


def clear_all_player_analytics() -> None:
    """
    Clear all player analytics metrics (e.g., when game ends).

    This removes all label combinations so dashboards show no data
    when no game is running.
    """
    player_accel_magnitude._metrics.clear()
    player_accel_magnitude._values.clear()
    player_movement_zone._metrics.clear()
    player_movement_zone._values.clear()
    player_playstyle._metrics.clear()
    player_playstyle._values.clear()
    player_peak_accel._metrics.clear()
    player_peak_accel._values.clear()
    player_alive._metrics.clear()
    player_alive._values.clear()
    # Reset game state gauges to 0 to indicate no game running
    music_tempo.set(0)
    game_sensitivity.set(0)
    effective_warning_threshold.set(0)
    effective_death_threshold.set(0)
