#!/usr/bin/env -S uv run
"""Run integration tests with mock environment (auto-teardown)."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    # Change to project root
    project_root = Path(__file__).parent.parent.parent

    sys.exit(
        subprocess.call(
            [
                "uv",
                "run",
                "--package",
                "joustmania-integration-tests",
                "pytest",
                "tests/integration/test_mock_environment.py",
                "-v",
            ],
            cwd=project_root,
        )
    )
