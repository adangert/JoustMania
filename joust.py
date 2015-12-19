import common
import psmove
from enum import Enum
from multiprocessing import Process, Value, Array


# How fast/slow the music can go
SLOW_MUSIC_SPEED = 1.5
FAST_MUSIC_SPEED = 0.5

# The min and max timeframe in seconds for
# the speed change to trigger, randomly selected
MIN_FAST = 4
MAX_FAST = 8
MIN_SLOW = 10
MAX_SLOW = 23

#Sensitivity of the contollers
SLOW_MAX = 1
SLOW_WARNING = 0.28
FAST_MAX = 1.8
FAST_WARNING = 0.8

#How long the speed change takes
CHANGE_TIME = 1.5

class Games(Enum):
    JoustFFA = 0
    JoustTeams = 1
    JoustRandomTeams = 2
    WereJoust = 3

def track_move(move_serial, move_num, dead_move, force_color, speed):
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
                speed_percent = (speed.value - SLOW_MUSIC_SPEED)/(FAST_MUSIC_SPEED - SLOW_MUSIC_SPEED)
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
        self.speed = Value('d', 1.5)
        self.running = True
        self.force_color = opts = Array('i', [0] * 3)
        self.game_loop()

    def track_moves(self):
        for move_num, move_serial in enumerate(self.move_serials):
            dead_move = Value('i', 1)
            
            proc = Process(target=track_move, args=(move_serial,
                                                    move_num,
                                                    dead_move,
                                                    self.force_color,
                                                    self.speed))
            proc.start()
            self.tracked_moves[move_serial] = proc
            self.dead_moves[move_serial] = dead_move

    #need to do the count_down here
    def count_down(self):
        pass
        

    def game_loop(self):
        self.track_moves()
        while self.running:
            pass
        
        

            
        

            
