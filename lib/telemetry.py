"""
Shared OpenTelemetry initialization for JoustMania services.

Provides consistent telemetry setup across all services with:
- OTLP trace exporting
- gRPC instrumentation (server and/or client)
- Standard resource attributes

Usage:
    from lib.telemetry import init_telemetry

    # Basic usage (uses OTEL_SERVICE_NAME env var)
    tracer = init_telemetry()

    # With explicit service name
    tracer = init_telemetry(service_name="my-service")

    # With client instrumentation (for services that call other gRPC services)
    tracer = init_telemetry(instrument_grpc_client=True)
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def init_telemetry(
    service_name: str | None = None,
    version: str = "1.0.0",
    instrument_grpc_server: bool = True,
    instrument_grpc_client: bool = False,
) -> trace.Tracer:
    """
    Initialize OpenTelemetry with OTLP exporter.

    Args:
        service_name: Service name for traces. Defaults to OTEL_SERVICE_NAME env var,
                      or "unknown-service" if not set.
        version: Service version for resource attributes.
        instrument_grpc_server: Whether to instrument incoming gRPC calls (default: True).
        instrument_grpc_client: Whether to instrument outgoing gRPC calls (default: False).
                               Enable for services that call other gRPC services.

    Returns:
        Configured tracer instance for creating spans.

    Environment Variables:
        OTEL_EXPORTER_OTLP_ENDPOINT: OTLP collector endpoint (default: http://localhost:4317)
        OTEL_SERVICE_NAME: Default service name if not provided as argument
    """
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    resolved_service_name = service_name or os.getenv("OTEL_SERVICE_NAME", "unknown-service")

    resource = Resource(
        attributes={
            SERVICE_NAME: resolved_service_name,
            SERVICE_VERSION: version,
            "service.namespace": "joustmania",
        }
    )

    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    # Instrument gRPC based on flags
    if instrument_grpc_server:
        GrpcInstrumentorServer().instrument()

    if instrument_grpc_client:
        GrpcInstrumentorClient().instrument()

    logger.info(f"OpenTelemetry initialized: {resolved_service_name} -> {otlp_endpoint}")
    return trace.get_tracer(resolved_service_name)
