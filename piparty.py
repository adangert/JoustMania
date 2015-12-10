import os
import psmove
import pair
import common
from enum import Enum
from multiprocessing import Process, Value, Array

class Opts(Enum):
    alive = 0
    selection = 1
    holding = 2
    team = 3
    game_mode = 4

class Games(Enum):
    JoustFFA = 0
    JoustTeams = 1
    JoustRandomTeams = 2
    WereJoust = 3
    Zombies = 4


def track_move(serial, move_num, opts):
    move = common.get_move(serial, move_num)
    move.set_leds(255,255,255)
    move.update_leds()
    while True:
        if move.poll():
            game_mode = opts[Opts.game_mode]
            if game_mode == Games.JoustFFA:
                move.set_leds(10,10,10)
                
        move.update_leds()
            

class Menu():
    def __init__(self):
        self.move_count = psmove.count_connected()
        self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
        #may need to make it a dict of a list?
        self.tracked_moves = {}
        self.paired_moves = []
        self.move_opts = {}
        
        self.pair = pair.Pair()
        
        self.game_loop()

    def scan_moves():
        pass

    def check_for_new_moves(self):
        bt_moves = os.popen("hcitool dev | grep hci | awk '{print $1}'").read().split('\n')
        bt_moves = filter(None, bt_moves)
        if psmove.count_connected() != self.move_count:
            self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
        
        
    def pair_move(self, move, move_num):
        move_serial = move.get_serial()
        if move_serial not in self.tracked_moves:
            if move.connection_type == psmove.Conn_USB:
                if move_serial not in self.paired_moves:
                    self.pair.pair_move(move)
                    self.paired_moves.append(move_serial)
            #the move is connected via bluetooth
            else:
                opts = Array('i', [0] * 5)
                #now start tracking the move controller
                proc = Process(target=track_move, args=(move_serial, move_num, opts))
                proc.start()
                self.tracked_moves[move_serial] = proc
    
    def change_game(self):
        pass

    def start_game(self):
        pass

    def game_loop(self):
        #need to turn on search for BT
        while True:
            if psmove.count_connected() != len(self.tracked_moves):
                for move_num, move in enumerate(self.moves):
                    self.pair_move(move, move_num)

            self.check_for_new_moves()
                    

                
                    
    
if __name__ == "__main__":
    piparty = Menu()
