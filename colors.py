import psmove
import colorsys
import time
from enum import Enum
import random


color_range = 255

def hsv2rgb(h, s, v):
    return tuple(int(color * color_range) for color in colorsys.hsv_to_rgb(h, s, v))

def generate_colors(color_num):
    Hue = [ ((num + 1.0)/color_num, 1, 1) for num in range(color_num) ]
    colors = [ hsv2rgb(*hsv_color) for hsv_color in Hue ]
    return colors

def generate_team_colors(num_teams, color_lock=False, color_lock_choices=None):
    if color_lock and color_lock_choices != None and num_teams in [2,3,4]:
        temp_colors = color_lock_choices[num_teams]
        return [Colors[c] for c in temp_colors]

    if num_teams == 1:
        #only Werewolf, and it's ignored anyway, but let's prevent errors, eh?
        return [random.choice(team_color_list)]
    if num_teams == 2:
        team1 = random.choice(team_color_list)
        team2 = random.choice(dual_teams[team1])
        return [team1,team2]
    elif num_teams == 3:
        team1 = random.choice(team_color_list)
        team2 = random.choice(tri_teams[team1])
        allowed = tri_teams[team1] + tri_teams[team2]
        team3_allowed = [x for x in allowed if x in tri_teams[team1] and x in tri_teams[team2]]
        team3 = random.choice(team3_allowed)
        return [team1,team2,team3]
    elif num_teams == 4:
        team_a = random.choice([Colors.Orange,Colors.Yellow])
        team_b = random.choice([Colors.Purple,Colors.Pink,Colors.Magenta])
        teams = [Colors.Green,Colors.Blue,team_a,team_b]
        random.shuffle(teams)
        return teams
    elif num_teams > 4:
        #set colors, we're in FFA territory now
        sets_needed = (num_teams//8)+1
        teams = ordered_color_list*sets_needed
        teams = teams[:num_teams]
        return teams

def change_color(color_array, r, g, b):
    color_array[0] = r
    color_array[1] = g
    color_array[2] = b

class Colors(Enum):
    #first 8 are team colors
    Pink = (255,108,108)
    Magenta = (255,0,192)
    Orange = (255,64,0)
    Yellow = (255,255,0)
    Green = (0,255,0)
    Turquoise = (0,255,255)
    Blue = (0,0,255)
    Purple = (96,0,255)
    #these are used for various things
    White = (255,255,255)
    White80 = (200,200,200)
    White60 = (150,150,150)
    White40 = (100,100,100)
    White20 = (50,50,50)
    Red = (255,0,0)
    Red60 = (150,0,0)
    Red80 = (200,0,0)
    Green80 = (0,200,0)
    Blue40 = (0,0,100)
    LimeGreen = (100,255,0)
    Zombie = (50,150,50)
    Black = (0,0,0)
    #stay fresh
    SplatoonGreen = (255,50,120)
    SplatoonPink = (30,220,0)

team_color_list = [x for x in Colors][0:8]
ordered_color_list = [Colors.Blue,Colors.Yellow,Colors.Green,Colors.Orange,Colors.Purple,
    Colors.Magenta,Colors.Turquoise,Colors.Pink]

#pick one color, then pick among the colors not near the first
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