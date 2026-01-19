"""
Async gRPC client interceptor for OpenTelemetry trace propagation.

The standard GrpcInstrumentorClient doesn't reliably work with grpc.aio async channels.
This module provides a manual interceptor that:
- Creates spans for outgoing RPC calls
- Injects W3C Trace Context (traceparent, tracestate) into gRPC metadata
- Properly propagates context across async calls

Usage:
    from lib.grpc_tracing import create_traced_channel

    # Create a channel with tracing interceptor
    channel = create_traced_channel("service:50051")
    stub = MyServiceStub(channel)

    # All RPC calls will now be traced and linked to parent spans
"""

import logging
from collections.abc import Callable
from typing import Any

import grpc
import grpc.aio
from opentelemetry import trace
from opentelemetry.propagate import inject
from opentelemetry.trace import SpanKind, Status, StatusCode

logger = logging.getLogger(__name__)


def _extract_method_name(method: str | bytes) -> str:
    """Extract clean method name from gRPC method path.

    Args:
        method: Method path like "/package.Service/Method" (can be bytes or str)

    Returns:
        Clean method name like "package.Service/Method"
    """
    if isinstance(method, bytes):
        method = method.decode("utf-8")
    if method.startswith("/"):
        method = method[1:]
    return method


def _prepare_metadata(existing_metadata: Any) -> tuple:
    """Prepare metadata with trace context injection.

    Args:
        existing_metadata: Existing metadata (can be None, tuple, list, or grpc.aio.Metadata)

    Returns:
        Tuple of (key, value) pairs with trace context injected
    """
    # Convert existing metadata to dict, handling various input types
    # IMPORTANT: Do NOT use dict(metadata) - grpc.aio.Metadata has broken dict() behavior
    # that causes KeyError when iterating because it yields (key, value) tuples but
    # dict() treats them as keys to look up.
    metadata: dict[str, str] = {}
    if existing_metadata is not None:
        # Check for grpc.aio.Metadata or similar objects that iterate over (key, value) tuples
        # but shouldn't be passed to dict() constructor
        type_name = type(existing_metadata).__name__
        if type_name == "Metadata" or isinstance(existing_metadata, list | tuple):
            # Iterate and unpack tuples directly
            for item in existing_metadata:
                if isinstance(item, tuple | list) and len(item) >= 2:
                    metadata[str(item[0])] = str(item[1])
        elif isinstance(existing_metadata, dict):
            metadata = dict(existing_metadata)
        elif hasattr(existing_metadata, "items"):
            # Dict-like object with items() method
            for key, value in existing_metadata.items():
                metadata[str(key)] = str(value)

    inject(metadata)
    return tuple(metadata.items())


class TracingClientInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """
    Async unary-unary client interceptor for OpenTelemetry tracing.

    Creates a client span for each RPC call and injects trace context
    into gRPC metadata for cross-service propagation.
    """

    def __init__(self, tracer: trace.Tracer | None = None):
        """
        Initialize the interceptor.

        Args:
            tracer: OpenTelemetry tracer instance. If None, uses the global tracer.
        """
        self._tracer = tracer or trace.get_tracer(__name__)

    async def intercept_unary_unary(
        self,
        continuation: Callable,
        client_call_details: grpc.aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        """Intercept unary-unary RPC calls to add tracing."""
        method = _extract_method_name(client_call_details.method)

        with self._tracer.start_as_current_span(
            method,
            kind=SpanKind.CLIENT,
            attributes={"rpc.system": "grpc", "rpc.method": method},
        ) as span:
            new_details = grpc.aio.ClientCallDetails(
                method=client_call_details.method,
                timeout=client_call_details.timeout,
                metadata=_prepare_metadata(client_call_details.metadata),
                credentials=client_call_details.credentials,
                wait_for_ready=client_call_details.wait_for_ready,
            )

            try:
                response = await continuation(new_details, request)
                span.set_status(Status(StatusCode.OK))
                return response
            except grpc.aio.AioRpcError as e:
                span.set_status(Status(StatusCode.ERROR, str(e.code())))
                span.set_attribute("rpc.grpc.status_code", e.code().value[0])
                raise


class TracingStreamUnaryInterceptor(grpc.aio.StreamUnaryClientInterceptor):
    """Async stream-unary client interceptor for OpenTelemetry tracing."""

    def __init__(self, tracer: trace.Tracer | None = None):
        self._tracer = tracer or trace.get_tracer(__name__)

    async def intercept_stream_unary(
        self,
        continuation: Callable,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: Any,
    ) -> Any:
        """Intercept stream-unary RPC calls to add tracing."""
        method = _extract_method_name(client_call_details.method)

        with self._tracer.start_as_current_span(
            method,
            kind=SpanKind.CLIENT,
            attributes={"rpc.system": "grpc", "rpc.method": method},
        ) as span:
            new_details = grpc.aio.ClientCallDetails(
                method=client_call_details.method,
                timeout=client_call_details.timeout,
                metadata=_prepare_metadata(client_call_details.metadata),
                credentials=client_call_details.credentials,
                wait_for_ready=client_call_details.wait_for_ready,
            )

            try:
                response = await continuation(new_details, request_iterator)
                span.set_status(Status(StatusCode.OK))
                return response
            except grpc.aio.AioRpcError as e:
                span.set_status(Status(StatusCode.ERROR, str(e.code())))
                span.set_attribute("rpc.grpc.status_code", e.code().value[0])
                raise


class TracingUnaryStreamInterceptor(grpc.aio.UnaryStreamClientInterceptor):
    """Async unary-stream client interceptor for OpenTelemetry tracing."""

    def __init__(self, tracer: trace.Tracer | None = None):
        self._tracer = tracer or trace.get_tracer(__name__)

    async def intercept_unary_stream(
        self,
        continuation: Callable,
        client_call_details: grpc.aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        """Intercept unary-stream RPC calls to add tracing."""
        method = _extract_method_name(client_call_details.method)

        # For streaming responses, span covers initial call setup only
        with self._tracer.start_as_current_span(
            method,
            kind=SpanKind.CLIENT,
            attributes={"rpc.system": "grpc", "rpc.method": method},
        ) as span:
            new_details = grpc.aio.ClientCallDetails(
                method=client_call_details.method,
                timeout=client_call_details.timeout,
                metadata=_prepare_metadata(client_call_details.metadata),
                credentials=client_call_details.credentials,
                wait_for_ready=client_call_details.wait_for_ready,
            )

            try:
                call = await continuation(new_details, request)
                span.set_status(Status(StatusCode.OK))
                return call
            except grpc.aio.AioRpcError as e:
                span.set_status(Status(StatusCode.ERROR, str(e.code())))
                span.set_attribute("rpc.grpc.status_code", e.code().value[0])
                raise


class TracingStreamStreamInterceptor(grpc.aio.StreamStreamClientInterceptor):
    """Async stream-stream client interceptor for OpenTelemetry tracing."""

    def __init__(self, tracer: trace.Tracer | None = None):
        self._tracer = tracer or trace.get_tracer(__name__)

    async def intercept_stream_stream(
        self,
        continuation: Callable,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: Any,
    ) -> Any:
        """Intercept stream-stream RPC calls to add tracing."""
        method = _extract_method_name(client_call_details.method)

        with self._tracer.start_as_current_span(
            method,
            kind=SpanKind.CLIENT,
            attributes={"rpc.system": "grpc", "rpc.method": method},
        ) as span:
            new_details = grpc.aio.ClientCallDetails(
                method=client_call_details.method,
                timeout=client_call_details.timeout,
                metadata=_prepare_metadata(client_call_details.metadata),
                credentials=client_call_details.credentials,
                wait_for_ready=client_call_details.wait_for_ready,
            )

            try:
                call = await continuation(new_details, request_iterator)
                span.set_status(Status(StatusCode.OK))
                return call
            except grpc.aio.AioRpcError as e:
                span.set_status(Status(StatusCode.ERROR, str(e.code())))
                span.set_attribute("rpc.grpc.status_code", e.code().value[0])
                raise


def get_tracing_interceptors(tracer: trace.Tracer | None = None) -> list:
    """
    Get all tracing interceptors for async gRPC clients.

    Args:
        tracer: OpenTelemetry tracer instance. If None, uses the global tracer.

    Returns:
        List of interceptors covering all RPC patterns (unary-unary, stream-unary,
        unary-stream, stream-stream).
    """
    return [
        TracingClientInterceptor(tracer),
        TracingStreamUnaryInterceptor(tracer),
        TracingUnaryStreamInterceptor(tracer),
        TracingStreamStreamInterceptor(tracer),
    ]


def create_traced_channel(
    address: str,
    options: list[tuple[str, Any]] | None = None,
    tracer: trace.Tracer | None = None,
) -> grpc.aio.Channel:
    """
    Create an async gRPC channel with tracing interceptors.

    This is the primary function to use for creating traced gRPC client channels.
    It combines the standard JoustMania channel options with OpenTelemetry
    tracing interceptors.

    Args:
        address: Target address in format "host:port"
        options: Optional custom channel options (defaults to optimized options)
        tracer: OpenTelemetry tracer instance. If None, uses the global tracer.

    Returns:
        Configured async gRPC channel with tracing interceptors

    Example:
        >>> from lib.grpc_tracing import create_traced_channel
        >>> channel = create_traced_channel("audio:50056")
        >>> stub = AudioServiceStub(channel)
        >>> # All calls through stub will now create spans and propagate context
    """
    from lib.grpc_utils import get_optimized_channel_options

    if options is None:
        options = get_optimized_channel_options()

    interceptors = get_tracing_interceptors(tracer)

    return grpc.aio.insecure_channel(
        address,
        options=options,
        interceptors=interceptors,
    )
