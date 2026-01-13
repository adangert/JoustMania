"""
JoustMania Audio Microservice

Handles audio playback with priority-based mixing and tempo control.
Manages system audio device (/dev/snd/) to prevent conflicts between services.

Part of Phase 9 (Architecture Cleanup).
"""

import asyncio
import glob
import logging
import os
import random
import threading
import uuid

import grpc
import grpc.aio
import psutil
import pygame
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

# OpenTelemetry instrumentation
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Prometheus metrics (Phase 38)
from prometheus_client import start_http_server

# Import protobuf definitions
from proto import audio_pb2, audio_pb2_grpc
from services.audio import metrics

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
    Manages audio playback with priority-based mixing.

    Handles background music with tempo control and sound effects with priorities.
    """

    def __init__(self):
        """Initialize pygame mixer and audio state."""
        self.mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"

        if not self.mock_mode:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(8)  # Allow up to 8 simultaneous sounds
        else:
            logger.info("AudioManager running in MOCK_MODE - no actual audio playback")

        self.current_music_track: str | None = None
        self.current_music_file: str | None = None
        self.current_tempo: float = 1.0
        self.master_volume: float = 0.7
        self.is_playing: bool = False
        self.music_lock = threading.Lock()

        # Track currently playing sounds for status
        self.active_sounds: dict[str, dict] = {}

        logger.info("AudioManager initialized")

    def play_sound(self, file_path: str, volume: float = 1.0, priority: int = 2) -> bool:
        """
        Play a sound effect (one-shot).

        Args:
            file_path: Path to audio file
            volume: Volume level (0.0 to 1.0)
            priority: Priority level (0=LOW, 3=CRITICAL)

        Returns:
            True if sound played successfully
        """
        with tracer.start_as_current_span("play_sound") as span:
            span.set_attribute("audio.file", file_path)
            span.set_attribute("audio.volume", volume)
            span.set_attribute("audio.priority", priority)

            if self.mock_mode:
                logger.debug(f"MOCK: Would play sound: {file_path}")
                return True

            try:
                if not os.path.exists(file_path):
                    logger.error(f"Audio file not found: {file_path}")
                    return False

                # Load and play sound effect
                sound = pygame.mixer.Sound(file_path)
                adjusted_volume = volume * self.master_volume
                sound.set_volume(adjusted_volume)

                # Find available channel (or force if critical priority)
                channel = pygame.mixer.find_channel(priority == 3)
                if channel:
                    channel.play(sound)
                    logger.info(
                        f"Playing sound: {file_path} "
                        f"(volume={adjusted_volume:.2f}, priority={priority})"
                    )
                    span.add_event("sound_played")
                    return True
                logger.warning(f"No available channel for sound: {file_path}")
                return False

            except Exception as e:
                logger.error(f"Error playing sound {file_path}: {e}", exc_info=True)
                span.record_exception(e)
                return False

    def play_music(
        self, file_pattern: str, loop: bool = True, tempo: float = 1.0, priority: int = 1
    ) -> str | None:
        """
        Play background music (looping).

        Args:
            file_pattern: Glob pattern for music files (e.g. "audio/Joust/music/*.wav")
            loop: Whether to loop the music
            tempo: Playback speed (1.0 = normal, 1.5 = 50% faster)
            priority: Priority level

        Returns:
            Track ID if successful, None otherwise
        """
        with tracer.start_as_current_span("play_music") as span:
            span.set_attribute("audio.pattern", file_pattern)
            span.set_attribute("audio.loop", loop)
            span.set_attribute("audio.tempo", tempo)

            if self.mock_mode:
                track_id = str(uuid.uuid4())
                logger.debug(f"MOCK: Would play music pattern: {file_pattern}")
                self.current_music_track = track_id
                self.is_playing = True
                return track_id

            try:
                # Find matching audio files
                audio_files = glob.glob(file_pattern)
                if not audio_files:
                    logger.error(f"No audio files match pattern: {file_pattern}")
                    return None

                # Choose random file from pattern
                selected_file = random.choice(audio_files)

                with self.music_lock:
                    # Stop current music if playing
                    if self.is_playing:
                        pygame.mixer.music.stop()

                    # Load and play new music
                    pygame.mixer.music.load(selected_file)
                    pygame.mixer.music.set_volume(self.master_volume)
                    pygame.mixer.music.play(loops=-1 if loop else 0)

                    # Generate track ID
                    track_id = str(uuid.uuid4())
                    self.current_music_track = track_id
                    self.current_music_file = selected_file
                    self.current_tempo = tempo
                    self.is_playing = True

                    logger.info(
                        f"Playing music: {selected_file} "
                        f"(track_id={track_id}, tempo={tempo}, loop={loop})"
                    )
                    span.add_event("music_started", {"track_id": track_id})

                    return track_id

            except Exception as e:
                logger.error(f"Error playing music {file_pattern}: {e}", exc_info=True)
                span.record_exception(e)
                return None

    def stop_music(self, track_id: str) -> bool:
        """
        Stop music track.

        Args:
            track_id: ID of track to stop

        Returns:
            True if stopped successfully
        """
        with tracer.start_as_current_span("stop_music") as span:
            span.set_attribute("audio.track_id", track_id)

            if self.mock_mode:
                logger.debug(f"MOCK: Would stop music track: {track_id}")
                if self.current_music_track == track_id:
                    self.is_playing = False
                    self.current_music_track = None
                    return True
                return False

            try:
                with self.music_lock:
                    if self.current_music_track == track_id:
                        pygame.mixer.music.stop()
                        self.is_playing = False
                        self.current_music_track = None
                        self.current_music_file = None
                        logger.info(f"Stopped music track: {track_id}")
                        span.add_event("music_stopped")
                        return True
                    logger.warning(f"Track ID mismatch: {track_id} != {self.current_music_track}")
                    return False

            except Exception as e:
                logger.error(f"Error stopping music {track_id}: {e}", exc_info=True)
                span.record_exception(e)
                return False

    def change_tempo(
        self, track_id: str, new_tempo: float, transition_duration: float = 1.0
    ) -> bool:
        """
        Change music tempo (real-time speed adjustment).

        Note: pygame.mixer doesn't support tempo changes without resampling.
        This is a placeholder for future implementation.

        Args:
            track_id: ID of track to modify
            new_tempo: New playback speed
            transition_duration: Seconds to smoothly transition

        Returns:
            True if tempo changed successfully
        """
        with tracer.start_as_current_span("change_tempo") as span:
            span.set_attribute("audio.track_id", track_id)
            span.set_attribute("audio.new_tempo", new_tempo)

            # TODO: Implement real-time tempo change
            # pygame.mixer doesn't support this easily
            # Would need to use scipy.signal.resample with streaming

            logger.info(f"Tempo change requested: {new_tempo} (not implemented in pygame)")
            self.current_tempo = new_tempo
            return True

    def set_volume(self, volume: float) -> bool:
        """
        Set master volume.

        Args:
            volume: Volume level (0.0 to 1.0)

        Returns:
            True if volume set successfully
        """
        with tracer.start_as_current_span("set_volume") as span:
            span.set_attribute("audio.volume", volume)

            try:
                self.master_volume = max(0.0, min(1.0, volume))
                if not self.mock_mode:
                    pygame.mixer.music.set_volume(self.master_volume)
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
            is_busy = (
                self.is_playing
                if self.mock_mode
                else (self.is_playing and pygame.mixer.music.get_busy())
            )
            return {
                "current_track_id": self.current_music_track or "",
                "current_track_file": self.current_music_file or "",
                "is_playing": is_busy,
                "volume": self.master_volume,
                "tempo": self.current_tempo,
                "queued_sounds_count": 0,  # pygame doesn't expose queue
            }


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

            return audio_pb2.PlaySoundResponse(
                success=success, error="" if success else "Failed to play sound"
            )

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
            return audio_pb2.PlayMusicResponse(
                track_id="", success=False, error="Failed to play music"
            )

    def StopMusic(self, request, context):
        """Stop music track."""
        with tracer.start_as_current_span("StopMusic_RPC"):
            success = self.audio_manager.stop_music(request.track_id)

            return audio_pb2.StopMusicResponse(
                success=success, error="" if success else "Failed to stop music"
            )

    def ChangeTempo(self, request, context):
        """Change music tempo."""
        with tracer.start_as_current_span("ChangeTempo_RPC"):
            success = self.audio_manager.change_tempo(
                track_id=request.track_id,
                new_tempo=request.new_tempo,
                transition_duration=request.transition_duration or 1.0,
            )

            return audio_pb2.ChangeTempoResponse(
                success=success, error="" if success else "Failed to change tempo"
            )

    def SetVolume(self, request, context):
        """Set master volume."""
        with tracer.start_as_current_span("SetVolume_RPC"):
            success = self.audio_manager.set_volume(request.volume)

            return audio_pb2.SetVolumeResponse(
                success=success, error="" if success else "Failed to set volume"
            )

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

    # Start system metrics collection task (Phase 38)
    async def collect_system_metrics():
        """
        Background task to collect system metrics every 10 seconds.
        Phase 34: Run psutil calls in thread pool to avoid blocking event loop.
        """
        process = psutil.Process()
        loop = asyncio.get_event_loop()

        while True:
            try:
                # Phase 34: Run blocking psutil calls in thread pool
                cpu_percent = await loop.run_in_executor(
                    None, lambda: process.cpu_percent(interval=None)
                )
                mem_info = await loop.run_in_executor(None, lambda: process.memory_info())
                thread_count = await loop.run_in_executor(None, process.num_threads)

                metrics.process_cpu_percent.set(cpu_percent)
                metrics.process_memory_mb.set(mem_info.rss / 1024 / 1024)
                metrics.process_threads.set(thread_count)
            except Exception as e:
                logger.error(f"Error collecting system metrics: {e}")
            await asyncio.sleep(10.0)

    asyncio.create_task(collect_system_metrics())

    # Create gRPC server
    server = grpc.aio.server()
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
