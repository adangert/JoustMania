import time
import psmove
import numpy
import random
from oustpair import Oustpair
from oustaudioblock import Oustaudioblock
from multiprocessing import Process, Value, Array
import psutil, os
import common


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

def check_team_win():
    global controllers_alive, controller_teams
    team_to_check = controller_teams[controllers_alive.keys()[0]][0]
    for con in controllers_alive:
        if controller_teams[con][0] != team_to_check:
            return -1
    return team_to_check


#These will need to be passed in from PiParty
HSV = colour_range = []
controller_colours = {}

controllers_alive = {}
controller_teams = {}


paired_controllers = []


audio = Oustaudioblock()


# How fast/slow the music can go
slow_speed = 1.5
fast_speed = 0.5

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

#SHOULD THIS FILE HAVE TEAM SELECTION?
#OR SHOULD THERE BE ANOTHER MODULE FOR ALL OF THAT?

def track_controller(mov_array, dead, place, teams, speed):
    global controller_colors, team_colors, controller_teams
    proc = psutil.Process(os.getpid())
    proc.nice(-3)
    moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
    move_list = []
    for move in mov_array:
        for real_move in moves:
            if move.get_serial() == real_move.get_serial():
                move_list.append(real_move)
    move_last_values = []
    for i in range(len(moves)):
        move_last_values.append(None)
    while True:
        for i in range(len(mov_array)):
            move = move_list[i]
            if dead[place + i].value == 1 and move.poll():
                ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
                total = sum([ax, ay, az])
                if move_last_values[i] is not None:
                    change = abs(move_last_values[i] - total)
                    # Dead

                    speed_percent = (speed.value - slow_speed)/(fast_speed - slow_speed)
                    warning = lerp(slow_warning, fast_warning, speed_percent)
                    threshold = lerp(slow_max, fast_max, speed_percent)

                    if change > threshold:
                        print "DEAD", move.get_serial()
                        move.set_leds(0,0,0)
                        move.set_rumble(90)
                        #del controllers_alive[serial]
                        dead[place + i].value = 0

                    # Warn
                    elif change > warning:
                        #scaled = [int(v*0.3) for v in controller_colours[move.get_serial()]]
                        #move.set_leds(*scaled)
                        move.set_leds(20,50,100)
                        move.set_rumble(110)
                        move.update_leds()

                    # Reset
                    else:
                        #print str(moves[i].get_leds())
                        #move.set_leds(255,0,0)
                        if not teams:
                            move.set_leds(*controller_colours[move.get_serial()])
                        else:
                            move.set_leds(*team_colors[controller_teams[move.get_serial()][0]])
                        move.set_rumble(0)
                        move.update_leds()

                move.update_leds()
                move_last_values[i]  = total


def Joust(cont_alive, cont_colors, teams=False):
    global controllers_alive, audio, moves, controller_colours
    print "GAME START"

    
    controllers_alive = cont_alive
    controller_colours = cont_colors

    print str(controller_colours)
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
        print 'serial is ' + str(serial) + 'move is ' + str(move)
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
    speed = Value('d', 1.5)
    audio.change_ratio(speed.value)

    controller_status = {}
    processes = []
    print 'start loop'
    moves_to_add = []
    dead_array = [Value('i', 1) for i in range(len(controllers_alive))]
    addup = 0

    #This probably should have it's own function to multi-process controllers
    for serial, move in controllers_alive.items():
        moves_to_add.append(move)
        if len(moves_to_add) == 4:

            for i, move in enumerate(moves_to_add):
                controller_status[move.get_serial()] = dead_array[addup + i]
            p = Process(target=track_controller, args=(moves_to_add, dead_array, addup, teams, speed))
            p.start()
            processes.append(p)
            addup += 4
            moves_to_add = []

    if len(moves_to_add) > 0:
        for i, move in enumerate(moves_to_add):
            controller_status[move.get_serial()] = dead_array[addup + i]
        p = Process(target=track_controller, args=(moves_to_add, dead_array, addup, teams, speed))
        p.start()
        processes.append(p)

    while running:
        if time.time() > event_time and slow and not change_speed:
            slow = False
            fast = True
            change_speed = True

        elif time.time() > event_time and fast and not change_speed:
            slow = True
            fast = False
            change_speed = True

        if fast and speed.value > fast_speed and change_speed:
            percent = numpy.clip((time.time() - event_time)/change_time, 0, 1)
            speed.value = lerp(slow_speed, fast_speed, percent)
            audio.change_ratio(speed.value)
        elif fast and speed.value <= fast_speed and change_speed:
            added_time = random.uniform(min_fast, max_fast)
            event_time = time.time() + added_time
            change_speed = False

        if slow and speed.value < slow_speed and change_speed:
            percent = numpy.clip((time.time() - event_time)/change_time, 0, 1)
            speed.value = lerp(fast_speed, slow_speed, percent)
            audio.change_ratio(speed.value)
        elif slow and speed.value >= slow_speed and change_speed:
            added_time = random.uniform(min_slow, max_slow)
            event_time = time.time() + added_time
            change_speed = False

        for serial, dead in controller_status.items():
            #print 'testprint ' + str(serial) + " " + str(dead.value)
            if dead.value == 0:
                print str(controllers_alive)
                del controllers_alive[serial]
                del controller_status[serial]

        if teams:
            team_win = check_team_win()
        if (not teams and len(controllers_alive) <= 1) or (teams and team_win != -1):
            for proc in processes:
                #May need to just finish the loop in the tracker()
                proc.terminate()
                proc.join()

            print "WIN", serial
            HSV = [(x*1.0/50, 0.9, 1) for x in range(50)]
            colour_range = [[int(x) for x in common.hsv_to_rgb(*colour)] for colour in HSV]
            pause_time = time.time() + 3
            if not teams:
                serial, move = controllers_alive.items()[0]
                while time.time() < pause_time:
                    move.set_leds(*colour_range[0])
                    colour_range.append(colour_range.pop(0))
                #for othermove in moves:
                #    othermove.set_rumble(100)
                 #   othermove.poll()
                #    othermove.update_leds()
                    move.update_leds()
                    time.sleep(0.01)
            else:
                while time.time() < pause_time:
                    for win_move in moves:
                        if win_move.get_serial() in controller_teams:
                            if controller_teams[win_move.get_serial()][0] == team_win:
                                #print 'the winner is ' + win_move.get_serial()
                                win_move.set_leds(*colour_range[0])
                                colour_range.append(colour_range.pop(0))
                                win_move.update_leds()
                            else:
                                win_move.set_rumble(100)
                                win_move.poll()
                                win_move.set_leds(0, 0, 0)
                                win_move.update_leds()
                    time.sleep(0.01)

            running = False
            controllers_alive = {}
            audio.stop_audio()

        # TODO: THIS WONT WORK, AND NEEDS TO BE ADDED TO THE MULTIPROCCESSING TRACKERS
        #if running:
            # If a controller vanishes during the game, remove it from the game
            # to allow others to finish
            # This needs to be put in the tracking()
         #   if psmove.count_connected() != len(moves):
         #       moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
         #       available = [ move.get_serial() for move in moves]

          #      for serial, move in controllers_alive.items():
           #         if serial not in available:
            #            del controllers_alive[serial]
