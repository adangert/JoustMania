"""
Process Supervisor for JoustMania

Manages lifecycle and health of all microservice processes:
- Start processes in dependency order
- Monitor process health
- Restart failed processes automatically
- Coordinate graceful shutdown
- Provide status queries

This is part of the microservices refactoring (Phase 4).
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from multiprocessing import Process

logger = logging.getLogger(__name__)


class ProcessStatus(Enum):
    """Process status states."""

    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class ProcessInfo:
    """Information about a managed process."""

    name: str
    process: Process
    status: ProcessStatus = ProcessStatus.STARTING
    start_time: float = field(default_factory=time.time)
    last_health_check: float = field(default_factory=time.time)
    restart_count: int = 0
    last_error: str | None = None
    critical: bool = True

    def uptime(self) -> float:
        """Get process uptime in seconds."""
        return time.time() - self.start_time

    def time_since_health_check(self) -> float:
        """Get time since last successful health check."""
        return time.time() - self.last_health_check

    def to_dict(self) -> dict:
        """Convert to dict for status queries."""
        return {
            "name": self.name,
            "pid": self.process.pid if self.process else None,
            "status": self.status.value,
            "uptime_seconds": self.uptime(),
            "restart_count": self.restart_count,
            "last_health_check_ago": self.time_since_health_check(),
            "last_error": self.last_error,
            "critical": self.critical,
        }


class ProcessSupervisor:
    """
    Manages lifecycle and health of all microservice processes.

    Responsibilities:
    - Start processes in dependency order
    - Monitor process health
    - Restart failed processes
    - Coordinate graceful shutdown
    - Provide status queries

    Note: This is NOT a separate process, but a manager class that runs
    in the main piparty.py process.
    """

    def __init__(self):
        """Initialize Process Supervisor."""
        self.processes: dict[str, ProcessInfo] = {}
        self.running = False
        self.monitor_thread: threading.Thread | None = None

        # Process configuration
        self.process_configs = {
            "Settings": {
                "dependencies": [],
                "restart_on_failure": True,
                "max_restarts": 3,
                "health_check_interval": 5.0,
                "critical": True,
                "startup_timeout": 5.0,
            },
            "ControllerManager": {
                "dependencies": ["Settings"],
                "restart_on_failure": True,
                "max_restarts": 3,
                "health_check_interval": 5.0,
                "critical": True,
                "startup_timeout": 5.0,
            },
            "GameCoordinator": {
                "dependencies": ["Settings", "ControllerManager"],
                "restart_on_failure": True,
                "max_restarts": 3,
                "health_check_interval": 5.0,
                "critical": False,  # Can operate without games
                "startup_timeout": 5.0,
            },
        }

        # Factory functions (set by piparty.py)
        self.process_factories: dict[str, Callable] = {}

        logger.info("ProcessSupervisor initialized")

    def register_process_factory(self, name: str, factory: Callable):
        """
        Register a factory function for creating a process.

        Args:
            name: Process name (Settings, ControllerManager, GameCoordinator)
            factory: Callable that returns a Process instance
        """
        self.process_factories[name] = factory
        logger.debug(f"Registered factory for {name}")

    def start_all_processes(self):
        """
        Start all microservice processes in dependency order.

        Order:
        1. Settings (no dependencies)
        2. ControllerManager (depends on Settings)
        3. GameCoordinator (depends on ControllerManager, Settings)
        """
        logger.info("Starting all processes...")

        try:
            # Start in dependency order
            self.start_process("Settings")
            self.wait_for_process_ready("Settings")

            self.start_process("ControllerManager")
            self.wait_for_process_ready("ControllerManager")

            self.start_process("GameCoordinator")
            self.wait_for_process_ready("GameCoordinator")

            logger.info("All processes started successfully")

            # Start health monitoring
            self.start_monitoring()

        except Exception as e:
            logger.error(f"Failed to start all processes: {e}", exc_info=True)
            # Cleanup any started processes
            self.stop_all_processes()
            raise

    def start_process(self, name: str):
        """
        Start a single process.

        Args:
            name: Process name

        Raises:
            ValueError: If factory not registered or dependencies not met
            RuntimeError: If process fails to start
        """
        if name not in self.process_factories:
            raise ValueError(f"No factory registered for process: {name}")

        if name in self.processes:
            logger.warning(f"Process {name} already exists, stopping first")
            self.stop_process(name)

        # Check dependencies
        config = self.process_configs[name]
        for dep in config["dependencies"]:
            if dep not in self.processes:
                raise ValueError(f"Dependency {dep} not started for {name}")
            if self.processes[dep].status != ProcessStatus.RUNNING:
                raise ValueError(f"Dependency {dep} not running for {name}")

        logger.info(f"Starting {name} process...")

        try:
            # Create process via factory
            process = self.process_factories[name]()
            process.start()

            # Track process
            proc_info = ProcessInfo(
                name=name,
                process=process,
                status=ProcessStatus.STARTING,
                critical=config["critical"],
            )
            self.processes[name] = proc_info

            logger.info(f"{name} process started (PID: {process.pid})")

        except Exception as e:
            logger.error(f"Failed to start {name}: {e}", exc_info=True)
            raise RuntimeError(f"Failed to start {name}") from e

    def wait_for_process_ready(self, name: str):
        """
        Wait for process to be ready.

        Args:
            name: Process name

        Raises:
            RuntimeError: If process dies or doesn't become ready
        """
        proc_info = self.processes[name]
        config = self.process_configs[name]
        timeout = config["startup_timeout"]

        logger.debug(f"Waiting for {name} to be ready (timeout: {timeout}s)...")

        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if process is still alive
            if not proc_info.process.is_alive():
                raise RuntimeError(f"{name} process died during startup")

            # Simple ready check: If alive for 1 second, consider ready
            if time.time() - proc_info.start_time >= 1.0:
                proc_info.status = ProcessStatus.RUNNING
                proc_info.last_health_check = time.time()
                logger.info(f"{name} is ready")
                return

            time.sleep(0.1)

        raise RuntimeError(f"{name} did not become ready within {timeout}s")

    def stop_all_processes(self):
        """
        Stop all processes in reverse dependency order.

        Order:
        1. GameCoordinator (depends on others)
        2. ControllerManager (depends on Settings)
        3. Settings (no dependencies)
        """
        logger.info("Stopping all processes...")

        # Stop health monitoring first
        self.stop_monitoring()

        # Stop in reverse dependency order
        for name in ["GameCoordinator", "ControllerManager", "Settings"]:
            if name in self.processes:
                self.stop_process(name)

        logger.info("All processes stopped")

    def stop_process(self, name: str, timeout: float = 5.0):
        """
        Stop a process gracefully.

        Steps:
        1. Mark as stopping
        2. Wait for process to exit (via join)
        3. If still alive, terminate forcefully

        Args:
            name: Process name
            timeout: Maximum time to wait for graceful exit
        """
        if name not in self.processes:
            logger.debug(f"Process {name} not tracked, nothing to stop")
            return

        proc_info = self.processes[name]

        if not proc_info.process.is_alive():
            logger.info(f"{name} already stopped")
            proc_info.status = ProcessStatus.STOPPED
            return

        logger.info(f"Stopping {name} process...")
        proc_info.status = ProcessStatus.STOPPING

        # Note: Shutdown command should be sent by piparty.py before calling this
        # We just wait for the process to exit

        # Wait for clean exit
        proc_info.process.join(timeout=timeout)

        # Force terminate if needed
        if proc_info.process.is_alive():
            logger.warning(f"{name} didn't stop gracefully, terminating")
            proc_info.process.terminate()
            proc_info.process.join(timeout=2.0)

            # Kill if still alive
            if proc_info.process.is_alive():
                logger.error(f"{name} still alive after terminate, killing")
                proc_info.process.kill()
                proc_info.process.join(timeout=1.0)

        proc_info.status = ProcessStatus.STOPPED
        logger.info(f"{name} stopped")

    def start_monitoring(self):
        """Start health monitoring thread."""
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning("Monitoring already running")
            return

        self.running = True
        self.monitor_thread = threading.Thread(
            target=self.monitor_loop, name="ProcessMonitor", daemon=True
        )
        self.monitor_thread.start()
        logger.info("Health monitoring started")

    def stop_monitoring(self):
        """Stop health monitoring thread."""
        if not self.monitor_thread:
            return

        logger.info("Stopping health monitoring...")
        self.running = False

        if self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10.0)

        logger.info("Health monitoring stopped")

    def monitor_loop(self):
        """
        Continuous health monitoring loop.

        Runs in separate thread, checks all processes periodically.
        """
        logger.info("Health monitoring loop started")

        while self.running:
            try:
                for name, proc_info in list(self.processes.items()):
                    # Skip if process is not supposed to be running
                    if proc_info.status not in [ProcessStatus.RUNNING, ProcessStatus.STARTING]:
                        continue

                    # Check if process is alive
                    if not proc_info.process.is_alive():
                        logger.error(f"{name} process died unexpectedly")
                        self.handle_process_failure(name)
                        continue

                    # Update last health check time
                    proc_info.last_health_check = time.time()

                    # Log status periodically (every 60 seconds)
                    if proc_info.uptime() % 60 < 5:  # Within 5s of minute mark
                        logger.debug(
                            f"{name} healthy (uptime: {proc_info.uptime():.0f}s, restarts: {proc_info.restart_count})"
                        )

            except Exception as e:
                logger.error(f"Error in health monitoring: {e}", exc_info=True)

            # Sleep between checks
            time.sleep(5.0)

        logger.info("Health monitoring loop stopped")

    def check_process_health(self, name: str) -> bool:
        """
        Check if process is healthy.

        Simple check: Just verify process is alive.

        Args:
            name: Process name

        Returns:
            True if healthy, False otherwise
        """
        if name not in self.processes:
            return False

        proc_info = self.processes[name]
        return proc_info.process.is_alive()

    def handle_process_failure(self, name: str):
        """
        Handle process failure.

        Strategy:
        1. Log failure details
        2. Check restart count
        3. If under max_restarts, restart process
        4. If over limit, mark as failed and alert

        Args:
            name: Process name
        """
        proc_info = self.processes[name]
        config = self.process_configs[name]

        # Update status
        proc_info.status = ProcessStatus.FAILED
        proc_info.restart_count += 1

        # Log failure
        logger.error(f"{name} process failed (restart count: {proc_info.restart_count})")

        # Check if we should restart
        if not config["restart_on_failure"]:
            logger.info(f"{name} restart disabled, not restarting")
            return

        if proc_info.restart_count > config["max_restarts"]:
            logger.error(f"{name} exceeded max restarts ({config['max_restarts']}), giving up")
            if config["critical"]:
                logger.critical(f"Critical process {name} failed permanently!")
            return

        # Attempt restart with delay
        restart_delay = min(proc_info.restart_count * 2, 10)  # Exponential backoff, max 10s
        logger.info(f"Attempting to restart {name} in {restart_delay}s...")
        time.sleep(restart_delay)

        try:
            self.restart_process(name)
            logger.info(f"{name} restarted successfully")
        except Exception as e:
            logger.error(f"Failed to restart {name}: {e}", exc_info=True)
            proc_info.last_error = str(e)

    def restart_process(self, name: str):
        """
        Restart a failed process.

        Args:
            name: Process name

        Raises:
            RuntimeError: If restart fails
        """
        logger.info(f"Restarting {name}...")

        # Stop existing process (cleanup)
        if name in self.processes:
            old_proc_info = self.processes[name]
            if old_proc_info.process.is_alive():
                old_proc_info.process.terminate()
                old_proc_info.process.join(timeout=2.0)

        # Start new process
        try:
            self.start_process(name)
            self.wait_for_process_ready(name)
        except Exception as e:
            raise RuntimeError(f"Failed to restart {name}") from e

    def get_status(self) -> dict[str, dict]:
        """
        Get status of all managed processes.

        Returns:
            Dict mapping process name to status dict
        """
        return {name: proc_info.to_dict() for name, proc_info in self.processes.items()}

    def get_process_status(self, name: str) -> dict | None:
        """
        Get status of specific process.

        Args:
            name: Process name

        Returns:
            Status dict or None if not found
        """
        if name not in self.processes:
            return None
        return self.processes[name].to_dict()

    def is_all_healthy(self) -> bool:
        """
        Check if all processes are healthy.

        Returns:
            True if all processes running, False otherwise
        """
        for proc_info in self.processes.values():
            if proc_info.status != ProcessStatus.RUNNING:
                return False
            if not proc_info.process.is_alive():
                return False
        return True

    def get_summary(self) -> str:
        """
        Get human-readable status summary.

        Returns:
            Status summary string
        """
        lines = ["Process Supervisor Status:"]
        lines.append(f"  Monitoring: {'Active' if self.running else 'Inactive'}")
        lines.append(f"  Processes: {len(self.processes)}")

        for name, proc_info in self.processes.items():
            status_symbol = {
                ProcessStatus.RUNNING: "✅",
                ProcessStatus.STARTING: "🔄",
                ProcessStatus.STOPPING: "⏹️ ",
                ProcessStatus.STOPPED: "⏸️ ",
                ProcessStatus.FAILED: "❌",
            }.get(proc_info.status, "❓")

            lines.append(
                f"  {status_symbol} {name}: {proc_info.status.value} "
                f"(uptime: {proc_info.uptime():.0f}s, restarts: {proc_info.restart_count})"
            )

            if proc_info.last_error:
                lines.append(f"    Last error: {proc_info.last_error}")

        return "\n".join(lines)
