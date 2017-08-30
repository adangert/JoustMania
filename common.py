import psmove
import colorsys
import time
from enum import Enum
import random

color_range = 255

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

def hsv2rgb(h, s, v):
    return tuple(int(color * color_range) for color in colorsys.hsv_to_rgb(h, s, v))

def generate_colors(color_num):
    Hue = [ ((num + 1.0)/color_num, 1, 1) for num in range(color_num) ]
    colors = [ hsv2rgb(*hsv_color) for hsv_color in Hue ]
    return colors

def generate_team_colors(num_teams):
	if num_teams == 2:
		team1 = random.choice(color_list)
		team2 = random.choice(dual_teams[team1])
		return [team1,team2]
	elif num_teams == 3:
		team1 = random.choice(color_list)
		team2 = random.choice(tri_teams[team1])
		allowed = [tri_teams[team1],tri_teams[team2]]
		team3_allowed = list(set([x for sublist in allowed for x in sublist]))
		team3 = random.choice(team3_allowed)
		return [team1,team2,team3]
	elif num_teams == 4:
		team_a = random.choice([Colors.Orange,Colors.Yellow])
		team_b = random.choice([Colors.Purple,Colors.Pink,Colors.Magenta])
		teams = [Colors.Green,Colors.Blue,team_a,team_b]
		random.shuffle(teams)
		return teams
	elif num_teams in [5,6,7,8]:
		return = [five_colors,six_colors,seven_colors,eight_colors][numteams-5]
	elif num_teams > 8:
		#we're in FFA territory now
		remaining = eight_colors
		teams = eight_colors
		for i in range(7,num_teams):
			next_team = random.choice(remaining)
			remaining.remove(next_team)
			teams.append(next_team)
			if remaining == []:
				remaning = eight_colors
		random.shuffle(teams)
		return teams



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

def change_color(color_array, r, g, b):
    color_array[0] = r
    color_array[1] = g
    color_array[2] = b

class Colors(Enum):
	Pink = (255,96,96)
	Magenta = (255,0,192)
	Orange = (255,64,0)
	Yellow = (255,255,0)
	Green = (0,255,0)
	Turquoise = (0,255,255)
	Blue = (0,0,255)
	Purple = (96,0,255)

color_list = [x for x in Colors]

#pick one color, then pick among
dual_teams = {
	Colors.Pink : [Colors.Yellow,Colors.Green,Colors.Turquoise,Colors.Blue],
	Colors.Magenta : [Colors.Yellow,Colors.Green,Colors.Turquoise,Colors.Blue],
	Colors.Orange : [Colors.Green,Colors.Turquoise,Colors.Blue,Colors.Purple],
	Colors.Yellow : [Colors.Turquoise,Colors.Blue,Colors.Purple,Colors.Pink,Colors.Magenta],
	Colors.Green : [Colors.Purple,Colors.Pink,Colors.Magenta,Colors.Orange],
	Colors.Turquoise : [Colors.Purple,Colors.Pink,Colors.Magenta,Colors.Orange,Colors.Yellow],
	Colors.Blue : [Colors.Pink,Colors.Magenta,Colors.Orange,Colors.Yellow],
	Colors.Purple :  [Colors.Orange,Colors.Yellow,Colors.Green,Colors.Turquoise]
}

#remove pairings from dual_teams that don't have a shared third color
#pick two colors like dual_team, then pick third shared between those two
tri_teams = {
	Colors.Pink : [Colors.Yellow,Colors.Turquoise,Colors.Blue],
	Colors.Magenta : [Colors.Yellow,Colors.Turquoise,Colors.Blue],
	Colors.Orange : [Colors.Green,Colors.Turquoise,Colors.Purple],
	Colors.Yellow : [Colors.Turquoise,Colors.Blue,Colors.Purple,Colors.Pink,Colors.Magenta],
	Colors.Green : [Colors.Purple,Colors.Orange],
	Colors.Turquoise : [Colors.Purple,Colors.Pink,Colors.Magenta,Colors.Orange,Colors.Yellow],
	Colors.Blue : [Colors.Pink,Colors.Magenta,Colors.Yellow],
	Colors.Purple :  [Colors.Orange,Colors.Yellow,Colors.Green,Colors.Turquoise]
}

"""
quad_teams - generated above, here's how
all groups have green and blue, one of orange/yellow, one of pink/magenta/purple
"""

#at this point just force colors
five_colors = [Colors.Orange,Colors.Yellow,Colors.Green,Colors.Blue,Colors.Purple]
six_colors = [Colors.Magenta,Colors.Orange,Colors.Yellow,Colors.Green,Colors.Blue,Colors.Purple]
seven_colors = [x for x in Colors if x not Colors.Pink]
eight_colors = [x for x in Colors]

multi_colors = [five_colors,six_colors,seven_colors,eight_colors]



#included in case I need them later
class ExtraColors(Enum):
	White = (255,255,255)
	Red = (255,0,0)
	SplatoonGreen = (255,50,120)
	SplatoonPink = (30,220,0)


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

class Buttons(Enum):
    middle = 524288
    start = 2048
    select = 256
    circle = 32
    nothing = 0

battery_levels = {
    0: "Low",
    1: "20%",
    2: "40%",
    3: "60%",
    4: "80%",
    5: "100%",
    238: "Charging",
    239: "Charged"
}