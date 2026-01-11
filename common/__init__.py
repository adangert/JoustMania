"""
Common utilities shared across JoustMania services (Phase 33).
"""

from .grpc_utils import (
    get_optimized_channel_options,
    create_channel,
    create_channel_with_custom_options,
)

__all__ = [
    "get_optimized_channel_options",
    "create_channel",
    "create_channel_with_custom_options",
]
