import common
from multiprocessing import Process, Value, Array


class Games(Enum):
    JoustFFA = 0
    JoustTeams = 1
    JoustRandomTeams = 2
    WereJoust = 3

def track_move(move_serial, move_num):
    move = common.get_move(serial, move_num)

class Joust():
    def __init__(self, game_mode, moves):
        self.move_serials = moves
        self.game_mode = game_mode

        self.game_loop()

    def game_loop(self):
        for move_serial in enumerate(self.move_serials):
            proc = Process(target=track_move, args=(move_serial, move_serial))
            proc.start()
            self.move_opts[move_serial] = opts
            self.tracked_moves[move_serial] = proc

            
