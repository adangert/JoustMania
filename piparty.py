import time
import psmove
import numpy
import random
from oustpair import Oustpair
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

#TODO: This function needs to manage the controller
#TIPLE TUPLE FOR ALL OPTIONS?

#OPTS:
#0. ON OFF
#1. BUTTON SELECTION
#2. HOLDING BUTTON
#3. TEAM
#4. GAME MODE

#BUTTONS:
#1. start game
#2. change game

#GAME MODES:
#0. FFA
#1. TEAMS
def track_controller(move_copy, opts):
    global team_colors
    move = None
    for move_num in range(psmove.count_connected()):
        move = psmove.PSMove(move_num)
        if move.get_serial() == move_copy.get_serial():
            break
    while True:
        if move.poll():
            if opts[4] == 0:
                #print 'ops is 0'
                move.set_leds(255,255,255)
            elif opts[4] == 1:
                #print 'ops is 1'
                move.set_leds(*team_colors[opts[3]])

            if move.get_buttons() == 0:
                opts[2] = 0

            # middle button changes team
            if move.get_buttons() == 524288:
                if (opts[4] == 1 and opts[2] == 0):
                    opts[2] = 1
                    opts[3] = (opts[3]+1)%6

            # start button starts the game
            if move.get_buttons() == 2048:
                if(opts[2] == 0):
                    opts[2] = 1
                    opts[1] = 1

            # select button changes game type
            if move.get_buttons() == 256:

                if(opts[2] == 0):
                    opts[2] = 1
                    opts[1] = 2

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

 
def start():
    global moves, controllers_alive, current_game
    while True:
        start_game = False
        controller_procs = []
        controller_opts = {}
        #controllers = []
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
                        #Need a triple tuple for controller options

                    move.set_leds(255,255,255)
                    move.update_leds()
                    continue
                
                # If the trigger is pulled, join the game
                if move.get_serial() not in controllers_alive:
                    if move.poll():
                        if move.get_trigger() > 100:
                            controllers_alive[move.get_serial()] = move

                            opts = Array('i', [0] * 5)
                            p = Process(target=track_controller, args=(move, opts))
                            p.start()
                            controller_procs.append(p)
                            controller_opts[move.get_serial()] = opts

            for key, opt in controller_opts.iteritems():
                if opt[1] == 2:
                    if (current_game == Games.JoustFFA):
                        current_game = Games.JoustTeams
                    elif (current_game == Games.JoustTeams):
                        current_game = Games.JoustFFA
                    opt[1] = 0
                if opt[1] == 1:
                    start_game = True
                    opt[1] = 0
                if (current_game == Games.JoustFFA):
                    opt[4] = 0
                elif (current_game == Games.JoustTeams):
                    opt[4] = 1

            # If we've got more/less moves, register them
            if psmove.count_connected() != len(moves):
                moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]

            #TODO: controllers_alive doesn't have all controllers after some have been
            #added mid game, need to look into this
            #TODO: need to remove multi-processed controllers before game starts
            # Someone hit triangle
            if (len(controllers_alive) >= 2 and start_game == True):
                print 'start_game is ' + str(start_game)
                for move_serial in controllers_alive:
                    #TODO: need better solution for this
                    #TODO: THIS NEED TO BE UPDATED
                    #TODO: NO SAVED STATE BETWEEN GAMES
                    controller_teams[move_serial] = controller_opts[move_serial]
                for proc in controller_procs:
                    proc.terminate()
                    proc.join()
                if (current_game == Games.JoustFFA):
                    joust.Joust(controllers_alive, controller_colours)
                    controllers_alive = {}
                    break

                if (current_game == Games.JoustTeams):
                    check = True
                    for move in controllers_alive:
                        if move not in controller_teams:
                            check = False
                    if check:
                        joust.Joust(controllers_alive, controller_colours,
                                    team_cols=team_colors, cont_teams=controller_teams, teams=True)
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
