import asyncio
import unittest

from games import ffa
from testing import fakes
import piaudio

class TestFFA(unittest.TestCase):
    def test_one_winner(self):
        controller1 = fakes.FakeMove()
        controller2 = fakes.FakeMove()

        loop = asyncio.get_event_loop()
        game = ffa.FreeForAll([controller1, controller2], piaudio.DummyMusic())
        game.set_rainbow_duration_for_testing(0.1)
        game_task = asyncio.ensure_future(game.run())

        loop.run_until_complete(asyncio.sleep(1))

        self.assertFalse(game_task.done())
        self.assertFalse(game_task.cancelled())

        controller1.accel = (100, 100, 100)

        # Shouldn't throw timeout.
        loop.run_until_complete(asyncio.wait_for(game_task, timeout=3))
        self.assertTrue(game.has_winner_())
    def test_two_outs(self):
        """Tests that we don't lose all the players if they all simultaenously register high accel."""
        controller1 = fakes.FakeMove()
        controller2 = fakes.FakeMove()

        loop = asyncio.get_event_loop()
        game = ffa.FreeForAll([controller1, controller2], piaudio.DummyMusic())
        game.set_rainbow_duration_for_testing(0.1)
        game_task = asyncio.ensure_future(game.run())

        loop.run_until_complete(asyncio.sleep(0.01))

        self.assertFalse(game_task.done())
        self.assertFalse(game_task.cancelled())

        controller1.accel = (100, 100, 100)
        controller2.accel = (100, 100, 100)

        # Shouldn't throw timeout.
        loop.run_until_complete(asyncio.wait_for(game_task, timeout=3))
        self.assertTrue(game.has_winner_())

if __name__ == '__main__':
    unittest.main()
