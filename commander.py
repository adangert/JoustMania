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
SLOW_MAX = 1.3
SLOW_WARNING = 0.28
FAST_MAX = 2.0
FAST_WARNING = 1.0



#How long the speed change takes
INTERVAL_CHANGE = 1.5

#How long the winning moves shall sparkle
END_GAME_PAUSE = 4


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

class Buttons(Enum):
    middle = 524288
    all_buttons = 240
    sync = 65536
    start = 2048
    select = 256
    circle = 32
    triangle = 16
    nothing = 0

class Bool(Enum):
    no = 0
    yes = 1


#red blue
Commander_colors = [(255,0,0),(0,0,255)]
Overdrive_colors = [(255,127,0),(0,255,255)]
Current_commander_colors = [(255,0,255),(0,255,0)]

class Team(Enum):
    red = 0
    blue = 1


def calculate_flash_time(r,g,b, score):
    flash_percent = max(min(float(score)+0.2,1.0),0.0)
    #val_percent = (val-(flash_speed/2))/(flash_speed/2)
    new_r = int(common.lerp(255, r, flash_percent))
    new_g = int(common.lerp(255, g, flash_percent))
    new_b = int(common.lerp(255, b, flash_percent))
    return (new_r, new_g, new_b)

def track_move(move_serial, move_num, team, team_num, dead_move, force_color, music_speed, commander_intro, move_opts, power, overdrive):
    #proc = psutil.Process(os.getpid())
    #proc.nice(3)
    #explosion = Audio('audio/Joust/sounds/Explosion34.wav')
    #explosion.start_effect()

    start = False
    no_rumble = time.time() + 1
    move_last_value = None
    move = common.get_move(move_serial, move_num)
    team_colors = common.generate_colors(team_num)
    #keep on looping while move is not dead
    ready = False
    move.set_leds(0,0,0)
    move.update_leds()
    time.sleep(1)

    death_time = 8
    time_of_death = time.time()

    while commander_intro.value == 1:
        if move.poll():
            button = move.get_buttons()
            if button == Buttons.middle and move_opts[Opts.holding] == Holding.not_holding:

                move_opts[Opts.selection] = Selections.a_button
                move_opts[Opts.holding] = Holding.holding
            elif button == Buttons.triangle and move_opts[Opts.holding] == Holding.not_holding:

                move_opts[Opts.selection] = Selections.triangle
                move_opts[Opts.holding] = Holding.holding

            elif move_opts[Opts.is_commander] == Bool.no and move_opts[Opts.holding] == Holding.holding:
                move.set_leds(200,200,200)

            elif move_opts[Opts.is_commander] == Bool.yes and move_opts[Opts.holding] == Holding.holding:
                    move.set_leds(*Current_commander_colors[team])
            else:
                #print 'boop'
                move.set_leds(*Commander_colors[team])
        move.update_leds()

    move_opts[Opts.holding] = Holding.not_holding
    move_opts[Opts.selection] = Selections.nothing

    while True:
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
                total = sum([ax, ay, az])
                if move_last_value is not None:
                    change = abs(move_last_value - total)
                    #speed_percent = (music_speed.value - SLOW_MUSIC_SPEED)/(FAST_MUSIC_SPEED - SLOW_MUSIC_SPEED)
                    #warning = common.lerp(SLOW_WARNING, FAST_WARNING, speed_percent)
                    #threshold = common.lerp(SLOW_MAX, FAST_MAX, speed_percent)
                    if move_opts[Opts.is_commander] == Bool.no:
                        if overdrive.value == 0:
                            warning = SLOW_WARNING
                            threshold = SLOW_MAX
                        else:
                            warning = FAST_WARNING
                            threshold = FAST_MAX
                    else:
                        #if affected by overdrive, this could make the power better
                        warning = SLOW_WARNING
                        threshold = SLOW_MAX
                        

                    if change > threshold:
                        if time.time() > no_rumble:
                            move.set_leds(0,0,0)
                            move.set_rumble(90)
                            dead_move.value = 0
                            time_of_death = time.time()

                    elif change > warning:
                        if time.time() > no_rumble:
                            move.set_leds(20,50,100)
                            move.set_rumble(110)

                    else:
                        if move_opts[Opts.is_commander] == Bool.no:
                            if overdrive.value == 0:
                                move.set_leds(*Commander_colors[team])
                            else:
                                move.set_leds(*Overdrive_colors[team])
                        else:
                            move.set_leds(*calculate_flash_time(Current_commander_colors[team][0],Current_commander_colors[team][1],Current_commander_colors[team][2], power.value))
                        move.set_rumble(0)


                    if move_opts[Opts.is_commander] == Bool.yes:
                        if (move.get_buttons() == 0 and move.get_trigger() < 10):
                            move_opts[Opts.holding] = Holding.not_holding
                            
                        button = move.get_buttons()
                        #print str(power.value)
                        if power.value >= 1.0:
                            #press trigger for overdrive
                            if (move_opts[Opts.holding] == Holding.not_holding and move.get_trigger() > 100):
                                print 'BOOOM'
                                move_opts[Opts.selection] = Selections.trigger
                                move_opts[Opts.holding] = Holding.holding
                            elif (move_opts[Opts.holding] == Holding.not_holding and button == Buttons.middle):
                                move_opts[Opts.selection] = Selections.a_button
                                move_opts[Opts.holding] = Holding.holding
                            elif (move_opts[Opts.holding] == Holding.not_holding and button == Buttons.triangle):
                                move_opts[Opts.selection] = Selections.triangle
                                move_opts[Opts.holding] = Holding.holding
                                
                            
                        
                move_last_value = total
            move.update_leds()
        #if we are dead
        elif dead_move.value <= 0:
            if time.time() - time_of_death >= death_time:
                dead_move.value = 3
        elif dead_move.value == 3:
                move_last_value = None
                dead_move.value = 1
                no_rumble = time.time() + 2
                if death_time < 25:
                    death_time += 1
            

class Commander():
    def __init__(self, moves):

        self.move_serials = moves
        self.tracked_moves = {}
        self.dead_moves = {}
        self.teams = {}
        self.music_speed = Value('d', 1.5)
        self.running = True
        self.force_move_colors = {}
        self.team_num = 2
        self.werewolf_timer = 35
        self.start_timer = time.time()
        self.audio_cue = 0

        self.move_opts = {}
        self.current_commander = ["",""]

        self.time_to_power = [20,20]
        self.activated_time = [time.time(), time.time()]

        self.activated_overdrive = [time.time(), time.time()]
        
        
        self.powers = [Value('d', 0.0), Value('d', 0.0)]
        #self.red_power = Value('d', 0.0)
        #self.blue_power = Value('d', 0.0)

        self.red_overdrive = Value('i', 0)
        self.blue_overdrive = Value('i', 0)

        
        self.generate_random_teams(self.team_num)
        self.commander_intro = Value('i', 1)

        self.powers_active = [False, False]

        


        music = 'audio/Commander/music/' + random.choice(os.listdir('audio/Commander/music'))
        self.start_beep = Audio('audio/Joust/sounds/start.wav')
        self.start_game = Audio('audio/Joust/sounds/start3.wav')
        self.explosion = Audio('audio/Joust/sounds/Explosion34.wav')
        fast_resample = False
        if len(moves) >= 5:
            fast_resample = True
        self.audio = Audio(music, fast_resample)
        #self.change_time = self.get_change_time(speed_up = True)
        self.change_time = time.time() + 8
        self.speed_up = True
        self.currently_changing = False
        self.game_end = False
        self.winning_moves = []
        
        self.game_loop()


    def generate_random_teams(self, team_num):
        team_pick = range(team_num)
        for serial in self.move_serials:
            random_choice = random.choice(team_pick)
            self.teams[serial] = random_choice
            team_pick.remove(random_choice)
            if not team_pick:
                team_pick = range(team_num)

    def track_moves(self):
        for move_num, move_serial in enumerate(self.move_serials):
            time.sleep(0.02)
            dead_move = Value('i', 1)
            force_color = Array('i', [1] * 3)
            opts = Array('i', [0] * 5)
            power = self.powers[self.teams[move_serial]]
            #if self.teams[move_serial] == Team.red:
            #    power = self.red_power
            #else:
            #    power = self.blue_power

            if self.teams[move_serial] == Team.red:
                overdrive = self.red_overdrive
            else:
                overdrive = self.blue_overdrive
            proc = Process(target=track_move, args=(move_serial,
                                                    move_num,
                                                    self.teams[move_serial],
                                                    self.team_num,
                                                    dead_move,
                                                    force_color,
                                                    self.music_speed,
                                                    self.commander_intro,
                                                    opts,
                                                    power,
                                                    overdrive))
            proc.start()
            self.tracked_moves[move_serial] = proc
            self.dead_moves[move_serial] = dead_move
            self.force_move_colors[move_serial] = force_color
            self.move_opts[move_serial] = opts
            
    def change_all_move_colors(self, r, g, b):
        for color in self.force_move_colors.itervalues():
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

    def get_winning_team_members(self, winning_team):
        self.end_game_sound(winning_team)
        for move_serial in self.teams.iterkeys():
            if self.teams[move_serial] == winning_team:
                self.winning_moves.append(move_serial)

    def check_end_game(self):
        winning_team = -100
        team_win = False
        for commander in self.current_commander:
            if self.dead_moves[commander].value <= 0:
                winning_team = (self.teams[commander] + 1) % 2
                self.get_winning_team_members(winning_team)
                self.game_end = True
                

        for move_serial, dead in self.dead_moves.iteritems():
            if dead.value == 0:
                dead_team = self.teams[move_serial]
                winning_team = (self.teams[move_serial] + 1) % 2
                if self.time_to_power[winning_team] > 10:
                    self.time_to_power[team] -= 1
                if self.time_to_power[dead_team] < 30:
                    self.time_to_power[team] -= +
                
                #This is to play the sound effect
                dead.value = -1
                self.explosion.start_effect()


    def stop_tracking_moves(self):
        for proc in self.tracked_moves.itervalues():
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
        #if self.game_mode == common.Games.JoustTeams:
        if winning_team == Team.red:
            team_win = Audio('audio/Commander/sounds/red winner.wav')
        if winning_team == Team.blue:
            team_win = Audio('audio/Commander/sounds/blue winner.wav')
        team_win.start_effect()

    def check_commander_select(self):
        for move_serial in self.move_opts.iterkeys():
            if self.move_opts[move_serial][Opts.selection] == Selections.triangle and self.move_opts[move_serial][Opts.holding] == Holding.holding:
                Audio('audio/Commander/sounds/commanderselect.wav').start_effect()
                self.change_commander(move_serial)
                self.move_opts[move_serial][Opts.selection] = Selections.nothing
            elif self.move_opts[move_serial][Opts.selection] == Selections.a_button and self.move_opts[move_serial][Opts.holding] == Holding.holding:
                Audio('audio/Commander/sounds/buttonselect.wav').start_effect()
                self.move_opts[move_serial][Opts.selection] = Selections.nothing

    def change_commander(self, new_commander):
        #print 'changing commander to ' + str(new_commander)
        commander_team = self.teams[new_commander]
        if self.current_commander[commander_team] != '':
            self.move_opts[self.current_commander[commander_team]][Opts.is_commander] = Bool.no
        
        self.move_opts[new_commander][Opts.is_commander] = Bool.yes
        self.current_commander[commander_team] = new_commander

    def change_random_commander(self, team, exclude_commander=None):
        team_move_serials = [ move_serial for move_serial in self.move_opts.iterkeys() if (self.teams[move_serial] == team and move_serial != exclude_commander and self.dead_moves[move_serial].value >= 1) ]
        print 'team move serials is ' + str(team_move_serials)
        if len(team_move_serials) > 0:
            new_commander = random.choice(team_move_serials)
            self.change_commander(new_commander)
            return True
        return False
            
    def update_team_powers(self):
        self.powers[Team.red].value = max(min((time.time() - self.activated_time[Team.red])/(self.time_to_power[Team.red] * 1.0),1.0), 0.0)
        self.powers[Team.blue].value = max(min((time.time() - self.activated_time[Team.blue])/(self.time_to_power[Team.blue] * 1.0), 1.0), 0.0)

        
        if self.powers_active[Team.red] == False:
            if self.powers[Team.red].value >= 1.0:
                self.powers_active[Team.red] = True
                Audio('audio/Commander/sounds/power ready.wav').start_effect()
                Audio('audio/Commander/sounds/red power ready.wav').start_effect()
                
                
        if self.powers_active[Team.blue] == False:
            if self.powers[Team.blue].value >= 1.0:
                self.powers_active[Team.blue] = True
                Audio('audio/Commander/sounds/power ready.wav').start_effect()
                Audio('audio/Commander/sounds/blue power ready.wav').start_effect()
                
            
    def overdrive(self, team):
        Audio('audio/Commander/sounds/overdrive.wav').start_effect()
        if team == Team.red:
            self.red_overdrive.value = 1
            self.activated_overdrive[Team.red] = time.time() + 10
            Audio('audio/Commander/sounds/red overdrive.wav').start_effect()
        else:
            self.blue_overdrive.value = 1
            self.activated_overdrive[Team.blue] = time.time() + 10
            Audio('audio/Commander/sounds/blue overdrive.wav').start_effect()

    def revive(self, team):
        print 'dadooda'
        dead_team_moves = [ move_serial for move_serial in self.move_opts.iterkeys() if (self.teams[move_serial] == team and self.dead_moves[move_serial].value <= 0) ]
        #print 'dead_team_moves is ' + str(dead_team_moves)
        for move in dead_team_moves:
            self.dead_moves[move].value = 3
        Audio('audio/Commander/sounds/revive.wav').start_effect()
        if team == Team.red:
            Audio('audio/Commander/sounds/red revive.wav').start_effect()
        if team == Team.blue:
            Audio('audio/Commander/sounds/blue revive.wav').start_effect()

    def shift(self, team, commander):
        print 'shifty'
        did_shift = self.change_random_commander(team, exclude_commander = commander)
        if did_shift:
            Audio('audio/Commander/sounds/shift.wav').start_effect()
            if team == Team.red:
                Audio('audio/Commander/sounds/red shift.wav').start_effect()
            if team == Team.blue:
                Audio('audio/Commander/sounds/blue shift.wav').start_effect()
        return did_shift
        
        
    def check_end_of_overdrive(self):
        if self.red_overdrive.value == 1:

            if time.time() >= self.activated_overdrive[Team.red]:
                #print 'its over'
                self.red_overdrive.value = 0
        if self.blue_overdrive.value == 1:
            
            if time.time() >= self.activated_overdrive[Team.blue]:
                #print 'itsa over'
                self.blue_overdrive.value = 0

    def reset_power(self, team):
        self.powers[team].value == 0.0
        self.activated_time[team] = time.time()
        self.powers_active[team] = False

    def check_commander_power(self):
        #print str(self.powers[0].value)
        #print str(self.powers[1].value)
        for commander in self.current_commander:
            #print self.move_opts[commander][Opts.selection] 
            if self.move_opts[commander][Opts.selection] == Selections.trigger:
                self.overdrive(self.teams[commander])
                self.reset_power(self.teams[commander])
                self.move_opts[commander][Opts.selection] = Selections.nothing

            if self.move_opts[commander][Opts.selection] == Selections.a_button:
                print 'BABOOBA'
                self.revive(self.teams[commander])
                self.reset_power(self.teams[commander])
                self.move_opts[commander][Opts.selection] = Selections.nothing
                
            if self.move_opts[commander][Opts.selection] == Selections.triangle:
                print 'balogalo'              
                if self.shift(self.teams[commander], commander):
                    self.reset_power(self.teams[commander])
                self.move_opts[commander][Opts.selection] = Selections.nothing

    def check_everyone_in(self):
        for move_serial in self.move_opts.iterkeys():
            if self.move_opts[move_serial][Opts.holding] == Holding.not_holding:
                return False
        return True
        
            
    def commander_intro_audio(self):
        #print 'BOOOP'
        intro_sound = Audio('audio/Commander/sounds/commander intro.wav')
        intro_sound.start_effect()
        #need while loop here
        play_last_one = True
        commander_select_time = time.time() + 50
        battle_ready_time = time.time() + 40
        while time.time() < commander_select_time:
            self.check_commander_select()
            if self.check_everyone_in():
                break

            if time.time() > battle_ready_time and play_last_one:
                play_last_one = False
                Audio('audio/Commander/sounds/10 seconds begins.wav').start_effect()
        intro_sound.stop_effect()        

        if self.current_commander[Team.red] == '':
            self.change_random_commander(Team.red)
        if self.current_commander[Team.blue] == '':
            self.change_random_commander(Team.blue)


        Audio('audio/Commander/sounds/commanders chosen.wav').start_effect()
        time.sleep(4)
        self.reset_power(Team.red)
        self.reset_power(Team.blue)
        self.commander_intro.value = 0

    def game_loop(self):
        self.track_moves()
        self.commander_intro_audio()
        
        self.count_down()
        time.sleep(0.02)
        self.audio.start_audio_loop()
        time.sleep(0.8)
        
        while self.running:
            
            #self.check_music_speed()


            self.update_team_powers()
            self.check_commander_power()
            self.check_end_of_overdrive()
            self.check_end_game()
            if self.game_end:
                self.end_game()

        self.stop_tracking_moves()
                    
                
                
        
        

            
        

            
