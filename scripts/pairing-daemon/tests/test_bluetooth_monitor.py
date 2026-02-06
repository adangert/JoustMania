"""Tests for psmove_pairing.bluetooth_monitor module."""

from unittest.mock import patch

import pytest

from psmove_pairing.bluetooth_monitor import BluetoothMonitor

from .conftest import (
    SAMPLE_HCICONFIG,
    SAMPLE_HCITOOL_CON,
    SAMPLE_HCITOOL_CON_EMPTY,
    SAMPLE_HCITOOL_RSSI,
    MockCommandRunner,
)


@pytest.fixture
def bt_monitor(mock_tracer):
    """Provide BluetoothMonitor instance for tests."""
    return BluetoothMonitor(mock_tracer)


class TestGetBluetoothAdapters:
    """Tests for get_bluetooth_adapters()."""

    @pytest.mark.asyncio
    async def test_parses_multiple_adapters(self, bt_monitor):
        """Test parsing multiple HCI adapters."""
        runner = MockCommandRunner()
        runner.add_response(["hciconfig", "-a"], (0, SAMPLE_HCICONFIG))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            adapters = await bt_monitor.get_bluetooth_adapters()
            assert len(adapters) == 2
            assert "hci0" in adapters
            assert "hci1" in adapters

    @pytest.mark.asyncio
    async def test_single_adapter(self, bt_monitor):
        """Test parsing single HCI adapter."""
        single_adapter = """\
hci0:   Type: Primary  Bus: USB
        BD Address: DC:A6:32:AA:BB:CC  ACL MTU: 1021:8  SCO MTU: 64:1
        UP RUNNING PSCAN ISCAN
"""
        runner = MockCommandRunner()
        runner.add_response(["hciconfig", "-a"], (0, single_adapter))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            adapters = await bt_monitor.get_bluetooth_adapters()
            assert adapters == ["hci0"]

    @pytest.mark.asyncio
    async def test_no_adapters(self, bt_monitor):
        """Test when no adapters are available."""
        runner = MockCommandRunner()
        runner.add_response(["hciconfig", "-a"], (0, ""))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            adapters = await bt_monitor.get_bluetooth_adapters()
            assert adapters == []

    @pytest.mark.asyncio
    async def test_hciconfig_failure(self, bt_monitor):
        """Test handling hciconfig command failure."""
        runner = MockCommandRunner()
        runner.add_response(["hciconfig", "-a"], (1, "command not found"))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            adapters = await bt_monitor.get_bluetooth_adapters()
            assert adapters == []


class TestGetAdapterConnections:
    """Tests for get_adapter_connections()."""

    @pytest.mark.asyncio
    async def test_parses_connections(self, bt_monitor):
        """Test parsing connected devices from hcitool."""
        runner = MockCommandRunner()
        runner.add_response(["hcitool", "-i", "hci0", "con"], (0, SAMPLE_HCITOOL_CON))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            connections = await bt_monitor.get_adapter_connections("hci0")
            assert len(connections) == 2
            assert "00:06:f7:aa:bb:cc" in connections
            assert "00:06:f7:dd:ee:ff" in connections

    @pytest.mark.asyncio
    async def test_no_connections(self, bt_monitor):
        """Test when no devices are connected."""
        runner = MockCommandRunner()
        runner.add_response(["hcitool", "-i", "hci0", "con"], (0, SAMPLE_HCITOOL_CON_EMPTY))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            connections = await bt_monitor.get_adapter_connections("hci0")
            assert connections == []

    @pytest.mark.asyncio
    async def test_hcitool_failure(self, bt_monitor):
        """Test handling hcitool command failure."""
        runner = MockCommandRunner()
        runner.add_response(["hcitool", "-i", "hci0", "con"], (1, "error"))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            connections = await bt_monitor.get_adapter_connections("hci0")
            assert connections == []

    @pytest.mark.asyncio
    async def test_lowercase_mac_addresses(self, bt_monitor):
        """Test that MAC addresses are returned in lowercase."""
        uppercase_output = """\
Connections:
        < ACL 00:06:F7:AA:BB:CC handle 256 state 1 lm MASTER
"""
        runner = MockCommandRunner()
        runner.add_response(["hcitool", "-i", "hci0", "con"], (0, uppercase_output))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            connections = await bt_monitor.get_adapter_connections("hci0")
            assert connections[0] == "00:06:f7:aa:bb:cc"


class TestGetRSSI:
    """Tests for get_rssi()."""

    @pytest.mark.asyncio
    async def test_parses_rssi(self, bt_monitor):
        """Test parsing RSSI value."""
        runner = MockCommandRunner()
        runner.add_response(["hcitool", "-i", "hci0", "rssi", "00:06:f7:aa:bb:cc"], (0, SAMPLE_HCITOOL_RSSI))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            rssi = await bt_monitor.get_rssi("hci0", "00:06:f7:aa:bb:cc")
            assert rssi == -45

    @pytest.mark.asyncio
    async def test_negative_rssi(self, bt_monitor):
        """Test parsing negative RSSI value."""
        runner = MockCommandRunner()
        runner.add_response(["hcitool", "-i", "hci0", "rssi", "00:06:f7:aa:bb:cc"], (0, "RSSI return value: -72"))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            rssi = await bt_monitor.get_rssi("hci0", "00:06:f7:aa:bb:cc")
            assert rssi == -72

    @pytest.mark.asyncio
    async def test_hcitool_rssi_failure(self, bt_monitor):
        """Test handling hcitool rssi command failure."""
        runner = MockCommandRunner()
        runner.add_response(["hcitool", "-i", "hci0", "rssi", "00:06:f7:aa:bb:cc"], (1, "error"))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            rssi = await bt_monitor.get_rssi("hci0", "00:06:f7:aa:bb:cc")
            assert rssi is None


class TestMonitor:
    """Tests for monitor()."""

    @pytest.mark.asyncio
    async def test_monitor_increments_count(self, bt_monitor):
        """Test that monitor count is incremented."""
        runner = MockCommandRunner()
        runner.add_response(["hciconfig", "-a"], (0, ""))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            initial_count = bt_monitor.monitor_count
            await bt_monitor.monitor()
            assert bt_monitor.monitor_count == initial_count + 1

    @pytest.mark.asyncio
    async def test_monitor_full_flow(self, bt_monitor):
        """Test complete monitoring flow with adapters and connections."""
        single_adapter = "hci0:   Type: Primary  Bus: USB\n"
        single_connection = """\
Connections:
        < ACL 00:06:f7:aa:bb:cc handle 256 state 1 lm MASTER
"""
        runner = MockCommandRunner()
        runner.add_response(["hciconfig", "-a"], (0, single_adapter))
        runner.add_response(["hcitool", "-i", "hci0", "con"], (0, single_connection))
        runner.add_response(["hcitool", "-i", "hci0", "rssi", "00:06:f7:aa:bb:cc"], (0, "RSSI return value: -50"))

        with patch("psmove_pairing.bluetooth_monitor.run_command", runner):
            await bt_monitor.monitor()
            assert ("00:06:f7:aa:bb:cc", "hci0") in bt_monitor._known_devices
