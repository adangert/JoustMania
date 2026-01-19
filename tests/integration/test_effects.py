"""
Controller effects tests for JoustMania mock environment.

Tests visual effects like FLASH, PULSE, RAINBOW, FADE.
"""

import asyncio
import os
import sys

import grpc
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from proto import (
    controller_manager_pb2,
    controller_manager_pb2_grpc,
)


@pytest.mark.asyncio
async def test_controller_effects(docker_compose):
    """Test controller visual effects (FLASH, PULSE, RAINBOW, FADE) - Phase 31."""

    # Get dynamically assigned port for controller manager
    host = docker_compose.get_service_host("controller-manager", 50052)
    port = docker_compose.get_service_port("controller-manager", 50052)

    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    # Test 1: FLASH effect on single controller
    flash_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_FLASH,
            color=controller_manager_pb2.RGB(r=255, g=0, b=0),  # Red
            duration_ms=500,
            speed=5,
        )
    )
    assert flash_response.success
    await asyncio.sleep(0.6)  # Wait for effect to complete

    # Test 2: PULSE effect on single controller
    pulse_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_1",
            effect=controller_manager_pb2.EFFECT_PULSE,
            color=controller_manager_pb2.RGB(r=0, g=255, b=0),  # Green
            duration_ms=500,
            speed=3,
        )
    )
    assert pulse_response.success
    await asyncio.sleep(0.6)

    # Test 3: RAINBOW effect on single controller
    rainbow_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_2",
            effect=controller_manager_pb2.EFFECT_RAINBOW,
            duration_ms=500,
            speed=5,
        )
    )
    assert rainbow_response.success
    await asyncio.sleep(0.6)

    # Test 4: FADE_OUT effect
    fade_out_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_3",
            effect=controller_manager_pb2.EFFECT_FADE_OUT,
            color=controller_manager_pb2.RGB(r=0, g=0, b=255),  # Blue
            duration_ms=300,
        )
    )
    assert fade_out_response.success
    await asyncio.sleep(0.4)

    # Test 5: FADE_IN effect
    fade_in_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_3",
            effect=controller_manager_pb2.EFFECT_FADE_IN,
            color=controller_manager_pb2.RGB(r=255, g=255, b=0),  # Yellow
            duration_ms=300,
        )
    )
    assert fade_in_response.success
    await asyncio.sleep(0.4)

    # Test 6: EFFECT_NONE (solid color)
    none_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_NONE,
            color=controller_manager_pb2.RGB(r=255, g=0, b=255),  # Magenta
            duration_ms=0,
        )
    )
    assert none_response.success

    # Test 7: Effect on all controllers (empty serial)
    all_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="",  # All controllers
            effect=controller_manager_pb2.EFFECT_FLASH,
            color=controller_manager_pb2.RGB(r=255, g=255, b=255),  # White
            duration_ms=500,
            speed=10,  # Fast flash
        )
    )
    assert all_response.success
    await asyncio.sleep(0.6)

    # Test 8: Effect cancellation (start new effect before previous completes)
    # Start long-running effect
    await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_PULSE,
            color=controller_manager_pb2.RGB(r=255, g=0, b=0),
            duration_ms=2000,  # 2 seconds
            speed=1,
        )
    )
    await asyncio.sleep(0.2)  # Let it start

    # Cancel by starting new effect
    cancel_response = await client.PlayControllerEffect(
        controller_manager_pb2.PlayControllerEffectRequest(
            serial="mock_controller_0",
            effect=controller_manager_pb2.EFFECT_FLASH,
            color=controller_manager_pb2.RGB(r=0, g=255, b=0),
            duration_ms=300,
            speed=5,
        )
    )
    assert cancel_response.success
    await asyncio.sleep(0.4)

    await channel.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "effect,color,duration",
    [
        (controller_manager_pb2.EFFECT_FLASH, (255, 0, 0), 500),
        (controller_manager_pb2.EFFECT_PULSE, (0, 255, 0), 500),
        (controller_manager_pb2.EFFECT_RAINBOW, None, 500),
        (controller_manager_pb2.EFFECT_FADE_OUT, (0, 0, 255), 300),
        (controller_manager_pb2.EFFECT_FADE_IN, (255, 255, 0), 300),
    ],
)
async def test_individual_effect(docker_compose, effect, color, duration):
    """Test individual controller effect types."""
    host = docker_compose.get_service_host("controller-manager", 50052)
    port = docker_compose.get_service_port("controller-manager", 50052)

    channel = grpc.aio.insecure_channel(f"{host}:{port}")
    client = controller_manager_pb2_grpc.ControllerManagerServiceStub(channel)

    request = controller_manager_pb2.PlayControllerEffectRequest(
        serial="mock_controller_0",
        effect=effect,
        duration_ms=duration,
        speed=5,
    )

    if color:
        request.color.CopyFrom(controller_manager_pb2.RGB(r=color[0], g=color[1], b=color[2]))

    response = await client.PlayControllerEffect(request)
    assert response.success

    # Wait for effect to complete
    await asyncio.sleep(duration / 1000 + 0.2)

    await channel.close()
