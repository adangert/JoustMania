"""
Feature Flag Wrapper for JoustMania
Integrates OpenFeature with flagd provider.
"""

import logging
import os
from typing import Any

from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider
from openfeature.contrib.provider.flagd.config import ResolverType
from openfeature.evaluation_context import EvaluationContext

logger = logging.getLogger(__name__)


class FeatureFlagClient:
    """
    Wrapper around OpenFeature SDK to provide simplified access to feature flags.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._setup_provider()
        # Use default client as suggested in PR review
        self.client = api.get_client()

    def _setup_provider(self):
        """Initialize the flagd provider."""
        # Check if running in a context where we want to use the real provider
        # or if we should fallback to a no-op/in-memory provider (default behavior if no provider set)

        # In a real deployment, flagd is available at the specified host/port
        # Defaulting to IN_PROCESS on port 8015 as suggested in PR review
        flagd_host = os.environ.get("FLAGD_HOST", "flagd")
        flagd_port = int(os.environ.get("FLAGD_PORT", "8015"))
        flagd_deadline = int(os.environ.get("FLAGD_DEADLINE_MS", "5000"))

        try:
            logger.info(f"Initializing OpenFeature with flagd (IN_PROCESS) at {flagd_host}:{flagd_port}")
            provider = FlagdProvider(
                host=flagd_host,
                port=flagd_port,
                deadline_ms=flagd_deadline,
                resolver_type=ResolverType.IN_PROCESS,
            )
            api.set_provider(provider)
        except Exception as e:
            logger.error(f"Failed to initialize flagd provider: {e}")
            # OpenFeature defaults to NoOpProvider which returns defaults,
            # so strict error handling might not be needed depending on requirements.

    def get_boolean_value(self, flag_key: str, default_value: bool, context: EvaluationContext | None = None) -> bool:
        """Evaluate a boolean flag."""
        return self.client.get_boolean_value(flag_key, default_value, context)

    def get_string_value(self, flag_key: str, default_value: str, context: EvaluationContext | None = None) -> str:
        """Evaluate a string flag."""
        return self.client.get_string_value(flag_key, default_value, context)

    def get_integer_value(self, flag_key: str, default_value: int, context: EvaluationContext | None = None) -> int:
        """Evaluate an integer flag."""
        return self.client.get_integer_value(flag_key, default_value, context)

    def get_float_value(self, flag_key: str, default_value: float, context: EvaluationContext | None = None) -> float:
        """Evaluate a float flag."""
        return self.client.get_float_value(flag_key, default_value, context)

    def get_object_value(self, flag_key: str, default_value: Any, context: EvaluationContext | None = None) -> Any:
        """Evaluate an object flag."""
        return self.client.get_object_value(flag_key, default_value, context)


# Global instance
_feature_flag_client = None


def get_feature_flag_client() -> FeatureFlagClient:
    """Get or create the global feature flag client instance."""
    global _feature_flag_client
    if _feature_flag_client is None:
        _feature_flag_client = FeatureFlagClient()
    return _feature_flag_client
