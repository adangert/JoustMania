import os
import psmove
import pair
import common
import joust
import time
import zombie
import commander
from piaudio import Audio
from enum import Enum
from multiprocessing import Process, Value, Array

TEAM_NUM = 6
TEAM_COLORS = common.generate_colors(TEAM_NUM)

#the number of game modes
GAME_MODES = 6

class Opts(Enum):
    alive = 0
    selection = 1
    holding = 2
    team = 3
    game_mode = 4

class Alive(Enum):
    on = 0
    off = 1

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
    all_buttons = 240
    sync = 65536
    start = 2048
    select = 256
    circle = 32
    nothing = 0

def track_move(serial, move_num, move_opts):
    move = common.get_move(serial, move_num)
    move.set_leds(0,0,0)
    move.update_leds()
    #move.set_leds(255,255,255)
    #move.update_leds()
    random_color = 0

    
    while True:
        time.sleep(0.01)
        if move.poll():
            game_mode = move_opts[Opts.game_mode.value]
            move_button = move.get_buttons()
            if move_opts[Opts.alive.value] == Alive.off.value:
                if move_button == Buttons.sync.value:
                    move_opts[Opts.alive.value] = Alive.on.value
                time.sleep(0.1)
            else:
                if move_button == Buttons.all_buttons.value:
                    move_opts[Opts.alive.value] = Alive.off.value
                    move.set_leds(0,0,0)
                    move.set_rumble(0)
                    move.update_leds()
                    continue
                    
                if game_mode == common.Games.JoustFFA.value:
                    move.set_leds(255,255,255)
                    
                elif game_mode == common.Games.JoustTeams.value:
                    if move_opts[Opts.team.value] >= TEAM_NUM:
                        move_opts[Opts.team.value] = 0
                    move.set_leds(*TEAM_COLORS[move_opts[Opts.team.value]])
                    if move_button == Buttons.middle.value:
                        #allow players to increase their own team
                        if move_opts[Opts.holding.value] == Holding.not_holding.value:
                            move_opts[Opts.team.value] = (move_opts[Opts.team.value] + 1) % TEAM_NUM
                            move_opts[Opts.holding.value] = Holding.holding.value
                            
                elif game_mode == common.Games.JoustRandomTeams.value:
                    color = common.hsv2rgb(random_color, 1, 1)
                    move.set_leds(*color)
                    random_color += 0.001
                    if random_color >= 1:
                        random_color = 0

                elif game_mode == common.Games.WereJoust.value:
                    if move_num <= 0:
                        move.set_leds(150,0,0)
                    else:
                        move.set_leds(200,200,200)

                elif game_mode == common.Games.Zombies.value:
                        move.set_leds(50,150,50)

                elif game_mode == common.Games.Commander.value:
                    if move_num % 2 == 0:
                        move.set_leds(150,0,0)
                    else:
                        move.set_leds(0,0,150)
                    

                if move_opts[Opts.holding.value] == Holding.not_holding.value:
                    if move_button == Buttons.select.value:
                        move_opts[Opts.selection.value] = Selections.change_mode.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                    if move_button == Buttons.start.value:
                        print ('start')
                        move_opts[Opts.selection.value] = Selections.start_game.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                if move_button == Buttons.nothing.value:
                    move_opts[Opts.holding.value] = Holding.not_holding.value
            
        move.update_leds()
            

class Menu():
    def __init__(self):
        self.move_count = psmove.count_connected()
        self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
        self.out_moves = {}
        #may need to make it a dict of a list?
        self.tracked_moves = {}
        self.paired_moves = []
        self.move_opts = {}
        self.teams = {}
        self.game_mode = common.Games.JoustFFA.value
        
        self.pair = pair.Pair()
        
        self.game_loop()

    def exclude_out_moves(self):
        for move in self.moves:
            serial = move.get_serial()
            if self.move_opts[move.get_serial()][Opts.alive.value] == Alive.off:
                self.out_moves[move.get_serial()] = Alive.off.value
            else:
                self.out_moves[move.get_serial()] = Alive.on.value

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
                if move_serial in self.teams:
                    opts[Opts.team.value] = self.teams[move_serial]
                if move_serial in self.out_moves:
                    opts[Opts.alive.value] = self.out_moves[move_serial]
                opts[Opts.game_mode.value] = self.game_mode
                
                #now start tracking the move controller
                proc = Process(target=track_move, args=(move_serial, move_num, opts))
                proc.start()
                self.move_opts[move_serial] = opts
                self.tracked_moves[move_serial] = proc

    def game_mode_announcement(self):
        if self.game_mode == common.Games.JoustFFA.value:
            Audio('audio/Menu/menu Joust FFA.wav').start_effect()
        if self.game_mode == common.Games.JoustTeams.value:
            Audio('audio/Menu/menu Joust Teams.wav').start_effect()
        if self.game_mode == common.Games.JoustRandomTeams.value:
            Audio('audio/Menu/menu Joust Random Teams.wav').start_effect()
        if self.game_mode == common.Games.WereJoust.value:
            Audio('audio/Menu/menu werewolfs.wav').start_effect()
        if self.game_mode == common.Games.Zombies.value:
            Audio('audio/Menu/menu Zombies.wav').start_effect()
        if self.game_mode == common.Games.Commander.value:
            Audio('audio/Menu/menu Commander.wav').start_effect()

    def check_change_mode(self):
        for move_opt in self.move_opts.values():
            if move_opt[Opts.selection.value] == Selections.change_mode.value:
                self.game_mode = (self.game_mode + 1) %  GAME_MODES
                move_opt[Opts.selection.value] = Selections.nothing.value
                for opt in self.move_opts.values():
                    opt[Opts.game_mode.value] = self.game_mode
                self.game_mode_announcement()

    def game_loop(self):
        while True:
            if psmove.count_connected() != len(self.tracked_moves):
                for move_num, move in enumerate(self.moves):
                    self.pair_move(move, move_num)

            self.check_for_new_moves()
            self.check_change_mode()
            self.check_start_game()

    def stop_tracking_moves(self):
        for proc in self.tracked_moves.values():
            proc.terminate()
            proc.join()
            
    def check_start_game(self):
        for move_opt in self.move_opts.values():
            if move_opt[Opts.selection.value] == Selections.start_game.value:
                self.start_game()

    def start_game(self):
        self.enable_bt_scanning(False)
        self.exclude_out_moves()
        self.stop_tracking_moves()
        time.sleep(0.2)
        game_moves = [move.get_serial() for move in self.moves if self.out_moves[move.get_serial()] == Alive.on.value]
        
        self.teams = {serial: self.move_opts[serial][Opts.team.value] for serial in self.tracked_moves.keys() if self.out_moves[serial] == Alive.on.value}
        if self.game_mode == common.Games.Zombies.value:
            zombie.Zombie(game_moves)
            self.tracked_moves = {}
        elif self.game_mode == common.Games.Commander.value:
            commander.Commander(game_moves)
            self.tracked_moves = {}
        else:
            #may need to put in moves that have selected to not be in the game
            joust.Joust(self.game_mode, game_moves, self.teams)
            self.tracked_moves = {}

            
            
            
if __name__ == "__main__":
    piparty = Menu()
