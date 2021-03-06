import common, colors
import psmove
import time
import psutil, os
import random
import numpy
import json
from piaudio import Audio
from enum import Enum
from multiprocessing import Process, Value, Array, Queue
from math import sqrt


# How fast/slow the music can go
SLOW_MUSIC_SPEED = 1.5
#this was 0.5
FAST_MUSIC_SPEED = 0.5

# The min and max timeframe in seconds for
# the speed change to trigger, randomly selected
MIN_MUSIC_FAST_TIME = 4
MAX_MUSIC_FAST_TIME = 8
MIN_MUSIC_SLOW_TIME = 10
MAX_MUSIC_SLOW_TIME = 23


#How long the speed change takes
INTERVAL_CHANGE = 1.5

#How long the winning moves shall sparkle
END_GAME_PAUSE = 6
KILL_GAME_PAUSE = 4


class Opts(Enum):
    alive = 0
    selection = 1
    holding = 2
    team = 3
    is_commander = 4

class Selections(Enum):
    nothing = 0
    a_button = 1
    trigger = 2
    triangle = 3

class Holding(Enum):
    not_holding = 0
    holding = 1

class Bool(Enum):
    no = 0
    yes = 1

#TODO: remove
#red blue
#team_colors = [(255,0,0),(0,0,255)]

#class Team(Enum):
#    red = 1
#    blue = 0


def calculate_flash_time(r,g,b, score):
    flash_percent = max(min(float(score)+0.2,1.0),0.0)
    #val_percent = (val-(flash_speed/2))/(flash_speed/2)
    new_r = int(common.lerp(255, r, flash_percent))
    new_g = int(common.lerp(255, g, flash_percent))
    new_b = int(common.lerp(255, b, flash_percent))
    return (new_r, new_g, new_b)

def track_move(move, team, num_teams, team_colors, dead_move, force_color, music_speed, move_opts, restart, menu, controller_sensitivity):
    start = False
    no_rumble = time.time() + 1
    move_last_value = None
    #keep on looping while move is not dead
    ready = False
    move.set_leds(*colors.Colors.Black.value)
    move.update_leds()
    time.sleep(1)
    vibrate = False
    vibration_time = time.time() + 1
    flash_lights = True
    flash_lights_timer = 0
    change = 0
    
    SLOW_MAX = controller_sensitivity[0]
    SLOW_WARNING = controller_sensitivity[1]
    FAST_MAX = controller_sensitivity[2]
    FAST_WARNING = controller_sensitivity[3] 

    death_time = 2
    time_of_death = time.time()
    move_opts[Opts.holding.value] = Holding.not_holding.value
    move_opts[Opts.selection.value] = Selections.nothing.value

    while True:
        if(menu.value == 1 or restart.value == 1):
            return
        if sum(force_color) != 0:
            no_rumble_time = time.time() + 5
            time.sleep(0.01)
            move.set_leds(*force_color)
            move.update_leds()
            move.set_rumble(0)
            no_rumble = time.time() + 0.5
        #if we are not dead
        elif dead_move.value == 1:
            if move.poll():

                ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
                total = sqrt(sum([ax**2, ay**2, az**2]))
                change = (change * 4 + total)/5
                
                warning = SLOW_WARNING
                threshold = SLOW_MAX


                if vibrate:
                    flash_lights_timer += 1
                    if flash_lights_timer > 7:
                        flash_lights_timer = 0
                        flash_lights = not flash_lights
                    if flash_lights:
                        move.set_leds(*colors.Colors.White60.value)
                    else:
                        if(team.value == 0):
                            
                            move.set_leds(team_colors[0],team_colors[1],team_colors[2])
                        else:
                            move.set_leds(team_colors[3],team_colors[4],team_colors[5])
                    if time.time() < vibration_time - 0.22:
                        move.set_rumble(110)
                    else:
                        move.set_rumble(0)
                    if time.time() > vibration_time:
                        vibrate = False
                else:
                    if(team.value == 0):
                        
                        move.set_leds(team_colors[0],team_colors[1],team_colors[2])
                    else:
                        move.set_leds(team_colors[3],team_colors[4],team_colors[5])


                if change > threshold:
                    if time.time() > no_rumble:
                        #vibrate = False
                        move.set_leds(*colors.Colors.Black.value)
                        move.set_rumble(90)
                        dead_move.value = 0
                        time_of_death = time.time()

                elif change > warning and not vibrate:
                    if time.time() > no_rumble:
                        vibrate = True
                        vibration_time = time.time() + 0.5
                        move.set_leds(20,50,100)
                #else:
                #    move.set_rumble(0)
                    

                    
            move.update_leds()
        #if we are dead
        elif dead_move.value <= 0:
            move.set_leds(*colors.Colors.Black.value)
            
            if time.time() - time_of_death >= death_time:
                dead_move.value = 3
        elif dead_move.value == 3:
                move_last_value = None
                dead_move.value = 1
                no_rumble = time.time() + 1
                team.value = (team.value + 1) % num_teams
            

class Swapper():
    def __init__(self, moves, command_queue, ns, music, controller_colors, dead_moves, music_speed, force_move_colors, controller_opts, controller_teams, restart):

        self.command_queue = command_queue
        self.ns = ns
        self.voice = self.ns.settings['menu_voice']
        #save locally in case settings change from web
        self.play_audio = self.ns.settings['play_audio']
        self.sensitivity = self.ns.settings['sensitivity']
        self.color_lock = self.ns.settings['color_lock']
        self.color_lock_choices = self.ns.settings['color_lock_choices']
        self.random_teams = self.ns.settings['random_teams']
        
        self.move_serials = moves
        self.tracked_moves = {}
        self.dead_moves = dead_moves
        self.teams = controller_teams
        self.music_speed = music_speed
        self.music_speed.value = 1
        self.running = True
        self.force_move_colors = force_move_colors
        self.num_teams = 2
        self.restart = restart

        self.start_timer = time.time()
        self.audio_cue = 0

        self.move_opts = controller_opts

        self.update_time = 0

        self.team_colors = colors.generate_team_colors(self.num_teams,self.color_lock,self.color_lock_choices)
        self.controller_colors = controller_colors
        self.controller_colors[0] = self.team_colors[0].value[0]
        self.controller_colors[1] = self.team_colors[0].value[1]
        self.controller_colors[2] = self.team_colors[0].value[2]
        
        self.controller_colors[3] = self.team_colors[1].value[0]
        self.controller_colors[4] = self.team_colors[1].value[1]
        self.controller_colors[5] = self.team_colors[1].value[2]

        self.generate_random_teams(self.num_teams)

        if self.play_audio:

            self.start_beep = Audio('audio/Joust/sounds/start.wav')
            self.start_game = Audio('audio/Joust/sounds/start3.wav')
            self.explosion = Audio('audio/Joust/sounds/Explosion34.wav')
            fast_resample = False
            end = False
            try:
                self.audio = music
            except:
                print('no audio loaded')

        self.change_time = time.time() + 8
        self.speed_up = True
        self.currently_changing = False
        self.game_end = False
        self.winning_moves = []
        self.game_loop()

    def generate_random_teams(self, num_teams):
        if self.random_teams == False:
            players_per_team = (len(self.move_serials)//num_teams)+1
            team_num = [x for x in range(num_teams)]*players_per_team
            for num,move in zip(team_num,self.move_serials):
                self.teams[move].value = num# = Value('i',num)
        else:
            team_pick = list(range(num_teams))
            for serial in self.move_serials:
                self.teams[serial].value = random.choice(team_pick) # = random_choice
                team_pick.remove(self.teams[serial].value)
                if not team_pick:
                    team_pick = list(range(num_teams))

    def track_moves(self):
        for move_num, move_serial in enumerate(self.move_serials):
            self.dead_moves[move_serial].value = 1
            for i in range(3):
                self.force_move_colors[move_serial][i] = 1
            for i in range(5):
                self.move_opts[move_serial][i]=0
            
    def change_all_move_colors(self, r, g, b):
        for color in self.force_move_colors.values():
            colors.change_color(color, r, g, b)

    #need to do the count_down here
    def count_down(self):
        self.change_all_move_colors(80, 0, 0)
        if self.play_audio:
            self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(70, 100, 0)
        if self.play_audio:
            self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(0, 70, 0)
        if self.play_audio:
            self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(0, 0, 0)
        if self.play_audio:
            self.start_game.start_effect()

    def check_end_game(self):
        self.winning_team = -100
        team_win = True
        
        for move_serial, dead in self.dead_moves.items():
            if self.winning_team == -100:
                self.winning_team = self.teams[move_serial].value
            if self.teams[move_serial].value != self.winning_team:
                team_win = False
                #TODO: This wont work if the last move is the first of the dead_moves
                self.last_move = move_serial
            if dead.value == 0:
                #This is to play the sound effect
                dead.value = -1
                if self.play_audio:
                    self.explosion.start_effect()
        self.game_end = team_win


    def stop_tracking_moves(self):
        self.restart.value = 1

    def end_game(self):
        if self.play_audio:
            try:
                self.audio.stop_audio()
            except:
                print('no audio loaded to stop')
        end_time = time.time() + END_GAME_PAUSE
        h_value = 0
        self.update_status('ending',self.winning_team)
        if self.play_audio:
            self.end_game_sound(self.winning_team)
        while (time.time() < end_time):
            time.sleep(0.01)
            win_color = colors.hsv2rgb(h_value, 1, 1)
            for win_move in self.move_serials:
                if win_move != self.last_move:
                    win_color_array = self.force_move_colors[win_move]
                    colors.change_color(win_color_array, *win_color)
                else:
                    win_color_array = self.force_move_colors[win_move]
                    colors.change_color(win_color_array, 1,1,1)
            h_value = (h_value + 0.01)
            if h_value >= 1:
                h_value = 0
        self.running = False

    def end_game_sound(self, winning_team):
        win_team_name = self.team_colors[winning_team].name
        if win_team_name == 'Pink':
            if self.voice == 'aaron':
                os.popen('espeak -ven -p 70 -a 200 "And the winner is ...Pink Team')
            else:
                team_win = Audio('audio/Joust/vox/' + self.voice + '/pink team win.wav')
        if win_team_name == 'Magenta':
            team_win = Audio('audio/Joust/vox/' + self.voice + '/magenta team win.wav')
        if win_team_name == 'Orange':
            if self.voice == 'aaron':
                os.popen('espeak -ven -p 70 -a 200 "And the winner is ...Orange Team')
            else:
                team_win = Audio('audio/Joust/vox/' + self.voice + '/orange team win.wav')
        if win_team_name == 'Yellow':
            team_win = Audio('audio/Joust/vox/' + self.voice + '/yellow team win.wav')
        if win_team_name == 'Green':
            team_win = Audio('audio/Joust/vox/' + self.voice + '/green team win.wav')
        if win_team_name == 'Turquoise':
            team_win = Audio('audio/Joust/vox/' + self.voice + '/cyan team win.wav')
        if win_team_name == 'Blue':
            team_win = Audio('audio/Joust/vox/' + self.voice + '/blue team win.wav')
        if win_team_name == 'Purple':
            if self.voice == 'aaron':
                os.popen('espeak -ven -p 70 -a 200 "And the winner is ...Purple Team')
            else:
                team_win = Audio('audio/Joust/vox/' + self.voice + '/purple team win.wav')
        team_win.start_effect()

    def game_loop(self):
        self.track_moves()
        self.restart.value = 0
        self.count_down()
        if self.play_audio:
            try:
                self.audio.start_audio_loop()
            except:
                print('no audio loaded to start')
        while self.running:
            #I think the loop is so fast that this causes 
            #a crash if done every loop
            if time.time() - 0.1 > self.update_time:
                self.update_time = time.time()
                self.check_command_queue()
                self.update_status('in_game')

            self.check_end_game()
            if self.game_end:
                self.end_game()

        self.stop_tracking_moves()

    def check_command_queue(self):
        package = None
        while not(self.command_queue.empty()):
            package = self.command_queue.get()
            command = package['command']
        if not(package == None):
            if command == 'killgame':
                self.kill_game()

    def kill_game(self):
        if self.play_audio:
            try:
                self.audio.stop_audio()
            except:
                print('no audio loaded to stop')        
        self.update_status('killed')
        all_moves = [x for x in self.dead_moves.keys()]
        end_time = time.time() + KILL_GAME_PAUSE     
        
        bright = 255
        while (time.time() < end_time):
            time.sleep(0.01)
            color = (bright,0,0)
            for move in all_moves:
                color_array = self.force_move_colors[move]
                colors.change_color(color_array, *color)
            bright = bright - 1
            if bright < 10:
                bright = 10
        self.running = False

    def update_status(self,game_status,winning_team=-1):
        data ={'game_status' : game_status,
               'game_mode' : 'Swapper',
               'winning_team' : winning_team}
        team_total = [0,0]
        team_alive = [0,0]
        for move in self.move_serials:
            team = self.teams[move].value
            team_total[team] += 1
            if self.dead_moves[move].value == 1:
                team_alive[team] += 1
        team_comp = list(zip(team_total,team_alive))
        data['team_comp'] = team_comp
        data['team_names'] = [color.name + ' Team' for color in self.team_colors]

        self.ns.status = data
                    
            
