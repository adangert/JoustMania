import os
import psmove
import bluetooth
import pair
from multiprocessing import Process, Value, Array


def track_move(serial, move_num, opts):
    pass


class menu():
    def __init__(self):
        self.move_count = psmove.count_connected()
        self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
        #may need to make it a dict of a list?
        self.tracked_moves = {}
        self.paired_moves = []
        self.move_opts = {}
        
        self.pair = pair.Pair()
        
        self.game_loop()

        
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

    def game_loop(self):
        #need to turn on search for BT
        while True:
            for move_num, move in enumerate(moves):
                self.pair_move(move, move_num)
                
                    
    
if __name__ == "__main__":
    piparty = menu()
