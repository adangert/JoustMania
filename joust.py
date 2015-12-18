import common
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

#How long the speed change takes
CHANGE_TIME = 1.5

#Sensitivity of the contollers
SLOW_MAX = 1
SLOW_WARNING = 0.28
FAST_MAX = 1.8
FAST_WARNING = 0.8

class Games(Enum):
    JoustFFA = 0
    JoustTeams = 1
    JoustRandomTeams = 2
    WereJoust = 3

def track_move(move_serial, move_num, move_opts, dead_move, force_color, speed):
    move_last_value = None
    move = common.get_move(move_serial, move_num)
    #keep on looping while move is not dead
    while dead_move.value == 1:
        if move.poll():
            ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
            total = sum([ax, ay, az])
            if move_last_value in not None:
                change = abs(move_last_value - total)
                speed_percent = (speed.value - slow_speed)/(fast_speed - slow_speed)
                warning = lerp(slow_warning, fast_warning, speed_percent)
                threshold = lerp(slow_max, fast_max, speed_percent)
            
        
        

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
            
            proc = Process(target=track_move, args=(move_serial, move_num, dead_move, self.force_color, self.speed))
            proc.start()
            self.tracked_moves[move_serial] = proc
            self.dead_moves[move_serial] = dead_move

    def count_down(self):
        

    def game_loop(self):
        self.track_moves()
        while self.running:
            
        
        

            
        

            
