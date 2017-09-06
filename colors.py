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

def generate_team_colors(num_teams):
    if num_teams == 1:
        #only Werewolf, and it's ignored anyway, but let's prevent errors, eh?
        return [random.choice(color_list)]
    if num_teams == 2:
        team1 = random.choice(color_list)
        team2 = random.choice(dual_teams[team1])
        return [team1,team2]
    elif num_teams == 3:
        team1 = random.choice(color_list)
        team2 = random.choice(tri_teams[team1])
        allowed = tri_teams[team1] + tri_teams[team2]
        team3_allowed = [x for x in allowed if x in tri_teams[team1] and x in tri_teams[team2]]
        team3 = random.choice(team3_allowed)
        return [team1,team2,team3]
    elif num_teams == 4:
        team_a = random.choice([TeamColors.Orange,TeamColors.Yellow])
        team_b = random.choice([TeamColors.Purple,TeamColors.Pink,TeamColors.Magenta])
        teams = [TeamColors.Green,TeamColors.Blue,team_a,team_b]
        random.shuffle(teams)
        return teams
    elif num_teams in [5,6,7,8]:
        teams =  [five_colors,six_colors,seven_colors,eight_colors][num_teams-5]
        random.shuffle(teams)
        return teams
    elif num_teams > 8:
        #we're in FFA territory now
        remaining = eight_colors[:]
        teams = eight_colors[:]
        for i in range(7,num_teams):
            next_team = random.choice(remaining)
            remaining.remove(next_team)
            teams.append(next_team)
            if remaining == []:
                remaining = eight_colors[:]
        random.shuffle(teams)
        return teams

def change_color(color_array, r, g, b):
    color_array[0] = r
    color_array[1] = g
    color_array[2] = b

class TeamColors(Enum):
    Pink = (255,96,96)
    Magenta = (255,0,192)
    Orange = (255,64,0)
    Yellow = (255,255,0)
    Green = (0,255,0)
    Turquoise = (0,255,255)
    Blue = (0,0,255)
    Purple = (96,0,255)

#included in case I need them later
class ExtraColors(Enum):
    White = (255,255,255)
    White80 = (200,200,200)
    Red = (255,0,0)
    Red60 = (150,0,0)
    Red80 = (200,0,0)
    Green80 = (0,200,0)
    LimeGreen = (100,255,0)
    Zombie = (50,150,50)
    Black = (0,0,0)
    #stay fresh
    SplatoonGreen = (255,50,120)
    SplatoonPink = (30,220,0)

color_list = [x for x in TeamColors]

#pick one color, then pick among the colors not near the first
dual_teams = {
    TeamColors.Pink : [TeamColors.Yellow,TeamColors.Green,TeamColors.Turquoise,TeamColors.Blue],
    TeamColors.Magenta : [TeamColors.Yellow,TeamColors.Green,TeamColors.Turquoise,TeamColors.Blue],
    TeamColors.Orange : [TeamColors.Green,TeamColors.Turquoise,TeamColors.Blue,TeamColors.Purple],
    TeamColors.Yellow : [TeamColors.Turquoise,TeamColors.Blue,TeamColors.Purple,TeamColors.Pink,TeamColors.Magenta],
    TeamColors.Green : [TeamColors.Purple,TeamColors.Pink,TeamColors.Magenta,TeamColors.Orange],
    TeamColors.Turquoise : [TeamColors.Purple,TeamColors.Pink,TeamColors.Magenta,TeamColors.Orange,TeamColors.Yellow],
    TeamColors.Blue : [TeamColors.Pink,TeamColors.Magenta,TeamColors.Orange,TeamColors.Yellow],
    TeamColors.Purple :  [TeamColors.Orange,TeamColors.Yellow,TeamColors.Green,TeamColors.Turquoise]
}

#remove pairings from dual_teams that don't have a shared third color
#pick two colors like dual_team, then pick third shared between those two
tri_teams = {
    TeamColors.Pink : [TeamColors.Yellow,TeamColors.Turquoise,TeamColors.Blue],
    TeamColors.Magenta : [TeamColors.Yellow,TeamColors.Turquoise,TeamColors.Blue],
    TeamColors.Orange : [TeamColors.Green,TeamColors.Turquoise,TeamColors.Purple],
    TeamColors.Yellow : [TeamColors.Turquoise,TeamColors.Blue,TeamColors.Purple,TeamColors.Pink,TeamColors.Magenta],
    TeamColors.Green : [TeamColors.Purple,TeamColors.Orange],
    TeamColors.Turquoise : [TeamColors.Purple,TeamColors.Pink,TeamColors.Magenta,TeamColors.Orange,TeamColors.Yellow],
    TeamColors.Blue : [TeamColors.Pink,TeamColors.Magenta,TeamColors.Yellow],
    TeamColors.Purple :  [TeamColors.Orange,TeamColors.Yellow,TeamColors.Green,TeamColors.Turquoise]
}

"""
quad_teams - generated above, here's how
all groups have green and blue, one of orange/yellow, one of pink/magenta/purple
"""

#at this point just force colors
five_colors = [TeamColors.Orange,TeamColors.Yellow,TeamColors.Green,TeamColors.Blue,TeamColors.Purple]
six_colors = [TeamColors.Magenta,TeamColors.Orange,TeamColors.Yellow,TeamColors.Green,TeamColors.Blue,TeamColors.Purple]
seven_colors = [x for x in TeamColors if x != TeamColors.Pink]
eight_colors = [x for x in TeamColors]

multi_colors = [five_colors,six_colors,seven_colors,eight_colors]