"""
Shared gRPC utilities for JoustMania services (Phase 33).

Provides standardized channel options and factory functions to eliminate
code duplication across services.
"""

import grpc
from typing import Optional


def get_optimized_channel_options() -> list[tuple[str, any]]:
    """
    Get standard gRPC channel options for JoustMania services.

    These options optimize for:
    - Connection keepalive (30s ping, 5s timeout)
    - Fast reconnection (1s initial backoff, 5s max)
    - Large message support (10MB max)
    - Compression (Gzip)

    Returns:
        List of (option_name, value) tuples for gRPC channel configuration
    """
    return [
        # Keepalive settings (Phase 26 - Network Improvements)
        ("grpc.keepalive_time_ms", 30000),  # Send keepalive ping every 30s
        ("grpc.keepalive_timeout_ms", 5000),  # Wait 5s for keepalive ack
        ("grpc.keepalive_permit_without_calls", True),  # Allow keepalive without active calls
        ("grpc.http2.max_pings_without_data", 2),  # Allow pings without data
        # Reconnection settings
        ("grpc.initial_reconnect_backoff_ms", 1000),  # Start reconnect after 1s
        ("grpc.max_reconnect_backoff_ms", 5000),  # Max reconnect backoff 5s
        # Message size limits
        ("grpc.max_receive_message_length", 10 * 1024 * 1024),  # 10MB receive
        ("grpc.max_send_message_length", 10 * 1024 * 1024),  # 10MB send
        # Compression (Phase 26 - Performance)
        ("grpc.default_compression_algorithm", grpc.Compression.Gzip),
        ("grpc.grpc.default_compression_level", grpc.Compression.Gzip),
    ]


def create_channel(
    address: str,
    options: Optional[list[tuple[str, any]]] = None,
    **kwargs
) -> grpc.aio.Channel:
    """
    Create an async gRPC channel with standard JoustMania options.

    Args:
        address: Target address in format "host:port"
        options: Optional custom channel options (defaults to optimized options)
        **kwargs: Additional arguments passed to grpc.aio.insecure_channel

    Returns:
        Configured async gRPC channel

    Example:
        >>> channel = create_channel("localhost:50051")
        >>> stub = MyServiceStub(channel)
    """
    if options is None:
        options = get_optimized_channel_options()

    return grpc.aio.insecure_channel(address, options=options, **kwargs)


def create_channel_with_custom_options(
    address: str,
    extra_options: list[tuple[str, any]],
    **kwargs
) -> grpc.aio.Channel:
    """
    Create an async gRPC channel with standard options plus custom additions.

    Args:
        address: Target address in format "host:port"
        extra_options: Additional channel options to merge with standard options
        **kwargs: Additional arguments passed to grpc.aio.insecure_channel

    Returns:
        Configured async gRPC channel with merged options

    Example:
        >>> extra = [("grpc.max_connection_idle_ms", 60000)]
        >>> channel = create_channel_with_custom_options("localhost:50051", extra)
    """
    options = get_optimized_channel_options() + extra_options
    return grpc.aio.insecure_channel(address, options=options, **kwargs)
