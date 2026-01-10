"""
Root pytest configuration for JoustMania.

Handles mocking of optional dependencies like psmove that may not be installed.
"""

import sys
from unittest.mock import MagicMock

# Mock psmove module globally before any imports
# This is needed because psmove is a compiled C library that may not be available during testing
sys.modules["psmove"] = MagicMock()
