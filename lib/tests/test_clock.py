"""
Tests for the Clock abstraction.

Verifies that FakeClock works correctly for testing time-dependent code.
"""

import asyncio
import time

import pytest

from lib.clock import FakeClock, RealClock


class TestRealClock:
    """Tests for RealClock (production implementation)."""

    def test_time_returns_current_time(self):
        """RealClock.time() should return current system time."""
        clock = RealClock()
        before = time.time()
        result = clock.time()
        after = time.time()

        assert before <= result <= after

    @pytest.mark.asyncio
    async def test_sleep_actually_sleeps(self):
        """RealClock.sleep() should actually sleep."""
        clock = RealClock()
        start = time.time()
        await clock.sleep(0.05)  # 50ms
        elapsed = time.time() - start

        assert elapsed >= 0.04  # Allow some tolerance


class TestFakeClock:
    """Tests for FakeClock (test implementation)."""

    def test_initial_time_defaults_to_zero(self):
        """FakeClock starts at time 0 by default."""
        clock = FakeClock()
        assert clock.time() == 0.0

    def test_initial_time_can_be_set(self):
        """FakeClock can start at a specified time."""
        clock = FakeClock(start_time=1000.0)
        assert clock.time() == 1000.0

    def test_advance_increases_time(self):
        """advance() should increase the clock time."""
        clock = FakeClock(start_time=100.0)
        clock.advance(50.0)
        assert clock.time() == 150.0

    def test_set_time_sets_absolute_time(self):
        """set_time() should set clock to specific value."""
        clock = FakeClock()
        clock.set_time(500.0)
        assert clock.time() == 500.0

    @pytest.mark.asyncio
    async def test_sleep_advances_time(self):
        """sleep() should advance the fake clock."""
        clock = FakeClock(start_time=0.0)
        await clock.sleep(10.0)
        assert clock.time() == 10.0

    @pytest.mark.asyncio
    async def test_sleep_returns_immediately(self):
        """sleep() should return immediately (not actually wait)."""
        clock = FakeClock()
        start = time.time()
        await clock.sleep(1000.0)  # "Sleep" for 1000 seconds
        elapsed = time.time() - start

        # Should complete in milliseconds, not 1000 seconds
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_sleep_records_calls(self):
        """sleep() should record all sleep durations."""
        clock = FakeClock()
        await clock.sleep(1.0)
        await clock.sleep(2.0)
        await clock.sleep(0.5)

        assert clock.sleep_calls == [1.0, 2.0, 0.5]

    @pytest.mark.asyncio
    async def test_total_sleep_time(self):
        """total_sleep_time should sum all sleep durations."""
        clock = FakeClock()
        await clock.sleep(1.0)
        await clock.sleep(2.0)
        await clock.sleep(0.5)

        assert clock.total_sleep_time == 3.5

    @pytest.mark.asyncio
    async def test_multiple_sleeps_accumulate(self):
        """Multiple sleeps should accumulate time."""
        clock = FakeClock(start_time=0.0)
        await clock.sleep(5.0)
        await clock.sleep(3.0)
        await clock.sleep(2.0)

        assert clock.time() == 10.0

    @pytest.mark.asyncio
    async def test_sleep_yields_control(self):
        """sleep() should yield control to other coroutines."""
        clock = FakeClock()
        order = []

        async def task1():
            order.append("task1_start")
            await clock.sleep(0)
            order.append("task1_end")

        async def task2():
            order.append("task2_start")
            await clock.sleep(0)
            order.append("task2_end")

        await asyncio.gather(task1(), task2())

        # Both tasks should interleave
        assert "task1_start" in order
        assert "task2_start" in order


class TestClockProtocol:
    """Tests verifying Clock protocol compliance."""

    def test_real_clock_has_time_method(self):
        """RealClock should have time() method."""
        clock = RealClock()
        assert hasattr(clock, "time")
        assert callable(clock.time)

    def test_real_clock_has_sleep_method(self):
        """RealClock should have sleep() method."""
        clock = RealClock()
        assert hasattr(clock, "sleep")
        assert callable(clock.sleep)

    def test_fake_clock_has_time_method(self):
        """FakeClock should have time() method."""
        clock = FakeClock()
        assert hasattr(clock, "time")
        assert callable(clock.time)

    def test_fake_clock_has_sleep_method(self):
        """FakeClock should have sleep() method."""
        clock = FakeClock()
        assert hasattr(clock, "sleep")
        assert callable(clock.sleep)


class TestFakeClockBlockingMode:
    """Tests for FakeClock blocking mode (for testing cancellation)."""

    @pytest.mark.asyncio
    async def test_blocking_mode_pauses_sleep(self):
        """In blocking mode, sleep should wait until released."""
        clock = FakeClock()
        clock.enable_blocking()

        completed = False

        async def sleeper():
            nonlocal completed
            await clock.sleep(1.0)
            completed = True

        asyncio.create_task(sleeper())
        await asyncio.sleep(0.01)  # Let task start

        # Task should be blocked
        assert not completed
        assert clock.blocked_count == 1

        # Release and let it complete
        clock.release_one()
        await asyncio.sleep(0.01)

        assert completed

    @pytest.mark.asyncio
    async def test_blocking_mode_allows_cancellation(self):
        """Blocking mode should allow tasks to be cancelled mid-sleep."""
        clock = FakeClock()
        clock.enable_blocking()

        async def long_sleeper():
            await clock.sleep(1000.0)

        task = asyncio.create_task(long_sleeper())
        await asyncio.sleep(0.01)  # Let task start and block

        # Task should be blocked in sleep
        assert clock.blocked_count == 1

        # Cancel should work
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_release_all_releases_multiple_sleeps(self):
        """release_all should release all blocked sleep calls."""
        clock = FakeClock()
        clock.enable_blocking()

        completed = []

        async def sleeper(name):
            await clock.sleep(1.0)
            completed.append(name)

        asyncio.create_task(sleeper("a"))
        asyncio.create_task(sleeper("b"))
        await asyncio.sleep(0.01)

        assert clock.blocked_count == 2
        assert len(completed) == 0

        count = clock.release_all()
        assert count == 2
        await asyncio.sleep(0.01)

        assert len(completed) == 2

    @pytest.mark.asyncio
    async def test_disable_blocking_releases_all(self):
        """disable_blocking should release all blocked sleeps."""
        clock = FakeClock()
        clock.enable_blocking()

        completed = False

        async def sleeper():
            nonlocal completed
            await clock.sleep(1.0)
            completed = True

        asyncio.create_task(sleeper())
        await asyncio.sleep(0.01)

        assert not completed
        clock.disable_blocking()
        await asyncio.sleep(0.01)

        assert completed

    @pytest.mark.asyncio
    async def test_blocking_still_advances_time(self):
        """Blocking mode should still advance time when sleep is called."""
        clock = FakeClock()
        clock.enable_blocking()

        async def sleeper():
            await clock.sleep(5.0)

        task = asyncio.create_task(sleeper())
        await asyncio.sleep(0.01)

        # Time should have advanced even though we're blocked
        assert clock.time() == 5.0

        clock.release_one()
        await task

    def test_release_one_returns_false_when_none_blocked(self):
        """release_one should return False when no sleeps are blocked."""
        clock = FakeClock()
        assert clock.release_one() is False

    def test_release_all_returns_zero_when_none_blocked(self):
        """release_all should return 0 when no sleeps are blocked."""
        clock = FakeClock()
        assert clock.release_all() == 0
