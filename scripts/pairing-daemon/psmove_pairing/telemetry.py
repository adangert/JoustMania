"""OpenTelemetry initialization for PS Move pairing daemon."""

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import OTEL_ENDPOINT

logger = logging.getLogger("psmove-pairing")


def init_telemetry() -> trace.Tracer:
    """Initialize OpenTelemetry with OTLP exporter."""
    service_name = "psmove-pairing"

    resource = Resource(
        attributes={
            SERVICE_NAME: service_name,
            SERVICE_VERSION: "1.0.0",
            "service.namespace": "joustmania",
        }
    )

    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    logger.info(f"OpenTelemetry initialized: {service_name} -> {OTEL_ENDPOINT}")
    return trace.get_tracer(service_name)
