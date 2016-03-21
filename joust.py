import common
import psmove
import time
import psutil, os
import random
import numpy
from piaudio import Audio
from enum import Enum
from multiprocessing import Process, Value, Array


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

#Sensitivity of the contollers
SLOW_MAX = 1
SLOW_WARNING = 0.28
FAST_MAX = 1.8
FAST_WARNING = 0.8

#How long the speed change takes
INTERVAL_CHANGE = 1.5

#How long the winning moves shall sparkle
END_GAME_PAUSE = 4


def track_move(move_serial, move_num, game_mode, team, team_num, dead_move, force_color, music_speed, werewolf_reveal):
    #proc = psutil.Process(os.getpid())
    #proc.nice(3)
    #explosion = Audio('audio/Joust/sounds/Explosion34.wav')
    #explosion.start_effect()
    start = False
    no_rumble = time.time() + 1
    move_last_value = None
    move = common.get_move(move_serial, move_num)
    team_colors = common.generate_colors(team_num)
    werewolf = False
    if team < 0:
        team = (team + 1) * -1
        werewolf = True
    #keep on looping while move is not dead
    while True:
        if sum(force_color) != 0:
            no_rumble_time = time.time() + 5
            time.sleep(0.01)
            move.set_leds(*force_color)
            move.update_leds()
            if sum(force_color) > 75:
                if werewolf:
                    move.set_rumble(80)
            else:
                move.set_rumble(0)
            no_rumble = time.time() + 0.5
        elif dead_move.value == 1 and werewolf_reveal.value > 0:   
            if move.poll():
                ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
                total = sum([ax, ay, az])
                if move_last_value is not None:
                    change = abs(move_last_value - total)
                    speed_percent = (music_speed.value - SLOW_MUSIC_SPEED)/(FAST_MUSIC_SPEED - SLOW_MUSIC_SPEED)
                    warning = common.lerp(SLOW_WARNING, FAST_WARNING, speed_percent)
                    threshold = common.lerp(SLOW_MAX, FAST_MAX, speed_percent)

                    if change > threshold:
                        if time.time() > no_rumble:
                            move.set_leds(0,0,0)
                            move.set_rumble(90)
                            dead_move.value = 0

                    elif change > warning:
                        if time.time() > no_rumble:
                            move.set_leds(20,50,100)
                            move.set_rumble(110)

                    else:
                        if game_mode == common.Games.WereJoust.value:
                            if werewolf_reveal.value == 2 and werewolf:
                                move.set_leds(255,0,0)
                            else:
                                move.set_leds(100,100,100)
                        else:
                            move.set_leds(*team_colors[team])
                        move.set_rumble(0)
                        
                move_last_value = total
            move.update_leds()
            

class Joust():
    def __init__(self, game_mode, moves, teams):

        self.move_serials = moves
        self.game_mode = game_mode
        self.tracked_moves = {}
        self.dead_moves = {}
        self.music_speed = Value('d', 1.5)
        self.running = True
        self.force_move_colors = {}
        self.teams = teams
        self.team_num = 6
        self.game_mode = game_mode
        self.werewolf_timer = 35
        self.start_timer = time.time()
        self.audio_cue = 0
        self.werewolf_reveal = Value('i', 2)
        if game_mode == common.Games.JoustFFA.value:
            self.team_num = len(moves)
        if game_mode == common.Games.JoustRandomTeams.value:
            #this should be 3 for smaller number of controllers
            self.team_num = 4
        if game_mode == common.Games.WereJoust.value:
            self.werewolf_reveal.value = 0
            self.team_num = 1
        if game_mode != common.Games.JoustTeams.value:
            self.generate_random_teams(self.team_num)

        if game_mode == common.Games.WereJoust.value:
            #were_num = int((len(moves)+2)/4)
            were_num = int((len(moves)*3)/8)
            if were_num <= 0:
                were_num = 1
            self.choose_werewolf(were_num)

        music = 'audio/Joust/music/' + random.choice(os.listdir('audio/Joust/music'))
        self.start_beep = Audio('audio/Joust/sounds/start.wav')
        self.start_game = Audio('audio/Joust/sounds/start3.wav')
        self.explosion = Audio('audio/Joust/sounds/Explosion34.wav')
        fast_resample = False
        end = False
        self.audio = Audio(music, end)
        #self.change_time = self.get_change_time(speed_up = True)
        self.change_time = time.time() + 8
        self.speed_up = True
        self.currently_changing = False
        self.game_end = False
        self.winning_moves = []
        
        
        self.game_loop()

    def choose_werewolf(self, were_num):
        for were in range(were_num):
            werewolf = random.choice(self.move_serials)
            while self.teams[werewolf] < 0:
                werewolf = random.choice(self.move_serials)
            self.teams[werewolf] = (self.teams[werewolf] * -1) - 1

    def generate_random_teams(self, team_num):
        print ('about to generate teams')
        team_pick = list(range(team_num))
        print (str(team_pick))
        for serial in self.move_serials:
            print ('doin serial ' + str(serial))
            random_choice = random.choice(team_pick)
            self.teams[serial] = random_choice
            print ('removing it')
            team_pick.remove(random_choice)
            if not team_pick:
                team_pick = list(range(team_num))

    def track_moves(self):
        print ('starting track moves')
        print ('move serials is ' + str(self.move_serials))
        for move_num, move_serial in enumerate(self.move_serials):
            
            time.sleep(0.02)
            dead_move = Value('i', 1)
            force_color = Array('i', [1] * 3)
            proc = Process(target=track_move, args=(move_serial,
                                                    move_num,
                                                    self.game_mode,
                                                    self.teams[move_serial],
                                                    self.team_num,
                                                    dead_move,
                                                    force_color,
                                                    self.music_speed,
                                                    self.werewolf_reveal))
            proc.start()
            self.tracked_moves[move_serial] = proc
            self.dead_moves[move_serial] = dead_move
            self.force_move_colors[move_serial] = force_color
            
    def change_all_move_colors(self, r, g, b):
        for color in self.force_move_colors.values():
            common.change_color(color, r, g, b)

    #need to do the count_down here
    def count_down(self):
        self.change_all_move_colors(80, 0, 0)
        self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(70, 100, 0)
        self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(0, 70, 0)
        self.start_beep.start_effect()
        time.sleep(0.75)
        self.change_all_move_colors(0, 0, 0)
        self.start_game.start_effect()
        
    def get_change_time(self, speed_up):
        if speed_up:
            added_time = random.uniform(MIN_MUSIC_FAST_TIME, MAX_MUSIC_FAST_TIME)
        else:
            added_time = random.uniform(MIN_MUSIC_SLOW_TIME, MAX_MUSIC_SLOW_TIME)
        return time.time() + added_time

    def change_music_speed(self, fast):
        change_percent = numpy.clip((time.time() - self.change_time)/INTERVAL_CHANGE, 0, 1)
        if fast:
            self.music_speed.value = common.lerp(FAST_MUSIC_SPEED, SLOW_MUSIC_SPEED, change_percent)
        elif not fast:
            self.music_speed.value = common.lerp(SLOW_MUSIC_SPEED, FAST_MUSIC_SPEED, change_percent)
        self.audio.change_ratio(self.music_speed.value)

    def check_music_speed(self):
        if time.time() > self.change_time and time.time() < self.change_time + INTERVAL_CHANGE:
            self.change_music_speed(self.speed_up)
            self.currently_changing = True
            self.audio.change_chunk_size(True)
        elif time.time() >= self.change_time + INTERVAL_CHANGE and self.currently_changing:
            self.music_speed.value = SLOW_MUSIC_SPEED if self.speed_up else FAST_MUSIC_SPEED
            self.speed_up =  not self.speed_up
            self.change_time = self.get_change_time(speed_up = self.speed_up)
            self.audio.change_ratio(self.music_speed.value)
            self.currently_changing = False
            self.audio.change_chunk_size(False)

    def get_real_team(self, team):
        if team < 0:
            return -1
        else:
            return team

    def reveal(self):
        self.werewolf_reveal.value = 2

    def werewolf_audio_cue(self):
        if self.game_mode == common.Games.WereJoust:
            #print self.werewolf_timer - (time.time() - self.start_timer)
            if self.werewolf_timer - (time.time() - self.start_timer) <= 30 and self.audio_cue == 0:
                Audio('audio/Joust/sounds/30 werewolf.wav').start_effect()
                self.audio_cue = 1
            if self.werewolf_timer - (time.time() - self.start_timer) <= 10 and self.audio_cue == 1:
                Audio('audio/Joust/sounds/10 werewolf.wav').start_effect()
                self.audio_cue = 2
            if self.werewolf_timer - (time.time() - self.start_timer) <= 0 and self.audio_cue == 2:
                Audio('audio/Joust/sounds/werewolf reveal 2.wav').start_effect()
                self.reveal()
                self.audio_cue = 3
                

    def check_end_game(self):
        winning_team = -100
        team_win = True
        #print ('dead moves is ' + str(self.dead_moves))
        for move_serial, dead in self.dead_moves.items():
            #print ('the dead move is ' + str(move_serial))
            #if we are alive
            if dead.value == 1:
                if winning_team == -100:
                    winning_team = self.get_real_team(self.teams[move_serial])
                elif self.get_real_team(self.teams[move_serial]) != winning_team:
                    team_win = False
            if dead.value == 0:
                #This is to play the sound effect
                dead.value = -1
                self.explosion.start_effect()
                
        if team_win:
            self.end_game_sound(winning_team)
            for move_serial in self.teams.keys():
                if self.get_real_team(self.teams[move_serial]) == winning_team:
                    self.winning_moves.append(move_serial)
            self.game_end = True

    def stop_tracking_moves(self):
        for proc in self.tracked_moves.values():
            proc.terminate()
            proc.join()
            time.sleep(0.02)

    def end_game(self):
        self.audio.stop_audio()
        end_time = time.time() + END_GAME_PAUSE
        h_value = 0

        while (time.time() < end_time):
            time.sleep(0.01)
            win_color = common.hsv2rgb(h_value, 1, 1)
            for win_move in self.winning_moves:
                win_color_array = self.force_move_colors[win_move]
                common.change_color(win_color_array, *win_color)
            h_value = (h_value + 0.01)
            if h_value >= 1:
                h_value = 0
        self.running = False

    def end_game_sound(self, winning_team):
        if self.game_mode == common.Games.JoustTeams.value:
            if winning_team == 0:
                team_win = Audio('audio/Joust/sounds/yellow team win.wav')
            if winning_team == 1:
                team_win = Audio('audio/Joust/sounds/green team win.wav')
            if winning_team == 2:
                team_win = Audio('audio/Joust/sounds/cyan team win.wav')
            if winning_team == 3:
                team_win = Audio('audio/Joust/sounds/blue team win.wav')
            if winning_team == 4:
                team_win = Audio('audio/Joust/sounds/magenta team win.wav')
            if winning_team == 5:
                team_win = Audio('audio/Joust/sounds/red team win.wav')
            team_win.start_effect()
        if self.game_mode == common.Games.JoustRandomTeams.value:
            if winning_team == 0:
                team_win = Audio('audio/Joust/sounds/yellow team win.wav')
            if winning_team == 1:
                team_win = Audio('audio/Joust/sounds/cyan team win.wav')
            if winning_team == 2:
                team_win = Audio('audio/Joust/sounds/magenta team win.wav')
            if winning_team == 3:
                team_win = Audio('audio/Joust/sounds/red team win.wav')
            team_win.start_effect()
        if self.game_mode == common.Games.WereJoust.value:
            if winning_team == -1:
                team_win = Audio('audio/Joust/sounds/werewolf win.wav')
            else:
                team_win = Audio('audio/Joust/sounds/human win.wav')
            team_win.start_effect()
        #self.explosion = Audio('audio/Joust/sounds/Explosion34.wav')
        
    def werewolf_intro(self):
        Audio('audio/Joust/sounds/werewolf intro.wav').start_effect()
        time.sleep(3)
        self.change_all_move_colors(80, 0, 0)
        time.sleep(2)
        self.change_all_move_colors(0, 0, 0)
        time.sleep(20)
        self.start_timer = time.time()
        

    def game_loop(self):
        self.track_moves()
        if self.game_mode == common.Games.WereJoust.value:
            self.werewolf_intro()
        self.werewolf_reveal.value = 1
        self.count_down()
        time.sleep(0.02)
        self.audio.start_audio_loop()
        time.sleep(0.8)
        
        while self.running:
            self.check_music_speed()
            self.check_end_game()
            self.werewolf_audio_cue()
            if self.game_end:
                print ('end of game')
                self.end_game()

        self.stop_tracking_moves()
                    
                
                
        
        

            
        

            
