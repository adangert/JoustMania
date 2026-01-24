"""
OTEL Push Metrics Library for JoustMania.

Provides wrapper classes that match the prometheus_client API but push metrics
via OTLP to the OpenTelemetry Collector for sub-second dashboard updates.

Usage:
    from lib.otel_metrics import init_metrics, Gauge, Counter, Histogram

    # Define metrics at module level (before init_metrics)
    gauge = Gauge("metric_name", "description", ["serial"])
    counter = Counter("events_total", "description", ["type"])

    # Initialize in server startup (100ms for real-time services)
    init_metrics(service_name="game-coordinator", export_interval_ms=100)

    # Use same API as prometheus_client
    gauge.labels(serial="ABC").set(1.5)
    counter.labels(type="click").inc()
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Sequence
from contextlib import contextmanager
from threading import Lock
from typing import Any

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource

logger = logging.getLogger(__name__)

# Global meter instance
_meter: metrics.Meter | None = None
_initialized = False
_pending_metrics: list[LabeledMetric] = []
_init_lock = Lock()


def init_metrics(
    service_name: str | None = None,
    version: str = "1.0.0",
    export_interval_ms: int = 100,
) -> metrics.Meter:
    """
    Initialize OpenTelemetry metrics with OTLP push exporter.

    This must be called during service startup, after metric objects are defined
    but before they are used.

    Args:
        service_name: Service name for metrics. Defaults to OTEL_SERVICE_NAME env var.
        version: Service version for resource attributes.
        export_interval_ms: How often to push metrics (default 100ms for real-time).

    Returns:
        Configured meter instance.

    Environment Variables:
        OTEL_EXPORTER_OTLP_ENDPOINT: OTLP collector endpoint (default: http://otel-collector:4317)
        OTEL_SERVICE_NAME: Default service name if not provided as argument
    """
    global _meter, _initialized

    with _init_lock:
        if _initialized:
            logger.warning("Metrics already initialized, returning existing meter")
            return _meter

        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
        resolved_service_name = service_name or os.getenv("OTEL_SERVICE_NAME", "unknown-service")

        resource = Resource(
            attributes={
                SERVICE_NAME: resolved_service_name,
                SERVICE_VERSION: version,
                "service.namespace": "joustmania",
            }
        )

        # Create OTLP exporter with fast export interval
        exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)

        # Use PeriodicExportingMetricReader for push-based export
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=export_interval_ms,
        )

        provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(provider)

        _meter = metrics.get_meter(resolved_service_name, version)
        _initialized = True

        # Initialize any metrics that were created before init_metrics() was called
        for metric in _pending_metrics:
            metric._initialize()
        _pending_metrics.clear()

        logger.info(
            f"OTEL metrics initialized: {resolved_service_name} -> {otlp_endpoint} "
            f"(export interval: {export_interval_ms}ms)"
        )
        return _meter


def get_meter() -> metrics.Meter:
    """Get the global meter instance. Raises if not initialized."""
    if _meter is None:
        raise RuntimeError("Metrics not initialized. Call init_metrics() first.")
    return _meter


def _is_initialized() -> bool:
    """Check if metrics have been initialized."""
    return _initialized


def _register_pending(metric: LabeledMetric) -> None:
    """Register a metric for deferred initialization."""
    with _init_lock:
        if _initialized:
            metric._initialize()
        else:
            _pending_metrics.append(metric)


class LabeledMetric:
    """Base class for labeled metric wrappers with lazy initialization."""

    def __init__(self, name: str, documentation: str, labelnames: Sequence[str] | None = None):
        self.name = name
        self.documentation = documentation
        self.labelnames = list(labelnames) if labelnames else []
        self._lock = Lock()
        # Track label combinations for removal support
        self._metrics: dict[frozenset, Any] = {}
        self._instrument_initialized = False

        # Register for deferred initialization
        _register_pending(self)

    def _initialize(self) -> None:
        """Initialize the OTEL instrument. Called after init_metrics()."""
        raise NotImplementedError

    def _make_key(self, labels: dict[str, str]) -> frozenset:
        """Create a hashable key from labels dict."""
        return frozenset(labels.items())

    def _validate_labels(self, kwargs: dict[str, Any]) -> dict[str, str]:
        """Validate and convert label values to strings."""
        if set(kwargs.keys()) != set(self.labelnames):
            raise ValueError(f"Labels mismatch for {self.name}: expected {self.labelnames}, got {list(kwargs.keys())}")
        return {k: str(v) for k, v in kwargs.items()}


class Gauge(LabeledMetric):
    """
    OTEL Gauge wrapper matching prometheus_client API.

    Supports:
        - gauge.set(value)
        - gauge.inc() / gauge.inc(amount)
        - gauge.dec() / gauge.dec(amount)
        - gauge.labels(key=value).set(value)
        - gauge.remove(label_value) - remove specific label combination
        - gauge._metrics.clear() - clear all labels
    """

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Sequence[str] | None = None,
    ):
        # Store current values for callback-based reporting
        self._values: dict[frozenset, float] = {}
        self._gauge = None
        super().__init__(name, documentation, labelnames)

    def _initialize(self) -> None:
        """Initialize the OTEL observable gauge."""
        if self._instrument_initialized:
            return
        meter = get_meter()
        self._gauge = meter.create_observable_gauge(
            name=self.name,
            description=self.documentation,
            callbacks=[self._observe],
        )
        self._instrument_initialized = True

    def _observe(self, _options: metrics.CallbackOptions):
        """Callback for observable gauge - reports all current values."""
        with self._lock:
            for key, value in list(self._values.items()):
                labels = dict(key) if key else {}
                yield metrics.Observation(value, labels)

    def _ensure_initialized(self) -> bool:
        """Ensure the gauge is initialized before use. Returns False if not ready."""
        if not self._instrument_initialized:
            if not _is_initialized():
                # Silently skip if not initialized (e.g., during tests)
                return False
            self._initialize()
        return True

    def set(self, value: float) -> None:
        """Set gauge value (no labels)."""
        if not self._ensure_initialized():
            return
        with self._lock:
            self._values[frozenset()] = value

    def inc(self, amount: float = 1) -> None:
        """Increment gauge value (no labels)."""
        if not self._ensure_initialized():
            return
        with self._lock:
            key = frozenset()
            self._values[key] = self._values.get(key, 0) + amount

    def dec(self, amount: float = 1) -> None:
        """Decrement gauge value (no labels)."""
        self.inc(-amount)

    def labels(self, **kwargs) -> _LabeledGauge:
        """Return a labeled gauge instance."""
        labels = self._validate_labels(kwargs)
        return _LabeledGauge(self, labels)

    def remove(self, *labelvalues) -> None:
        """Remove a label combination from the gauge."""
        if len(labelvalues) != len(self.labelnames):
            raise ValueError(f"Expected {len(self.labelnames)} label values, got {len(labelvalues)}")
        labels = dict(zip(self.labelnames, [str(v) for v in labelvalues], strict=False))
        key = self._make_key(labels)
        with self._lock:
            self._values.pop(key, None)
            self._metrics.pop(key, None)


class _LabeledGauge:
    """Helper class for labeled gauge operations."""

    def __init__(self, parent: Gauge, labels: dict[str, str]):
        self._parent = parent
        self._labels = labels
        self._key = parent._make_key(labels)

    def set(self, value: float) -> None:
        """Set the labeled gauge value."""
        if not self._parent._ensure_initialized():
            return
        with self._parent._lock:
            self._parent._values[self._key] = value
            self._parent._metrics[self._key] = True  # Track for removal

    def inc(self, amount: float = 1) -> None:
        """Increment the labeled gauge value."""
        if not self._parent._ensure_initialized():
            return
        with self._parent._lock:
            self._parent._values[self._key] = self._parent._values.get(self._key, 0) + amount
            self._parent._metrics[self._key] = True

    def dec(self, amount: float = 1) -> None:
        """Decrement the labeled gauge value."""
        self.inc(-amount)


class Counter(LabeledMetric):
    """
    OTEL Counter wrapper matching prometheus_client API.

    Supports:
        - counter.inc()
        - counter.inc(amount)
        - counter.labels(key=value).inc()
    """

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Sequence[str] | None = None,
    ):
        self._counter = None
        super().__init__(name, documentation, labelnames)

    def _initialize(self) -> None:
        """Initialize the OTEL counter."""
        if self._instrument_initialized:
            return
        meter = get_meter()
        self._counter = meter.create_counter(
            name=self.name,
            description=self.documentation,
        )
        self._instrument_initialized = True

    def _ensure_initialized(self) -> bool:
        """Ensure the counter is initialized before use. Returns False if not ready."""
        if not self._instrument_initialized:
            if not _is_initialized():
                # Silently skip if not initialized (e.g., during tests)
                return False
            self._initialize()
        return True

    def inc(self, amount: float = 1) -> None:
        """Increment counter (no labels)."""
        if not self._ensure_initialized():
            return
        self._counter.add(amount)

    def labels(self, **kwargs) -> _LabeledCounter:
        """Return a labeled counter instance."""
        labels = self._validate_labels(kwargs)
        return _LabeledCounter(self, labels)


class _LabeledCounter:
    """Helper class for labeled counter operations."""

    def __init__(self, parent: Counter, labels: dict[str, str]):
        self._parent = parent
        self._labels = labels

    def inc(self, amount: float = 1) -> None:
        """Increment the labeled counter."""
        if not self._parent._ensure_initialized():
            return
        self._parent._counter.add(amount, self._labels)


class Histogram(LabeledMetric):
    """
    OTEL Histogram wrapper matching prometheus_client API.

    Supports:
        - histogram.observe(value)
        - histogram.labels(key=value).observe(value)
        - histogram.time() context manager
        - histogram.labels(key=value).time() context manager
        - Custom bucket boundaries (informational, OTEL uses different bucketing)
    """

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Sequence[str] | None = None,
        buckets: Sequence[float] | None = None,
    ):
        self.buckets = list(buckets) if buckets else [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
        self._histogram = None
        super().__init__(name, documentation, labelnames)

    def _initialize(self) -> None:
        """Initialize the OTEL histogram."""
        if self._instrument_initialized:
            return
        meter = get_meter()
        self._histogram = meter.create_histogram(
            name=self.name,
            description=self.documentation,
        )
        self._instrument_initialized = True

    def _ensure_initialized(self) -> bool:
        """Ensure the histogram is initialized before use. Returns False if not ready."""
        if not self._instrument_initialized:
            if not _is_initialized():
                # Silently skip if not initialized (e.g., during tests)
                return False
            self._initialize()
        return True

    def observe(self, value: float) -> None:
        """Record a value in the histogram (no labels)."""
        if not self._ensure_initialized():
            return
        self._histogram.record(value)

    def labels(self, **kwargs) -> _LabeledHistogram:
        """Return a labeled histogram instance."""
        labels = self._validate_labels(kwargs)
        return _LabeledHistogram(self, labels)

    @contextmanager
    def time(self):
        """Context manager to time a block and record the duration."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.observe(duration)


class _LabeledHistogram:
    """Helper class for labeled histogram operations."""

    def __init__(self, parent: Histogram, labels: dict[str, str]):
        self._parent = parent
        self._labels = labels

    def observe(self, value: float) -> None:
        """Record a value in the labeled histogram."""
        if not self._parent._ensure_initialized():
            return
        self._parent._histogram.record(value, self._labels)

    @contextmanager
    def time(self):
        """Context manager to time a block and record the duration."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.observe(duration)
