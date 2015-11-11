import time
import psmove
import numpy
import random
from oustpair import Oustpair
from oustaudioblock import Oustaudioblock
from multiprocessing import Process, Value, Array
from enum import Enum
import psutil, os
import joust
import common


# This module should only be for selecting game modes/options for the game/starting a game
# and pairing controllers
# The selection needs to be made into multiprocessing for 10+ controllers



def regenerate_colours():
    global HSV, colour_range, controller_colours
    HSV = [(x*1.0/len(moves), 1, 1) for x in range(len(moves))]
    colour_range = [[int(x) for x in common.hsv_to_rgb(*colour)] for colour in HSV]
    controller_colours = {move.get_serial(): colour_range[i] for i, move in enumerate(moves)}

def team_colors():
    global HSV, colour_range, controller_colours, team_colors
    HSV = [(x*1.0/6.0, 1, 1) for x in range(6)]
    colour_range = [[int(x) for x in common.hsv_to_rgb(*colour)] for colour in HSV]
    team_colors = [colour_range[i] for i in range(6)]

# TODO: INSTEAD OF TAKING IN GLOBAL, TAKE IN VARS AND RETURN THE CONTROLLER TEAMS
def change_team(move):
    global HSV, colour_range, controller_teams, team_colors
    if move.get_serial() in controller_teams:
        if controller_teams[move.get_serial()][1] == True:
            controller_teams[move.get_serial()][0] = (controller_teams[move.get_serial()][0] + 1) % 6
            controller_teams[move.get_serial()][1] = False
    else:
        controller_teams[move.get_serial()] = [0, True]

 
def start():
    global moves, controllers_alive
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

                    # middle button changes team
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


            #TODO: controllers_alive doesn't have all controllers after some have been
            #added mid game, need to look into this
            # Someone hit triangle
            if (len(controllers_alive) >= 2 and start_ffa == True):
                joust.Joust(controllers_alive, controller_colours)
                controllers_alive = {}
                break

            if (len(controllers_alive) >= 2 and start_teams == True):
                check = True
                for move in controllers_alive:
                    if move not in controller_teams:
                        check = False
                if check:
                    joust.Joust(controllers_alive, controller_colours, teams=True)
                    controllers_alive = {}
                    break
                else:
                    break


if __name__ == "__main__":
    moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
    #controller_teams = {move.get_serial(): [0, True] for move in moves}
    controller_teams = {}
    pair = Oustpair()

    Games = Enum('JoustFFA', 'JoustTeams')
    current_game = Games.JoustFFA

    controllers_alive = {}

    controller_colours = {}
    team_colors()
    regenerate_colours()
    start()
