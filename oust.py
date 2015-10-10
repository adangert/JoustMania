import time
import psmove
import numpy
import random
from oustpair import Oustpair
from oustaudioblock import Oustaudioblock

# This nightmarish function was taken from stackoverflow
def hsv_to_rgb(h, s, v):
    if s == 0.0: v*=255; return [v, v, v]
    i = int(h*6.)
    f = (h*6.)-i; p,q,t = int(255*(v*(1.-s))), int(255*(v*(1.-s*f))), int(255*(v*(1.-s*(1.-f)))); v*=255; i%=6
    if i == 0: return [v, t, p]
    if i == 1: return [q, v, p]
    if i == 2: return [p, v, t]
    if i == 3: return [p, q, v]
    if i == 4: return [t, p, v]
    if i == 5: return [v, p, q]

HSV = colour_range = []
controller_colours = {}

def regenerate_colours():
    global HSV, colour_range, controller_colours
    HSV = [(x*1.0/len(moves), 1, 1) for x in range(len(moves))]
    colour_range = [[int(x) for x in hsv_to_rgb(*colour)] for colour in HSV]
    controller_colours = {move.get_serial(): colour_range[i] for i, move in enumerate(moves)}


def sleep_controllers(sleep=0.5, leds=(255,255,255), rumble=0, moves=[]):
    pause_time = time.time() + sleep
    while time.time() < pause_time:
        for othermove in moves:
            othermove.poll()
            othermove.set_rumble(rumble)
            othermove.set_leds(*leds)
            othermove.update_leds()

def music_speed_up(event_time):
    if time.time() - event_time < 2:
        audio.change_ratio(1.0-((time.time() - event_time)/3))
    else:
        event_time += 15
    return event_time

def lerp(a, b, p):
    return a*(1 - p) + b*p

paired_controllers = []
moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
controllers_alive = {}
audio = Oustaudioblock()
pair = Oustpair()

# The current speed of the music
speed = 1.5

# How fast/slow the music can go
slow_speed = 1.5
fast_speed = 0.3

# The min and max timeframe in seconds for
# the speed change to trigger, randomly selected
min_fast = 4
max_fast = 8
min_slow = 10
max_slow = 23

#How long the speed change takes
change_time = 1.5

#Sensitivity of the contollers
slow_max = 0.7
slow_warning = 0.28
fast_max = 1.5
fast_warning = 0.8 

while True:
    start = False

    while True:
        for move in moves:
            if move.this == None:
                print "Move initialisation failed, reinitialising"
                moves = []
                break

            # If a controller is plugged in over USB, pair it and turn it white
            # This appears to occasionally kernel panic raspbian!
            if move.connection_type == psmove.Conn_USB:
                if move.get_serial() not in paired_controllers:
                    pair.equal_pair(move)
                    paired_controllers.append(move.get_serial())

                move.set_leds(255,255,255)
                move.update_leds()
                continue

            if move.poll():
                # If the trigger is pulled, join the game
                if move.get_serial() not in controllers_alive:
                    if move.get_trigger() > 100:
                        controllers_alive[move.get_serial()] = move

                if move.get_serial() in controllers_alive:
                    move.set_leds(255,255,255)
                else:
                    move.set_leds(0,0,0)

                # Triangle starts the game early
                if move.get_buttons() == 16:
                    start = True

                # Circle shows battery level
                if move.get_buttons() == 32:
                    battery = move.get_battery()

                    if battery == 5: # 100% - green
                        move.set_leds(0, 255, 0)
                    elif battery == 4: # 80% - green-ish
                        move.set_leds(128, 200, 0)
                    elif battery == 3: # 60% - yellow
                        move.set_leds(255, 255, 0)
                    else: # <= 40% - red
                        move.set_leds(255, 0, 0)

                move.set_rumble(0)
                move.update_leds()

        # If we've got more/less moves, register them
        if psmove.count_connected() != len(moves):
            moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]

        # Everyone's in
        if (len(controllers_alive) == len(moves) and len(controllers_alive) > 0):
            break
        # Someone hit triangle
        if (len(controllers_alive) >= 2 and start == True):
            break

    print "GAME START"
    regenerate_colours()

    alive = controllers_alive.values()

    # White
    sleep_controllers(sleep=0.5, leds=(255,255,255), rumble=0, moves=alive)
    # White/rumble
    sleep_controllers(sleep=0.3, leds=(255,255,255), rumble=100, moves=alive)
    # Red/norumble
    sleep_controllers(sleep=0.75, leds=(50,0,0), rumble=0, moves=alive)
    # Yellow
    sleep_controllers(sleep=0.75, leds=(50,75,0), rumble=0, moves=alive)
    # Green
    sleep_controllers(sleep=0.75, leds=(0,50,0), rumble=0, moves=alive)

    # Individual colours
    for serial, move in controllers_alive.items():
        move.set_leds(*controller_colours[move.get_serial()])

    move_last_values = {}

    running = True

    audio.load_audio('audio/music/classical.wav')
    audio.start_audio()
    slow = True
    fast = False



    added_time = random.uniform(min_slow, max_slow)
    event_time = time.time() + added_time 
    change_speed = False
    speed = 1.5
    audio.change_ratio(speed)


    while running:
        
        if time.time() > event_time and slow and not change_speed:
            slow = False
            fast = True
            change_speed = True

        elif time.time() > event_time and fast and not change_speed:
            slow = True
            fast = False
            change_speed = True

        if fast and speed > fast_speed and change_speed:
            percent = numpy.clip((time.time() - event_time)/change_time, 0, 1)
            speed = lerp(slow_speed, fast_speed, percent)
            audio.change_ratio(speed)
        elif fast and speed <= fast_speed and change_speed:
            added_time = random.uniform(min_fast, max_fast)
            event_time = time.time() + added_time
            change_speed = False

        if slow and speed < slow_speed and change_speed:
            percent = numpy.clip((time.time() - event_time)/change_time, 0, 1)
            speed = lerp(fast_speed, slow_speed, percent)
            audio.change_ratio(speed)
        elif slow and speed >= slow_speed and change_speed:
            added_time = random.uniform(min_slow, max_slow)
            event_time = time.time() + added_time
            change_speed = False

        for serial, move in controllers_alive.items():

            if move.poll():
                ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
                total = sum([ax, ay, az])
                if serial in move_last_values:
                    change = abs(move_last_values[serial] - total)
                    # Dead

                    speed_percent = (speed - slow_speed)/(fast_speed - slow_speed)                    
		    warning = lerp(slow_warning, fast_warning, speed_percent)
                    threshold =  lerp(slow_max, fast_max, speed_percent)

                    if change > threshold:
                        print "DEAD", serial
                        move.set_leds(0,0,0)
                        move.set_rumble(90)
                        del controllers_alive[serial]
                    
                    
                    # Warn
                    elif change > warning:
                        scaled = [int(v*0.3) for v in controller_colours[move.get_serial()]]
                        move.set_leds(*scaled)
                        move.set_rumble(120)

                    # Reset
                    else:
                        move.set_leds(*controller_colours[move.get_serial()])
                        move.set_rumble(0)

                move.update_leds()
                move_last_values[serial] = total

		#audio.audio_buffer_loop(1.0)

                # Win animation / reset
                if len(controllers_alive) == 1:
                    print "WIN", serial

                    HSV = [(x*1.0/50, 0.9, 1) for x in range(50)]
                    colour_range = [[int(x) for x in hsv_to_rgb(*colour)] for colour in HSV]

                    serial, move = controllers_alive.items()[0]
                    pause_time = time.time() + 3
                    while time.time() < pause_time:
                        move.set_leds(*colour_range[0])
                        colour_range.append(colour_range.pop(0))
                        for othermove in moves:
                            othermove.set_rumble(100)
                            othermove.poll()
                            othermove.update_leds()
                        time.sleep(0.01)

                    running = False
                    controllers_alive = {}
                    audio.stop_audio()
                    break


        if running:
            # If a controller vanishes during the game, remove it from the game
            # to allow others to finish
            if psmove.count_connected() != len(moves):
                moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
                available = [ move.get_serial() for move in moves]

                for serial, move in controllers_alive.items():
                    if serial not in available:
                        del controllers_alive[serial]
