"""
Clock abstraction for testable time-dependent code.

Provides a Protocol for time operations that can be easily mocked in tests
without patching. Production code uses RealClock (default), tests use FakeClock.

Usage in production code:
    from lib.clock import Clock, RealClock

    class MyService:
        def __init__(self, clock: Clock | None = None):
            self._clock = clock or RealClock()

        async def do_something(self):
            start = self._clock.time()
            await self._clock.sleep(1.0)
            elapsed = self._clock.time() - start

Usage in tests:
    from lib.clock import FakeClock

    def test_something():
        clock = FakeClock()
        service = MyService(clock=clock)

        clock.advance(5.0)  # Simulate 5 seconds passing
        # No patching needed!
"""

import asyncio
import time
from typing import Protocol


class Clock(Protocol):
    """Protocol for time operations.

    Implementations provide current time and async sleep functionality.
    Using a protocol allows dependency injection without tight coupling.
    """

    def time(self) -> float:
        """Return current time in seconds since epoch."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Sleep for the specified number of seconds."""
        ...


class RealClock:
    """Production clock using real system time.

    This is the default clock for production code.
    """

    def time(self) -> float:
        """Return current time from system clock."""
        return time.time()

    async def sleep(self, seconds: float) -> None:
        """Sleep using asyncio.sleep."""
        await asyncio.sleep(seconds)


class FakeClock:
    """Fake clock for testing with controllable time.

    Allows tests to control time progression without patching.
    Sleep calls return immediately but advance the internal clock.

    Example:
        clock = FakeClock(start_time=1000.0)
        assert clock.time() == 1000.0

        await clock.sleep(5.0)
        assert clock.time() == 1005.0

        clock.advance(10.0)
        assert clock.time() == 1015.0

    For testing cancellation, use blocking mode:
        clock = FakeClock()
        clock.enable_blocking()  # Sleep calls will block until released

        task = asyncio.create_task(effect_that_sleeps())
        await asyncio.sleep(0)  # Let task start
        task.cancel()  # Task is blocked in sleep, so this works
    """

    def __init__(self, start_time: float = 0.0):
        """Initialize fake clock at specified time.

        Args:
            start_time: Initial time value (default 0.0)
        """
        self._time = start_time
        self._sleep_calls: list[float] = []
        self._blocking = False
        self._blocked_events: list[asyncio.Event] = []

    def time(self) -> float:
        """Return current fake time."""
        return self._time

    async def sleep(self, seconds: float) -> None:
        """Record sleep and advance time.

        In normal mode, returns immediately after advancing time.
        In blocking mode, waits until release_one() is called.

        Args:
            seconds: Duration to "sleep" - advances internal clock
        """
        self._sleep_calls.append(seconds)
        self._time += seconds

        if self._blocking:
            # Create an event and wait on it
            event = asyncio.Event()
            self._blocked_events.append(event)
            await event.wait()
        else:
            # Yield control to allow other coroutines to run
            await asyncio.sleep(0)

    def enable_blocking(self) -> None:
        """Enable blocking mode - sleep calls will block until released.

        Use this for testing cancellation behavior.
        """
        self._blocking = True

    def disable_blocking(self) -> None:
        """Disable blocking mode - sleep calls return immediately."""
        self._blocking = False
        # Release any currently blocked sleeps
        self.release_all()

    def release_one(self) -> bool:
        """Release one blocked sleep call.

        Returns:
            True if a sleep was released, False if none were blocked.
        """
        if self._blocked_events:
            event = self._blocked_events.pop(0)
            event.set()
            return True
        return False

    def release_all(self) -> int:
        """Release all blocked sleep calls.

        Returns:
            Number of sleeps released.
        """
        count = len(self._blocked_events)
        for event in self._blocked_events:
            event.set()
        self._blocked_events.clear()
        return count

    @property
    def blocked_count(self) -> int:
        """Return number of coroutines currently blocked in sleep."""
        return len(self._blocked_events)

    def advance(self, seconds: float) -> None:
        """Manually advance time without sleeping.

        Args:
            seconds: Amount to advance the clock
        """
        self._time += seconds

    def set_time(self, time: float) -> None:
        """Set clock to specific time.

        Args:
            time: New time value
        """
        self._time = time

    @property
    def sleep_calls(self) -> list[float]:
        """Return list of all sleep durations requested."""
        return self._sleep_calls.copy()

    @property
    def total_sleep_time(self) -> float:
        """Return total time spent in sleep calls."""
        return sum(self._sleep_calls)
