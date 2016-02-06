import psmove
import colorsys
from enum import Enum

color_range = 255

def hsv2rgb(h, s, v):
    return tuple(int(color * color_range) for color in colorsys.hsv_to_rgb(h, s, v))

def generate_colors(color_num):
    Hue = [ ((num + 1.0)/color_num, 1, 1) for num in range(color_num) ]
    colors = [ hsv2rgb(*hsv_color) for hsv_color in Hue ]
    return colors


def get_move(serial, move_num):
    move = psmove.PSMove(move_num)
    if move.get_serial() != serial:
        for move_num in range(psmove.count_connected()):
            move = psmove.PSMove(move_num)
            if move.get_serial() == serial:
                return move
        return None
    else:
        return move

def lerp(a, b, p):
    return a*(1 - p) + b*p

def change_color(color_array, r, g, b):
    color_array[0] = r
    color_array[1] = g
    color_array[2] = b

class Games(Enum):
    JoustFFA = 0
    JoustTeams = 1
    JoustRandomTeams = 2
    WereJoust = 3
    Zombies = 4
    Bubble_Joust = 5
    
