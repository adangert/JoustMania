import time
import psmove

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
        for move in moves:
            othermove.poll()
            othermove.set_rumble(rumble)
            othermove.set_leds(*leds)
            othermove.update_leds()


paired_controllers = []
moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
controllers_alive = {}

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
                    move.pair()
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
    while running:

        for serial, move in controllers_alive.items():

            if move.poll():
                ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
                total = sum([ax, ay, az])

                if serial in move_last_values:
                    change = abs(move_last_values[serial] - total)
                    # Dead
                    if change > 0.7:
                        print "DEAD", serial
                        move.set_leds(0,0,0)
                        move.set_rumble(100)
                        del controllers_alive[serial]
                    
                    # Warn
                    elif change > 0.2:
                        scaled = [int(v*0.3) for v in controller_colours[move.get_serial()]]
                        move.set_leds(*scaled)

                    # Reset
                    else:
                        move.set_leds(*controller_colours[move.get_serial()])
                        move.set_rumble(0)

                move.update_leds()
                move_last_values[serial] = total

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
