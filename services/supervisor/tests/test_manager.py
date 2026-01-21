"""Tests for ProcessSupervisor manager."""

import time
from multiprocessing import Process
from unittest.mock import MagicMock, patch

import pytest

from services.supervisor.manager import ProcessInfo, ProcessStatus, ProcessSupervisor


class TestProcessInfo:
    """Tests for ProcessInfo dataclass."""

    def test_uptime_calculation(self):
        """Test uptime returns correct duration."""
        mock_process = MagicMock(spec=Process)
        mock_process.pid = 1234

        info = ProcessInfo(name="Test", process=mock_process)
        # Set start_time to 10 seconds ago
        info.start_time = time.time() - 10

        uptime = info.uptime()
        assert 9.9 < uptime < 10.5  # Allow small timing variance

    def test_time_since_health_check(self):
        """Test time_since_health_check returns correct duration."""
        mock_process = MagicMock(spec=Process)
        info = ProcessInfo(name="Test", process=mock_process)
        info.last_health_check = time.time() - 5

        elapsed = info.time_since_health_check()
        assert 4.9 < elapsed < 5.5

    def test_to_dict(self):
        """Test to_dict returns correct structure."""
        mock_process = MagicMock(spec=Process)
        mock_process.pid = 1234

        info = ProcessInfo(
            name="Settings",
            process=mock_process,
            status=ProcessStatus.RUNNING,
            restart_count=2,
            last_error="Test error",
            critical=True,
        )

        result = info.to_dict()

        assert result["name"] == "Settings"
        assert result["pid"] == 1234
        assert result["status"] == "running"
        assert result["restart_count"] == 2
        assert result["last_error"] == "Test error"
        assert result["critical"] is True
        assert "uptime_seconds" in result
        assert "last_health_check_ago" in result

    def test_default_status_is_starting(self):
        """Test default status is STARTING."""
        mock_process = MagicMock(spec=Process)
        info = ProcessInfo(name="Test", process=mock_process)
        assert info.status == ProcessStatus.STARTING


class TestProcessSupervisor:
    """Tests for ProcessSupervisor class."""

    def test_init(self):
        """Test supervisor initializes with correct defaults."""
        supervisor = ProcessSupervisor()

        assert supervisor.processes == {}
        assert supervisor.running is False
        assert supervisor.monitor_thread is None
        assert "Settings" in supervisor.process_configs
        assert "ControllerManager" in supervisor.process_configs
        assert "GameCoordinator" in supervisor.process_configs

    def test_register_process_factory(self):
        """Test factory registration."""
        supervisor = ProcessSupervisor()
        factory = MagicMock()

        supervisor.register_process_factory("Settings", factory)

        assert "Settings" in supervisor.process_factories
        assert supervisor.process_factories["Settings"] is factory

    def test_start_process_no_factory(self):
        """Test start_process raises error when no factory registered."""
        supervisor = ProcessSupervisor()

        with pytest.raises(ValueError, match="No factory registered"):
            supervisor.start_process("Settings")

    def test_start_process_dependency_not_started(self):
        """Test start_process raises error when dependency not started."""
        supervisor = ProcessSupervisor()
        supervisor.register_process_factory("ControllerManager", MagicMock())

        with pytest.raises(ValueError, match="Dependency Settings not started"):
            supervisor.start_process("ControllerManager")

    def test_start_process_dependency_not_running(self):
        """Test start_process raises error when dependency not running."""
        supervisor = ProcessSupervisor()
        supervisor.register_process_factory("ControllerManager", MagicMock())

        # Add Settings but mark it as failed
        mock_process = MagicMock(spec=Process)
        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
            status=ProcessStatus.FAILED,
        )

        with pytest.raises(ValueError, match="Dependency Settings not running"):
            supervisor.start_process("ControllerManager")

    def test_start_process_success(self):
        """Test successful process start."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        mock_process.pid = 1234
        factory = MagicMock(return_value=mock_process)
        supervisor.register_process_factory("Settings", factory)

        supervisor.start_process("Settings")

        factory.assert_called_once()
        mock_process.start.assert_called_once()
        assert "Settings" in supervisor.processes
        assert supervisor.processes["Settings"].status == ProcessStatus.STARTING

    def test_wait_for_process_ready_success(self):
        """Test wait_for_process_ready marks process as running."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        mock_process.is_alive.return_value = True

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
            start_time=time.time() - 2,  # Started 2 seconds ago
        )

        supervisor.wait_for_process_ready("Settings")

        assert supervisor.processes["Settings"].status == ProcessStatus.RUNNING

    def test_wait_for_process_ready_dies_during_startup(self):
        """Test wait_for_process_ready raises error if process dies."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        mock_process.is_alive.return_value = False  # Process died

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
        )

        with pytest.raises(RuntimeError, match="died during startup"):
            supervisor.wait_for_process_ready("Settings")

    def test_stop_process_not_tracked(self):
        """Test stop_process handles untracked process gracefully."""
        supervisor = ProcessSupervisor()
        # Should not raise
        supervisor.stop_process("NonExistent")

    def test_stop_process_already_stopped(self):
        """Test stop_process handles already stopped process."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        mock_process.is_alive.return_value = False

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
        )

        supervisor.stop_process("Settings")

        assert supervisor.processes["Settings"].status == ProcessStatus.STOPPED

    def test_stop_process_graceful(self):
        """Test graceful process stop."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        # First call returns True (alive), join makes it stop
        mock_process.is_alive.side_effect = [True, False]

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
            status=ProcessStatus.RUNNING,
        )

        supervisor.stop_process("Settings", timeout=0.1)

        mock_process.join.assert_called()
        assert supervisor.processes["Settings"].status == ProcessStatus.STOPPED

    def test_stop_process_force_terminate(self):
        """Test process termination when graceful stop fails."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        # Process stays alive until killed
        mock_process.is_alive.side_effect = [True, True, True, False]

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
            status=ProcessStatus.RUNNING,
        )

        supervisor.stop_process("Settings", timeout=0.1)

        mock_process.terminate.assert_called()
        assert supervisor.processes["Settings"].status == ProcessStatus.STOPPED

    def test_check_process_health_not_tracked(self):
        """Test check_process_health returns False for untracked process."""
        supervisor = ProcessSupervisor()
        assert supervisor.check_process_health("NonExistent") is False

    def test_check_process_health_alive(self):
        """Test check_process_health returns True for alive process."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        mock_process.is_alive.return_value = True

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
        )

        assert supervisor.check_process_health("Settings") is True

    def test_check_process_health_dead(self):
        """Test check_process_health returns False for dead process."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        mock_process.is_alive.return_value = False

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
        )

        assert supervisor.check_process_health("Settings") is False

    def test_handle_process_failure_increments_restart_count(self):
        """Test handle_process_failure increments restart count."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
            restart_count=0,
        )

        # Mock restart to avoid actually starting a process
        with patch.object(supervisor, "restart_process"):
            supervisor.handle_process_failure("Settings")

        assert supervisor.processes["Settings"].restart_count == 1
        assert supervisor.processes["Settings"].status == ProcessStatus.FAILED

    def test_handle_process_failure_exceeds_max_restarts(self):
        """Test handle_process_failure gives up after max restarts."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
            restart_count=3,  # Already at max
        )

        with patch.object(supervisor, "restart_process") as mock_restart:
            supervisor.handle_process_failure("Settings")

        # Should not attempt restart
        mock_restart.assert_not_called()

    def test_handle_process_failure_restart_disabled(self):
        """Test handle_process_failure respects restart_on_failure=False."""
        supervisor = ProcessSupervisor()
        supervisor.process_configs["Settings"]["restart_on_failure"] = False

        mock_process = MagicMock(spec=Process)
        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
        )

        with patch.object(supervisor, "restart_process") as mock_restart:
            supervisor.handle_process_failure("Settings")

        mock_restart.assert_not_called()

    def test_get_status(self):
        """Test get_status returns all process statuses."""
        supervisor = ProcessSupervisor()

        mock_process1 = MagicMock(spec=Process)
        mock_process1.pid = 1234
        mock_process2 = MagicMock(spec=Process)
        mock_process2.pid = 5678

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process1,
            status=ProcessStatus.RUNNING,
        )
        supervisor.processes["ControllerManager"] = ProcessInfo(
            name="ControllerManager",
            process=mock_process2,
            status=ProcessStatus.RUNNING,
        )

        status = supervisor.get_status()

        assert "Settings" in status
        assert "ControllerManager" in status
        assert status["Settings"]["status"] == "running"
        assert status["ControllerManager"]["status"] == "running"

    def test_get_process_status_found(self):
        """Test get_process_status returns status for tracked process."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        mock_process.pid = 1234

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
            status=ProcessStatus.RUNNING,
        )

        status = supervisor.get_process_status("Settings")

        assert status is not None
        assert status["name"] == "Settings"
        assert status["status"] == "running"

    def test_get_process_status_not_found(self):
        """Test get_process_status returns None for untracked process."""
        supervisor = ProcessSupervisor()
        assert supervisor.get_process_status("NonExistent") is None

    def test_is_all_healthy_true(self):
        """Test is_all_healthy returns True when all processes running."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        mock_process.is_alive.return_value = True

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
            status=ProcessStatus.RUNNING,
        )

        assert supervisor.is_all_healthy() is True

    def test_is_all_healthy_false_wrong_status(self):
        """Test is_all_healthy returns False when process not running."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        mock_process.is_alive.return_value = True

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
            status=ProcessStatus.FAILED,
        )

        assert supervisor.is_all_healthy() is False

    def test_is_all_healthy_false_process_dead(self):
        """Test is_all_healthy returns False when process is dead."""
        supervisor = ProcessSupervisor()

        mock_process = MagicMock(spec=Process)
        mock_process.is_alive.return_value = False

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
            status=ProcessStatus.RUNNING,
        )

        assert supervisor.is_all_healthy() is False

    def test_get_summary(self):
        """Test get_summary returns human-readable string."""
        supervisor = ProcessSupervisor()
        supervisor.running = True

        mock_process = MagicMock(spec=Process)
        mock_process.pid = 1234

        supervisor.processes["Settings"] = ProcessInfo(
            name="Settings",
            process=mock_process,
            status=ProcessStatus.RUNNING,
        )

        summary = supervisor.get_summary()

        assert "Process Supervisor Status:" in summary
        assert "Monitoring: Active" in summary
        assert "Settings" in summary
        assert "running" in summary


class TestProcessStatus:
    """Tests for ProcessStatus enum."""

    def test_status_values(self):
        """Test all expected status values exist."""
        assert ProcessStatus.STARTING.value == "starting"
        assert ProcessStatus.RUNNING.value == "running"
        assert ProcessStatus.STOPPING.value == "stopping"
        assert ProcessStatus.STOPPED.value == "stopped"
        assert ProcessStatus.FAILED.value == "failed"
