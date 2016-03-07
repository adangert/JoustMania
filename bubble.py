import common
import psmove
import time
import psutil, os
import random
import numpy
import math
from piaudio import Audio
from enum import Enum
from multiprocessing import Process, Value, Array


# How fast/slow the music can go
SLOW_MUSIC_SPEED = 1.5
FAST_MUSIC_SPEED = 0.5

# The min and max timeframe in seconds for
# the speed change to trigger, randomly selected
MIN_MUSIC_FAST_TIME = 4
MAX_MUSIC_FAST_TIME = 8
MIN_MUSIC_SLOW_TIME = 10
MAX_MUSIC_SLOW_TIME = 23

#Sensitivity of the contollers
SLOW_MAX = 1
SLOW_WARNING = 0.28
FAST_MAX = 1.8
FAST_WARNING = 0.8

#How long the speed change takes
INTERVAL_CHANGE = 1.5

#How long the winning moves shall sparkle
END_GAME_PAUSE = 4



MIN_FLASH = 3
MAX_FLASH = 0.05

def calculate_flash_time(r,g,b, score, win_amount):
    flash_percent = float(score)/(win_amount-1.0)
    flash_speed = common.lerp(MIN_FLASH, MAX_FLASH, flash_percent)
    val = (time.time() % float(flash_speed))
    if val < flash_speed/2:
        return (r,g,b)
    else:
        val_percent = (val-(flash_speed/2))/(flash_speed/2)
        new_r = int(common.lerp(r, 255, val_percent))
        new_g = int(common.lerp(g, 255, val_percent))
        new_b = int(common.lerp(b, 255, val_percent))
        return (new_r, new_g, new_b)

def track_move(move_serial, move_num, team, team_num, score, win_amount, dead_move, force_color, music_speed):
    #proc = psutil.Process(os.getpid())
    #proc.nice(3)
    #explosion = Audio('audio/Joust/sounds/Explosion34.wav')
    #explosion.start_effect()
    
    move_last_value = None
    move = common.get_move(move_serial, move_num)
    team_colors = common.generate_colors(team_num)
    werewolf = False
    flash_time = time.time()
    
    #keep on looping while move is not dead
    while True:
        if sum(force_color) != 0:
            time.sleep(0.01)
            move.set_leds(*force_color)
            move.update_leds()
            if werewolf:
                move.set_rumble(80)
        elif dead_move.value == 1:  
            if move.poll():
                ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
                total = sum([ax, ay, az])
                if move_last_value is not None:
                    change = abs(move_last_value - total)
                    speed_percent = (music_speed.value - SLOW_MUSIC_SPEED)/(FAST_MUSIC_SPEED - SLOW_MUSIC_SPEED)
                    warning = common.lerp(SLOW_WARNING, FAST_WARNING, speed_percent)
                    threshold = common.lerp(SLOW_MAX, FAST_MAX, speed_percent)

                    if change > threshold:
                        move.set_leds(0,0,0)
                        move.set_rumble(90)
                        score.value = -1
                        dead_move.value = 0

                    elif change > warning:
                        move.set_leds(20,50,100)
                        move.set_rumble(110)

                    else:
                        if score.value >= 1:
                            if time.time() > flash_time:
                                vall = calculate_flash_time(team_colors[team][0],team_colors[team][1],team_colors[team][2],score.value, win_amount)
                                #print vall
                                move.set_leds(*vall)
                                #flash_time = time.time() + calculate_flash_time(score.value, win_amount)
                        else:
                            move.set_leds(*team_colors[team])
                        move.set_rumble(0)
                        
                move_last_value = total
            move.update_leds()
            
        elif dead_move.value == 0:
            if move.poll():
                move_button = move.get_buttons()
                if score.value >= 0 and move_button == common.Buttons.middle:
                    dead_move.value = 1
                    move_last_value = None
                
                
            
            

class Bubble():
    def __init__(self, moves):

        self.move_serials = moves
        self.tracked_moves = {}
        self.dead_moves = {}
        self.scores = {}
        self.music_speed = Value('d', 1.5)
        self.running = True
        self.force_move_colors = {}
        self.teams = {}
        self.win_amount = int(math.ceil((len(moves)/2.0)+2))
        self.team_num = 2

        self.generate_random_teams(self.team_num)

        music = 'audio/Joust/music/' + random.choice(os.listdir('audio/Joust/music'))
        self.start_beep = Audio('audio/Joust/sounds/start.wav')
        self.start_game = Audio('audio/Joust/sounds/start3.wav')
        self.explosion = Audio('audio/Joust/sounds/Explosion34.wav')
        fast_resample = False
        if len(moves) >= 5:
            fast_resample = True
        self.audio = Audio(music, fast_resample)
        #self.change_time = self.get_change_time(speed_up = True)
        self.change_time = time.time() + 8
        self.speed_up = True
        self.currently_changing = False
        self.game_end = False
        self.winning_moves = []
        self.losing_moves = []
        
        
        self.game_loop()


    def generate_random_teams(self, team_num):
        team_pick = range(team_num)
        for serial in self.move_serials:
            random_choice = random.choice(team_pick)
            self.teams[serial] = random_choice
            team_pick.remove(random_choice)
            if not team_pick:
                team_pick = range(team_num)

    def track_moves(self):
        for move_num, move_serial in enumerate(self.move_serials):
            dead_move = Value('i', 1)
            score = Value('i', 0)
            
            force_color = Array('i', [1] * 3)
            proc = Process(target=track_move, args=(move_serial,
                                                    move_num,
                                                    self.teams[move_serial],
                                                    self.team_num,
                                                    score,
                                                    self.win_amount,
                                                    dead_move,
                                                    force_color,
                                                    self.music_speed))
            proc.start()
            self.scores[move_serial] = score
            self.tracked_moves[move_serial] = proc
            self.dead_moves[move_serial] = dead_move
            self.force_move_colors[move_serial] = force_color
            
    def change_all_move_colors(self, r, g, b):
        for color in self.force_move_colors.itervalues():
            common.change_color(color, r, g, b)

    #need to do the count_down here
    def count_down(self):
        self.change_all_move_colors(70, 0, 0)
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
        
    def get_change_time(self, speed_up):
        if speed_up:
            added_time = random.uniform(MIN_MUSIC_FAST_TIME, MAX_MUSIC_FAST_TIME)
        else:
            added_time = random.uniform(MIN_MUSIC_SLOW_TIME, MAX_MUSIC_SLOW_TIME)
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
            self.audio.change_chunk_size(True)
        elif time.time() >= self.change_time + INTERVAL_CHANGE and self.currently_changing:
            self.music_speed.value = SLOW_MUSIC_SPEED if self.speed_up else FAST_MUSIC_SPEED
            self.speed_up =  not self.speed_up
            self.change_time = self.get_change_time(speed_up = self.speed_up)
            self.audio.change_ratio(self.music_speed.value)
            self.currently_changing = False
            self.audio.change_chunk_size(False)

    def get_real_team(self, team):
        if team < 0:
            return -1
        else:
            return team

    def check_end_game(self):
        team_win = False
        for move_serial, score in self.scores.iteritems():
            #if we are alive
            if score.value >= self.win_amount:
                winning_team = self.teams[move_serial]
                team_win = True
                
        if team_win:
            for move_serial in self.teams.iterkeys():
                if self.teams[move_serial] == winning_team:
                    self.winning_moves.append(move_serial)
                else:
                    self.losing_moves.append(move_serial)
            self.game_end = True

    def check_for_points(self):
        for move_serial, score in self.scores.iteritems():
            if score.value == -1:
                score.value = 0
                self.explosion.start_effect()
                team_increase = self.teams[move_serial]
                for move_serial_increase, score_increase in self.scores.iteritems():
                    if self.teams[move_serial_increase] != team_increase:
                        score_increase.value += 1
            

    def stop_tracking_moves(self):
        for proc in self.tracked_moves.itervalues():
            proc.terminate()
            proc.join()

    def end_game(self):
        self.audio.stop_audio()
        end_time = time.time() + END_GAME_PAUSE
        h_value = 0
        while (time.time() < end_time):
            time.sleep(0.01)
            win_color = common.hsv2rgb(h_value, 1, 1)
            for win_move in self.winning_moves:
                win_color_array = self.force_move_colors[win_move]
                common.change_color(win_color_array, *win_color)
            for lose_move in self.losing_moves:
                lose_color_array = self.force_move_colors[lose_move]
                common.change_color(lose_color_array, 1,0,0)
            h_value = (h_value + 0.01)
            if h_value >= 1:
                h_value = 0
        self.running = False

    def game_loop(self):
        self.track_moves()
        self.count_down()
        self.audio.start_audio_loop()
        
        while self.running:

            self.check_music_speed()
            self.check_for_points()
            self.check_end_game()
            if self.game_end:
                self.end_game()

        self.stop_tracking_moves()
                    

