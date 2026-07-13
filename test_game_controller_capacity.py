import multiprocessing
import unittest

from games.game import Game


class GameControllerCapacityTest(unittest.TestCase):
    def test_clears_each_controller_option_array(self):
        game = Game.__new__(Game)
        game.opts = {
            "controller-{}".format(index): multiprocessing.Array("i", [1] * 10)
            for index in range(17)
        }

        for serial in game.opts:
            game.clear_move_opts(serial)

        self.assertTrue(all(
            list(opts) == [0] * 10
            for opts in game.opts.values()
        ))

    def test_games_without_options_do_not_need_controller_arrays(self):
        game = Game.__new__(Game)
        game.opts = None

        game.clear_move_opts("controller-0")


if __name__ == "__main__":
    unittest.main()
