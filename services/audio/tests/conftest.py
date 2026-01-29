"""
Pytest fixtures for audio service tests.
"""

# Disable OpenTelemetry for tests - must be done before importing service modules
from lib.otel_metrics import disable_metrics_for_tests
from lib.telemetry import disable_telemetry_for_tests

disable_telemetry_for_tests()
disable_metrics_for_tests()
