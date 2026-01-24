"""
Shared pytest fixtures for JoustMania integration tests.

These fixtures provide:
- Docker compose environment management
- Automatic cleanup between tests
- Pre-connected gRPC clients

Usage:
    Fixtures are auto-discovered by pytest from this conftest.py file.
    Import helpers from helpers.py for shared utility functions.

Environment Variables:
    USE_PREBUILT_IMAGES: Set to "true" to pull images from GHCR instead of building
    IMAGE_TAG: Specify image tag to pull (default: latest)
"""

import asyncio
import os
import sys
import time

import grpc
import pytest
from testcontainers.compose import DockerCompose

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from proto import (
    game_coordinator_pb2,
    game_coordinator_pb2_grpc,
)


@pytest.fixture(scope="session")
def docker_compose():
    """Fixture to start docker-compose mock environment.

    Uses docker-compose.yml with overrides for testing:
    - docker-compose.override.yml: port exposures for testing
    - docker-compose.ci.yml: mock mode for audio/controllers (no hardware)

    By default, builds images locally. Set USE_PREBUILT_IMAGES=true to pull from GHCR.
    """
    # Check if we should use prebuilt images
    use_prebuilt = os.getenv("USE_PREBUILT_IMAGES", "false").lower() == "true"
    image_tag = os.getenv("IMAGE_TAG", "latest")

    compose = DockerCompose(
        context=".",
        compose_file_name=[
            "docker-compose.yml",
            "docker-compose.override.yml",
            "docker-compose.ci.yml",
        ],
        pull=use_prebuilt,
        build=not use_prebuilt,
        env_file=None,  # Avoid conflicts with .env (e.g., IMAGE_TAG from development)
    )

    # Set IMAGE_TAG if using prebuilt images
    # Note: This modifies the environment for docker-compose but is session-scoped
    if use_prebuilt:
        os.environ["IMAGE_TAG"] = image_tag
        print(f"\n🐳 Using prebuilt images from GHCR (tag: {image_tag})")
    else:
        print("\n🔨 Building images locally")

    compose.start()

    # Wait for services to be ready
    time.sleep(10)

    print("\n" + "=" * 80)
    print("🚀 Mock environment is running!")
    print("=" * 80)
    print("Jaeger UI: http://localhost:16686")
    print("WebUI: http://localhost:80")
    print("Mock Control API: localhost:50062")
    print("=" * 80)

    yield compose

    # Optional pause before teardown (set PAUSE_BEFORE_TEARDOWN=1 to inspect Jaeger)
    if os.getenv("PAUSE_BEFORE_TEARDOWN"):
        print("\n" + "=" * 80)
        print("⏸️  PAUSED - Inspect Jaeger at http://localhost:16686")
        print("=" * 80)
        print("Press ENTER to tear down the environment...")
        input()

    compose.stop()


@pytest.fixture
async def ensure_game_stopped(docker_compose):
    """Ensure no game is running before and after each test.

    Use this fixture explicitly in tests that start games to prevent
    'Game already in progress' errors between tests.
    """
    async def force_end_game():
        """Force end any running game."""
        try:
            host = docker_compose.get_service_host("game-coordinator", 50053)
            port = docker_compose.get_service_port("game-coordinator", 50053)
            channel = grpc.aio.insecure_channel(f"{host}:{port}")
            client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(channel)

            # Try to force end any running game
            await client.ForceEndGame(game_coordinator_pb2.ForceEndGameRequest())

            # Brief wait for cleanup
            await asyncio.sleep(0.5)

            await channel.close()
        except Exception:
            pass  # Ignore errors (no game running, service not ready, etc.)

    # Before test: ensure no game is running
    await force_end_game()

    yield

    # After test: cleanup any game that was started
    await force_end_game()
