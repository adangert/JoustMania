import enum
import psmove
import time
import random

SETTINGSFILE = 'joustsettings.yaml'

#Human speeds[slow, mid, fast]
SLOW_WARNING = [0.1, 0.15, 0.28]
SLOW_MAX = [0.25, 0.8, 1]
FAST_WARNING = [0.5, 0.6, 0.8]
FAST_MAX = [1, 1.4, 1.8]

#SLOW_WARNING = [0.1, 0.15, 0.28]
#SLOW_MAX = [0.5, 0.8, 1]
#FAST_WARNING = [0.5, 0.6, 0.8]
#FAST_MAX = [1, 1.4, 1.8]

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

class Games(enum.Enum):
    JoustFFA = (0, 'Joust Free-for-All', 2)
    JoustTeams = (1, 'Joust Teams', 3)
    JoustRandomTeams = (2, 'Joust Random Teams', 3)
    Traitor = (3, 'Traitors', 6)
    WereJoust = (4, 'Werewolves', 3)
    Zombies = (5, 'Zombies', 4)
    Commander = (6, 'Commander', 4)
    Swapper = (7, 'Swapper', 3)
    Tournament = (8, 'Tournament', 3)
    Ninja = (9, 'Ninja Bomb', 2)
    Random = (10, 'Random', 2)


    def __new__(cls, value, pretty_name, min_players):
        """This odd constructor lets us keep Foo.value as an integer, but also
           add some extra properties to each option."""
        obj = object.__new__(cls)
        obj._value_ = value
        obj.pretty_name = pretty_name
        obj.minimum_players = min_players
        return obj

    def next(self):
        """Return the next game mode after this one in the list. Wraps around after hitting bottom."""
        return Games((self.value + 1) % len(Games))

#These buttons are based off of
#The mapping of PS Move controllers
class Button(enum.Flag):
    NONE     = 0

    TRIANGLE = psmove.Btn_TRIANGLE
    CIRCLE   = psmove.Btn_CIRCLE
    CROSS    = psmove.Btn_CROSS
    SQUARE   = psmove.Btn_SQUARE

    SELECT   = psmove.Btn_SELECT
    START    = psmove.Btn_START

    SYNC     = psmove.Btn_PS
    MIDDLE   = psmove.Btn_MOVE
    TRIGGER  = psmove.Btn_T

    SHAPES   = TRIANGLE | CIRCLE | CROSS | SQUARE

battery_levels = {
    psmove.Batt_MIN:           "Low",
    psmove.Batt_20Percent:     "20%",
    psmove.Batt_40Percent:     "40%",
    psmove.Batt_60Percent:     "60%",
    psmove.Batt_80Percent:     "80%",
    psmove.Batt_MAX:           "100%",
    psmove.Batt_CHARGING:      "Charging",
    psmove.Batt_CHARGING_DONE: "Charged",
}

# Common colors lifted from https://xkcd.com/color/rgb/
# TODO: Add more colors -- probably need to have 14 player colors at least.
class Color(enum.Enum):
    BLACK =      0x000000
    WHITE =      0xffffff
    RED =        0xff0000

    GREEN =      0x00ff00
    BLUE =       0x0000ff
    YELLOW =     0xffff14
    PURPLE =     0x7e1e9c
    ORANGE =     0xf97306
    PINK =       0xff81c0
    TURQUOISE =  0x06c2ac
    BROWN =      0x653700

    def rgb_bytes(self):
        v = self.value
        return  v >> 16, (v >> 8) & 0xff, v & 0xff

# Red is reserved for warnings/knockouts.
PLAYER_COLORS = [ c for c in Color if c not in (Color.RED, Color.WHITE, Color.BLACK) ]

REQUIRED_SETTINGS = [
'play_audio',
'move_can_be_admin',
'enforce_minimum',
'sensitivity',
'play_instructions',
'random_modes',
'color_lock',
'color_lock_choices',
'red_on_kill',
'random_teams'
]
