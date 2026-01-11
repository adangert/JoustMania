"""
Runtime Configuration System for JoustMania (Phase 43)

Simple configuration holder for game performance parameters.
Provides default values that can be read by game loop.

Phase 44 will add OpenFeature integration for dynamic flag-based configuration.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GamePerformanceConfig:
    """Runtime configuration for game performance parameters."""

    # Core performance
    update_frequency_hz: int = 30  # Game loop frequency
    enable_delta_compression: bool = True

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
    Phase 44: Will integrate with OpenFeature for dynamic flag evaluation.
    """

    def __init__(self):
        self.config = GamePerformanceConfig()

    def get_config(self) -> GamePerformanceConfig:
        """Get current configuration."""
        return self.config

    async def get_update_interval(self) -> float:
        """Get current update interval in seconds."""
        return 1.0 / self.config.update_frequency_hz

    def export_config(self) -> dict:
        """Export current configuration as dict (for reports/logs)."""
        return self.config.__dict__.copy()


# Global singleton instance
_global_config_manager: Optional[RuntimeConfigManager] = None


def get_config_manager() -> RuntimeConfigManager:
    """Get the global runtime configuration manager."""
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = RuntimeConfigManager()
    return _global_config_manager


def get_current_config() -> GamePerformanceConfig:
    """Quick access to current configuration."""
    return get_config_manager().get_config()
