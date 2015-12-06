import os
import psmove
import pair
from multiprocessing import Process, Value, Array


def get_move(serial, move_num):
    move = psmove.PSMove(move_num)
    if move.get_serial() != serial:
        for move_num in range(psmove.count_connected()):
            move = psmove.PSMove(move_num)
            if move.get_serial() == serial:
                return move
        return None
    else:
        return move


def track_move(serial, move_num, opts):
    move = get_move(serial, move_num)
    move.set_leds(255,255,255)
    move.update_leds()


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

    def scan_moves():
        pass

    def check_for_new_moves(self):
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
    piparty = menu()
