import multiprocessing
import unittest

from common import Status
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

    def test_all_dead_players_end_without_an_invalid_winner(self):
        game = Game.__new__(Game)
        game.dead_moves = {
            "controller-0": multiprocessing.Value("i", Status.DEAD.value),
            "controller-1": multiprocessing.Value("i", Status.DEAD.value),
        }
        game.teams = {"controller-0": 0, "controller-1": 1}
        game.get_real_team = lambda team: team

        self.assertTrue(game.check_winner())
        self.assertIsNone(game.winning_team)


if __name__ == "__main__":
    unittest.main()
