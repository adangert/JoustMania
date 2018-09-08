import common, colors
import psmove
import time
import psutil, os
import random
import numpy
import math
import json
from piaudio import Audio
from enum import Enum
from multiprocessing import Process, Value, Array
from math import sqrt


# How fast/slow the music can go
SLOW_MUSIC_SPEED = 0.5
#this was 0.5
FAST_MUSIC_SPEED = 2.0

# The min and max timeframe in seconds for
# the speed change to trigger, randomly selected
MIN_MUSIC_FAST_TIME = 4
MAX_MUSIC_FAST_TIME = 8
MIN_MUSIC_SLOW_TIME = 10
MAX_MUSIC_SLOW_TIME = 23

END_MIN_MUSIC_FAST_TIME = 6
END_MAX_MUSIC_FAST_TIME = 10
END_MIN_MUSIC_SLOW_TIME = 8
END_MAX_MUSIC_SLOW_TIME = 12

#Default Sensitivity of the contollers
#These are changed from the options in common
SLOW_MAX = 1
SLOW_WARNING = 0.28
FAST_MAX = 1.8
FAST_WARNING = 0.8


#How long the speed change takes
INTERVAL_CHANGE = 1.5

#How long the winning moves shall sparkle
END_GAME_PAUSE = 6
KILL_GAME_PAUSE = 4


def track_move(move_serial, move_num, team, num_teams, dead_move, force_color, music_speed, show_team_colors, invincibility):
    #proc = psutil.Process(os.getpid())
    #proc.nice(3)
    #explosion = Audio('audio/Joust/sounds/Explosion34.wav')
    #explosion.start_effect()
    start = False
    no_rumble = time.time() + 1
    move_last_value = None
    move = common.get_move(move_serial, move_num)
    team_colors = colors.generate_colors(num_teams)
    vibrate = False
    vibration_time = time.time() + 1
    flash_lights = True
    flash_lights_timer = 0
    start_inv = False
    change_arr = [0,0,0]

    #keep on looping while move is not dead
    while True:
        if show_team_colors.value == 1:
            if team.value != -1:
                move.set_leds(*team_colors[team.value])
            else:
                move.set_leds(100,100,100)
            move.update_leds()
        elif sum(force_color) != 0:
            no_rumble_time = time.time() + 5
            time.sleep(0.01)
            move.set_leds(*force_color)
            if sum(force_color) == 30:
                move.set_leds(0, 0, 0)
            move.set_rumble(0)
            move.update_leds()
            no_rumble = time.time() + 0.5
        elif dead_move.value == 1 and team.value != -1:   
            if move.poll():
                ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
                #total = sum([ax, ay, az])
                total = sqrt(sum([ax**2, ay**2, az**2]))
                if move_last_value is not None:
                    change_real = abs(move_last_value - total)
                    change_arr[0] = change_arr[1]
                    change_arr[1] = change_arr[2]
                    change_arr[2] = change_real
                    change = (change_arr[0] + change_arr[1]+change_arr[2])/3
                    speed_percent = (music_speed.value - SLOW_MUSIC_SPEED)/(FAST_MUSIC_SPEED - SLOW_MUSIC_SPEED)
                    warning = common.lerp(SLOW_WARNING, FAST_WARNING, speed_percent)
                    threshold = common.lerp(SLOW_MAX, FAST_MAX, speed_percent)
                    if not start_inv and invincibility.value == 1:
                        start_inv = True
                        vibrate = True
                        vibration_time = time.time() + 3
                        

                    if vibrate:
                        flash_lights_timer += 1
                        if flash_lights_timer > 7:
                            flash_lights_timer = 0
                            flash_lights = not flash_lights
                        if flash_lights:
                            move.set_leds(100,100,100)
                        else:
                            if team.value != -1:
                                move.set_leds(*team_colors[team.value])
                            else:
                                move.set_leds(100,100,100)
                        if time.time() < vibration_time - 0.22:
                            move.set_rumble(110)
                        else:
                            move.set_rumble(0)
                        if time.time() > vibration_time:
                            vibrate = False
                            start_inv = False
                            invincibility.value = 0
                    else:
                        if team.value != -1:
                            move.set_leds(*team_colors[team.value])
                        else:
                            move.set_leds(100,100,100)
                            
                    if invincibility.value == 0:
                        if change > threshold:
                            if time.time() > no_rumble:
                                move.set_leds(0,0,0)
                                move.set_rumble(90)
                                dead_move.value = 0

                        elif change > warning and not vibrate:
                            if time.time() > no_rumble:
                                vibrate = True
                                vibration_time = time.time() + 0.5
                                move.set_leds(20,50,100)


                        
                move_last_value = total
            move.update_leds()
        else:
            if dead_move.value < 1:
                move.set_leds(0,0,0)
            elif team.value == -1:
                move.set_leds(100,100,100)
            move.update_leds()
                
            time.sleep(0.5)
            move.set_rumble(0)


class Tournament():
    def __init__(self, moves, command_queue, ns, music):

        self.command_queue = command_queue
        self.ns = ns

        self.sensitivity = self.ns.settings['sensitivity']
        self.play_audio = self.ns.settings['play_audio']

        print("speed is {}".format(self.sensitivity))
        global SLOW_MAX
        global SLOW_WARNING
        global FAST_MAX
        global FAST_WARNING
        
        SLOW_MAX = common.SLOW_MAX[self.sensitivity]
        SLOW_WARNING = common.SLOW_WARNING[self.sensitivity]
        FAST_MAX = common.FAST_MAX[self.sensitivity]
        FAST_WARNING = common.FAST_WARNING[self.sensitivity]

        self.move_serials = moves

        self.tracked_moves = {}
        self.dead_moves = {}
        self.music_speed = Value('d', 1.5)
        self.running = True
        self.force_move_colors = {}
        self.invince_moves = {}
        

        self.start_timer = time.time()
        self.audio_cue = 0
        self.num_dead = 0
        self.show_team_colors = Value('i', 0)
        self.teams = {}
        self.update_time = 0
        
        #self.num_teams = math.ceil(len(moves)/2)
        self.num_teams = len(moves)

        
        self.generate_random_teams(self.num_teams)

        self.tourney_list = self.generate_tourney_list(len(moves))
        fast_resample = False
        if self.play_audio:
            print("tourney list is " + str(self.tourney_list))

##            music = 'audio/Joust/music/' + random.choice(os.listdir('audio/Joust/music'))
            self.start_beep = Audio('audio/Joust/sounds/start.wav')
            self.start_game = Audio('audio/Joust/sounds/start3.wav')
            self.explosion = Audio('audio/Joust/sounds/Explosion34.wav')
            
            end = False
            self.audio = music
        #self.change_time = self.get_change_time(speed_up = True)
        
        self.speed_up = True
        self.currently_changing = False
        self.game_end = False
        self.winning_moves = []
        self.game_loop()

    def generate_tourney_list(self, player_num):
        def divide(arr, depth, m):
            if len(complements) <= depth:
                complements.append(2 ** (depth + 2) + 1)
            complement = complements[depth]
            for i in range(2):
                if complement - arr[i] <= m:
                    arr[i] = [arr[i], complement - arr[i]]
                    divide(arr[i], depth + 1, m)

        m = player_num

        arr = [1, 2]
        complements = []

        divide(arr, 0, m)
        dup_serials = self.move_serials[:]
        
        def insert_move(arr):
            for i in range(2):
                if type(arr[i]) is list:
                    insert_move(arr[i])
                else:
                    arr[i] = random.choice(dup_serials)
                    dup_serials.remove(arr[i])
        insert_move(arr)
        print(arr)
        return arr


    def generate_random_teams(self, num_teams):
        team_pick = list(range(num_teams))
        for serial in self.move_serials:
            random_choice = Value('i',  random.choice(team_pick) )
            self.teams[serial] = random_choice
            team_pick.remove(random_choice.value)
            if not team_pick:
                team_pick = list(range(num_teams))

    def track_moves(self):
        for move_num, move_serial in enumerate(self.move_serials):
            
            time.sleep(0.02)
            dead_move = Value('i', 1)
            
            force_color = Array('i', [1] * 3)
            invincibility = Value('i', 0)
            proc = Process(target=track_move, args=(move_serial,
                                                    move_num,
                                                    self.teams[move_serial],
                                                    self.num_teams,
                                                    dead_move,
                                                    force_color,
                                                    self.music_speed,
                                                    self.show_team_colors,
                                                    invincibility))
            proc.start()
            self.invince_moves[move_serial] = invincibility
            self.tracked_moves[move_serial] = proc
            self.dead_moves[move_serial] = dead_move
            self.force_move_colors[move_serial] = force_color
            
    def change_all_move_colors(self, r, g, b):
        for color in self.force_move_colors.values():
            colors.change_color(color, r, g, b)

    #need to do the count_down here
    def count_down(self):
        self.change_all_move_colors(80, 0, 0)
        if self.play_audio:
            self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(70, 100, 0)
        if self.play_audio:
            self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(0, 70, 0)
        if self.play_audio:
            self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(0, 0, 0)
        if self.play_audio:
            self.start_game.start_effect()

    def get_change_time(self, speed_up):
        min_moves = len(self.move_serials) - 2
        if min_moves <= 0:
            min_moves = 1
        
        game_percent = (self.num_dead/min_moves)
        if game_percent > 1.0:
            game_percent = 1.0
        min_music_fast = common.lerp(MIN_MUSIC_FAST_TIME, END_MIN_MUSIC_FAST_TIME, game_percent)
        max_music_fast = common.lerp(MAX_MUSIC_FAST_TIME, END_MAX_MUSIC_FAST_TIME, game_percent)

        min_music_slow = common.lerp(MIN_MUSIC_SLOW_TIME, END_MIN_MUSIC_SLOW_TIME, game_percent)
        max_music_slow = common.lerp(MAX_MUSIC_SLOW_TIME, END_MAX_MUSIC_SLOW_TIME, game_percent)
        if speed_up:
            added_time = random.uniform(min_music_fast, max_music_fast)
        else:
            added_time = random.uniform(min_music_slow, max_music_slow)
        return time.time() + added_time

    def change_music_speed(self, fast):
        change_percent = numpy.clip((time.time() - self.change_time)/INTERVAL_CHANGE, 0, 1)
        if fast:
            self.music_speed.value = common.lerp(FAST_MUSIC_SPEED, SLOW_MUSIC_SPEED, change_percent)
        elif not fast:
            self.music_speed.value = common.lerp(SLOW_MUSIC_SPEED, FAST_MUSIC_SPEED, change_percent)
        self.audio.change_ratio(self.music_speed.value)

    def check_music_speed(self):
        if time.time() > self.change_time and time.time() < self.change_time + INTERVAL_CHANGE:
            self.change_music_speed(self.speed_up)
            self.currently_changing = True
        elif time.time() >= self.change_time + INTERVAL_CHANGE and self.currently_changing:
            self.music_speed.value = SLOW_MUSIC_SPEED if self.speed_up else FAST_MUSIC_SPEED
            self.speed_up =  not self.speed_up
            self.change_time = self.get_change_time(speed_up = self.speed_up)
            self.audio.change_ratio(self.music_speed.value)
            self.currently_changing = False


    def check_matches(self):
        #do this only when a controller dies, or at the beginning
        def check_moves(arr):
            if (type(arr[0]) is not list and type(arr[1]) is not list):
                if self.teams[arr[1]].value != -1:
                    self.teams[arr[0]].value = self.teams[arr[1]].value
                else:
                    self.teams[arr[1]].value = self.teams[arr[0]].value
            elif(type(arr[0]) is not list and type(arr[1]) is list):
                self.teams[arr[0]].value = -1
                check_moves(arr[1])
            elif(type(arr[1]) is not list and type(arr[0]) is list):
                self.teams[arr[1]].value = -1
                check_moves(arr[0])
            elif(type(arr[0]) is list and type(arr[1]) is list):
                check_moves(arr[0])
                check_moves(arr[1])
        check_moves(self.tourney_list)

    def remove_dead_player(self, dead_serial):
        def remove_dead(arr):
            if type(arr) is list and dead_serial in arr:
                arr.remove(dead_serial)
            else:
                if type(arr[0]) is list:
                    remove_dead(arr[0])
                if type(arr[1]) is list:
                    remove_dead(arr[1])
        remove_dead(self.tourney_list)


        def move_up(arr):
            if type(arr) is list and len(arr) == 1:
                return arr[0]
            else:
                if type(arr[0]) is list and move_up(arr[0]):
                    arr[0] = move_up(arr[0])
                    if type(arr[1]) is not list:
                        self.teams[arr[1]].value = self.teams[arr[0]].value
                        self.invince_moves[arr[1]].value = 1
                        self.invince_moves[arr[0]].value = 1
                    else:
                        self.teams[arr[0]].value = -1
                elif type(arr[1]) is list and move_up(arr[1]):
                    arr[1] = move_up(arr[1])

                    if type(arr[0]) is not list:
                        self.teams[arr[0]].value = self.teams[arr[1]].value
                        self.invince_moves[arr[1]].value = 1
                        self.invince_moves[arr[0]].value = 1
                    else:
                        self.teams[arr[1]].value = -1
        move_up(self.tourney_list)



    def check_end_game(self):
        self.winning_moves = []
        for move_serial, dead in self.dead_moves.items():
            #if we are alive
            if dead.value == 1:
                self.winning_moves.append(move_serial)
            if dead.value == 0:
                self.remove_dead_player(move_serial)
                #This is to play the sound effect
                self.num_dead += 1
                dead.value = -1
                if self.play_audio:
                    self.explosion.start_effect()
        if len(self.winning_moves) <= 1:
            self.game_end = True
                


    def stop_tracking_moves(self):
        for proc in self.tracked_moves.values():
            proc.terminate()
            proc.join()
            time.sleep(0.02)

    def end_game(self):
        self.audio.stop_audio()
        self.update_status('ending')
        end_time = time.time() + END_GAME_PAUSE
        h_value = 0

        while (time.time() < end_time):
            time.sleep(0.01)
            win_color = colors.hsv2rgb(h_value, 1, 1)
            for win_move in self.winning_moves:
                win_color_array = self.force_move_colors[win_move]
                colors.change_color(win_color_array, *win_color)
            h_value = (h_value + 0.01)
            if h_value >= 1:
                h_value = 0
        self.running = False
        
        

    def game_loop(self):
        self.track_moves()
        self.show_team_colors.value = 0
        self.count_down()
        self.change_time = time.time() + 6
        time.sleep(0.02)
        if self.play_audio:
            self.audio.start_audio_loop()
        else:
            #when no audio is playing set the music speed to middle speed
            self.music_speed.value = (FAST_MUSIC_SPEED + SLOW_MUSIC_SPEED) / 2
        time.sleep(0.8)
        self.check_matches()
        
        while self.running:
            #I think the loop is so fast that this causes 
            #a crash if done every loop
            if time.time() - 0.1 > self.update_time:
                self.update_time = time.time()
                self.check_command_queue()
                self.update_status('in_game')
            if self.play_audio:
                self.check_music_speed()
            self.check_end_game()
            if self.game_end:
                self.end_game()

        self.stop_tracking_moves()

    def check_command_queue(self):
        package = None
        while not(self.command_queue.empty()):
            package = self.command_queue.get()
            command = package['command']
        if not(package == None):
            if command == 'killgame':
                self.kill_game()

    def kill_game(self):
        if self.play_audio:
            try:
                self.audio.stop_audio()
            except:
                print('no audio loaded to stop')        
        self.update_status('killed')
        all_moves = [x for x in self.dead_moves.keys()]
        end_time = time.time() + KILL_GAME_PAUSE     
        
        bright = 255
        while (time.time() < end_time):
            time.sleep(0.01)
            color = (bright,0,0)
            for move in all_moves:
                color_array = self.force_move_colors[move]
                colors.change_color(color_array, *color)
            bright = bright - 1
            if bright < 10:
                bright = 10
        self.running = False

    def update_status(self,game_status,winning_team=-1):
        data ={'game_status' : game_status,
               'game_mode' : 'Tournament',
               'winning_team' : winning_team}
        self.ns.status = data
                    
                
                
        
        

            
        

            
