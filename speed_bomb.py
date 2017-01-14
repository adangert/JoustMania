import common
import psmove
import time
import psutil, os
import random
import numpy
from piaudio import Audio
from enum import Enum
from multiprocessing import Process, Value, Array


#How long the winning moves shall sparkle
END_GAME_PAUSE = 4


class Opts(Enum):
    alive = 0
    selection = 1
    holding = 2
    team = 3
    has_bomb = 4

class Selections(Enum):
    nothing = 0
    a_button = 1
    trigger = 2
    triangle = 3

class Holding(Enum):
    not_holding = 0
    holding = 1

class Buttons(Enum):
    middle = 524288
    all_buttons = 240
    sync = 65536
    start = 2048
    select = 256
    circle = 32
    triangle = 16
    nothing = 0

class Bool(Enum):
    no = 0
    yes = 1

class Team(Enum):
    red = 0
    blue = 1


def calculate_flash_time(r,g,b, score):
    flash_percent = max(min(float(score)+0.2,1.0),0.0)
    #val_percent = (val-(flash_speed/2))/(flash_speed/2)
    new_r = int(common.lerp(255, r, flash_percent))
    new_g = int(common.lerp(255, g, flash_percent))
    new_b = int(common.lerp(255, b, flash_percent))
    return (new_r, new_g, new_b)

def track_move(move_serial, move_num, dead_move, force_color, move_opts):
    #proc = psutil.Process(os.getpid())
    #proc.nice(3)


    start = False
    no_rumble = time.time() + 1
    move_last_value = None
    move = common.get_move(move_serial, move_num)

    #keep on looping while move is not dead
    ready = False
    move.set_leds(0,0,0)
    move.update_leds()
    time.sleep(1)

    death_time = 8
    time_of_death = time.time()


    move_opts[Opts.holding.value] = Holding.not_holding.value
    move_opts[Opts.selection.value] = Selections.nothing.value

    while True:
        if sum(force_color) != 0:
            no_rumble_time = time.time() + 5
            time.sleep(0.01)
            move.set_leds(*force_color)
            move.update_leds()
            move.set_rumble(0)
            no_rumble = time.time() + 0.5
        #if we are not dead
        elif dead_move.value == 1:
            if move.poll():
                button = move.get_buttons()

                    
                if move_opts[Opts.has_bomb.value] == Bool.yes.value:
                    move.set_leds(100,20,0)
                    move.set_rumble(40)

                else:
                    if button == Buttons.middle.value and move_opts[Opts.holding.value] == Holding.not_holding.value:
                        print('blow hole')
                        dead_move.value = 0
                    move.set_leds(10,30,10)
                    move.set_rumble(0)

                if button == Buttons.middle.value:
                    move_opts[Opts.selection.value] = Selections.a_button.value
                    move_opts[Opts.holding.value] = Holding.holding.value
                elif button == Buttons.nothing.value:
                    move_opts[Opts.selection.value] = Selections.nothing.value
                    move_opts[Opts.holding.value] = Holding.not_holding.value
        else:
            #do dead animation here
            move.set_leds(0,0,0)

        move.update_leds()
        #if we are dead
            

class Bomb():
    def __init__(self, moves):

        self.move_serials = moves
        self.tracked_moves = {}
        self.dead_moves = {}
        self.alive_moves = []
        self.teams = {}
        self.music_speed = Value('d', 1)
        self.running = True
        self.force_move_colors = {}

        self.start_timer = time.time()
        self.audio_cue = 0

        self.move_opts = {}




        try:
            music = 'audio/Commander/music/' + random.choice(os.listdir('audio/Commander/music'))
        except:
            print('no music in audio/Commander/music')
        self.start_beep = Audio('audio/Joust/sounds/start.wav')
        self.start_game = Audio('audio/Joust/sounds/start3.wav')
        self.explosion = Audio('audio/Joust/sounds/Explosion34.wav')


        end = False
        try:
            self.audio = Audio(music, end)
        except:
            print('no audio loaded')
        #self.change_time = self.get_change_time(speed_up = True)


        self.game_end = False

        
        self.game_loop()


    def get_next_bomb_holder(self):
        holder = random.choice(range(len(self.move_serials)))
        while True:
            holder = (holder +1) % len(self.move_serials)
            serial = self.move_serials[holder]
            if self.dead_moves[serial].value == 1:
                yield serial 
        

    def game_loop(self):
        self.track_moves()

        self.rotate_colors()
        #import pdb; pdb.set_trace()
        self.bomb_generator = self.get_next_bomb_holder()
        self.bomb_serial = next(self.bomb_generator)
        self.move_opts[self.bomb_serial][Opts.has_bomb.value] = Bool.yes.value
        
        self.count_down()
        time.sleep(0.02)
        try:
            self.audio.start_audio_loop()
        except:
            print('no audio loaded to start')
        time.sleep(0.8)
        holding = True
        while self.running:
            if self.move_opts[self.bomb_serial][Opts.selection.value] == Selections.nothing.value:
                holding = False
            if self.move_opts[self.bomb_serial][Opts.selection.value] == Selections.a_button.value and holding == False:
                self.move_opts[self.bomb_serial][Opts.has_bomb.value] = Bool.no.value
                #self.bomb_holder =  (self.bomb_holder +1) % len(self.alive_moves)
                self.bomb_serial = next(self.bomb_generator)
                self.move_opts[self.bomb_serial][Opts.has_bomb.value] = Bool.yes.value
                self.start_beep.start_effect()
                holding = True
    

            self.check_dead_moves()
            if self.game_end:
                self.end_game()

        self.stop_tracking_moves()
        

    def track_moves(self):
        for move_num, move_serial in enumerate(self.move_serials):
            self.alive_moves.append(move_serial)
            time.sleep(0.02)
            dead_move = Value('i', 1)
            force_color = Array('i', [1] * 3)
            opts = Array('i', [0] * 5)


            proc = Process(target=track_move, args=(move_serial,
                                                    move_num,
                                                    dead_move,
                                                    force_color,
                                                    opts))
            proc.start()
            self.tracked_moves[move_serial] = proc
            self.dead_moves[move_serial] = dead_move
            self.force_move_colors[move_serial] = force_color
            self.move_opts[move_serial] = opts


    def rotate_colors(self):
        for move_num, move_serial in enumerate(self.move_serials):
            common.change_color(self.force_move_colors[move_serial], 100,0,0)
            time.sleep(1)
            common.change_color(self.force_move_colors[move_serial], 0,0,0)
            
            

    #need to do the count_down here
    def count_down(self):
        self.change_all_move_colors(80, 0, 0)
        self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(70, 100, 0)
        self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(0, 70, 0)
        self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(0, 0, 0)
        self.start_game.start_effect()
        

    def change_all_move_colors(self, r, g, b):
        for color in self.force_move_colors.values():
            common.change_color(color, r, g, b)

    #remove dead controllers, and change bomb holder
    def check_dead_moves(self):

        #check for one controller left first
        for alive_serial in self.alive_moves:
            if self.dead_moves[alive_serial].value == 0:
                if self.move_opts[alive_serial][Opts.has_bomb.value] == Bool.yes.value:
                    self.move_opts[alive_serial][Opts.has_bomb.value] = Bool.no.value
                    #self.bomb_holder =  (self.bomb_holder +1) % len(self.alive_moves)
                    self.bomb_serial = next(self.bomb_generator)
                    self.move_opts[self.bomb_serial][Opts.has_bomb.value] = Bool.yes.value
                #remove alive move:

                self.alive_moves.remove(alive_serial)
                self.explosion.start_effect()

        if len(self.alive_moves) <= 1:
            self.end_game()
    
    def stop_tracking_moves(self):
        for proc in self.tracked_moves.values():
            proc.terminate()
            proc.join()
            time.sleep(0.02)

    def end_game(self):
        try:
            self.audio.stop_audio()
        except:
            print('no audio loaded to stop')
        end_time = time.time() + END_GAME_PAUSE
        h_value = 0

        while (time.time() < end_time):
            time.sleep(0.01)
            win_color = common.hsv2rgb(h_value, 1, 1)
            if len(self.alive_moves) > 0:
                win_move = self.alive_moves[0]
                win_color_array = self.force_move_colors[win_move]
                common.change_color(win_color_array, *win_color)
                h_value = (h_value + 0.01)
                if h_value >= 1:
                    h_value = 0
        self.running = False

    def end_game_sound(self, winning_team):
        #if self.game_mode == common.Games.JoustTeams:
        if winning_team == Team.red.value:
            team_win = Audio('audio/Commander/sounds/red winner.wav')
        if winning_team == Team.blue.value:
            team_win = Audio('audio/Commander/sounds/blue winner.wav')
        team_win.start_effect()

