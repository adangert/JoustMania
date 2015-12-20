import common
import psmove
import time
import psutil, os
import random
import numpy
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

class Games(Enum):
    JoustFFA = 0
    JoustTeams = 1
    JoustRandomTeams = 2
    WereJoust = 3

def track_move(move_serial, move_num, dead_move, force_color, music_speed):
    #proc = psutil.Process(os.getpid())
    #proc.nice(3)
    move_last_value = None
    move = common.get_move(move_serial, move_num)
    #keep on looping while move is not dead
    while dead_move.value == 1:
        if sum(force_color) != 0:
            move.set_leds(*force_color)
            move.update_leds()
        elif move.poll():
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
                    dead_move.value = 0

                elif change > warning:
                    move.set_leds(20,50,100)
                    move.set_rumble(110)

                else:
                    move.set_leds(50,50,50)
                    move.set_rumble(0)
                    
            move_last_value = total
        move.update_leds()
            
        
        

class Joust():
    def __init__(self, game_mode, moves):
        self.move_serials = moves
        self.game_mode = game_mode
        self.tracked_moves = {}
        self.dead_moves = {}
        self.music_speed = Value('d', 1.5)
        self.running = True
        self.force_color = opts = Array('i', [1] * 3)
        music = 'audio/Joust/music/' + random.choice(os.listdir('audio/Joust/music'))
        fast_resample = False
        if len(moves) >= 5:
            fast_resample = True
        self.audio = Audio(music, fast_resample)
        self.change_time = self.get_change_time(speed_up = True)
        self.speed_up = True
        self.currently_changing = False
        
        self.game_loop()

    def track_moves(self):
        for move_num, move_serial in enumerate(self.move_serials):
            dead_move = Value('i', 1)
            
            proc = Process(target=track_move, args=(move_serial,
                                                    move_num,
                                                    dead_move,
                                                    self.force_color,
                                                    self.music_speed))
            proc.start()
            self.tracked_moves[move_serial] = proc
            self.dead_moves[move_serial] = dead_move

    #need to do the count_down here
    def count_down(self):
        common.change_color(self.force_color, 70, 0, 0)
        time.sleep(0.75)
        common.change_color(self.force_color, 70, 100, 0)
        time.sleep(0.75)
        common.change_color(self.force_color, 0, 70, 0)
        time.sleep(0.75)
        common.change_color(self.force_color, 0, 0, 0)
        
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
            
    def game_loop(self):
        self.track_moves()
        self.count_down()
        self.audio.start_audio_loop()
        
        while self.running:
            if time.time() > self.change_time and time.time() < self.change_time + INTERVAL_CHANGE:
                self.change_music_speed(self.speed_up)
                self.currently_changing = True
            elif time.time() >= self.change_time + INTERVAL_CHANGE and self.currently_changing:
                self.music_speed.value = SLOW_MUSIC_SPEED if self.speed_up else FAST_MUSIC_SPEED
                self.speed_up =  not self.speed_up
                self.change_time = self.get_change_time(speed_up = self.speed_up)
                self.audio.change_ratio(self.music_speed.value)
                
        
        

            
        

            
