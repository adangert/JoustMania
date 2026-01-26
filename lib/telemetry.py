"""
Shared OpenTelemetry initialization for JoustMania services.

Provides consistent telemetry setup across all services with:
- OTLP trace exporting
- Standard resource attributes
- Span attribute constants

Usage:
    from lib.telemetry import init_telemetry, SpanAttr

    # Basic usage (uses OTEL_SERVICE_NAME env var)
    tracer = init_telemetry()

    # With explicit service name
    tracer = init_telemetry(service_name="my-service")

    # Use span attribute constants
    span.set_attribute(SpanAttr.CONTROLLER_SERIAL, serial)
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


class SpanAttr:
    """Constants for OpenTelemetry span attribute names.

    Using constants prevents typos and enables IDE autocomplete.
    """

    # Controller attributes
    CONTROLLER_SERIAL = "controller.serial"

    # Admin mode attributes
    ADMIN_OPTION = "admin.option"

    # Validation attributes
    VALIDATION_RESULT = "validation.result"
    VALIDATION_REASON = "validation.reason"


def init_telemetry(
    service_name: str | None = None,
    version: str = "1.0.0",
) -> trace.Tracer:
    """
    Initialize OpenTelemetry with OTLP exporter.

    Args:
        service_name: Service name for traces. Defaults to OTEL_SERVICE_NAME env var,
                      or "unknown-service" if not set.
        version: Service version for resource attributes.

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

    logger.info(f"OpenTelemetry initialized: {resolved_service_name} -> {otlp_endpoint}")
    return trace.get_tracer(resolved_service_name)
