"""Tests for psmove_pairing.daemon module."""

import time
from unittest.mock import patch

import pytest

from psmove_pairing.daemon import _HEALTH_STALENESS_THRESHOLD, PairingDaemon

from .conftest import MockCommandRunner


@pytest.fixture
def daemon(mock_tracer):
    """Provide PairingDaemon instance for tests."""
    return PairingDaemon(mock_tracer, "/usr/bin/psmove")


class TestValidatePrerequisites:
    """Tests for validate_prerequisites()."""

    @pytest.mark.asyncio
    async def test_all_prerequisites_pass(self, daemon):
        """Test when all prerequisites are available."""
        runner = MockCommandRunner()
        runner.add_response(["/usr/bin/psmove", "list"], (0, "Controller 0: ..."))
        runner.add_response(["bluetoothctl", "show"], (0, "Controller ..."))

        with patch("psmove_pairing.daemon.run_command", runner):
            with patch("psmove_pairing.daemon.shutil.which", return_value="/usr/bin/bluetoothctl"):
                result = await daemon.validate_prerequisites()
                assert result is True

    @pytest.mark.asyncio
    async def test_psmove_fails(self, daemon):
        """Test when psmove binary fails."""
        runner = MockCommandRunner()
        runner.add_response(["/usr/bin/psmove", "list"], (1, "error"))
        runner.add_response(["bluetoothctl", "show"], (0, "Controller ..."))

        with patch("psmove_pairing.daemon.run_command", runner):
            with patch("psmove_pairing.daemon.shutil.which", return_value="/usr/bin/tool"):
                result = await daemon.validate_prerequisites()
                assert result is False

    @pytest.mark.asyncio
    async def test_bluetoothctl_not_found(self, daemon):
        """Test when bluetoothctl is not found."""
        runner = MockCommandRunner()
        runner.add_response(["/usr/bin/psmove", "list"], (0, "ok"))

        def mock_which(cmd):
            if cmd == "bluetoothctl":
                return None
            return f"/usr/bin/{cmd}"

        with patch("psmove_pairing.daemon.run_command", runner):
            with patch("psmove_pairing.daemon.shutil.which", side_effect=mock_which):
                result = await daemon.validate_prerequisites()
                assert result is False


class TestIsHealthy:
    """Tests for is_healthy()."""

    def test_healthy_during_startup(self, daemon):
        """Test that daemon is healthy during startup grace period."""
        assert daemon.is_healthy() is True

    def test_healthy_after_polls(self, daemon):
        """Test daemon is healthy after both loops have run."""
        daemon.update_usb_poll_timestamp()
        daemon.update_bt_monitor_timestamp()
        daemon._startup_time = time.time() - _HEALTH_STALENESS_THRESHOLD - 10
        assert daemon.is_healthy() is True

    def test_unhealthy_when_usb_stale(self, daemon):
        """Test daemon is unhealthy when USB poll is stale."""
        daemon._startup_time = time.time() - _HEALTH_STALENESS_THRESHOLD - 10
        daemon.update_bt_monitor_timestamp()
        daemon._last_usb_poll = time.time() - _HEALTH_STALENESS_THRESHOLD - 10
        assert daemon.is_healthy() is False

    def test_unhealthy_when_bt_stale(self, daemon):
        """Test daemon is unhealthy when Bluetooth monitor is stale."""
        daemon._startup_time = time.time() - _HEALTH_STALENESS_THRESHOLD - 10
        daemon.update_usb_poll_timestamp()
        daemon._last_bt_monitor = time.time() - _HEALTH_STALENESS_THRESHOLD - 10
        assert daemon.is_healthy() is False


class TestGetHealthStatus:
    """Tests for get_health_status()."""

    def test_status_includes_all_fields(self, daemon):
        """Test health status includes all expected fields."""
        status = daemon.get_health_status()
        assert "healthy" in status
        assert "uptime_seconds" in status
        assert "last_usb_poll_seconds_ago" in status
        assert "last_bt_monitor_seconds_ago" in status
        assert "usb_poll_count" in status
        assert "bt_monitor_count" in status

    def test_status_reflects_health(self, daemon):
        """Test health status reflects actual health."""
        daemon.update_usb_poll_timestamp()
        daemon.update_bt_monitor_timestamp()
        status = daemon.get_health_status()
        assert status["healthy"] is True

    def test_status_tracks_poll_counts(self, daemon):
        """Test health status tracks poll counts."""
        initial_status = daemon.get_health_status()
        assert initial_status["usb_poll_count"] == 0
        assert initial_status["bt_monitor_count"] == 0


class TestTimestampUpdates:
    """Tests for timestamp update methods."""

    def test_update_usb_poll_timestamp(self, daemon):
        """Test USB poll timestamp is updated."""
        assert daemon._last_usb_poll == 0.0
        daemon.update_usb_poll_timestamp()
        assert daemon._last_usb_poll > 0

    def test_update_bt_monitor_timestamp(self, daemon):
        """Test Bluetooth monitor timestamp is updated."""
        assert daemon._last_bt_monitor == 0.0
        daemon.update_bt_monitor_timestamp()
        assert daemon._last_bt_monitor > 0


class TestRun:
    """Tests for run()."""

    @pytest.mark.asyncio
    async def test_run_starts_both_loops(self, daemon):
        """Test that run starts both USB and BT loops."""
        import asyncio

        usb_loop_started = False
        bt_loop_started = False

        async def mock_usb_loop():
            nonlocal usb_loop_started
            usb_loop_started = True
            raise asyncio.CancelledError()

        async def mock_bt_loop():
            nonlocal bt_loop_started
            bt_loop_started = True
            raise asyncio.CancelledError()

        daemon._usb_poll_loop = mock_usb_loop
        daemon._bt_monitor_loop = mock_bt_loop

        runner = MockCommandRunner()
        runner.add_response(["/usr/bin/psmove", "list"], (0, "ok"))
        runner.add_response(["bluetoothctl", "show"], (0, "ok"))

        with patch("psmove_pairing.daemon.run_command", runner):
            with patch("psmove_pairing.daemon.shutil.which", return_value="/usr/bin/tool"):
                try:
                    await daemon.run()
                except asyncio.CancelledError:
                    pass

        assert usb_loop_started
        assert bt_loop_started
