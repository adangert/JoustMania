#!/home/pi/JoustMania/venv/bin/python3.6

import asyncio
import psmove
import player
import piparty
import math


# Continually prints sensor readings from the first controller found.

def FormatVec(v, places=5):
    fmt = '{:%d.2f}' % places
    return ', '.join([ fmt.format(e) for e in v ])
def VecLen(v):
    return math.sqrt(sum([ e*e for e in v ]))
def Normalize(v):
    m = VecLen(v)
    return tuple([ e / m for e in v ])

async def Loop(plr):
    print("Acceleration                      Jerk                                       Gyro")
    while True:
        for event in plr.get_events():
            if event.type != player.EventType.SENSOR:
                continue
            print('\r|%s| = %+.02f    |%s| = %+7.02f      |%s| = %+2.02f'  % (
                FormatVec(event.acceleration),
                event.acceleration_magnitude,
                FormatVec(event.jerk, 7),
                event.jerk_magnitude,
                FormatVec(event.gyroscope),
                VecLen(event.gyroscope)), end='')

        await asyncio.sleep(1/30)


def Main():
    piparty.Menu.enable_bt_scanning()
    move = psmove.PSMove(0)
    move.enable_orientation(True)
    p1 = player.Player(move)
    asyncio.get_event_loop().run_until_complete(Loop(p1))

if __name__ == '__main__':
    Main()
