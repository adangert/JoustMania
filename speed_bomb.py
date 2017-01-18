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
END_GAME_PAUSE = 6


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
    false_trigger = 4

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

def track_move(move_serial, move_num, dead_move, force_color,bomb_color, move_opts, game_start, false_color, faked):
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
    super_dead = False
    no_bomb_color = [0,0,200]

    death_time = 8
    time_of_death = time.time()


    move_opts[Opts.holding.value] = Holding.not_holding.value
    move_opts[Opts.selection.value] = Selections.nothing.value
    while  not super_dead:
        if sum(force_color) != 0:
            no_rumble_time = time.time() + 5
            time.sleep(0.01)
            move.set_leds(*force_color)
            move.update_leds()
            move.set_rumble(0)
            no_rumble = time.time() + 0.5
        #if we are not dead
        elif dead_move.value > 0:
            if dead_move.value == 2:
                no_bomb_color = [0,0,255]
            else:
                no_bomb_color = [0,0,50]
            if move.poll():
                button = move.get_buttons()
                

                if move_opts[Opts.has_bomb.value] == Bool.yes.value:
                    if(move.get_trigger() > 50):

                        move_opts[Opts.selection.value] = Selections.false_trigger.value
                        col1 = int(common.lerp(bomb_color[0], no_bomb_color[0], (move.get_trigger()-50)/77))
                        col2 = int(common.lerp(bomb_color[1], no_bomb_color[1], (move.get_trigger()-50)/77))
                        col3 = int(common.lerp(bomb_color[2], no_bomb_color[2], (move.get_trigger()-50)/77))
                        move.set_leds(col1,col2,col3)
                        if (move.get_trigger() > 127 and move.get_trigger() <= 140):
                            move.set_leds(*no_bomb_color)
                        if (move.get_trigger() > 140):
                            move.set_leds(200,0,200)
                    

                    else:
                        move.set_leds(*bomb_color)

                else:
                    #if move_opts[Opts.selection.value] == Selections.a_button.value and move_opts[Opts.holding.value] == Holding.not_holding.value:
                        #print("BOOOOOM CONTROLLER PUSHED {}, the selection was a and it was not holding :O".format(str(move.get_serial())))
                        #dead_move.value = 0
                    if false_color.value == 1:
                        move.set_leds(150,20,20)
                    else:
                        move.set_leds(*no_bomb_color)
                    if move.get_trigger() > 50 and move_opts[Opts.holding.value] == Holding.not_holding.value:
                        if move_opts[Opts.has_bomb.value] == Bool.no.value:
                            move_opts[Opts.holding.value] = Holding.holding.value
                            
                            if game_start.value == 1 and false_color.value == 1:
                                print("JUST DIED TO TRIGGER FAKED")
                                faked.value = 1
                                dead_move.value -= 1
                    move.set_rumble(0)

                if button == Buttons.triangle.value and move_opts[Opts.holding.value] == Holding.not_holding.value:
                    move_opts[Opts.selection.value] = Selections.triangle.value
                    #move_opts[Opts.holding.value] = Holding.holding.value

                if button == Buttons.middle.value and move_opts[Opts.holding.value] == Holding.not_holding.value:
                    #print("controller {} was not holding, and now it's pushing middle, let's change it's values to a and holding".format(str(move.get_serial())))
                    move_opts[Opts.selection.value] = Selections.a_button.value
                    move_opts[Opts.holding.value] = Holding.holding.value
                    if move_opts[Opts.has_bomb.value] == Bool.no.value:
                        if game_start.value == 1 and false_color.value == 1:
                            print("DIED FROM MIDDLE BUTTON FAKED")
                            faked.value = 1
                            dead_move.value -= 1
                            

                            
                #elif (move_opts[Opts.holding.value] == Holding.not_holding.value and move.get_trigger() > 100):
                #    move_opts[Opts.selection.value] = Selections.trigger.value
                    
                    
                elif move_opts[Opts.holding.value] == Holding.holding.value and button == Buttons.nothing.value:
                    #print("controller {} was holding, and now it's pushing nothing, let's change it's values to nothing and not holding".format(str(move.get_serial())))
                    move_opts[Opts.selection.value] = Selections.nothing.value
                    move_opts[Opts.holding.value] = Holding.not_holding.value
        else:
            if super_dead == False:
                for i in range(100):
                    time.sleep(0.01)
                    move.set_leds(200,200,200)
                    move.set_rumble(130)
                    move.update_leds()
                super_dead = True
            move.set_rumble(0)
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
        self.bomb_color = Array('i', [0] * 3)
        self.start_timer = time.time()
        self.audio_cue = 0
        self.num_bombs = 2
        self.move_opts = {}
        self.false_colors = {}
        self.was_faked = {}

        self.game_start = Value('i', 0)

        try:
            music = 'audio/Commander/music/' + random.choice(os.listdir('audio/Commander/music'))
        except:
            print('no music in audio/Commander/music')
        self.start_beep = Audio('audio/Joust/sounds/start.wav')
        self.start_game = Audio('audio/Joust/sounds/start3.wav')
        self.explosion = Audio('audio/Joust/sounds/Explosion34.wav')
        self.fakedout = Audio('audio/Joust/sounds/Fakedout.wav')
        self.explosion40 = Audio('audio/Joust/sounds/Explosion40.wav')
        self.countered = Audio('audio/Joust/sounds/countered.wav')
        self.explosiondeath = Audio('audio/Joust/sounds/explosiondeath.wav')

        end = False
        try:
            self.audio = Audio(music, end)
        except:
            print('no audio loaded')


        self.game_end = False

        
        self.game_loop()

    def get_bomb_length(self):
        return random.choice(range(20, 40))

    def get_next_bomb_holder(self, serial=None):
        if serial:
            holder = self.get_serial_pos(serial)
        else:
            holder = random.choice(range(len(self.move_serials)))
        while True:
            new_serial = self.move_serials[holder]
            if self.dead_moves[new_serial].value > 0:
                yield new_serial
            holder = (holder +1) % len(self.move_serials)

        
    def reset_bomb_time(self):
        self.bomb_time = time.time() + self.get_bomb_length()
        self.bomb_start_time = time.time()

    def game_loop(self):
        self.track_moves()
        self.print_bombs()
        self.rotate_colors()

        self.bomb_generator = self.get_next_bomb_holder()

        self.bomb_serial = next(self.bomb_generator)
        self.move_opts[self.bomb_serial][Opts.has_bomb.value] = Bool.yes.value
        

        self.holding = True

        self.count_down()
        time.sleep(0.02)
        try:
            self.audio.start_audio_loop()
        except:
            print('no audio loaded to start')
        time.sleep(0.8)
        
        self.bomb_time = time.time() + self.get_bomb_length()
        self.bomb_start_time = time.time()
        self.game_start.value = 1
        while self.running:
            percentage = 1-((self.bomb_time - time.time())/(self.bomb_time - self.bomb_start_time))
            self.bomb_color[0] = int(common.lerp(70, 255, percentage))
            self.bomb_color[1] = int(common.lerp(40, 0, percentage))
            self.bomb_color[2] = int(common.lerp(40, 0, percentage))

            if self.move_opts[self.bomb_serial][Opts.selection.value] == Selections.nothing.value:
                self.holding = False
            if self.move_opts[self.bomb_serial][Opts.selection.value] == Selections.a_button.value and self.holding == False:
                
                #self.print_bombs()

                self.move_bomb()

                self.start_beep.start_effect()
                self.holding = True
            if time.time() > self.bomb_time:
                self.dead_moves[bomb_serial].value -= 1
                self.move_opts[bomb_serial][Opts.has_bomb.value] = Bool.no.value
                print("TIME BOMB")
                self.explosiondeath.start_effect()
                self.place_bombs()
                self.explosion.start_effect()
                self.reset_bomb_time()


            self.check_dead_moves()
            self.check_false_sound()
            if self.game_end:
                self.end_game()

        self.stop_tracking_moves()

    def move_bomb(self):
        self.move_opts[self.bomb_serial][Opts.has_bomb.value] = Bool.no.value
        self.bomb_serial = next(self.bomb_generator)
        self.move_opts[self.bomb_serial][Opts.has_bomb.value] = Bool.yes.value
        

    def check_false_sound(self):
        #check for one controller left first
        for move_serial in self.move_serials:
            if self.dead_moves[move_serial].value > 0:
                if self.move_opts[move_serial][Opts.selection.value] == Selections.false_trigger.value and self.move_opts[move_serial][Opts.holding.value] == Holding.not_holding.value:
                    faker = self.get_next_serial(move_serial)
                    self.false_colors[faker].value = 1
                    self.start_beep.start_effect()
                    self.move_opts[move_serial][Opts.holding.value] = Holding.holding.value
                if self.false_colors[move_serial].value == 1:
                    prev_faker = self.get_prev_serial(move_serial)
                    if self.move_opts[move_serial][Opts.selection.value] == Selections.triangle.value:
                        self.dead_moves[prev_faker].value -= 1
                        self.false_colors[move_serial].value = 0
                        self.move_opts[move_serial][Opts.holding.value] = Holding.holding.value

                        self.explosion40.start_effect()
                        self.countered.start_effect()
                        self.move_bomb()
                        
                        print("JUST DIED TO BEING COUNTERED")
                    if self.move_opts[prev_faker][Opts.holding.value] == Holding.not_holding.value:
                        self.false_colors[move_serial].value = 0
                elif self.false_colors[move_serial].value == 0  and self.move_opts[move_serial][Opts.holding.value] == Holding.not_holding.value:
                    if self.move_opts[move_serial][Opts.selection.value] == Selections.triangle.value:
                        self.dead_moves[move_serial].value -= 1
                        self.move_opts[move_serial][Opts.holding.value] = Holding.holding.value
                        self.explosion40.start_effect()
                        self.countered.start_effect()
                        self.move_bomb()
                        print("JUST DIED TO PRESSING TRIANGLE")
                

    def get_next_serial(self, serial):
        pos = (self.get_serial_pos(serial) + 1) % len(self.move_serials)
        new_serial = self.move_serials[pos]
        while self.dead_moves[new_serial].value == 0:
            pos = (pos + 1) % len(self.move_serials)
            new_serial = self.move_serials[pos]
        return self.move_serials[pos]

    def get_prev_serial(self, serial):
        pos = (self.get_serial_pos(serial) - 1) % len(self.move_serials)
        new_serial = self.move_serials[pos]
        while self.dead_moves[new_serial].value == 0:
            pos = (pos - 1) % len(self.move_serials)
            new_serial = self.move_serials[pos]
        return self.move_serials[pos]


    def get_serial_pos(self, serial):
        for i, move_serial in enumerate(self.move_serials):
            if serial == move_serial:
                return i
        

    def track_moves(self):
        for move_num, move_serial in enumerate(self.move_serials):
            self.alive_moves.append(move_serial)
            time.sleep(0.02)
            dead_move = Value('i', 2)
            force_color = Array('i', [1] * 3)
            false_color = Value('i', 0)
            
            opts = Array('i', [0] * 5)
            faked = Value('i', 0)

            proc = Process(target=track_move, args=(move_serial,
                                                    move_num,
                                                    dead_move,
                                                    force_color,
                                                    self.bomb_color,
                                                    opts,
                                                    self.game_start,
                                                    false_color,
                                                    faked))
            proc.start()
            self.tracked_moves[move_serial] = proc
            self.dead_moves[move_serial] = dead_move
            self.force_move_colors[move_serial] = force_color
            self.move_opts[move_serial] = opts
            self.false_colors[move_serial] = false_color
            self.was_faked[move_serial] = faked


    def rotate_colors(self):
        move_on = False
        in_cons = []
        for move_serial_beg in self.move_serials:
            self.move_opts[move_serial_beg][Opts.has_bomb.value] = Bool.yes.value
            self.move_opts[move_serial_beg][Opts.holding.value] = Holding.holding.value
        while len(in_cons) != len(self.move_serials):
            for move_serial in self.move_serials:
                for move_serial_beg in self.move_serials:
                    if self.move_opts[move_serial_beg][Opts.selection.value] == Selections.a_button.value:
                        if move_serial_beg not in in_cons:
                            self.start_beep.start_effect()
                            in_cons.append(move_serial_beg)
                    if move_serial_beg in in_cons:
                        common.change_color(self.force_move_colors[move_serial_beg], 100,100,100)
                common.change_color(self.force_move_colors[move_serial], 100,0,0)
                time.sleep(0.5)
                common.change_color(self.force_move_colors[move_serial], 0,0,0)
        for move_serial_beg in self.move_serials:
            self.move_opts[move_serial_beg][Opts.has_bomb.value] = Bool.no.value
            #self.move_opts[move_serial_beg][Opts.holding.value] = Holding.not_holding.value

        #print("rotate colors print bombs")
        self.print_bombs()

    def print_bombs(self):
        for i, move_serial in enumerate(self.move_serials):
            pass
            #print("controller {}, serial {}, is dead {}, is holding {}, has bomb {}".format(i, move_serial, self.dead_moves[move_serial].value, self.move_opts[move_serial][Opts.holding.value], self.move_opts[move_serial][Opts.has_bomb.value]))
        #print("\n")

            

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
                    for i, bomb_serial in enumerate(self.bomb_serials):
                        if bomb_serial == alive_serial:
                            bomb_serial = next(self.bomb_generators[i])
                        self.move_opts[bomb_serial][Opts.has_bomb.value] = Bool.yes.value
                #remove alive move:

                self.alive_moves.remove(alive_serial)
                self.explosion.start_effect()
                self.reset_bomb_time()
        #check for faked
        for move_serial in self.move_serials:
            if self.was_faked[move_serial].value == 1:
                print("WASSSFAKED")
                self.was_faked[move_serial].value = 2
                self.explosion40.start_effect()
                self.fakedout.start_effect()
            
            

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

