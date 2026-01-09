"""
Unit tests for ControllerState and ControllerStateManager.

Tests the state-based non-blocking architecture for Move controller tracking.
"""

import unittest
import time
from multiprocessing import Process, Value
from controller_state import ControllerState, ControllerStateManager
from testing.fakes import FakeMove


class TestControllerState(unittest.TestCase):
    """Test ControllerState shared memory implementation."""

    def setUp(self):
        """Create a fresh ControllerState for each test."""
        self.state = ControllerState()
        self.fake_move = FakeMove()

    def test_initial_state(self):
        """Test initial state values."""
        snapshot = self.state.get_snapshot()

        self.assertFalse(snapshot['connected'])
        self.assertEqual(snapshot['timestamp'], 0.0)
        self.assertEqual(snapshot['age_ms'], float('inf'))
        self.assertEqual(snapshot['buttons'], 0)
        self.assertEqual(snapshot['trigger'], 0)

    def test_update_from_controller(self):
        """Test updating state from FakeMove."""
        # Set up fake controller data
        self.fake_move.set_accelerometer(1.0, 2.0, 3.0)
        self.fake_move.set_gyroscope(4.0, 5.0, 6.0)
        self.fake_move.buttons = 128  # Some button
        self.fake_move.trigger = 200
        self.fake_move.battery = 5

        # Update state
        result = self.state.update(self.fake_move)
        self.assertTrue(result, "update() should return True when data available")

        # Verify state
        snapshot = self.state.get_snapshot()
        self.assertTrue(snapshot['connected'])
        self.assertEqual(snapshot['accelerometer'], (1.0, 2.0, 3.0))
        self.assertEqual(snapshot['gyroscope'], (4.0, 5.0, 6.0))
        self.assertEqual(snapshot['buttons'], 128)
        self.assertEqual(snapshot['trigger'], 200)
        self.assertEqual(snapshot['battery'], 5)
        self.assertLess(snapshot['age_ms'], 10.0, "Data should be fresh")

    def test_update_no_data(self):
        """Test update when controller has no new data."""
        # FakeMove.poll() alternates True/False, so second call returns False
        self.state.update(self.fake_move)  # First call returns True
        result = self.state.update(self.fake_move)  # Second call returns False

        self.assertFalse(result, "update() should return False when no data")

    def test_update_counter(self):
        """Test that update counter increments."""
        snapshot1 = self.state.get_snapshot()
        count1 = snapshot1['update_count']

        self.state.update(self.fake_move)
        snapshot2 = self.state.get_snapshot()
        count2 = snapshot2['update_count']

        self.assertEqual(count2, count1 + 1, "Update counter should increment")

    def test_set_leds(self):
        """Test setting LED colors."""
        self.state.set_leds(255, 128, 64)

        self.assertEqual(self.state.led_r.value, 255)
        self.assertEqual(self.state.led_g.value, 128)
        self.assertEqual(self.state.led_b.value, 64)

    def test_set_rumble(self):
        """Test setting rumble intensity."""
        self.state.set_rumble(200)

        self.assertEqual(self.state.rumble.value, 200)

    def test_apply_outputs(self):
        """Test applying LED and rumble to hardware."""
        self.state.set_leds(100, 150, 200)
        self.state.set_rumble(75)

        self.state.apply_outputs(self.fake_move)

        self.assertEqual(self.fake_move.led_r, 100)
        self.assertEqual(self.fake_move.led_g, 150)
        self.assertEqual(self.fake_move.led_b, 200)
        self.assertEqual(self.fake_move.rumble_intensity, 75)
        self.assertTrue(self.fake_move.leds_updated)

    def test_is_fresh(self):
        """Test freshness checking."""
        # Fresh state (just updated)
        self.state.update(self.fake_move)
        self.assertTrue(self.state.is_fresh(100.0))
        self.assertTrue(self.state.is_fresh(10.0))

        # Stale state
        time.sleep(0.02)  # 20ms
        self.assertTrue(self.state.is_fresh(100.0))
        self.assertFalse(self.state.is_fresh(10.0))

        # Never updated
        fresh_state = ControllerState()
        self.assertFalse(fresh_state.is_fresh(1000.0))

    def test_mark_disconnected(self):
        """Test marking controller as disconnected."""
        self.state.update(self.fake_move)
        self.assertTrue(self.state.get_snapshot()['connected'])

        self.state.mark_disconnected()
        self.assertFalse(self.state.get_snapshot()['connected'])

    def test_multiprocess_shared_memory(self):
        """Test that state is shared across processes."""

        def writer_process(state, kill_flag):
            """Process that writes to shared state."""
            fake = FakeMove()
            fake.set_accelerometer(9.8, 0.0, 0.0)
            while not kill_flag.value:
                state.update(fake)
                time.sleep(0.001)

        # Start writer process
        kill_flag = Value('b', False)
        proc = Process(target=writer_process, args=(self.state, kill_flag))
        proc.start()

        # Wait for data
        time.sleep(0.05)

        # Read from main process
        snapshot = self.state.get_snapshot()

        # Verify we can read data written by other process
        self.assertTrue(snapshot['connected'])
        self.assertEqual(snapshot['accelerometer'][0], 9.8)

        # Clean up
        kill_flag.value = True
        proc.join(timeout=1.0)
        if proc.is_alive():
            proc.terminate()


class TestControllerStateManager(unittest.TestCase):
    """Test ControllerStateManager."""

    def setUp(self):
        """Create a fresh manager for each test."""
        self.manager = ControllerStateManager()

    def test_create_state(self):
        """Test creating a controller state."""
        state = self.manager.create_state("serial123", 0)

        self.assertIsNotNone(state)
        self.assertIn("serial123", self.manager.states)
        self.assertEqual(self.manager.move_num_to_serial[0], "serial123")

    def test_create_duplicate_state(self):
        """Test creating state for existing controller."""
        state1 = self.manager.create_state("serial123", 0)
        state2 = self.manager.create_state("serial123", 0)

        self.assertIs(state1, state2, "Should return existing state")

    def test_get_state(self):
        """Test getting state by serial."""
        self.manager.create_state("serial123", 0)

        state = self.manager.get_state("serial123")
        self.assertIsNotNone(state)

        missing = self.manager.get_state("serial999")
        self.assertIsNone(missing)

    def test_get_state_by_num(self):
        """Test getting state by move number."""
        self.manager.create_state("serial123", 5)

        state = self.manager.get_state_by_num(5)
        self.assertIsNotNone(state)

        missing = self.manager.get_state_by_num(99)
        self.assertIsNone(missing)

    def test_remove_state(self):
        """Test removing a controller state."""
        self.manager.create_state("serial123", 0)
        self.assertIn("serial123", self.manager.states)

        self.manager.remove_state("serial123")
        self.assertNotIn("serial123", self.manager.states)
        self.assertNotIn(0, self.manager.move_num_to_serial)

    def test_get_all_states(self):
        """Test getting all states."""
        self.manager.create_state("serial1", 0)
        self.manager.create_state("serial2", 1)
        self.manager.create_state("serial3", 2)

        states = self.manager.get_all_states()
        self.assertEqual(len(states), 3)
        self.assertIn("serial1", states)
        self.assertIn("serial2", states)
        self.assertIn("serial3", states)

    def test_get_fresh_states(self):
        """Test filtering for fresh states."""
        fake1 = FakeMove()
        fake2 = FakeMove()

        state1 = self.manager.create_state("serial1", 0)
        state2 = self.manager.create_state("serial2", 1)

        # Update both
        state1.update(fake1)
        state2.update(fake2)

        # Both should be fresh
        fresh = self.manager.get_fresh_states(100.0)
        self.assertEqual(len(fresh), 2)

        # Wait for state1 to become stale
        time.sleep(0.02)

        # Only state2 is fresh with 10ms threshold
        fresh = self.manager.get_fresh_states(10.0)
        self.assertIn("serial2", fresh)
        self.assertIn("serial1", fresh)  # Still fresh at 20ms

        # Neither fresh with 5ms threshold
        fresh = self.manager.get_fresh_states(5.0)
        self.assertEqual(len(fresh), 0)

    def test_get_stale_controllers(self):
        """Test finding stale controllers."""
        fake = FakeMove()
        state = self.manager.create_state("serial1", 0)
        self.manager.create_state("serial2", 1)

        # Only serial1 has been updated
        state.update(fake)

        # serial2 should be stale (never updated)
        stale = self.manager.get_stale_controllers(100.0)
        self.assertEqual(len(stale), 1)
        self.assertIn("serial2", stale)


class TestStateFreshnessUnderLoad(unittest.TestCase):
    """Test state freshness under concurrent load."""

    def test_high_frequency_updates(self):
        """Test that high-frequency updates maintain freshness."""
        state = ControllerState()
        fake = FakeMove()
        fake.set_accelerometer(1.0, 2.0, 3.0)

        # Simulate 1000Hz update loop
        updates = 0
        start = time.time()
        duration = 0.1  # Run for 100ms

        while time.time() - start < duration:
            if state.update(fake):
                updates += 1
            time.sleep(0.001)

        # Should have ~50 updates (alternating True/False from FakeMove)
        self.assertGreater(updates, 40, "Should have many updates")
        self.assertLess(updates, 60, "Shouldn't have too many updates")

        # Final state should be very fresh
        snapshot = state.get_snapshot()
        self.assertLess(snapshot['age_ms'], 5.0, "Should be very fresh")


if __name__ == '__main__':
    unittest.main()
