import time
import psmove
import numpy
import random
from oustpair import Oustpair
from oustaudioblock import Oustaudioblock
from multiprocessing import Process, Value, Array
import psutil, os

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

def team_colors():
    global HSV, colour_range, controller_colours, team_colors
    HSV = [(x*1.0/6.0, 1, 1) for x in range(6)]
    colour_range = [[int(x) for x in hsv_to_rgb(*colour)] for colour in HSV]
    team_colors = [colour_range[i] for i in range(6)]


def change_team(move):
    global HSV, colour_range, controller_teams, team_colors
    if move.get_serial() in controller_teams:
        if controller_teams[move.get_serial()][1] == True:
            controller_teams[move.get_serial()][0] = (controller_teams[move.get_serial()][0] + 1) % 6
            controller_teams[move.get_serial()][1] = False
    else:
        controller_teams[move.get_serial()] = [0, True]

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
    print 'asdekljasgfjasdas' + str(controllers_alive.keys()[0])
    team_to_check = controller_teams[controllers_alive.keys()[0]][0]
    print 'first con is' + str(team_to_check)
    #team_to_check = controller_teams[first_con][0]
    for con in controllers_alive:
        if controller_teams[con][0] != team_to_check:
            return -1
    return team_to_check


controllers_alive = {}
controller_teams = {}

team_colors()
paired_controllers = []
moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
#controller_teams = {move.get_serial(): [0, True] for move in moves}
controller_teams = {}

audio = Oustaudioblock()
pair = Oustpair()


# The current speed of the music
speed = 1.5

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

def track_controller(mov_array, dead, place):
    proc = psutil.Process(os.getpid())
    proc.nice(-3)
    print 'THE NEW NICE IS ' + str(proc.nice())
    moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
    move_list = []
    for move in mov_array:
        for real_move in moves:
            if move.get_serial() == real_move.get_serial():
                move_list.append(real_move)
                print 'we just appened ' + str(real_move.get_serial())
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

                    speed_percent = (speed - slow_speed)/(fast_speed - slow_speed)                    
                    warning = lerp(slow_warning, fast_warning, speed_percent)
                    threshold =  lerp(slow_max, fast_max, speed_percent)

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
                        move.set_leds(255,0,0)
                        #move.set_leds(*controller_colours[move.get_serial()])
                        move.set_rumble(0)
                        move.update_leds()

                move.update_leds()
                move_last_values[i]  = total



def FFA():
    global controllers_alive, audio, moves, controller_colours
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

    controller_status = {}
    processes = []
    print 'start loop'
    moves_to_add = []
    dead_array = [Value('i', 1) for i in range(len(controllers_alive))]
    addup = 0

    for serial, move in controllers_alive.items():
        moves_to_add.append(move)
        if len(moves_to_add) == 4:
            
            for i, move in enumerate(moves_to_add):
                controller_status[move.get_serial()] = dead_array[addup + i]
            p = Process(target=track_controller, args=(moves_to_add, dead_array, addup))
            p.start()
            processes.append(p)
            addup += 4
            moves_to_add = []
            
    if len(moves_to_add) > 0:
        for i, move in enumerate(moves_to_add):
            controller_status[move.get_serial()] = dead_array[addup + i]
        p = Process(target=track_controller, args=(moves_to_add, dead_array, addup))
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

        for serial, dead in controller_status.items():
            #print 'testprint ' + str(serial) + " " + str(dead.value)
            if dead.value == 0:
                print str(controllers_alive)
                del controllers_alive[serial]
                del controller_status[serial]

        if len(controllers_alive) <= 1:
            for proc in processes:
                proc.terminate()
                proc.join()

            print "WIN", serial
            print 'THE THING IS ' + str(controllers_alive)
            HSV = [(x*1.0/50, 0.9, 1) for x in range(50)]
            colour_range = [[int(x) for x in hsv_to_rgb(*colour)] for colour in HSV]

            serial, move = controllers_alive.items()[0]
            pause_time = time.time() + 3
            while time.time() < pause_time:
                move.set_leds(*colour_range[0])
                colour_range.append(colour_range.pop(0))
                #for othermove in moves:
                #    othermove.set_rumble(100)
                 #   othermove.poll()
                #    othermove.update_leds()
                move.update_leds()
                time.sleep(0.01)

            running = False
            controllers_alive = {}
            audio.stop_audio()


        if running:
            # If a controller vanishes during the game, remove it from the game
            # to allow others to finish
            if psmove.count_connected() != len(moves):
                moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
                available = [ move.get_serial() for move in moves]

                for serial, move in controllers_alive.items():
                    if serial not in available:
                        del controllers_alive[serial]


def Teams():
    global controllers_alive, audio, moves, controller_teams
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
        move.set_leds(*team_colors[controller_teams[serial][0]])
        #move.set_leds(*controller_colours[move.get_serial()])

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

                # Win animation / reset
                        team_win = check_team_win()
                        if team_win != -1:
                            print "WIN", serial

                            HSV = [(x*1.0/50, 0.9, 1) for x in range(50)]
                            colour_range = [[int(x) for x in hsv_to_rgb(*colour)] for colour in HSV]

                            
                            pause_time = time.time() + 3
                            while time.time() < pause_time:
                                for win_move in moves:
                                    if win_move.get_serial() in controller_teams:
                                        print 'the winner is ' + win_move.get_serial()
                                        if controller_teams[win_move.get_serial()][0] == team_win:
                                            win_move.set_leds(*colour_range[0])
                                            colour_range.append(colour_range.pop(0))
                                            win_move.update_leds()
                                        else:
                                            win_move.set_rumble(100)
                                            win_move.poll()
                                            win_move.update_leds()
                                    time.sleep(0.01)

                            running = False
                            controllers_alive = {}
                            audio.stop_audio()
                            break

                    
                    
                    # Warn
                    elif change > warning:
                        scaled = [int(v*0.3) for v in team_colors[controller_teams[serial][0]]]
                        move.set_leds(*scaled)
                        move.set_rumble(120)

                    # Reset
                    else:
                        move.set_leds(*team_colors[controller_teams[serial][0]])
                        move.set_rumble(0)

                move.update_leds()
                move_last_values[serial] = total

		#audio.audio_buffer_loop(1.0)

        if running:
            # If a controller vanishes during the game, remove it from the game
            # to allow others to finish
            if psmove.count_connected() != len(moves):
                moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
                available = [ move.get_serial() for move in moves]

                for serial, move in controllers_alive.items():
                    if serial not in available:
                        del controllers_alive[serial]


while True:
    start_ffa = False
    start_teams = False
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
                        print 'WE JUST PULLED' + str(move.get_serial())

                if move.get_serial() in controllers_alive:
                    if move.get_serial() not in controller_teams:
                        move.set_leds(255,255,255)
                    else:
                        move.set_leds(*team_colors[controller_teams[move.get_serial()][0]])
                else:
                    move.set_leds(0,0,0)

                if move.get_buttons() == 0:
                    if move.get_serial() in controller_teams:
                        controller_teams[move.get_serial()][1] = True                

                # Triangle starts the game early
                if move.get_buttons() == 524288:
                    change_team(move)

                # Triangle starts the game early
                if move.get_buttons() == 16:
                    start_ffa = True

                #print move.get_buttons()
                # Triangle starts the game early
                if move.get_buttons() == 128:
                    start_teams = True

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
        #if (len(controllers_alive) == len(moves) and len(controllers_alive) > 0):
        #    break


        # Someone hit triangle
        if (len(controllers_alive) >= 2 and start_ffa == True):
            FFA() 
            break

        if (len(controllers_alive) >= 2 and start_teams == True):
            check = True
            for move in controllers_alive:
                if move not in controller_teams:
                    check = False
            if check:
                Teams()
                break
            else:
                break

