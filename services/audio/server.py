"""
JoustMania Audio Microservice

Handles audio playback with priority-based mixing and real-time tempo control.
- Sound effects: pygame.mixer (8 channels, priority-based)
- Background music: MusicPlayer with scipy resampling for tempo control

Phase 9: Architecture Cleanup
Phase 70: Dynamic Music System
"""

import asyncio
import logging
import os
import threading

import grpc
import grpc.aio
import pygame
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import start_http_server

from lib.system_metrics import start_system_metrics_collector
from proto import audio_pb2, audio_pb2_grpc
from services.audio import metrics
from services.audio.music_player import DummyMusicPlayer, MusicPlayer

# Configure logging with environment variable support
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# OpenTelemetry setup
resource = Resource(attributes={"service.name": os.getenv("OTEL_SERVICE_NAME", "audio-service")})
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

# Configure OTLP exporter
otlp_exporter = OTLPSpanExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
    insecure=True,
)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(otlp_exporter))

# Instrument gRPC server
GrpcInstrumentorServer().instrument()


class AudioManager:
    """
    Manages audio playback with priority-based mixing and tempo control.

    - Sound effects: pygame.mixer (8 channels, priority-based)
    - Background music: MusicPlayer with scipy resampling for real-time tempo control
    """

    def __init__(self):
        """Initialize audio systems."""
        self.mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"

        # Assets directory - clients send relative paths, we resolve to full path
        self.assets_dir = os.getenv("AUDIO_ASSETS_DIR", "services/audio/assets")

        # Initialize pygame for sound effects
        if not self.mock_mode:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(8)  # Allow up to 8 simultaneous sounds
        else:
            logger.info("AudioManager running in MOCK_MODE - no actual audio playback")

        # Initialize music player with tempo control (Phase 70)
        if self.mock_mode:
            self.music_player = DummyMusicPlayer("background")
        else:
            self.music_player = MusicPlayer("background")

        self.current_music_file: str | None = None
        self.master_volume: float = 0.7
        self.music_lock = threading.Lock()

        logger.info(f"AudioManager initialized (assets_dir={self.assets_dir})")

        # Track currently playing sounds for status
        self.active_sounds: dict[str, dict] = {}

    def _resolve_path(self, relative_path: str) -> str:
        """Resolve relative path to full path using assets directory."""
        # If already absolute or starts with assets dir, use as-is
        if os.path.isabs(relative_path) or relative_path.startswith(self.assets_dir):
            return relative_path
        return os.path.join(self.assets_dir, relative_path)

    def play_sound(self, file_path: str, volume: float = 1.0, priority: int = 2) -> bool:
        """
        Play a sound effect (one-shot).

        Args:
            file_path: Relative path to audio file (e.g., "Joust/sounds/beep.wav")
            volume: Volume level (0.0 to 1.0)
            priority: Priority level (0=LOW, 3=CRITICAL)

        Returns:
            True if sound played successfully
        """
        # Resolve relative path to full path
        full_path = self._resolve_path(file_path)

        with tracer.start_as_current_span("play_sound") as span:
            span.set_attribute("audio.file", file_path)
            span.set_attribute("audio.full_path", full_path)
            span.set_attribute("audio.volume", volume)
            span.set_attribute("audio.priority", priority)

            if self.mock_mode:
                logger.debug(f"MOCK: Would play sound: {file_path}")
                return True

            try:
                if not os.path.exists(full_path):
                    logger.error(f"Audio file not found: {full_path} (requested: {file_path})")
                    return False

                # Load and play sound effect
                sound = pygame.mixer.Sound(full_path)
                adjusted_volume = volume * self.master_volume
                sound.set_volume(adjusted_volume)

                # Find available channel (or force if critical priority)
                channel = pygame.mixer.find_channel(priority == 3)
                if channel:
                    channel.play(sound)
                    logger.info(f"Playing sound: {file_path} " f"(volume={adjusted_volume:.2f}, priority={priority})")
                    span.add_event("sound_played")
                    return True
                logger.warning(f"No available channel for sound: {file_path}")
                return False

            except Exception as e:
                logger.error(f"Error playing sound {file_path}: {e}", exc_info=True)
                span.record_exception(e)
                return False

    def play_music(self, file_pattern: str, loop: bool = True, tempo: float = 1.0, priority: int = 1) -> str | None:
        """
        Play background music with tempo control.

        Args:
            file_pattern: Glob pattern for music files (e.g., "Joust/music/*.wav")
            loop: Whether to loop the music (always True for MusicPlayer)
            tempo: Playback speed (1.0 = normal, 1.3 = 30% faster)
            priority: Priority level (not used for music)

        Returns:
            Track ID if successful, None otherwise
        """
        # Resolve pattern to full path
        full_pattern = self._resolve_path(file_pattern)

        with tracer.start_as_current_span("play_music") as span:
            span.set_attribute("audio.pattern", file_pattern)
            span.set_attribute("audio.full_pattern", full_pattern)
            span.set_attribute("audio.loop", loop)
            span.set_attribute("audio.tempo", tempo)

            try:
                with self.music_lock:
                    # Stop current music if playing
                    if self.music_player.is_playing:
                        self.music_player.stop()

                    # Load and configure music
                    self.music_player.load(full_pattern)
                    self.music_player.set_volume(self.master_volume)
                    self.music_player.set_ratio(tempo)

                    # Start playback
                    track_id = self.music_player.start()
                    self.current_music_file = full_pattern

                    logger.info(f"Playing music: {file_pattern} (track_id={track_id}, tempo={tempo})")
                    span.add_event("music_started", {"track_id": track_id})

                    return track_id

            except Exception as e:
                logger.error(f"Error playing music {file_pattern}: {e}", exc_info=True)
                span.record_exception(e)
                return None

    def stop_music(self, track_id: str = "") -> bool:
        """
        Stop music track.

        Args:
            track_id: ID of track to stop (optional, stops current if empty)

        Returns:
            True if stopped successfully
        """
        with tracer.start_as_current_span("stop_music") as span:
            span.set_attribute("audio.track_id", track_id)

            try:
                with self.music_lock:
                    current_track = self.music_player.track_id
                    # Stop if no track_id specified or if it matches
                    if not track_id or current_track == track_id:
                        self.music_player.stop()
                        self.current_music_file = None
                        logger.info(f"Stopped music track: {current_track}")
                        span.add_event("music_stopped")
                        return True

                    logger.warning(f"Track ID mismatch: {track_id} != {current_track}")
                    return False

            except Exception as e:
                logger.error(f"Error stopping music {track_id}: {e}", exc_info=True)
                span.record_exception(e)
                return False

    def change_tempo(self, track_id: str, new_tempo: float, transition_duration: float = 1.0) -> bool:
        """
        Change music tempo with smooth transition.

        Uses scipy.signal.resample for real-time tempo changes.

        Args:
            track_id: ID of track to modify
            new_tempo: New playback speed (1.0 = normal, 1.3 = 30% faster)
            transition_duration: Seconds to smoothly transition

        Returns:
            True if tempo change started successfully
        """
        with tracer.start_as_current_span("change_tempo") as span:
            span.set_attribute("audio.track_id", track_id)
            span.set_attribute("audio.new_tempo", new_tempo)
            span.set_attribute("audio.transition_duration", transition_duration)

            try:
                current_track = self.music_player.track_id
                if track_id and current_track != track_id:
                    logger.warning(f"Track ID mismatch: {track_id} != {current_track}")
                    return False

                # Start async tempo transition
                asyncio.create_task(self.music_player.transition_ratio(new_tempo, transition_duration))

                logger.info(f"Tempo transition started: {self.music_player.ratio:.2f} -> {new_tempo:.2f}")
                span.add_event("tempo_transition_started")
                return True

            except Exception as e:
                logger.error(f"Error changing tempo: {e}", exc_info=True)
                span.record_exception(e)
                return False

    def set_volume(self, volume: float) -> bool:
        """
        Set master volume for both music and sound effects.

        Args:
            volume: Volume level (0.0 to 1.0)

        Returns:
            True if volume set successfully
        """
        with tracer.start_as_current_span("set_volume") as span:
            span.set_attribute("audio.volume", volume)

            try:
                self.master_volume = max(0.0, min(1.0, volume))
                self.music_player.set_volume(self.master_volume)
                logger.info(f"Master volume set to {self.master_volume:.2f}")
                return True
            except Exception as e:
                logger.error(f"Error setting volume: {e}", exc_info=True)
                span.record_exception(e)
                return False

    def get_status(self) -> dict:
        """
        Get current playback status.

        Returns:
            Dictionary with current status
        """
        with self.music_lock:
            return {
                "current_track_id": self.music_player.track_id or "",
                "current_track_file": self.current_music_file or "",
                "is_playing": self.music_player.is_playing,
                "volume": self.master_volume,
                "tempo": self.music_player.ratio,
                "queued_sounds_count": 0,
            }

    def cleanup(self):
        """Clean up audio resources."""
        self.music_player.cleanup()
        if not self.mock_mode:
            pygame.mixer.quit()


class AudioServiceServicer(audio_pb2_grpc.AudioServiceServicer):
    """gRPC servicer for Audio service."""

    def __init__(self):
        """Initialize audio servicer."""
        self.audio_manager = AudioManager()
        logger.info("AudioServiceServicer initialized")

    def PlaySound(self, request, context):
        """Play a sound effect."""
        with tracer.start_as_current_span("PlaySound_RPC") as span:
            span.set_attribute("audio.file", request.file_path)

            success = self.audio_manager.play_sound(
                file_path=request.file_path, volume=request.volume or 1.0, priority=request.priority
            )

            return audio_pb2.PlaySoundResponse(success=success, error="" if success else "Failed to play sound")

    def PlayMusic(self, request, context):
        """Play background music."""
        with tracer.start_as_current_span("PlayMusic_RPC") as span:
            span.set_attribute("audio.pattern", request.file_pattern)

            track_id = self.audio_manager.play_music(
                file_pattern=request.file_pattern,
                loop=request.loop,
                tempo=request.tempo or 1.0,
                priority=request.priority,
            )

            if track_id:
                return audio_pb2.PlayMusicResponse(track_id=track_id, success=True, error="")
            return audio_pb2.PlayMusicResponse(track_id="", success=False, error="Failed to play music")

    def StopMusic(self, request, context):
        """Stop music track."""
        with tracer.start_as_current_span("StopMusic_RPC"):
            success = self.audio_manager.stop_music(request.track_id)

            return audio_pb2.StopMusicResponse(success=success, error="" if success else "Failed to stop music")

    def ChangeTempo(self, request, context):
        """Change music tempo."""
        with tracer.start_as_current_span("ChangeTempo_RPC"):
            success = self.audio_manager.change_tempo(
                track_id=request.track_id,
                new_tempo=request.new_tempo,
                transition_duration=request.transition_duration or 1.0,
            )

            return audio_pb2.ChangeTempoResponse(success=success, error="" if success else "Failed to change tempo")

    def SetVolume(self, request, context):
        """Set master volume."""
        with tracer.start_as_current_span("SetVolume_RPC"):
            success = self.audio_manager.set_volume(request.volume)

            return audio_pb2.SetVolumeResponse(success=success, error="" if success else "Failed to set volume")

    def GetStatus(self, request, context):
        """Get current playback status."""
        with tracer.start_as_current_span("GetStatus_RPC"):
            status = self.audio_manager.get_status()

            return audio_pb2.GetStatusResponse(
                current_track_id=status["current_track_id"],
                current_track_file=status["current_track_file"],
                is_playing=status["is_playing"],
                volume=status["volume"],
                tempo=status["tempo"],
                queued_sounds_count=status["queued_sounds_count"],
                success=True,
                error="",
            )


async def serve(metrics_port=8000):
    """Start the Audio gRPC server."""
    logger.info("Starting JoustMania Audio service...")

    # Start Prometheus metrics HTTP server (Phase 38)
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics available at http://0.0.0.0:{metrics_port}/metrics")

    # Start system metrics collection (Phase 61: extracted to lib/system_metrics.py)
    start_system_metrics_collector(
        cpu_gauge=metrics.process_cpu_percent,
        memory_gauge=metrics.process_memory_mb,
        threads_gauge=metrics.process_threads,
    )

    # Create gRPC server with keepalive options to match client settings
    from lib.grpc_utils import get_server_options

    server = grpc.aio.server(options=get_server_options())
    audio_pb2_grpc.add_AudioServiceServicer_to_server(AudioServiceServicer(), server)

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the Audio service as SERVING
    await health_servicer.set("audio.AudioService", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # Overall health

    # Bind to port
    port = "50056"
    server.add_insecure_port(f"[::]:{port}")

    logger.info(f"Audio service listening on port {port}")

    # Start server
    await server.start()

    logger.info("Audio service ready")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Audio service...")
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
