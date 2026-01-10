from enum import Enum

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

quad_teams_banned = {
    Colors.Pink : [Colors.Magenta,Colors.Purple],
    Colors.Magenta : [Colors.Pink,Colors.Purple],
    Colors.Orange : [Colors.Yellow],
    Colors.Yellow : [Colors.Orange],
    Colors.Green : [Colors.Turquoise],
    Colors.Turquoise : [Colors.Green,Colors.Blue],
    Colors.Blue : [Colors.Turquoise],
    Colors.Purple :  [Colors.Magenta,Colors.Pink]
}

for a,b,c,d in [(a,b,c,d) for a in range(8) for b in range(a+1,8) for c in range(b+1,8) for d in range(c+1,8)]:
    quad = [color_list[x] for x in (a,b,c,d)]
    
    quad_banned = [quad_teams_banned[i] for i in quad]
    quad_banned = list(set([i for sublist in quad_banned for i in sublist]))
    bad = False
    for color in quad:
        if color in quad_banned:
            bad = True
    if not bad:
        print(quad)

