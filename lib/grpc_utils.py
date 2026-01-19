"""
Shared gRPC utilities for JoustMania services (Phase 33).

Provides standardized channel options and factory functions to eliminate
code duplication across services.

Phase 80: Added tracing interceptors for distributed trace propagation
across async gRPC calls.
"""

from typing import Any

import grpc


def get_optimized_channel_options() -> list[tuple[str, any]]:
    """
    Get standard gRPC channel options for JoustMania services (client-side).

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


def get_server_options() -> list[tuple[str, any]]:
    """
    Get standard gRPC server options for JoustMania services.

    These options must be compatible with client keepalive settings to avoid
    "GOAWAY too many pings" errors.

    Returns:
        List of (option_name, value) tuples for gRPC server configuration
    """
    return [
        # Server-side keepalive settings (must match client expectations)
        ("grpc.keepalive_time_ms", 30000),  # Server sends keepalive every 30s
        ("grpc.keepalive_timeout_ms", 5000),  # Wait 5s for keepalive ack
        ("grpc.keepalive_permit_without_calls", True),  # Allow keepalive without active calls
        # Critical: Allow clients to send pings frequently (every 20s minimum)
        # Default is 300000ms (5 min), which causes "too many pings" with 30s client pings
        ("grpc.http2.min_recv_ping_interval_without_data_ms", 20000),
        ("grpc.http2.max_ping_strikes", 0),  # Disable ping strike detection
        # Message size limits
        ("grpc.max_receive_message_length", 10 * 1024 * 1024),  # 10MB receive
        ("grpc.max_send_message_length", 10 * 1024 * 1024),  # 10MB send
    ]


def create_channel(
    address: str,
    options: list[tuple[str, Any]] | None = None,
    enable_tracing: bool = True,
    **kwargs,
) -> grpc.aio.Channel:
    """
    Create an async gRPC channel with standard JoustMania options and tracing.

    Args:
        address: Target address in format "host:port"
        options: Optional custom channel options (defaults to optimized options)
        enable_tracing: Whether to add OpenTelemetry tracing interceptors (default: True).
                       When enabled, all RPC calls through this channel will create
                       spans and propagate trace context to downstream services.
        **kwargs: Additional arguments passed to grpc.aio.insecure_channel

    Returns:
        Configured async gRPC channel with optional tracing interceptors

    Example:
        >>> channel = create_channel("localhost:50051")
        >>> stub = MyServiceStub(channel)
        >>> # All calls through stub will now be traced
    """
    if options is None:
        options = get_optimized_channel_options()

    if enable_tracing:
        from lib.grpc_tracing import get_tracing_interceptors

        interceptors = get_tracing_interceptors()
        return grpc.aio.insecure_channel(address, options=options, interceptors=interceptors, **kwargs)

    return grpc.aio.insecure_channel(address, options=options, **kwargs)


def create_channel_with_custom_options(
    address: str,
    extra_options: list[tuple[str, Any]],
    enable_tracing: bool = True,
    **kwargs,
) -> grpc.aio.Channel:
    """
    Create an async gRPC channel with standard options plus custom additions.

    Args:
        address: Target address in format "host:port"
        extra_options: Additional channel options to merge with standard options
        enable_tracing: Whether to add OpenTelemetry tracing interceptors (default: True)
        **kwargs: Additional arguments passed to grpc.aio.insecure_channel

    Returns:
        Configured async gRPC channel with merged options and optional tracing

    Example:
        >>> extra = [("grpc.max_connection_idle_ms", 60000)]
        >>> channel = create_channel_with_custom_options("localhost:50051", extra)
    """
    options = get_optimized_channel_options() + extra_options
    return create_channel(address, options=options, enable_tracing=enable_tracing, **kwargs)
