"""
Async gRPC interceptors for OpenTelemetry trace context propagation.

The standard gRPC OpenTelemetry instrumentation doesn't reliably work with grpc.aio.
This module provides manual interceptors for both client and server:

CLIENT INTERCEPTORS:
- Inject W3C Trace Context (traceparent, tracestate) into outgoing gRPC metadata
- Optionally create client spans (disabled by default, enable with OTEL_GRPC_CLIENT_SPANS=true)

SERVER INTERCEPTORS:
- Extract W3C Trace Context from incoming gRPC metadata
- Attach extracted context so service spans are linked to the parent trace

Usage (Client):
    from lib.grpc_tracing import get_context_propagation_interceptors

    interceptors = get_context_propagation_interceptors()
    channel = grpc.aio.insecure_channel("service:50051", interceptors=interceptors)

Usage (Server):
    from lib.grpc_tracing import get_server_interceptors

    interceptors = get_server_interceptors()
    server = grpc.aio.server(options=options, interceptors=interceptors)
"""

import inspect
import logging
import os
from collections.abc import Callable
from typing import Any

import grpc
import grpc.aio
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind, Status, StatusCode

logger = logging.getLogger(__name__)

# Configuration: Set OTEL_GRPC_CLIENT_SPANS=true to enable client spans
_CREATE_CLIENT_SPANS = os.getenv("OTEL_GRPC_CLIENT_SPANS", "false").lower() == "true"


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


def _extract_method_name(method: str | bytes) -> str:
    """Extract clean method name from gRPC method path."""
    if isinstance(method, bytes):
        method = method.decode("utf-8")
    return method[1:] if method.startswith("/") else method


class ContextPropagationInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """
    Async unary-unary client interceptor for trace context propagation.

    Injects current trace context into gRPC metadata so server-side spans
    are linked to the parent trace. Optionally creates client spans when
    OTEL_GRPC_CLIENT_SPANS=true.
    """

    def __init__(self):
        self._tracer = trace.get_tracer(__name__) if _CREATE_CLIENT_SPANS else None

    async def intercept_unary_unary(
        self,
        continuation: Callable,
        client_call_details: grpc.aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        """Intercept unary-unary RPC calls to propagate trace context."""
        new_details = grpc.aio.ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=_prepare_metadata(client_call_details.metadata),
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )

        if not _CREATE_CLIENT_SPANS:
            return await continuation(new_details, request)

        # Optional: Create client span for debugging
        method = _extract_method_name(client_call_details.method)
        with self._tracer.start_as_current_span(
            method, kind=SpanKind.CLIENT, attributes={"rpc.system": "grpc", "rpc.method": method}
        ) as span:
            try:
                response = await continuation(new_details, request)
                span.set_status(Status(StatusCode.OK))
                return response
            except grpc.aio.AioRpcError as e:
                span.set_status(Status(StatusCode.ERROR, str(e.code())))
                raise


class ContextPropagationStreamUnaryInterceptor(grpc.aio.StreamUnaryClientInterceptor):
    """Async stream-unary client interceptor for trace context propagation."""

    def __init__(self):
        self._tracer = trace.get_tracer(__name__) if _CREATE_CLIENT_SPANS else None

    async def intercept_stream_unary(
        self,
        continuation: Callable,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: Any,
    ) -> Any:
        """Intercept stream-unary RPC calls to propagate trace context."""
        new_details = grpc.aio.ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=_prepare_metadata(client_call_details.metadata),
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )

        if not _CREATE_CLIENT_SPANS:
            return await continuation(new_details, request_iterator)

        method = _extract_method_name(client_call_details.method)
        with self._tracer.start_as_current_span(
            method, kind=SpanKind.CLIENT, attributes={"rpc.system": "grpc", "rpc.method": method}
        ) as span:
            try:
                response = await continuation(new_details, request_iterator)
                span.set_status(Status(StatusCode.OK))
                return response
            except grpc.aio.AioRpcError as e:
                span.set_status(Status(StatusCode.ERROR, str(e.code())))
                raise


class ContextPropagationUnaryStreamInterceptor(grpc.aio.UnaryStreamClientInterceptor):
    """Async unary-stream client interceptor for trace context propagation."""

    def __init__(self):
        self._tracer = trace.get_tracer(__name__) if _CREATE_CLIENT_SPANS else None

    async def intercept_unary_stream(
        self,
        continuation: Callable,
        client_call_details: grpc.aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        """Intercept unary-stream RPC calls to propagate trace context."""
        new_details = grpc.aio.ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=_prepare_metadata(client_call_details.metadata),
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )

        if not _CREATE_CLIENT_SPANS:
            return await continuation(new_details, request)

        method = _extract_method_name(client_call_details.method)
        with self._tracer.start_as_current_span(
            method, kind=SpanKind.CLIENT, attributes={"rpc.system": "grpc", "rpc.method": method}
        ) as span:
            try:
                call = await continuation(new_details, request)
                span.set_status(Status(StatusCode.OK))
                return call
            except grpc.aio.AioRpcError as e:
                span.set_status(Status(StatusCode.ERROR, str(e.code())))
                raise


class ContextPropagationStreamStreamInterceptor(grpc.aio.StreamStreamClientInterceptor):
    """Async stream-stream client interceptor for trace context propagation."""

    def __init__(self):
        self._tracer = trace.get_tracer(__name__) if _CREATE_CLIENT_SPANS else None

    async def intercept_stream_stream(
        self,
        continuation: Callable,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: Any,
    ) -> Any:
        """Intercept stream-stream RPC calls to propagate trace context."""
        new_details = grpc.aio.ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=_prepare_metadata(client_call_details.metadata),
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )

        if not _CREATE_CLIENT_SPANS:
            return await continuation(new_details, request_iterator)

        method = _extract_method_name(client_call_details.method)
        with self._tracer.start_as_current_span(
            method, kind=SpanKind.CLIENT, attributes={"rpc.system": "grpc", "rpc.method": method}
        ) as span:
            try:
                call = await continuation(new_details, request_iterator)
                span.set_status(Status(StatusCode.OK))
                return call
            except grpc.aio.AioRpcError as e:
                span.set_status(Status(StatusCode.ERROR, str(e.code())))
                raise


def get_context_propagation_interceptors() -> list:
    """
    Get all context propagation interceptors for async gRPC clients.

    These interceptors inject W3C Trace Context headers into gRPC metadata
    so that server-side spans are linked to the parent trace. They do NOT
    create client spans - server-side services should create their own
    manual spans with descriptive names.

    Returns:
        List of interceptors covering all RPC patterns (unary-unary, stream-unary,
        unary-stream, stream-stream).
    """
    return [
        ContextPropagationInterceptor(),
        ContextPropagationStreamUnaryInterceptor(),
        ContextPropagationUnaryStreamInterceptor(),
        ContextPropagationStreamStreamInterceptor(),
    ]


# Backward compatibility alias
def get_tracing_interceptors(_tracer=None) -> list:
    """Deprecated: Use get_context_propagation_interceptors() instead."""
    return get_context_propagation_interceptors()


# =============================================================================
# Server-side interceptors
# =============================================================================


def _extract_context_from_metadata(context: grpc.aio.ServicerContext) -> otel_context.Context:
    """Extract OpenTelemetry context from gRPC metadata.

    Args:
        context: gRPC servicer context containing request metadata

    Returns:
        OpenTelemetry context with extracted trace information
    """
    metadata: dict[str, str] = {}
    invocation_metadata = context.invocation_metadata()
    if invocation_metadata:
        for key, value in invocation_metadata:
            metadata[key] = value
    return extract(metadata)


class ServerContextPropagationInterceptor(grpc.aio.ServerInterceptor):
    """
    Async server interceptor that extracts trace context from incoming requests.

    Extracts W3C Trace Context (traceparent, tracestate) from gRPC metadata and
    attaches it to the current context. This allows service spans to be linked
    to the parent trace from the calling service.
    """

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> Any:
        """Intercept incoming RPC to extract and attach trace context."""
        # Note: We can't extract context here because we don't have ServicerContext yet.
        # The actual context extraction happens in the handler wrapper below.
        return await continuation(handler_call_details)


class ServerUnaryUnaryInterceptor(grpc.aio.ServerInterceptor):
    """Server interceptor for unary-unary RPCs that extracts trace context."""

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Wrap the handler to extract trace context."""
        handler = await continuation(handler_call_details)

        if handler is None:
            return None

        if handler.unary_unary:
            original_handler = handler.unary_unary

            async def wrapped_unary_unary(request, context):
                parent_ctx = _extract_context_from_metadata(context)
                token = otel_context.attach(parent_ctx)
                try:
                    result = original_handler(request, context)
                    # Handle both sync and async handlers
                    if inspect.iscoroutine(result):
                        return await result
                    return result
                finally:
                    otel_context.detach(token)

            return grpc.unary_unary_rpc_method_handler(
                wrapped_unary_unary,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.unary_stream:
            original_handler = handler.unary_stream

            async def wrapped_unary_stream(request, context):
                parent_ctx = _extract_context_from_metadata(context)
                token = otel_context.attach(parent_ctx)
                try:
                    async for response in original_handler(request, context):
                        yield response
                finally:
                    otel_context.detach(token)

            return grpc.unary_stream_rpc_method_handler(
                wrapped_unary_stream,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.stream_unary:
            original_handler = handler.stream_unary

            async def wrapped_stream_unary(request_iterator, context):
                parent_ctx = _extract_context_from_metadata(context)
                token = otel_context.attach(parent_ctx)
                try:
                    result = original_handler(request_iterator, context)
                    # Handle both sync and async handlers
                    if inspect.iscoroutine(result):
                        return await result
                    return result
                finally:
                    otel_context.detach(token)

            return grpc.stream_unary_rpc_method_handler(
                wrapped_stream_unary,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.stream_stream:
            original_handler = handler.stream_stream

            async def wrapped_stream_stream(request_iterator, context):
                parent_ctx = _extract_context_from_metadata(context)
                token = otel_context.attach(parent_ctx)
                try:
                    async for response in original_handler(request_iterator, context):
                        yield response
                finally:
                    otel_context.detach(token)

            return grpc.stream_stream_rpc_method_handler(
                wrapped_stream_stream,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler


def get_server_interceptors() -> list:
    """
    Get server-side interceptors for trace context extraction.

    These interceptors extract W3C Trace Context from incoming gRPC metadata
    and attach it to the current OpenTelemetry context. This allows spans
    created in service handlers to be linked to the parent trace.

    Returns:
        List of server interceptors.
    """
    return [ServerUnaryUnaryInterceptor()]
