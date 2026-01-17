"""
Controller Analytics for Gameplay Analysis

Tracks player movement patterns, acceleration data, and near-death events
during games for post-game analysis and real-time dashboards.

Key features:
- Per-frame sampling of acceleration (and optionally gyroscope)
- Movement zone classification (still/active/warning/danger)
- Near-death event detection (raw > threshold but EMA saved player)
- Per-game summary statistics
- Optional 60Hz replay data for testing/replay

Memory footprint:
- Base: ~500 bytes per player (counters + running stats)
- Replay mode: +48 bytes per sample x 60Hz x duration (~170KB/3min game)
"""

import json
import logging
import math
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.game_coordinator.runtime_config import AnalyticsConfig

logger = logging.getLogger(__name__)


class MovementZone(IntEnum):
    """Movement intensity zones based on acceleration magnitude."""

    STILL = 0  # < 1.1g - minimal movement
    ACTIVE = 1  # 1.1-1.5g - normal movement
    WARNING = 2  # 1.5-2.0g - approaching danger
    DANGER = 3  # > 2.0g - high risk of death


class Playstyle(IntEnum):
    """Player playstyle classification based on movement patterns."""

    CALM = 0  # Mostly still, minimal movement
    BALANCED = 1  # Mix of still and active
    ACTIVE = 2  # Frequent movement, some warning zone
    AGGRESSIVE = 3  # Lots of warning/danger zone time


@dataclass
class ReplaySample:
    """Single 60Hz sample for replay/testing."""

    timestamp_ms: int  # Milliseconds since game start
    accel_x: float
    accel_y: float
    accel_z: float
    accel_mag: float
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "ts": self.timestamp_ms,
            "ax": round(self.accel_x, 4),
            "ay": round(self.accel_y, 4),
            "az": round(self.accel_z, 4),
            "am": round(self.accel_mag, 4),
            "gx": round(self.gyro_x, 4),
            "gy": round(self.gyro_y, 4),
            "gz": round(self.gyro_z, 4),
        }


@dataclass
class PlayerAnalytics:
    """
    Analytics tracker for a single player during a game.

    Accumulates statistics on movement patterns, near-death events,
    and optionally stores full 60Hz replay data.
    """

    serial: str
    game_start_time: float

    # Running totals (updated every frame)
    total_accel_magnitude: float = 0.0
    sample_count: int = 0
    peak_accel: float = 0.0
    peak_accel_time: float = 0.0  # Seconds since game start

    # Gyro tracking (optional, enabled via config)
    total_gyro_magnitude: float = 0.0
    peak_gyro: float = 0.0

    # Zone tracking (milliseconds in each zone) - fixed thresholds
    time_still_ms: int = 0  # < 1.1g
    time_active_ms: int = 0  # 1.1-1.5g
    time_warning_ms: int = 0  # 1.5-2.0g
    time_danger_ms: int = 0  # > 2.0g

    # Events
    near_death_count: int = 0  # Times raw > death threshold but EMA saved player
    warning_count: int = 0  # Total warning triggers

    # For standard deviation calculation (Welford's algorithm)
    _mean: float = 0.0
    _m2: float = 0.0  # Sum of squared differences from mean

    # Replay buffer (if enabled)
    replay_samples: list[ReplaySample] = field(default_factory=list)

    # Track last zone for metrics
    _last_zone: MovementZone = MovementZone.STILL

    def record_sample(
        self,
        accel_x: float,
        accel_y: float,
        accel_z: float,
        raw_accel_mag: float,
        smoothed_accel: float,
        death_threshold: float,
        config: "AnalyticsConfig",
        gyro_x: float = 0.0,
        gyro_y: float = 0.0,
        gyro_z: float = 0.0,
        frame_duration_ms: float = 16.67,  # ~60Hz
    ) -> MovementZone:
        """
        Record a single frame of controller data.

        Args:
            accel_x, accel_y, accel_z: Raw accelerometer values (g-force)
            raw_accel_mag: Raw acceleration magnitude (g-force)
            smoothed_accel: EMA-smoothed acceleration magnitude
            death_threshold: Current death threshold (for near-death detection)
            config: Analytics configuration
            gyro_x, gyro_y, gyro_z: Raw gyroscope values (optional)
            frame_duration_ms: Duration of this frame in milliseconds

        Returns:
            The movement zone for this sample
        """
        self.sample_count += 1
        self.total_accel_magnitude += raw_accel_mag

        # Update peak
        if raw_accel_mag > self.peak_accel:
            self.peak_accel = raw_accel_mag
            self.peak_accel_time = time.time() - self.game_start_time

        # Welford's online algorithm for mean/variance
        delta = raw_accel_mag - self._mean
        self._mean += delta / self.sample_count
        delta2 = raw_accel_mag - self._mean
        self._m2 += delta * delta2

        # Gyro tracking (optional)
        if config.track_gyro:
            gyro_mag = math.sqrt(gyro_x**2 + gyro_y**2 + gyro_z**2)
            self.total_gyro_magnitude += gyro_mag
            if gyro_mag > self.peak_gyro:
                self.peak_gyro = gyro_mag

        # Zone classification using fixed thresholds
        zone = self._classify_zone(raw_accel_mag, config)
        frame_ms = int(frame_duration_ms)

        if zone == MovementZone.STILL:
            self.time_still_ms += frame_ms
        elif zone == MovementZone.ACTIVE:
            self.time_active_ms += frame_ms
        elif zone == MovementZone.WARNING:
            self.time_warning_ms += frame_ms
        else:  # DANGER
            self.time_danger_ms += frame_ms

        self._last_zone = zone

        # Near-death detection: raw exceeded threshold but EMA saved them
        if raw_accel_mag > death_threshold and smoothed_accel <= death_threshold:
            self.near_death_count += 1

        # Replay buffer (optional)
        if config.enable_replay:
            timestamp_ms = int((time.time() - self.game_start_time) * 1000)
            sample = ReplaySample(
                timestamp_ms=timestamp_ms,
                accel_x=accel_x,
                accel_y=accel_y,
                accel_z=accel_z,
                accel_mag=raw_accel_mag,
                gyro_x=gyro_x if config.track_gyro else 0.0,
                gyro_y=gyro_y if config.track_gyro else 0.0,
                gyro_z=gyro_z if config.track_gyro else 0.0,
            )
            self.replay_samples.append(sample)

        return zone

    def record_warning(self) -> None:
        """Record that a warning was triggered for this player."""
        self.warning_count += 1

    def _classify_zone(self, accel_mag: float, config: "AnalyticsConfig") -> MovementZone:
        """Classify acceleration magnitude into movement zone."""
        if accel_mag < config.zone_still_max:
            return MovementZone.STILL
        if accel_mag < config.zone_active_max:
            return MovementZone.ACTIVE
        if accel_mag < config.zone_warning_max:
            return MovementZone.WARNING
        return MovementZone.DANGER

    @property
    def average_accel(self) -> float:
        """Calculate average acceleration magnitude."""
        if self.sample_count == 0:
            return 0.0
        return self.total_accel_magnitude / self.sample_count

    @property
    def std_deviation(self) -> float:
        """Calculate standard deviation of acceleration (Welford's algorithm)."""
        if self.sample_count < 2:
            return 0.0
        return math.sqrt(self._m2 / (self.sample_count - 1))

    @property
    def total_time_ms(self) -> int:
        """Total tracked time in milliseconds."""
        return self.time_still_ms + self.time_active_ms + self.time_warning_ms + self.time_danger_ms

    def get_zone_percentages(self) -> dict[str, float]:
        """Get percentage of time spent in each zone."""
        total = self.total_time_ms
        if total == 0:
            return {"still": 0.0, "active": 0.0, "warning": 0.0, "danger": 0.0}

        return {
            "still": (self.time_still_ms / total) * 100,
            "active": (self.time_active_ms / total) * 100,
            "warning": (self.time_warning_ms / total) * 100,
            "danger": (self.time_danger_ms / total) * 100,
        }

    def get_playstyle(self) -> Playstyle:
        """
        Classify player's playstyle based on zone distribution.

        Categories:
        - CALM: >70% still, <10% warning+danger
        - BALANCED: 40-70% still, <20% warning+danger
        - ACTIVE: <40% still, <30% warning+danger
        - AGGRESSIVE: >30% warning+danger
        """
        zones = self.get_zone_percentages()
        warning_danger = zones["warning"] + zones["danger"]

        if warning_danger > 30:
            return Playstyle.AGGRESSIVE
        if zones["still"] > 70 and warning_danger < 10:
            return Playstyle.CALM
        if zones["still"] > 40 and warning_danger < 20:
            return Playstyle.BALANCED
        return Playstyle.ACTIVE

    def get_summary(self) -> dict:
        """
        Get complete analytics summary for this player.

        Returns dict suitable for span attributes, event publishing, etc.
        """
        zones = self.get_zone_percentages()
        playstyle = self.get_playstyle()

        return {
            "serial": self.serial,
            "sample_count": self.sample_count,
            "duration_ms": self.total_time_ms,
            # Acceleration stats
            "peak_accel": round(self.peak_accel, 3),
            "peak_accel_time": round(self.peak_accel_time, 2),
            "avg_accel": round(self.average_accel, 3),
            "std_accel": round(self.std_deviation, 3),
            "total_accel": round(self.total_accel_magnitude, 2),
            # Gyro stats (if tracked)
            "peak_gyro": round(self.peak_gyro, 3),
            "avg_gyro": round(self.total_gyro_magnitude / max(1, self.sample_count), 3),
            # Zone distribution
            "zone_still_pct": round(zones["still"], 1),
            "zone_active_pct": round(zones["active"], 1),
            "zone_warning_pct": round(zones["warning"], 1),
            "zone_danger_pct": round(zones["danger"], 1),
            # Events
            "near_death_count": self.near_death_count,
            "warning_count": self.warning_count,
            # Classification
            "playstyle": playstyle.name.lower(),
            "playstyle_value": playstyle.value,
        }

    def export_replay_json(self) -> str:
        """Export replay samples as JSON string."""
        return json.dumps(
            {
                "serial": self.serial,
                "game_start": self.game_start_time,
                "samples": [s.to_dict() for s in self.replay_samples],
            }
        )

    async def store_replay_to_redis(
        self,
        redis_client,
        game_id: str,
        ttl_seconds: int = 3600,
    ) -> bool:
        """
        Store replay data to Redis for later retrieval.

        Args:
            redis_client: Async Redis client
            game_id: Unique game identifier
            ttl_seconds: Time-to-live for the key

        Returns:
            True if stored successfully, False otherwise
        """
        if not self.replay_samples:
            return False

        try:
            key = f"replay:{game_id}:{self.serial}"
            data = self.export_replay_json()
            await redis_client.setex(key, ttl_seconds, data)
            logger.debug(f"Stored {len(self.replay_samples)} replay samples to {key}")
            return True
        except Exception as e:
            logger.warning(f"Failed to store replay data: {e}")
            return False
