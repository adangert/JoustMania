"""
Runtime Configuration System for JoustMania (Phase 43)

Simple configuration holder for game performance parameters.
Provides default values that can be read by game loop.

Phase 44 will add OpenFeature integration for dynamic flag-based configuration.
"""

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsConfig:
    """Configuration for controller analytics during gameplay."""

    # Master toggle
    enabled: bool = True

    # Feature toggles
    track_gyro: bool = False  # Track rotation data (increases memory/cpu slightly)
    enable_replay: bool = False  # Store 60Hz samples for replay/testing
    replay_ttl_seconds: int = 3600  # Redis TTL for replay data (1 hour)

    # Fixed zone thresholds (in g-force units, ~4096 raw = 1g)
    # These define movement intensity zones for activity classification
    zone_still_max: float = 1.1  # < 1.1g = still
    zone_active_max: float = 1.5  # 1.1-1.5g = active movement
    zone_warning_max: float = 2.0  # 1.5-2.0g = warning zone
    # > 2.0g = danger zone

    # Metrics emission interval (emit Prometheus gauges every N frames)
    metrics_emit_interval_frames: int = 6  # ~100ms at 60Hz (10Hz updates)


@dataclass
class GamePerformanceConfig:
    """Runtime configuration for game performance parameters."""

    # Core performance
    # Phase 72: Increased from 30Hz to 60Hz for better responsiveness
    update_frequency_hz: int = 60  # Game loop frequency
    enable_delta_compression: bool = True

    # Countdown duration (seconds) - configurable for faster tests
    # Set COUNTDOWN_DURATION_SECONDS=0 to skip countdown entirely
    countdown_duration_seconds: int = 3

    # Winner rainbow effect duration (milliseconds) - configurable for faster tests
    # Set WINNER_RAINBOW_DURATION_MS=300 for fast tests (default 3000ms = 3s)
    winner_rainbow_duration_ms: int = 3000

    # Analytics configuration
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)

    # Monitoring
    enable_metrics: bool = True
    enable_tracing: bool = True
    metrics_interval_sec: int = 5

    # Performance thresholds
    max_latency_ms: float = 100.0
    target_cpu_percent: float = 50.0

    # USB/Streaming
    stream_buffer_size: int = 100
    usb_check_interval_sec: float = 30.0

    # Sensitivity
    sensitivity_mode: str = "MEDIUM"  # SLOW, MEDIUM, FAST

    # Experimental features
    adaptive_hz: bool = False
    adaptive_min_hz: int = 15
    adaptive_max_hz: int = 60


class RuntimeConfigManager:
    """
    Manages runtime configuration.

    Phase 43: Simple configuration holder with defaults.
    Phase 44: Integrated with OpenFeature for dynamic flag evaluation.
    """

    def __init__(self):
        self.config = GamePerformanceConfig()
        self._apply_environment_overrides()

        # Initialize feature flag client
        try:
            from lib.feature_flags import get_feature_flag_client

            self.flag_client = get_feature_flag_client()
            logger.info("Feature flag client initialized")
        except ImportError:
            self.flag_client = None
            logger.warning("Could not import FeatureFlagClient, using defaults")
        except Exception as e:
            self.flag_client = None
            logger.error(f"Failed to initialize feature flags: {e}")

    def _apply_environment_overrides(self):
        """Apply environment variable overrides to configuration."""
        # Countdown duration override (for faster tests)
        countdown_env = os.environ.get("COUNTDOWN_DURATION_SECONDS")
        if countdown_env is not None:
            try:
                self.config.countdown_duration_seconds = int(countdown_env)
                logger.info(f"Countdown duration overridden to {self.config.countdown_duration_seconds}s")
            except ValueError:
                logger.warning(f"Invalid COUNTDOWN_DURATION_SECONDS: {countdown_env}")

        # Winner rainbow duration override (for faster tests)
        rainbow_env = os.environ.get("WINNER_RAINBOW_DURATION_MS")
        if rainbow_env is not None:
            try:
                self.config.winner_rainbow_duration_ms = int(rainbow_env)
                logger.info(f"Winner rainbow duration overridden to {self.config.winner_rainbow_duration_ms}ms")
            except ValueError:
                logger.warning(f"Invalid WINNER_RAINBOW_DURATION_MS: {rainbow_env}")

    def _refresh_from_flags(self):
        """Update configuration from feature flags."""
        if not self.flag_client:
            return

        try:
            # Update frequency (15/30/60 Hz)
            hz = self.flag_client.get_integer_value("update_frequency_hz", self.config.update_frequency_hz)
            if hz != self.config.update_frequency_hz:
                logger.debug(f"Config update: update_frequency_hz = {hz}")
                self.config.update_frequency_hz = hz

            # Sensitivity mode (LOW, MEDIUM, HIGH)
            sensitivity = self.flag_client.get_string_value("sensitivity_mode", self.config.sensitivity_mode)
            if sensitivity != self.config.sensitivity_mode:
                logger.debug(f"Config update: sensitivity_mode = {sensitivity}")
                self.config.sensitivity_mode = sensitivity

        except Exception as e:
            # Don't crash on flag evaluation failure, just log and keep defaults
            logger.warning(f"Failed to evaluate flags: {e}")

    def get_config(self) -> GamePerformanceConfig:
        """Get current configuration (with fresh flag values)."""
        # Refresh flags on every access (OpenFeature client handles caching/evaluation)
        self._refresh_from_flags()
        return self.config

    async def get_update_interval(self) -> float:
        """Get current update interval in seconds."""
        # Ensure we're using fresh config
        self._refresh_from_flags()
        return 1.0 / self.config.update_frequency_hz

    def export_config(self) -> dict:
        """Export current configuration as dict (for reports/logs)."""
        self._refresh_from_flags()
        return self.config.__dict__.copy()


# Global singleton instance
_global_config_manager: RuntimeConfigManager | None = None


def get_config_manager() -> RuntimeConfigManager:
    """Get the global runtime configuration manager."""
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = RuntimeConfigManager()
    return _global_config_manager


def get_current_config() -> GamePerformanceConfig:
    """Quick access to current configuration."""
    return get_config_manager().get_config()
