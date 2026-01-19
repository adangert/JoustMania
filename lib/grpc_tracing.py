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
        """
        Intercept unary-unary RPC calls to add tracing.

        Args:
            continuation: Function to continue the RPC call
            client_call_details: RPC method details (method name, metadata, etc.)
            request: The RPC request message

        Returns:
            The RPC response
        """
        # Extract method name for span name (e.g., "/package.Service/Method" -> "Service/Method")
        method = client_call_details.method
        if method.startswith("/"):
            method = method[1:]

        # Create span for the outgoing call
        with self._tracer.start_as_current_span(
            method,
            kind=SpanKind.CLIENT,
            attributes={
                "rpc.system": "grpc",
                "rpc.method": client_call_details.method,
            },
        ) as span:
            # Inject trace context into metadata
            metadata = dict(client_call_details.metadata or [])
            inject(metadata)

            # Create new call details with trace metadata
            new_details = grpc.aio.ClientCallDetails(
                method=client_call_details.method,
                timeout=client_call_details.timeout,
                metadata=list(metadata.items()),
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
        method = client_call_details.method
        if method.startswith("/"):
            method = method[1:]

        with self._tracer.start_as_current_span(
            method,
            kind=SpanKind.CLIENT,
            attributes={"rpc.system": "grpc", "rpc.method": client_call_details.method},
        ) as span:
            metadata = dict(client_call_details.metadata or [])
            inject(metadata)

            new_details = grpc.aio.ClientCallDetails(
                method=client_call_details.method,
                timeout=client_call_details.timeout,
                metadata=list(metadata.items()),
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
        method = client_call_details.method
        if method.startswith("/"):
            method = method[1:]

        # For streaming responses, we create a span but don't wait for completion
        # The span covers the initial call setup
        with self._tracer.start_as_current_span(
            method,
            kind=SpanKind.CLIENT,
            attributes={"rpc.system": "grpc", "rpc.method": client_call_details.method},
        ) as span:
            metadata = dict(client_call_details.metadata or [])
            inject(metadata)

            new_details = grpc.aio.ClientCallDetails(
                method=client_call_details.method,
                timeout=client_call_details.timeout,
                metadata=list(metadata.items()),
                credentials=client_call_details.credentials,
                wait_for_ready=client_call_details.wait_for_ready,
            )

            try:
                # Note: For streaming, we return the call object immediately
                # The span ends when the with block exits, not when streaming completes
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
        method = client_call_details.method
        if method.startswith("/"):
            method = method[1:]

        with self._tracer.start_as_current_span(
            method,
            kind=SpanKind.CLIENT,
            attributes={"rpc.system": "grpc", "rpc.method": client_call_details.method},
        ) as span:
            metadata = dict(client_call_details.metadata or [])
            inject(metadata)

            new_details = grpc.aio.ClientCallDetails(
                method=client_call_details.method,
                timeout=client_call_details.timeout,
                metadata=list(metadata.items()),
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
