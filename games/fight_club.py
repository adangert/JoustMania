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
from random import shuffle


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
END_GAME_PAUSE = 12
KILL_GAME_PAUSE = 4


def track_move(move_serial, move_num, dead_move, force_color, music_speed, color, invincibility):
    #proc = psutil.Process(os.getpid())
    #proc.nice(3)
    #explosion = Audio('audio/Joust/sounds/Explosion34.wav')
    #explosion.start_effect()
    start = False
    no_rumble = time.time() + 1
    move_last_value = None
    move = common.get_move(move_serial, move_num)
    #team_colors = colors.generate_colors(num_teams)
    vibrate = False
    vibration_time = time.time() + 1
    flash_lights = True
    flash_lights_timer = 0
    start_inv = False
    change_arr = [0,0,0]

    #keep on looping while move is not dead
    while True:
        #if show_team_colors.value == 1:
        #    if team.value != -1:
        #        move.set_leds(*team_colors[team.value])
        #    else:
        #        move.set_leds(100,100,100)
        #    move.update_leds()
        if sum(force_color) != 0:
            no_rumble_time = time.time() + 5
            time.sleep(0.01)
            move.set_leds(*force_color)
            if sum(force_color) == 30:
                move.set_leds(0, 0, 0)
            move.set_rumble(0)
            move.update_leds()
            no_rumble = time.time() + 0.5
        elif dead_move.value == 1: #and not invincibility.value:   
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
                    if not start_inv and invincibility.value:
                        start_inv = True
                        vibrate = True
                        vibration_time = time.time() + 4
                        

                    if vibrate:
                        flash_lights_timer += 1
                        if flash_lights_timer > 7:
                            flash_lights_timer = 0
                            flash_lights = not flash_lights
                        if flash_lights:
                            #move.set_leds(100,100,100)
                            if color.value == 1:
                                move.set_leds(*colors.Colors.Orange.value)
                            if color.value == 2:
                                move.set_leds(*colors.Colors.Blue.value)
                            if color.value == 4:
                                move.set_leds(*colors.Colors.Green.value)
                        else:
                            #if team.value != -1:
                            #    move.set_leds(*team_colors[team.value])
                            #else:
                            move.set_leds(10,10,10)
                        if time.time() < vibration_time - 0.22:
                            move.set_rumble(110)
                        else:
                            move.set_rumble(0)
                        if time.time() > vibration_time:
                            #print("vibrate to false")
                            vibrate = False
                            start_inv = False
                            invincibility.value = False
                    else:
                        #move.set_leds(100,200,100)
                        if color.value == 1:
                            move.set_leds(*colors.Colors.Orange.value)
                        if color.value == 2:
                            move.set_leds(*colors.Colors.Blue.value)
                        if color.value == 4:
                            move.set_leds(*colors.Colors.Green.value)
                            
                    if not invincibility.value:
                        if change > threshold:
                            #print("over threshold")
                            if time.time() > no_rumble:
                                move.set_leds(*colors.Colors.Red.value)
                                move.set_rumble(90)
                                dead_move.value = -1

                        elif change > warning and not vibrate:
                            if time.time() > no_rumble:
                                vibrate = True
                                vibration_time = time.time() + 0.5
                                move.set_leds(20,50,100)


                        
                move_last_value = total
            move.update_leds()
        else:
            if dead_move.value < 1:
                if color.value == 3:
                    move.set_leds(*colors.Colors.Green80.value)
                else:
                    move.set_leds(20,20,20)
            #elif team.value == -1:
            #    move.set_leds(100,100,100)
            invincibility.value = 1
            move.update_leds()
            start_inv = False
            time.sleep(0.5)
            move.set_rumble(0)


class Fight_club():
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
        
        self.fighter_list = []
        self.create_fighter_list()

        self.chosen_defender = self.fighter_list.pop()
        self.chosen_fighter = self.fighter_list.pop()
        
        self.round_num = len(self.move_serials)*2
        
        #-1 because we reset at the beginning of the game
        self.round_counter = -1
        
        self.round_time = time.time()
        self.round_limit = 22
        self.score = {}
        self.add_initial_score()
        self.timer_beep = 4
        self.high_score = 1
        self.current_winner = ""
        
        self.revive_noise = True
        #just for the sound effects
        self.revive_time = time.time() + 4
        
        self.colors = {}
        


        fast_resample = False
        if self.play_audio:
##            music = 'audio/Joust/music/' + random.choice(os.listdir('audio/Joust/music'))
            self.loud_beep = Audio('audio/Joust/sounds/beep_loud.wav')
            self.start_beep = Audio('audio/Joust/sounds/start.wav')
            self.start_game = Audio('audio/Joust/sounds/start3.wav')
            self.explosion = Audio('audio/Joust/sounds/Explosion34.wav')
            self.revive = Audio('audio/Commander/sounds/revive.wav')
            
            
            
            end = False
            self.audio = music
        #self.change_time = self.get_change_time(speed_up = True)
        
        self.speed_up = True
        self.currently_changing = False
        self.game_end = False
        self.winning_moves = []
        self.game_loop()
        
    def create_fighter_list(self):
        self.fighter_list = self.move_serials[:]
        shuffle(self.fighter_list)
        
    def add_initial_score(self):
        for move in self.move_serials:
            self.score[move] = 0
            


    def track_moves(self):
        for move_num, move_serial in enumerate(self.move_serials):
            
            time.sleep(0.1)
            dead_move = Value('i', 0)
            
            force_color = Array('i', [1] * 3)
            invincibility = Value('b', True)
            color = Value('i', 0)
            proc = Process(target=track_move, args=(move_serial,
                                                    move_num,
                                                    dead_move,
                                                    force_color,
                                                    self.music_speed,
                                                    color,
                                                    invincibility))
            proc.start()
            self.colors[move_serial] = color
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


    def check_end_round(self):
        if self.play_audio:
            if time.time() > self.round_time - (3 * (self.timer_beep/4)):
                self.loud_beep.start_effect()
                self.timer_beep -= 1
            if time.time() > self.revive_time and self.revive_noise:
                self.revive_noise = False
                self.revive.start_effect()
                
            
        
        if time.time() > self.round_time:
            self.dead_moves[self.chosen_fighter].value = 0
            self.dead_moves[self.chosen_defender].value = 0
            self.colors[self.chosen_defender].value = 0
            self.colors[self.chosen_fighter].value = 0
            self.fighter_list.insert(0,self.chosen_defender)
            self.fighter_list.insert(0,self.chosen_fighter)
            if self.play_audio:
                    self.explosion.start_effect()
            self.chosen_defender = self.fighter_list.pop()
            self.chosen_fighter = self.fighter_list.pop()
            
            self.invince_moves[self.chosen_fighter].value = True
            self.invince_moves[self.chosen_defender].value = True
            self.revive_fighters()
            self.reset_round_timer()
            
            
    def alive_move_count(self):
        count =0
        for move, lives in self.dead_moves.items():
            if lives.value == 1:
                count += 1
        return count
            
            
    
    #more than one tied winner, have them face off
    def face_off(self):
        #print(self.winning_moves)
        #os.popen('espeak -ven -p 70 -a 200 "Tie game..... Face off"')
        
        Audio('audio/Fight_Club/tie_game.wav').start_effect()
        for move in self.move_serials:
            self.dead_moves[move].value = 0
        for move in self.winning_moves:
            self.dead_moves[move].value = 1
            self.colors[move].value = 4
        count_explode = self.alive_move_count()
        while count_explode > 1:
            if count_explode > self.alive_move_count():
                count_explode = self.alive_move_count()
                if self.play_audio:
                    self.explosion.start_effect()
        self.winning_moves = []
        for move, lives in self.dead_moves.items():
            if lives.value == 1:
                self.winning_moves.append(move)
        self.game_end = True
        
            
     
    #check to see if there is a winner,
    #if there is a tie, have them face off, no time limit
    #set winning moves
    def check_winner(self):
        self.winning_moves = []
        self.winning_score = 0
        print(self.score.items())
        for move, score in self.score.items():
            if score == self.winning_score:
                self.winning_moves.append(move)
            if score > self.winning_score:
                self.winning_moves = []
                self.winning_moves.append(move)
                self.winning_score = score
        if len(self.winning_moves) > 1:
            self.face_off()
        else:
            self.game_end = True
                
            
            
     
    def check_end_game(self):
        if self.round_counter >= self.round_num:
            self.check_winner()
        if self.round_counter == self.round_num - 5:
            Audio('audio/Fight_Club/5_rounds.wav').start_effect()
            #os.popen('espeak -ven -p 70 -a 200 "5 rounds remain"')
        if self.round_counter == self.round_num - 1:
            Audio('audio/Fight_Club/last_round.wav').start_effect()
            #os.popen('espeak -ven -p 70 -a 200 "last round"')
            
    
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
        for move in self.move_serials:
            self.dead_moves[move].value = 0
        Audio('audio/Fight_Club/game_over.wav').start_effect()
        #os.popen('espeak -ven -p 70 -a 200 "winner"')

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
        
    def check_next_fighter(self):
        #dead_moves: 0 dead waiting to be a fighter
        #dead_moves: 1 alive fighting
        #dead_moves: -1 just died as a fighter, go to the back of the line

            
        if  self.dead_moves[self.chosen_defender].value == -1:
            self.invince_moves[self.chosen_fighter].value = True
            if self.play_audio:
                    self.explosion.start_effect()
            self.add_score(self.chosen_fighter)
            self.fighter_list.insert(0,self.chosen_defender)
            self.dead_moves[self.chosen_defender].value = 0
            self.colors[self.chosen_defender].value = 0
            self.chosen_defender = self.chosen_fighter
            #self.colors[self.chosen_defender].value = 1
            self.chosen_fighter = self.fighter_list.pop()
            #self.colors[self.chosen_fighter].value = 2
            self.revive_fighters()
            self.reset_round_timer()
            
            #move to the back of the line
        elif  self.dead_moves[self.chosen_fighter].value == -1:
            self.invince_moves[self.chosen_defender].value = True
            if self.play_audio:
                    self.explosion.start_effect()
            self.add_score(self.chosen_defender)
            self.fighter_list.insert(0,self.chosen_fighter)
            self.colors[self.chosen_fighter].value = 0
            self.dead_moves[self.chosen_fighter].value = 0
            self.chosen_fighter = self.fighter_list.pop()
            #self.colors[self.chosen_fighter].value = 2
            self.revive_fighters()
            self.reset_round_timer()
            
            #move to the back of the line
            
    def revive_fighters(self):
        if  self.dead_moves[self.chosen_defender].value == 0:
            self.dead_moves[self.chosen_defender].value = 1
        if  self.dead_moves[self.chosen_fighter].value == 0:
            self.dead_moves[self.chosen_fighter].value = 1
        
            
    def add_score(self, serial):
        if serial not in self.score:
            self.score[serial] = 1
        else:
            self.score[serial] += 1
            
    def get_highest_score(self):
        max_score = 1
        for move, score in self.score.items():
            if score > max_score:
                max_score = score
        return max_score
            
            
    def set_highest_score_color(self):
        max_score = self.get_highest_score()
        for move,score in self.score.items():
            if score == max_score:
                if self.colors[move].value == 0:
                    self.colors[move].value = 3
            elif self.colors[move].value == 3:
                self.colors[move].value = 0
        
            
    def reset_round_timer(self):
        self.revive_time = time.time() + 4
        self.revive_noise = True
        
        self.round_counter += 1
        self.round_time = time.time() + self.round_limit
        self.timer_beep = 4
        self.colors[self.chosen_defender].value = 1
        self.colors[self.chosen_fighter].value = 2
        print(self.score.items())
        self.set_highest_score_color()
        print(self.get_highest_score())
        print(self.high_score)
        if self.get_highest_score() > self.high_score :
            self.high_score = self.get_highest_score()
            if self.current_winner != self.chosen_defender:
                self.current_winner = self.chosen_defender
                saying = random.randint(0,2)
                if saying == 0:
                    Audio('audio/Fight_Club/defender_lead.wav').start_effect()
                    #os.popen('espeak -ven -p 70 -a 200 "Defender has taken the lead"')
                elif saying == 1:
                    Audio('audio/Fight_Club/defender_winning.wav').start_effect()
                    #os.popen('espeak -ven -p 70 -a 200 "Defender is now winning"')
                elif saying == 2:
                    Audio('audio/Fight_Club/Defender_high_score.wav').start_effect()
                    #os.popen('espeak -ven -p 70 -a 200 "Defender has the high score"')
        self.check_end_game()
        

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
        
        
        self.revive_fighters()
        self.reset_round_timer()
        while self.running:
            #I think the loop is so fast that this causes 
            #a crash if done every loop
            if time.time() - 0.1 > self.update_time:
                self.update_time = time.time()
                self.check_command_queue()
                self.update_status('in_game')
            #if self.play_audio:
                #self.check_music_speed()
            self.check_next_fighter()
            self.check_end_round()
            if self.game_end:
                print("end game")
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
               'game_mode' : 'Fight Club',
               'winning_team' : winning_team}
        self.ns.status = data
                    
                
                
        
        

            
        

            
