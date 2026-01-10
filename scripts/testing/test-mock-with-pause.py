#!/usr/bin/env -S uv run
"""Run integration tests with mock environment (pause before teardown for Jaeger inspection)."""

import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    # Change to project root
    project_root = Path(__file__).parent.parent.parent

    # Set environment variable to pause before teardown
    env = os.environ.copy()
    env["PAUSE_BEFORE_TEARDOWN"] = "1"

    sys.exit(subprocess.call([
        "uv", "run",
        "--package", "joustmania-integration-tests",
        "pytest",
        "tests/integration/test_mock_environment.py",
        "-v",
        "-s"
    ], cwd=project_root, env=env))
