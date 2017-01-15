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

def track_move(move_serial, move_num, dead_move, force_color,bomb_color, move_opts):
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
        elif dead_move.value == 1:
            if move.poll():
                button = move.get_buttons()

                    
                if move_opts[Opts.has_bomb.value] == Bool.yes.value:
                    move.set_leds(*bomb_color)
                    #move.set_rumble(bomb_color[0])
                    move.set_rumble(0)
                else:
                    if move_opts[Opts.selection.value] == Selections.a_button.value and move_opts[Opts.holding.value] == Holding.not_holding.value:
                        print("BOOOOOM CONTROLLER PUSHED {}, the selection was a and it was not holding :O".format(str(move.get_serial())))
                        dead_move.value = 0
                    move.set_leds(0,10,50)
                    move.set_rumble(0)

                if button == Buttons.middle.value and move_opts[Opts.holding.value] == Holding.not_holding.value:
                    print("controller {} was not holding, and now it's pushing middle, let's change it's values to a and holding".format(str(move.get_serial())))
                    move_opts[Opts.selection.value] = Selections.a_button.value
                    move_opts[Opts.holding.value] = Holding.holding.value
                    
                elif move_opts[Opts.holding.value] == Holding.holding.value and button == Buttons.nothing.value:
                    print("controller {} was holding, and now it's pushing nothing, let's change it's values to nothing and not holding".format(str(move.get_serial())))
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

    def get_bomb_length(self):
        return random.choice(range(17, 33))

    def get_next_bomb_holder(self, serial=None):
        print("making a bomb holder with serial {}".format(str(serial)))
        if serial:
            holder = self.get_serial_pos(serial)
        else:
            holder = random.choice(range(len(self.move_serials)))
        print("the holder is {}".format(str(holder)))
        while True:
            new_serial = self.move_serials[holder]
            if self.dead_moves[new_serial].value == 1:
                print("called holder, found new serial to return {}".format(str(new_serial)))
                yield new_serial
            holder = (holder +1) % len(self.move_serials)

        

    def reset_bomb_time(self):
        self.bomb_time = time.time() + self.get_bomb_length()
        self.bomb_start_time = time.time()

    def game_loop(self):
        self.track_moves()
        print("controllers before rotation")
        self.print_bombs()
        self.rotate_colors()
        print("controllers after rotation")
        self.print_bombs()
        self.bomb_generators = []
        self.bomb_generators.append(self.get_next_bomb_holder())
        self.bomb_serials = []
        self.bomb_serials.append(next(self.bomb_generators[0]))
        self.move_opts[self.bomb_serials[0]][Opts.has_bomb.value] = Bool.yes.value
        print("first bomb selected")
        self.print_bombs()

        print("getting next bomb")
        far_serial = self.gen_furthest_point()
        self.bomb_generators.append(self.get_next_bomb_holder(far_serial))
        self.bomb_serials.append(next(self.bomb_generators[1]))
        self.move_opts[self.bomb_serials[1]][Opts.has_bomb.value] = Bool.yes.value
        print("second bomb selected")
        self.print_bombs()

        

        
        self.count_down()
        time.sleep(0.02)
        try:
            self.audio.start_audio_loop()
        except:
            print('no audio loaded to start')
        time.sleep(0.8)
        holding_arr = [True,True]
        self.bomb_time = time.time() + self.get_bomb_length()
        self.bomb_start_time = time.time()
        while self.running:
            percentage = 1-((self.bomb_time - time.time())/(self.bomb_time - self.bomb_start_time))
            self.bomb_color[0] = int(common.lerp(0, 200, percentage))
            self.bomb_color[1] = int(common.lerp(70, 0, percentage))


            for i, bomb_serial in enumerate(self.bomb_serials):
                if self.move_opts[bomb_serial][Opts.selection.value] == Selections.nothing.value:
                    holding_arr[i] = False
                if self.move_opts[bomb_serial][Opts.selection.value] == Selections.a_button.value and holding_arr[i] == False:
                    
                    print("the alive serials are " + str(self.alive_moves))
                    print("the bomb serials are " + str(self.bomb_serials))
                    
                    print("A BOMB PLAYER {} HAS PRESSED THE A BUTTON, MOVING TO NEXT PLAYER".format(bomb_serial))
                    self.print_bombs()

                    
                    self.move_opts[bomb_serial][Opts.has_bomb.value] = Bool.no.value
                    bomb_serial = next(self.bomb_generators[i])
                    self.bomb_serials[i] = bomb_serial
                    self.move_opts[bomb_serial][Opts.has_bomb.value] = Bool.yes.value

                    
                    print("new bomb serial is {} {}".format(i,  str(bomb_serial)))
                    self.print_bombs()
                    

                    self.start_beep.start_effect()
                    holding_arr[i] = True
                if time.time() > self.bomb_time:
                    print("times up for the bombs moving them")
                    self.dead_moves[bomb_serial].value = 0
                    self.explosion.start_effect()
                    self.move_opts[bomb_serial][Opts.has_bomb.value] = Bool.no.value
                    #THIS NEEDS TO BE CHANGED
                    self.bomb_serial = next(self.bomb_generators[i])
                    self.move_opts[bomb_serial][Opts.has_bomb.value] = Bool.yes.value
                    self.reset_bomb_time()
            #check for collision:
            for i, bomb_serial in enumerate(self.bomb_serials):
                for j, bomb_serial_n in enumerate(self.bomb_serials):
                    if i != j and bomb_serial == bomb_serial_n:
                        #collision
                        print("COLLISIONS! BETWEEN {} and {}".format(bomb_serial, bomb_serial_n))
                        
                        self.explosion.start_effect()
                        #bomb_serial_test =next(self.bomb_generators[i])
                        #if self.move_opts[bomb_serial_test][Opts.has_bomb.value] == Bool.yes.value:
                        #    print('next has a bomb, getting away')
                        new_bomb_serial = self.gen_furthest_point()
                        self.move_opts[new_bomb_serial][Opts.has_bomb.value] = Bool.yes.value
                        self.move_opts[bomb_serial][Opts.has_bomb.value] = Bool.no.value
                        self.dead_moves[bomb_serial].value = 0
                        self.bomb_generators[i] = self.get_next_bomb_holder(new_bomb_serial)
                        
                        print("moving first bomb away to {}".format(new_bomb_serial))
                        #else:
                        #    print('next doesnt have abomb, being next')
                        #    bomb_serial = bomb_serial_test
                        self.bomb_serials[i] = next(self.bomb_generators[i])
                        bomb_serial_n = self.gen_furthest_point()
                        self.bomb_generators[j] = self.get_next_bomb_holder(bomb_serial_n)
                        self.bomb_serials[j] = next(self.bomb_generators[j])
                        self.move_opts[bomb_serial_n][Opts.has_bomb.value] = Bool.yes.value
                        print("moving second bomb away to {}".format(bomb_serial_n))


            self.check_dead_moves()
            if self.game_end:
                self.end_game()

        self.stop_tracking_moves()



    def place_bomb_away(self):
        pass

    def gen_furthest_point(self):
        print("doing get furthest point")
        max_dist = 0
        max_dist_serial = None
        #print("here are the alive serials " + str(self.alive_moves))
        #self.print_bombs()
        for move_serial in self.move_serials:
            print("\ntrying dist for move_serial {}".format(str(move_serial)))
            #print("@@@@@doing move serial {}".format(str(move_serial)))
            if self.dead_moves[move_serial].value == 1 and  self.move_opts[move_serial][Opts.has_bomb.value] == Bool.no.value:
                #print("move serial is alive, and does not have a bomb")
                dist = self.calc_dist(move_serial)
                if dist > max_dist:
                    max_dist = dist
                    max_dist_serial = move_serial
                    print("dist is bigger its {}".format(str(dist)))
                    print("dist is bigger assigning " + str(max_dist_serial))
        print("returning the max_dist_serial " + str(max_dist_serial))
        return max_dist_serial

    def calc_dist(self, serial):
        #print("doing calc dist with " + str(serial))
        start_move_num = self.get_serial_pos(serial)
        forward_num = start_move_num
        back_num = start_move_num
        forward_dist = 0
        back_dist = 0
        print("calcing dist for serial {}".format(str(serial)))
        self.print_bombs()
        
        while self.move_opts[self.move_serials[forward_num]][Opts.has_bomb.value] == Bool.no.value:
            forward_num = (forward_num + 1) % len(self.move_serials)
            print ("forward num is {}".format(str(forward_num)))
            while self.dead_moves[self.move_serials[forward_num]].value == 0:
                forward_num = (forward_num + 1) % len(self.move_serials)
             #   print( "forward NUMMMMM")
            forward_dist += 1

        #cal back pass
        while self.move_opts[self.move_serials[back_num]][Opts.has_bomb.value] == Bool.no.value:
            back_num = (back_num - 1) % len(self.move_serials)
            while self.dead_moves[self.move_serials[back_num]].value == 0:
                back_num = (back_num - 1) % len(self.move_serials)
            back_dist += 1

        

        #print("forward is {}, backward is {}".format(forward_dist, back_dist))
        #print("forward is {}, backward is {}, returning {} for serial {}\n".format(forward_dist, back_dist, min(forward_dist, back_dist), serial))
        return min(forward_dist, back_dist)
                

    def get_serial_pos(self, serial):
        for i, move_serial in enumerate(self.move_serials):
            if serial == move_serial:
                return i
        

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
                                                    self.bomb_color,
                                                    opts))
            proc.start()
            self.tracked_moves[move_serial] = proc
            self.dead_moves[move_serial] = dead_move
            self.force_move_colors[move_serial] = force_color
            self.move_opts[move_serial] = opts


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

        print("rotate colors print bombs")
        self.print_bombs()

    def print_bombs(self):
        for i, move_serial in enumerate(self.move_serials):
            print("controller {}, serial {}, is dead {}, is holding {}, has bomb {}".format(i, move_serial, self.dead_moves[move_serial].value, self.move_opts[move_serial][Opts.holding.value], self.move_opts[move_serial][Opts.has_bomb.value]))
        print("\n")

            

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

