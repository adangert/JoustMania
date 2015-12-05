import os
import psmove
import bluetooth
import pair
from multiprocessing import Process, Value, Array


def track_controller():
    pass


class menu():
    def __init__(self):
        self.move_count = psmove.count_connected()
        self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
        self.tracked_moves = []
        self.pair = pair.Pair()
        
        self.game_loop()

        
    def pair_controller(self):
        pass
    
    def change_game(self):
        pass

    def game_loop(self):
        #need to turn on search for BT
        while True:
            for move in moves:
                if move.connection_type == psmove.Conn_USB:
                    self.pair.pair_move(move)
                    
                
    
if __name__ == "__main__":
    piparty = menu()
