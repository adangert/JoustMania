"""Unit tests for the OTEL metrics wrapper library."""

import time
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

# We need to reset the module state before importing to test from a clean slate
import lib.otel_metrics as otel_metrics


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level state before each test."""
    otel_metrics._meter = None
    otel_metrics._initialized = False
    otel_metrics._pending_metrics.clear()
    yield
    # Cleanup after test
    otel_metrics._meter = None
    otel_metrics._initialized = False
    otel_metrics._pending_metrics.clear()


class TestLabelValidation:
    """Tests for label validation in metric classes."""

    def test_validate_labels_correct(self):
        """Test that correct labels pass validation."""
        gauge = otel_metrics.Gauge("test_gauge", "Test gauge", ["label1", "label2"])
        result = gauge._validate_labels({"label1": "value1", "label2": "value2"})
        assert result == {"label1": "value1", "label2": "value2"}

    def test_validate_labels_converts_to_strings(self):
        """Test that label values are converted to strings."""
        gauge = otel_metrics.Gauge("test_gauge", "Test gauge", ["count", "ratio"])
        result = gauge._validate_labels({"count": 42, "ratio": 3.14})
        assert result == {"count": "42", "ratio": "3.14"}

    def test_validate_labels_missing_label(self):
        """Test that missing labels raise ValueError."""
        gauge = otel_metrics.Gauge("test_gauge", "Test gauge", ["label1", "label2"])
        with pytest.raises(ValueError, match="Labels mismatch"):
            gauge._validate_labels({"label1": "value1"})

    def test_validate_labels_extra_label(self):
        """Test that extra labels raise ValueError."""
        gauge = otel_metrics.Gauge("test_gauge", "Test gauge", ["label1"])
        with pytest.raises(ValueError, match="Labels mismatch"):
            gauge._validate_labels({"label1": "value1", "label2": "value2"})

    def test_validate_labels_wrong_label_name(self):
        """Test that wrong label names raise ValueError."""
        gauge = otel_metrics.Gauge("test_gauge", "Test gauge", ["expected"])
        with pytest.raises(ValueError, match="Labels mismatch"):
            gauge._validate_labels({"wrong": "value"})


class TestMakeKey:
    """Tests for the label key generation."""

    def test_make_key_creates_frozenset(self):
        """Test that _make_key creates a hashable frozenset."""
        gauge = otel_metrics.Gauge("test_gauge", "Test gauge", ["a", "b"])
        key = gauge._make_key({"a": "1", "b": "2"})
        assert isinstance(key, frozenset)
        assert key == frozenset({("a", "1"), ("b", "2")})

    def test_make_key_empty_labels(self):
        """Test that empty labels create empty frozenset."""
        gauge = otel_metrics.Gauge("test_gauge", "Test gauge")
        key = gauge._make_key({})
        assert key == frozenset()


class TestGaugeWithoutInit:
    """Tests for Gauge behavior without initialization."""

    def test_gauge_creation_without_init(self):
        """Test that gauges can be created before init_metrics."""
        gauge = otel_metrics.Gauge("test_gauge", "Test description", ["serial"])
        assert gauge.name == "test_gauge"
        assert gauge.documentation == "Test description"
        assert gauge.labelnames == ["serial"]
        assert gauge._instrument_initialized is False

    def test_gauge_set_without_init_is_noop(self):
        """Test that set() is a no-op when not initialized."""
        gauge = otel_metrics.Gauge("test_gauge", "Test")
        # Should not raise
        gauge.set(42.0)
        # Value is not stored since not initialized
        assert gauge._values == {}

    def test_gauge_inc_without_init_is_noop(self):
        """Test that inc() is a no-op when not initialized."""
        gauge = otel_metrics.Gauge("test_gauge", "Test")
        gauge.inc(5)
        assert gauge._values == {}

    def test_gauge_dec_without_init_is_noop(self):
        """Test that dec() is a no-op when not initialized."""
        gauge = otel_metrics.Gauge("test_gauge", "Test")
        gauge.dec(3)
        assert gauge._values == {}

    def test_labeled_gauge_set_without_init_is_noop(self):
        """Test that labeled gauge set() is a no-op when not initialized."""
        gauge = otel_metrics.Gauge("test_gauge", "Test", ["label"])
        gauge.labels(label="value").set(100)
        assert gauge._values == {}


class TestCounterWithoutInit:
    """Tests for Counter behavior without initialization."""

    def test_counter_creation_without_init(self):
        """Test that counters can be created before init_metrics."""
        counter = otel_metrics.Counter("test_counter", "Test description", ["type"])
        assert counter.name == "test_counter"
        assert counter.documentation == "Test description"
        assert counter.labelnames == ["type"]
        assert counter._instrument_initialized is False

    def test_counter_inc_without_init_is_noop(self):
        """Test that inc() is a no-op when not initialized."""
        counter = otel_metrics.Counter("test_counter", "Test")
        # Should not raise
        counter.inc()
        counter.inc(5)

    def test_labeled_counter_inc_without_init_is_noop(self):
        """Test that labeled counter inc() is a no-op when not initialized."""
        counter = otel_metrics.Counter("test_counter", "Test", ["type"])
        # Should not raise
        counter.labels(type="click").inc()


class TestHistogramWithoutInit:
    """Tests for Histogram behavior without initialization."""

    def test_histogram_creation_without_init(self):
        """Test that histograms can be created before init_metrics."""
        histogram = otel_metrics.Histogram("test_histogram", "Test description", ["method"])
        assert histogram.name == "test_histogram"
        assert histogram.documentation == "Test description"
        assert histogram.labelnames == ["method"]
        assert histogram._instrument_initialized is False

    def test_histogram_default_buckets(self):
        """Test that histograms have default buckets."""
        histogram = otel_metrics.Histogram("test_histogram", "Test")
        expected = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
        assert histogram.buckets == expected

    def test_histogram_custom_buckets(self):
        """Test that histograms can use custom buckets."""
        custom_buckets = [0.1, 0.5, 1.0, 5.0]
        histogram = otel_metrics.Histogram("test_histogram", "Test", buckets=custom_buckets)
        assert histogram.buckets == custom_buckets

    def test_histogram_observe_without_init_is_noop(self):
        """Test that observe() is a no-op when not initialized."""
        histogram = otel_metrics.Histogram("test_histogram", "Test")
        # Should not raise
        histogram.observe(0.5)

    def test_labeled_histogram_observe_without_init_is_noop(self):
        """Test that labeled histogram observe() is a no-op when not initialized."""
        histogram = otel_metrics.Histogram("test_histogram", "Test", ["method"])
        # Should not raise
        histogram.labels(method="GET").observe(0.1)

    def test_histogram_time_context_manager_without_init(self):
        """Test that time() context manager works without init."""
        histogram = otel_metrics.Histogram("test_histogram", "Test")
        # Should not raise
        with histogram.time():
            time.sleep(0.001)

    def test_labeled_histogram_time_context_manager_without_init(self):
        """Test that labeled time() context manager works without init."""
        histogram = otel_metrics.Histogram("test_histogram", "Test", ["method"])
        # Should not raise
        with histogram.labels(method="POST").time():
            time.sleep(0.001)


class TestPendingMetrics:
    """Tests for the pending metrics registration system."""

    def test_metric_registered_as_pending(self):
        """Test that metrics are registered as pending before init."""
        assert len(otel_metrics._pending_metrics) == 0
        gauge = otel_metrics.Gauge("test_gauge", "Test")
        assert gauge in otel_metrics._pending_metrics

    def test_multiple_metrics_registered(self):
        """Test that multiple metrics can be registered."""
        gauge = otel_metrics.Gauge("gauge", "Test gauge")
        counter = otel_metrics.Counter("counter", "Test counter")
        histogram = otel_metrics.Histogram("histogram", "Test histogram")
        assert len(otel_metrics._pending_metrics) == 3
        assert gauge in otel_metrics._pending_metrics
        assert counter in otel_metrics._pending_metrics
        assert histogram in otel_metrics._pending_metrics


class TestGaugeRemove:
    """Tests for gauge remove() functionality."""

    def test_remove_requires_correct_label_count(self):
        """Test that remove() validates label count."""
        gauge = otel_metrics.Gauge("test_gauge", "Test", ["a", "b"])
        with pytest.raises(ValueError, match="Expected 2 label values"):
            gauge.remove("only_one")

    def test_remove_too_many_labels(self):
        """Test that remove() rejects too many labels."""
        gauge = otel_metrics.Gauge("test_gauge", "Test", ["a"])
        with pytest.raises(ValueError, match="Expected 1 label values"):
            gauge.remove("one", "two")


class TestIsInitialized:
    """Tests for _is_initialized helper."""

    def test_is_initialized_false_by_default(self):
        """Test that _is_initialized returns False before init."""
        assert otel_metrics._is_initialized() is False

    def test_is_initialized_reflects_state(self):
        """Test that _is_initialized reflects the global state."""
        otel_metrics._initialized = True
        assert otel_metrics._is_initialized() is True


class TestGetMeter:
    """Tests for get_meter function."""

    def test_get_meter_raises_without_init(self):
        """Test that get_meter raises RuntimeError without init."""
        with pytest.raises(RuntimeError, match="Metrics not initialized"):
            otel_metrics.get_meter()


class TestInitMetricsWithMock:
    """Tests for init_metrics using mocks."""

    @patch("lib.otel_metrics.OTLPMetricExporter")
    @patch("lib.otel_metrics.PeriodicExportingMetricReader")
    @patch("lib.otel_metrics.MeterProvider")
    @patch("lib.otel_metrics.metrics")
    def test_init_metrics_creates_provider(self, mock_metrics, mock_provider, mock_reader, mock_exporter):
        """Test that init_metrics creates the meter provider."""
        mock_meter = MagicMock()
        mock_metrics.get_meter.return_value = mock_meter

        result = otel_metrics.init_metrics(service_name="test-service")

        assert result == mock_meter
        mock_exporter.assert_called_once()
        mock_reader.assert_called_once()
        mock_provider.assert_called_once()
        mock_metrics.set_meter_provider.assert_called_once()

    @patch("lib.otel_metrics.OTLPMetricExporter")
    @patch("lib.otel_metrics.PeriodicExportingMetricReader")
    @patch("lib.otel_metrics.MeterProvider")
    @patch("lib.otel_metrics.metrics")
    def test_init_metrics_uses_env_var_for_service_name(self, mock_metrics, mock_provider, mock_reader, mock_exporter):
        """Test that init_metrics uses OTEL_SERVICE_NAME env var."""
        mock_meter = MagicMock()
        mock_metrics.get_meter.return_value = mock_meter

        with patch.dict("os.environ", {"OTEL_SERVICE_NAME": "env-service"}):
            otel_metrics.init_metrics()

        mock_metrics.get_meter.assert_called_with("env-service", "1.0.0")

    @patch("lib.otel_metrics.OTLPMetricExporter")
    @patch("lib.otel_metrics.PeriodicExportingMetricReader")
    @patch("lib.otel_metrics.MeterProvider")
    @patch("lib.otel_metrics.metrics")
    def test_init_metrics_custom_export_interval(self, mock_metrics, mock_provider, mock_reader, mock_exporter):
        """Test that init_metrics respects custom export interval."""
        mock_meter = MagicMock()
        mock_metrics.get_meter.return_value = mock_meter

        otel_metrics.init_metrics(service_name="test", export_interval_ms=500)

        mock_reader.assert_called_once()
        call_kwargs = mock_reader.call_args[1]
        assert call_kwargs["export_interval_millis"] == 500

    @patch("lib.otel_metrics.OTLPMetricExporter")
    @patch("lib.otel_metrics.PeriodicExportingMetricReader")
    @patch("lib.otel_metrics.MeterProvider")
    @patch("lib.otel_metrics.metrics")
    def test_init_metrics_returns_existing_on_double_init(
        self, mock_metrics, mock_provider, mock_reader, mock_exporter
    ):
        """Test that init_metrics returns existing meter on double init."""
        mock_meter = MagicMock()
        mock_metrics.get_meter.return_value = mock_meter

        result1 = otel_metrics.init_metrics(service_name="test")
        result2 = otel_metrics.init_metrics(service_name="test")

        assert result1 == result2
        # Provider should only be created once
        assert mock_provider.call_count == 1

    @patch("lib.otel_metrics.OTLPMetricExporter")
    @patch("lib.otel_metrics.PeriodicExportingMetricReader")
    @patch("lib.otel_metrics.MeterProvider")
    @patch("lib.otel_metrics.metrics")
    def test_init_metrics_initializes_pending_metrics(self, mock_metrics, mock_provider, mock_reader, mock_exporter):
        """Test that init_metrics initializes pending metrics."""
        mock_meter = MagicMock()
        mock_metrics.get_meter.return_value = mock_meter

        # Create some pending metrics
        gauge = otel_metrics.Gauge("pending_gauge", "Test")
        counter = otel_metrics.Counter("pending_counter", "Test")
        assert len(otel_metrics._pending_metrics) == 2

        otel_metrics.init_metrics(service_name="test")

        # Pending metrics should be cleared
        assert len(otel_metrics._pending_metrics) == 0
        # Metrics should be initialized
        assert gauge._instrument_initialized is True
        assert counter._instrument_initialized is True


class TestMetricNoLabels:
    """Tests for metrics without labels."""

    def test_gauge_no_labels(self):
        """Test gauge can be created without labels."""
        gauge = otel_metrics.Gauge("simple_gauge", "A simple gauge")
        assert gauge.labelnames == []

    def test_counter_no_labels(self):
        """Test counter can be created without labels."""
        counter = otel_metrics.Counter("simple_counter", "A simple counter")
        assert counter.labelnames == []

    def test_histogram_no_labels(self):
        """Test histogram can be created without labels."""
        histogram = otel_metrics.Histogram("simple_histogram", "A simple histogram")
        assert histogram.labelnames == []


class TestThreadSafety:
    """Basic thread safety tests."""

    def test_pending_registration_threadsafe(self):
        """Test that concurrent metric creation doesn't lose registrations."""
        results = []

        def create_metric(i):
            gauge = otel_metrics.Gauge(f"gauge_{i}", "Test")
            results.append(gauge)

        threads = [Thread(target=create_metric, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        # All should be pending
        assert len(otel_metrics._pending_metrics) == 10


class TestLabeledMetricBase:
    """Tests for the LabeledMetric base class."""

    def test_initialize_not_implemented_in_base(self):
        """Test that _initialize raises NotImplementedError in base class."""
        # Create a direct instance of the base class
        base = otel_metrics.LabeledMetric("test", "Test", ["label"])
        with pytest.raises(NotImplementedError):
            base._initialize()
