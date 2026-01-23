"""
JoustMania Audio Microservice

Handles audio playback with priority-based mixing and real-time tempo control.
- Sound effects: miniaudio for distroless compatibility
- Background music: MusicPlayer with resampy for real-time tempo control

See services/audio/servicer.py for the AudioServiceServicer implementation.
"""

import asyncio
import logging
import os

import grpc.aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from prometheus_client import start_http_server

from lib.system_metrics import start_system_metrics_collector
from proto import audio_pb2_grpc
from services.audio import metrics
from services.audio.servicer import AudioServiceServicer

logger = logging.getLogger(__name__)


async def serve(metrics_port=8000):
    """Start the Audio gRPC server."""
    # Configure logging
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting JoustMania Audio service...")

    # Start Prometheus metrics HTTP server
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics available at http://0.0.0.0:{metrics_port}/metrics")

    # Start system metrics collection
    start_system_metrics_collector(
        cpu_gauge=metrics.process_cpu_percent,
        memory_gauge=metrics.process_memory_mb,
        threads_gauge=metrics.process_threads,
    )

    # Create gRPC server with keepalive options to match client settings
    from lib.grpc_utils import get_server_options

    server = grpc.aio.server(options=get_server_options())
    audio_servicer = AudioServiceServicer()
    audio_pb2_grpc.add_AudioServiceServicer_to_server(audio_servicer, server)

    # Set the event loop for async operations (tempo transitions)
    audio_servicer.audio_manager.set_event_loop(asyncio.get_running_loop())

    # Load audio enabled setting from settings service
    await audio_servicer._load_audio_setting()

    # Add health checking service
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark the Audio service as SERVING
    await health_servicer.set("audio.AudioService", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # Overall health

    # Bind to port (configurable via AUDIO_PORT env var)
    port = int(os.environ.get("AUDIO_PORT", "50056"))
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
