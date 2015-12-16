import os
import psmove
import pair
import common
import joust
from enum import Enum
from multiprocessing import Process, Value, Array

TEAM_NUM = 6
TEAM_COLORS = common.generate_colors(TEAM_NUM)

#the number of game modes
GAME_MODES = 6

class Games(Enum):
    JoustFFA = 0
    JoustTeams = 1
    JoustRandomTeams = 2
    WereJoust = 3
    Zombies = 4

class Opts(Enum):
    alive = 0
    selection = 1
    holding = 2
    team = 3
    game_mode = 4

class Selections(Enum):
    nothing = 0
    change_mode = 1
    start_game = 2

class Holding(Enum):
    not_holding = 0
    holding = 1


#These buttons are based off of
#The mapping of PS Move controllers
class Buttons(Enum):
    middle = 524288
    start = 2048
    select = 256
    circle = 32
    nothing = 0

def track_move(serial, move_num, move_opts):
    move = common.get_move(serial, move_num)
    move.set_leds(255,255,255)
    move.update_leds()
    
    while True:
        if move.poll():
            game_mode = move_opts[Opts.game_mode]
            move_button = move.get_buttons()
            
            if game_mode == Games.JoustFFA:
                move.set_leds(255,255,255)
                
            elif game_mode == Games.JoustTeams:
                move.set_leds(*TEAM_COLORS[move_opts[Opts.team]])
                if move_button == Buttons.middle:
                    #allow players to increase their own team
                    if move_opts[Opts.holding] == Holding.not_holding:
                        move_opts[Opts.team] = (move_opts[Opts.team] + 1) % TEAM_NUM
                        move_opts[Opts.holding] = Holding.holding


            if move_opts[Opts.holding] == Holding.not_holding:
                if move_button == Buttons.select:
                    move_opts[Opts.selection] = Selections.change_mode
                    move_opts[Opts.holding] = Holding.holding

                if move_button == Button.start:
                    move_opts[Opts.selection] = Selections.start_game
                    move_opts[Opts.holding] = Holding.holding

            if move_button == Buttons.nothing:
                move_opts[Opts.holding] = Holding.not_holding
            
        move.update_leds()
            

class Menu():
    def __init__(self):
        self.move_count = psmove.count_connected()
        self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
        #may need to make it a dict of a list?
        self.tracked_moves = {}
        self.paired_moves = []
        self.move_opts = {}
        self.game_mode = Games.JoustFFA
        
        self.pair = pair.Pair()
        
        self.game_loop()

    def check_for_new_moves(self):
        self.enable_bt_scanning(True)
        #need to start tracking of new moves in here
        if psmove.count_connected() != self.move_count:
            self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
            self.move_count = len(self.moves)

    def enable_bt_scanning(self, on=True):
        scan_cmd = "hciconfig {0} {1}"
        if on:
            scan = "pscan"
        else:
            scan = "noscan"
        bt_hcis = os.popen("hcitool dev | grep hci | awk '{print $1}'").read().split('\n')
        bt_hcis = filter(None, bt_hcis)
        for hci in bt_hcis:
            scan_enabled = os.popen(scan_cmd.format(hci, scan)).read()
        
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
                self.move_opts[move_serial] = opts
                self.tracked_moves[move_serial] = proc

    def check_change_mode(self):
        for move_opt in self.move_opts.itervalues():
            if move_opt[Opts.selection] == Selections.change_mode:
                self.game_mode = (self.game_mode + 1) %  GAME_MODES
                move_opt[Opts.selection] = Selections.nothing
                for opt in self.move_opts.itervalues():
                    opt[Opts.game_mode] = self.game_mode

    def game_loop(self):
        #need to turn on search for BT
        while True:
            if psmove.count_connected() != len(self.tracked_moves):
                for move_num, move in enumerate(self.moves):
                    self.pair_move(move, move_num)

            self.check_for_new_moves()
            self.check_change_mode()

    def start_game(self):
        enable_bt_scanning(False)
            
  
    
if __name__ == "__main__":
    piparty = Menu()
