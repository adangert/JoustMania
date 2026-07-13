from enum import Enum, Flag, IntEnum
import psmoveapi
import time
import logging

logger = logging.getLogger(__name__)

SETTINGSFILE = 'joustsettings.yaml'

def lerp(a, b, p):
    return a * (1 - p) + b * p

class Games(Enum):
    JoustFFA = (0, 'Joust Free-for-All', 2)
    JoustTeams = (1, 'Joust Teams', 3)
    JoustRandomTeams = (2, 'Joust Random Teams', 3)
    Traitor = (3, 'Traitors', 4)
    Werewolf = (4, 'Werewolf', 3)
    Zombies = (5, 'Zombies', 4)
    Commander = (6, 'Commander', 4)
    Swapper = (7, 'Swapper', 3)
    FightClub = (8, 'Fight Club', 2)
    Tournament = (9, 'Tournament', 3)
    NonStop = (10, 'Non Stop Joust', 2)
    Ninja = (11, 'Ninja Bomb', 2)
    Random = (12, 'Random', 2)

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
        
    def previous(self):
        """Return the previous game mode after this one in the list. Wraps around after hitting bottom."""
        return Games((self.value - 1) % len(Games))
    
    def find(self, str_name):
        for game in Games:
            if game.pretty_name == str_name:
                return game
        
class Status(Enum):
    ALIVE =     0 # Tracking move and can be killed
    DIED =      1 # Just died, will move to dead
    DEAD =      2 # Dead, will revive if enabled
    REVIVED =   3 # Just revived and will play sound
    RUMBLE =    4 # Will rumble
    ON =        5 # Team color and not polling
    OFF =       6 # Black and not polling


# All common opts will be 0-5, custom opts should be 6+
class Opts(Enum):
    BUTTON = 0 # Buttons that are currently pressed TODO - Not being used
    HOLDING = 1 # Whether buttons are being held
    SELECTION = 2 # What those buttons represent for this game
    STATUS = 3 # Status of the move

# Sensitivity levels
class Sensitivity(Enum):
    ULTRA_SLOW = 0
    SLOW = 1
    MID = 2
    FAST = 3
    ULTRA_FAST = 4

def get_game_name(value):
    for game in Games:
        if game.value == value:
            return game.pretty_name
    return None

#These buttons are based off of
#The mapping of PS Move controllers
class Button(Flag):
    NONE     = 0

    TRIANGLE = psmoveapi.Button.TRIANGLE
    CIRCLE   = psmoveapi.Button.CIRCLE
    CROSS    = psmoveapi.Button.CROSS
    SQUARE   = psmoveapi.Button.SQUARE

    SELECT   = psmoveapi.Button.SELECT
    START    = psmoveapi.Button.START

    SYNC     = psmoveapi.Button.PS
    MIDDLE   = psmoveapi.Button.MOVE
    TRIGGER  = psmoveapi.Button.T

    SHAPES   = TRIANGLE | CIRCLE | CROSS | SQUARE
    UPDATE   = SELECT | START

all_shapes = [Button.TRIANGLE, Button.CIRCLE, Button.CROSS, Button.SQUARE]


class Battery(IntEnum):
    """Battery values defined by the upstream PSMove API C interface."""

    MIN = 0x00
    PERCENT_20 = 0x01
    PERCENT_40 = 0x02
    PERCENT_60 = 0x03
    PERCENT_80 = 0x04
    MAX = 0x05
    CHARGING = 0xEE
    CHARGED = 0xEF

battery_levels = {
    Battery.MIN:           "Low",
    Battery.PERCENT_20:    "20%",
    Battery.PERCENT_40:    "40%",
    Battery.PERCENT_60:    "60%",
    Battery.PERCENT_80:    "80%",
    Battery.MAX:           "100%",
    Battery.CHARGING:      "Charging",
    Battery.CHARGED:       "Charged",
}

# Common colors lifted from https://xkcd.com/color/rgb/
# TODO: Add more colors -- probably need to have 14 player colors at least.
class Color(Enum):
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

REQUIRED_SETTINGS = [
    'play_audio',
    'move_can_be_admin',
    'current_game',
    'enforce_minimum',
    'sensitivity',
    'play_instructions',
    'random_modes',
    'color_lock',
    'color_lock_choices',
    'red_on_kill',
    'random_teams',
    'menu_voice',
    'random_team_size',
    'force_all_start',
]
