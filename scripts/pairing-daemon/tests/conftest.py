"""
Pytest fixtures for pairing daemon tests.

Mocks psmove module, DBus, and provides test utilities.
"""

import os
import sys

# Disable OTEL before importing modules that use it
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["OTEL_TRACES_EXPORTER"] = "none"
os.environ["OTEL_METRICS_EXPORTER"] = "none"

# Mock psmove module before it gets imported
from unittest.mock import MagicMock

mock_psmove = MagicMock()
mock_psmove.Conn_USB = 1
mock_psmove.Conn_Bluetooth = 2
mock_psmove.count_connected.return_value = 0
sys.modules["psmove"] = mock_psmove

# Mock dbus module for AdapterManager
mock_dbus = MagicMock()
mock_dbus.SystemBus.return_value = MagicMock()
sys.modules["dbus"] = mock_dbus
sys.modules["dbus.exceptions"] = MagicMock()

import pytest


class MockCommandRunner:
    """Mock for run_command() that returns predefined outputs.

    Usage:
        runner = MockCommandRunner()
        runner.add_response(["lsusb"], (0, "Bus 001 Device 003: ID 054c:03d5 Sony Corp."))

        with patch("psmove_pairing.usb_pairing.run_command", runner):
            result = await check_usb_controllers()
    """

    def __init__(self):
        self.responses: dict[tuple[str, ...], tuple[int, str]] = {}
        self.default_response: tuple[int, str] = (0, "")
        self.calls: list[list[str]] = []

    def add_response(self, cmd: list[str], response: tuple[int, str]) -> None:
        """Add a response for a specific command."""
        self.responses[tuple(cmd)] = response

    def add_prefix_response(self, cmd_prefix: list[str], response: tuple[int, str]) -> None:
        """Add a response that matches commands starting with the given prefix."""
        key = ("__PREFIX__", *cmd_prefix)
        self.responses[key] = response

    async def __call__(self, cmd: list[str], capture_stderr: bool = True, **kwargs) -> tuple[int, str]:
        """Return mocked response for command."""
        self.calls.append(cmd)

        # Exact match
        key = tuple(cmd)
        if key in self.responses:
            return self.responses[key]

        # Prefix match
        for resp_key, response in self.responses.items():
            if resp_key and resp_key[0] == "__PREFIX__":
                prefix = resp_key[1:]
                if tuple(cmd[: len(prefix)]) == prefix:
                    return response

        return self.default_response


@pytest.fixture
def mock_runner():
    """Provide a MockCommandRunner for tests."""
    return MockCommandRunner()


@pytest.fixture
def mock_tracer():
    """Provide a mock OpenTelemetry tracer."""
    tracer = MagicMock()
    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    tracer.start_as_current_span.return_value = span
    return tracer


@pytest.fixture
def mock_psmove_module():
    """Provide a configurable mock psmove module."""
    return mock_psmove


# Sample command outputs for testing
SAMPLE_LSUSB_NO_PSMOVE = """\
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
"""

SAMPLE_LSUSB_WITH_PSMOVE = """\
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 001 Device 003: ID 054c:03d5 Sony Corp. Motion Controller
Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
"""

SAMPLE_HCICONFIG = """\
hci0:   Type: Primary  Bus: USB
        BD Address: DC:A6:32:AA:BB:CC  ACL MTU: 1021:8  SCO MTU: 64:1
        UP RUNNING PSCAN ISCAN
        RX bytes:123456 acl:7890 sco:0 events:1234 errors:0
        TX bytes:123456 acl:7890 sco:0 commands:567 errors:0

hci1:   Type: Primary  Bus: USB
        BD Address: 00:1A:7D:DD:EE:FF  ACL MTU: 310:10  SCO MTU: 64:8
        UP RUNNING PSCAN ISCAN
        RX bytes:654321 acl:8901 sco:0 events:2345 errors:0
        TX bytes:654321 acl:8901 sco:0 commands:678 errors:0
"""

SAMPLE_HCITOOL_CON = """\
Connections:
        < ACL 00:06:F7:AA:BB:CC handle 256 state 1 lm MASTER
        < ACL 00:06:F7:DD:EE:FF handle 257 state 1 lm MASTER
"""

SAMPLE_HCITOOL_CON_EMPTY = """\
Connections:
"""

SAMPLE_HCITOOL_RSSI = """\
RSSI return value: -45
"""


@pytest.fixture
def sample_lsusb_no_psmove():
    return SAMPLE_LSUSB_NO_PSMOVE


@pytest.fixture
def sample_lsusb_with_psmove():
    return SAMPLE_LSUSB_WITH_PSMOVE


@pytest.fixture
def sample_hciconfig():
    return SAMPLE_HCICONFIG


@pytest.fixture
def sample_hcitool_con():
    return SAMPLE_HCITOOL_CON


@pytest.fixture
def sample_hcitool_rssi():
    return SAMPLE_HCITOOL_RSSI
