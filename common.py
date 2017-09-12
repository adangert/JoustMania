import psmove
import time
from enum import Enum
import random

SETTINGSFILE = 'joustsettings.yaml'

#Human speeds[slow, mid, fast]
SLOW_WARNING = [0.1, 0.15, 0.28]
SLOW_MAX = [0.5, 0.8, 1]
FAST_WARNING = [0.5, 0.6, 0.8]
FAST_MAX = [1, 1.4, 1.8]

WERE_SLOW_WARNING = [0.2, 0.3, 0.4]
WERE_SLOW_MAX = [0.7, 0.9, 1.1]
WERE_FAST_WARNING = [0.6, 0.7, 0.9]
WERE_FAST_MAX = [1.1, 1.5, 2.0]

ZOMBIE_WARNING = [0.5, 0.6, 0.8]
ZOMBIE_MAX = [0.8, 1, 1.4]


def get_move(serial, move_num):
    time.sleep(0.02)
    move = psmove.PSMove(move_num)
    time.sleep(0.05)
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

class Games(Enum):
    JoustFFA = 0
    JoustTeams = 1
    JoustRandomTeams = 2
    Traitor = 3
    WereJoust = 4
    Zombies = 5
    Commander = 6
    Swapper = 7
    Tournament = 8
    Ninja = 9
    Random = 10

minimum_players = {
    Games.JoustFFA.value: 2,
    Games.JoustTeams.value: 3,
    Games.JoustRandomTeams.value: 3,
    Games.Traitor.value: 6,
    Games.WereJoust.value: 3,
    Games.Zombies.value: 4,
    Games.Commander.value: 4,
    Games.Swapper.value: 3,
    Games.Tournament.value: 3,
    Games.Ninja.value: 2,
    Games.Random.value: 2
}

game_mode_names = {
    Games.JoustFFA.value: 'Joust Free-for-All',
    Games.JoustTeams.value: 'Joust Teams',
    Games.JoustRandomTeams.value: 'Joust Random Teams',
    Games.Traitor.value: 'Traitors',
    Games.WereJoust.value: 'Werewolves',
    Games.Zombies.value: 'Zombies',
    Games.Commander.value: 'Commander',
    Games.Swapper.value: 'Swapper',
    Games.Tournament.value: 'Tournament',
    Games.Ninja.value: 'Ninja Bomb',
    Games.Random.value: 'Random'
}

REQUIRED_SETTINGS = [
'play_audio',
'move_can_be_admin',
'enforce_minimum',
'sensitivity',
'play_instructions',
'con_games'
]

class Buttons(Enum):
    middle = 524288
    start = 2048
    select = 256
    circle = 32
    nothing = 0

battery_levels = {
    0: "Dead",
    1: "Low",
    2: "25%",
    3: "50%",
    4: "75%",
    5: "100%",
    238: "Charging",
    239: "Charged"
}