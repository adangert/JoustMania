import asyncio
from enum import Enum, Flag
import functools
import psmove
import time
import traceback
import logging

logger = logging.getLogger(__name__)

SETTINGSFILE = 'joustsettings.yaml'

def get_move(serial, move_num):
    time.sleep(0.02)
    move = psmove.PSMove(move_num)
    time.sleep(0.05)
    if move.get_serial() != serial:
        for move_num in range(psmove.count_connected()):
            move = psmove.PSMove(move_num)
            if move.get_serial() == serial:
                print("returning " +str(move.get_serial()))
                return move
        return None
    else:
        return move

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
    UPDATE   = SELECT | START

all_shapes = [Button.TRIANGLE, Button.CIRCLE, Button.CROSS, Button.SQUARE]

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

# Red is reserved for warnings/knockouts.
PLAYER_COLORS = [ c for c in Color if c not in (Color.RED, Color.WHITE, Color.BLACK) ]

def async_print_exceptions(f):
    """Wraps a coroutine to print exceptions (other than cancellations)."""
    @functools.wraps(f)
    async def wrapper(*args, **kwargs):
        try:
            await f(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except:
            traceback.print_exc()
            raise
    return wrapper

# Represents a pace the game is played at, encapsulating the tempo of the music as well
# as controller sensitivity.
class GamePace:
    __slots__ = ['tempo', 'warn_threshold', 'death_threshold']
    def __init__(self, tempo, warn_threshold, death_threshold):
        self.tempo = tempo
        self.warn_threshold = warn_threshold
        self.death_threshold = death_threshold

    def __str__(self):
        return '<GamePace tempo=%s, warn=%s, death=%s>' % (self.tempo, self.warn_threshold, self.death_threshold)

# TODO: These are placeholder values.
# We can't take the values from joust.py, since those are compared to the sum of the
# three accelerometer dimensions, whereas we compute the magnitude of the acceleration
# vector.
SLOW_PACE = GamePace(tempo=0.4, warn_threshold=2, death_threshold=4)
MEDIUM_PACE = GamePace(tempo=1.0, warn_threshold=3, death_threshold=5)
FAST_PACE = GamePace(tempo=1.5, warn_threshold=5, death_threshold=9)
FREEZE_PACE = GamePace(tempo=0, warn_threshold=1.1, death_threshold=1.2)

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
