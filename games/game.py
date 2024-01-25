import time
import os
import common, colors
from common import Status
from colors import Colors
from piaudio import Audio
import numpy
import random
import logging
import psmove
from math import sqrt
from audio.constants import *

logger = logging.getLogger(__name__)

class Game():

    SLOW_WARNING = [1.2, 1.3, 1.6, 2.0, 2.5]
    SLOW_MAX = [1.3, 1.5, 1.8, 2.5, 3.2]
    FAST_WARNING = [1.4, 1.6, 1.9, 2.7, 2.8]
    FAST_MAX = [1.6, 1.8, 2.8, 3.2, 3.5]

    # The min and max timeframe in seconds for
    # the speed change to trigger, randomly selected
    MIN_MUSIC_FAST_TIME = 4
    MAX_MUSIC_FAST_TIME = 8
    MIN_MUSIC_SLOW_TIME = 10
    MAX_MUSIC_SLOW_TIME = 23

    END_MIN_MUSIC_FAST_TIME = 6
    END_MAX_MUSIC_FAST_TIME = 10
    END_MIN_MUSIC_SLOW_TIME = 8
    END_MAX_MUSIC_SLOW_TIME = 12

    def __init__(self, moves, command_queue, ns, red_on_kill, music, teams, game_mode, controller_teams, controller_colors, dead_moves, invincible_moves, force_move_colors, music_speed, show_team_colors, restart, revive, opts=[]):
        logger.debug("Initializing {}".format(game_mode.pretty_name))

        # TODO - Document these variables
        # Admin settings
        self.ns = ns
        self.play_audio = self.ns.settings['play_audio']
        self.color_lock = self.ns.settings['color_lock']
        self.color_lock_choices = self.ns.settings['color_lock_choices']
        self.random_teams = self.ns.settings['random_teams']
        self.voice = self.ns.settings['menu_voice']

        # Admin settings shared with tracking
        self.red_on_kill = red_on_kill
        self.red_on_kill.value = self.ns.settings['red_on_kill']

        # Shared Variables
        self.game_mode = game_mode
        self.command_queue = command_queue
        self.move_serials = moves # TODO - get rid of the duplicate variables here
        self.moves = moves
        self.dead_moves = dead_moves
        self.invincible_moves = invincible_moves
        self.music = music
        self.music_speed = music_speed
        self.music_speed.value = SLOW_MUSIC_SPEED
        self.teams = teams
        self.controller_teams = controller_teams # TODO - get rid of the duplicate variables
        self.controller_colors = controller_colors
        self.force_move_colors = force_move_colors
        self.show_team_colors = show_team_colors
        self.restart = restart
        self.opts = opts

        # Class Variables
        self.start_timer = time.time()
        self.update_time = 0
        self.change_time = 0
        self.audio_cue = 0
        self.num_dead = 0
        self.speed_up = False
        self.currently_changing = False
        self.game_end = False
        self.running = True
        self.tracked_moves = {}
        self.alive_moves = []
        self.winning_moves = []
        self.team_colors = []
        self.winning_team = None
        self.revive = revive
        self.revive.value = False

        self.init_audio()

    def init_audio(self):
        if self.play_audio:
            self.start_beep = Audio('audio/Joust/sounds/start.wav')
            self.start_game = Audio('audio/Joust/sounds/start3.wav')
            self.explosion = Audio('audio/Joust/sounds/Explosion34.wav')
            self.revive_sound = Audio('audio/Commander/sounds/revive.wav')
            self.audio = self.music

    def get_real_team(self, team):
        if team < 0:
            return -1
        else:
            return team

    def generate_teams(self, num_teams, num_moves=None, team_colors=None):
        if team_colors is None:
            self.generate_team_colors(num_teams)
        else:
            self.team_colors = team_colors
        self.generate_random_teams(num_teams, num_moves)

    def generate_team_colors(self, num_teams):
        self.team_colors = colors.generate_team_colors(num_teams, self.color_lock, self.color_lock_choices)

    def generate_random_teams(self, num_teams, num_moves=None):
        if not self.random_teams:
            players_per_team = (len(self.move_serials)//num_teams)+1
            team_num = [x for x in range(num_teams)]*players_per_team
            for num,move in zip(team_num,self.move_serials):
                self.teams[move] = num
        else:
            team_pick = list(range(num_teams))
            copy_serials = self.move_serials[:]

            while len(copy_serials) >= 1:
                #for serial in self.move_serials:
                serial = random.choice(copy_serials)
                copy_serials.remove(serial)
                random_choice = random.choice(team_pick)
                self.teams[serial] = random_choice
                team_pick.remove(random_choice)
                if not team_pick:
                    team_pick = list(range(num_teams))

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

    def init_moves(self):
        for move_num, move_serial in enumerate(self.move_serials):
            self.alive_moves.append(move_serial)
            time.sleep(0.1)
            # if self.teams[move_serial]:
            #     logger.debug("Putting move {} on team {} with color {}".format(move_serial, self.teams[move_serial], self.team_colors[self.teams[move_serial]]))
            self.switch_teams(move_serial, self.teams[move_serial])
            self.dead_moves[move_serial].value = Status.ALIVE.value
            self.invincible_moves[move_serial].value = False
            self.force_black(move_serial)
            for i in range(len(self.opts)):
                self.opts[move_serial][i] = 0

    # Black, but not completely black, so that force_colors is activated
    def force_black(self, move_serial):
        colors.change_color(self.force_move_colors[move_serial], 1, 1, 1)

    def get_change_time(self, speed_up):
        min_moves = len(self.move_serials) - 2
        if min_moves <= 0:
            min_moves = 1

        game_percent = (self.num_dead/min_moves)
        if game_percent > 1.0:
            game_percent = 1.0
        min_music_fast = common.lerp(MIN_MUSIC_FAST_TIME, END_MIN_MUSIC_FAST_TIME, game_percent)
        max_music_fast = common.lerp(MAX_MUSIC_FAST_TIME, END_MAX_MUSIC_FAST_TIME, game_percent)

        min_music_slow = common.lerp(MIN_MUSIC_SLOW_TIME, END_MIN_MUSIC_SLOW_TIME, game_percent)
        max_music_slow = common.lerp(MAX_MUSIC_SLOW_TIME, END_MAX_MUSIC_SLOW_TIME, game_percent)
        if speed_up:
            added_time = random.uniform(min_music_fast, max_music_fast)
        else:
            added_time = random.uniform(min_music_slow, max_music_slow)
        return time.time() + added_time

    def change_music_speed(self, fast):
        change_percent = numpy.clip((time.time() - self.change_time)/INTERVAL_CHANGE, 0, 1)
        if fast:
            self.music_speed.value = common.lerp(FAST_MUSIC_SPEED, SLOW_MUSIC_SPEED, change_percent)
        elif not fast:
            self.music_speed.value = common.lerp(SLOW_MUSIC_SPEED, FAST_MUSIC_SPEED, change_percent)
        self.audio.change_ratio(self.music_speed.value)

    def check_music_speed(self):
        if self.change_time < time.time() < self.change_time + INTERVAL_CHANGE:
            self.change_music_speed(self.speed_up)
            self.currently_changing = True
        elif time.time() >= self.change_time + INTERVAL_CHANGE and self.currently_changing:
            self.music_speed.value = SLOW_MUSIC_SPEED if self.speed_up else FAST_MUSIC_SPEED
            self.speed_up =  not self.speed_up
            self.change_time = self.get_change_time(speed_up = self.speed_up)
            self.audio.change_ratio(self.music_speed.value)
            self.currently_changing = False

    def change_all_move_colors(self, r, g, b):
        for color in self.force_move_colors.values():
            colors.change_color(color, r, g, b)

    def handle_status(self):
        for move_serial, dead in self.dead_moves.items():
            # If we just died (dead.value = 0), play the dead explosion sound
            if dead.value == Status.DIED.value:
                logger.debug("Move has died: {}".format(move_serial))
                self.num_dead += 1
                dead.value = Status.DEAD.value
                self.play_death_sound(move_serial)
            elif dead.value == Status.REVIVED.value:
                logger.debug("Move has revived: {}".format(move_serial))
                dead.value = Status.ALIVE.value
                if self.play_audio:
                    self.revive_sound.start_effect()

    def play_death_sound(self, move_serial):
        if self.play_audio:
            self.explosion.start_effect()

    def play_revive_sound(self):
        if self.play_audio:
            self.revive_sound.start_effect()

    def check_winner(self):
        self.winning_team = -100
        team_win = True
        for move_serial, dead in self.dead_moves.items():
            # If we are alive set our team as the winning team
            # If no other teams are set in the loop, our team is the winner!
            if dead.value in [Status.ALIVE.value, Status.ON.value, Status.RUMBLE.value]:
                if self.winning_team == -100:
                    self.winning_team = self.get_real_team(self.teams[move_serial])
                elif self.get_real_team(self.teams[move_serial]) != self.winning_team:
                    team_win = False
        return team_win

    def check_end_game(self):
        team_win = self.check_winner()

        if team_win:
            logger.debug("Game ended, winning team: {}".format(self.winning_team))
            self.update_status('ending',self.winning_team)
            self.end_game_sound()
            for move_serial in self.teams.keys():
                if self.get_real_team(self.teams[move_serial]) == self.winning_team:
                    self.winning_moves.append(move_serial)
            self.game_end = True

    def end_game_sound(self):
        time.sleep(2) # Wait for last death crash to complete
        if self.play_audio:
            try:
                self.audio.stop_audio()
            except:
                logger.error('No audio loaded to stop')

            # Play game over
            Audio('audio/Joust/vox/' + self.voice + '/game_over.wav').start_effect_and_wait()

            self.winning_team_sound()

    def winning_team_sound(self):
        if self.winning_team is not None:
            logger.debug("Winning team: {}".format(self.winning_team))
            logger.debug("Winning team color: {}".format(self.team_colors[self.winning_team].name))
            win_team_name = self.team_colors[self.winning_team].name
            if win_team_name == 'Pink':
                if self.voice == 'aaron':
                    os.popen('espeak -ven -p 70 -a 200 "And the winner is ...Pink Team')
                else:
                    team_win = Audio('audio/Joust/vox/' + self.voice + '/pink team win.wav')
            elif win_team_name == 'Magenta':
                team_win = Audio('audio/Joust/vox/' + self.voice + '/magenta team win.wav')
            elif win_team_name == 'Orange':
                if self.voice == 'aaron':
                    os.popen('espeak -ven -p 70 -a 200 "And the winner is ...Orange Team')
                else:
                    team_win = Audio('audio/Joust/vox/' + self.voice + '/orange team win.wav')
            elif win_team_name == 'Yellow':
                team_win = Audio('audio/Joust/vox/' + self.voice + '/yellow team win.wav')
            elif win_team_name == 'Green':
                team_win = Audio('audio/Joust/vox/' + self.voice + '/green team win.wav')
            elif win_team_name == 'Turquoise':
                team_win = Audio('audio/Joust/vox/' + self.voice + '/cyan team win.wav')
            elif win_team_name == 'Blue':
                team_win = Audio('audio/Joust/vox/' + self.voice + '/blue team win.wav')
            elif win_team_name == 'Red':
                team_win = Audio('audio/Joust/vox/' + self.voice + '/red team win.wav')
            elif win_team_name == 'Purple':
                if self.voice == 'aaron':
                    os.popen('espeak -ven -p 70 -a 200 "And the winner is ...Purple Team')
                else:
                    team_win = Audio('audio/Joust/vox/' + self.voice + '/purple team win.wav')
            else:
                team_win = Audio('audio/Joust/vox/' + self.voice + '/congratulations.wav').start_effect();
        else:
            team_win = Audio('audio/Joust/vox/' + self.voice + '/congratulations.wav').start_effect()
        try:
            team_win.start_effect()
        except:
            pass

    def all_moves_off(self):
        for move_serial in self.moves:
            self.dead_moves[move_serial].value = Status.OFF.value

    def end_game(self):
        end_time = time.time() + END_GAME_PAUSE

        h_value = 0

        self.all_moves_off()

        while (time.time() < end_time):
            time.sleep(0.01)
            win_color = colors.hsv2rgb(h_value, 1, 1)
            for win_move in self.winning_moves:
                win_color_array = self.force_move_colors[win_move]
                colors.change_color(win_color_array, *win_color)
            h_value = (h_value + 0.01)
            if h_value >= 1:
                h_value = 0
        self.running = False

    def stop_tracking_moves(self):
        self.restart.value = 1
        # Clear opts
        for move_serial in self.moves:
            for i in range(len(self.opts)):
                self.opts[move_serial][i] = 0

    def kill_game(self):
        try:
            self.audio.stop_audio()
        except:
            logger.debug('no audio loaded to stop')
        self.update_status('killed')
        all_moves = [x for x in self.dead_moves.keys()]
        end_time = time.time() + self.KILL_GAME_PAUSE

        bright = 255
        while time.time() < end_time:
            time.sleep(0.01)
            color = (bright,0,0)
            for move in all_moves:
                color_array = self.force_move_colors[move]
                colors.change_color(color_array, *color)
            bright = bright - 1
            if bright < 10:
                bright = 10

        self.running = False

    def check_command_queue(self):
        package = None
        while not(self.command_queue.empty()):
            package = self.command_queue.get()
            command = package['command']
        if not(package == None):
            if command == 'killgame':
                self.kill_game()

    def update_status(self, game_status, winning_team=-1):
        data = {'game_status': game_status,
                'game_mode': self.game_mode.pretty_name,
                'winning_team': winning_team,
                'total_players': len(self.move_serials),
                'remaining_players': len([x[0] for x in self.dead_moves.items() if x[1].value == 1])}

        self.ns.status = data

    def before_game_loop(self):
        self.init_moves()
        self.restart.value = 0
        self.change_time = time.time() + 6

        time.sleep(0.02)

    def game_loop(self):
        self.before_game_loop()

        self.count_down()

        if self.play_audio:
            self.audio.start_audio_loop()
            self.audio.change_ratio(self.music_speed.value)
        else:
            #when no audio is playing set the music speed to middle speed
            self.music_speed.value = (FAST_MUSIC_SPEED + SLOW_MUSIC_SPEED) / 2
        time.sleep(0.8)

        while self.running:
            #I think the loop is so fast that this causes
            #a crash if done every loop
            if time.time() - 0.1 > self.update_time:
                self.update_time = time.time()
                self.check_command_queue()
                self.update_status('in_game')
            self.handle_status()
            self.check_end_game()

            if self.game_end:
                self.end_game()

        self.stop_tracking_moves()

    def switch_teams(self, serial, team):
        self.teams[serial] = team
        self.controller_teams[serial].value = self.teams[serial]
        self.controller_colors[serial][0] = self.team_colors[self.teams[serial]].value[0]
        self.controller_colors[serial][1] = self.team_colors[self.teams[serial]].value[1]
        self.controller_colors[serial][2] = self.team_colors[self.teams[serial]].value[2]

    @classmethod
    def pre_game_loop(cls, move, team, opts):
        pass

    @classmethod
    def get_slow_warning(cls, team, opts):
        return cls.SLOW_WARNING

    @classmethod
    def get_fast_warning(cls, team, opts):
         return cls.FAST_WARNING

    @classmethod
    def get_slow_max(cls, team, opts):
        return cls.SLOW_MAX

    @classmethod
    def get_fast_max(cls, team, opts):
        return cls.FAST_MAX

    @classmethod
    def get_warning(cls, team, speed_percent, sensitivity, opts):
        return common.lerp(cls.get_slow_warning(team, opts)[sensitivity], cls.get_fast_warning(team, opts)[sensitivity], speed_percent)

    @classmethod
    def get_threshold(cls, team, speed_percent, sensitivity, opts):
        return common.lerp(cls.get_slow_max(team, opts)[sensitivity], cls.get_fast_max(team, opts)[sensitivity], speed_percent)

    @classmethod
    def handle_opts(cls, move, team, opts, dead_move=None):
        return opts

    @classmethod
    def handle_team_color(cls, move, team, opts, team_color):
        return team_color

    @classmethod
    def get_revive_time(cls, move, team, opts):
        return 2

    @classmethod
    def track_move(cls, move, team, team_color_enum, dead_move, invincible_move, force_color, \
                   music_speed, show_team_colors, red_on_kill, restart, menu, sensitivity, revive, opts=None):

        no_rumble = time.time() + 2
        vibrate = False
        vibration_time = time.time() + 1
        flash_lights = True
        flash_lights_timer = 0
        change = 0
        reviving = 0

        cls.pre_game_loop(move, team.value, opts)

        while True:
            if menu.value == 1:
                return

            if dead_move.value == Status.RUMBLE.value:
                move.set_rumble(80)

            # Have the controller flash and rumble while invincible
            if invincible_move.value:
                vibration_time = time.time() + .3
                no_rumble = vibration_time
                vibrate = True

            if restart.value == 1:
                return

            opts = cls.handle_opts(move=move, team=team.value, opts=opts, dead_move=dead_move.value)
            team_color = cls.handle_team_color(move, team.value, opts, team_color_enum)

            if show_team_colors.value == 1:
                move.set_leds(*team_color)
                move.update_leds()
            elif sum(force_color) != 0:
                time.sleep(0.01)
                move.set_leds(*force_color)
                move.update_leds()
                no_rumble = time.time() + 0.5
                move.set_rumble(0)
            elif dead_move.value == Status.DIED.value:
                if red_on_kill.value:
                    move.set_leds(*Colors.Red.value)
                else:
                    move.set_leds(*Colors.Black.value)
                move.set_rumble(90)
                move.update_leds()
                time.sleep(0.25) # Wait for death to process in main loop
                dead_move.value = Status.DEAD.value
                vibration_time = time.time() + 0.5
            elif dead_move.value == Status.ALIVE.value:
                if move.poll():
                    ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
                    total = sqrt(sum([ax**2, ay**2, az**2]))
                    change = (change * 4 + total)/5
                    speed_percent = (music_speed.value - SLOW_MUSIC_SPEED)/(FAST_MUSIC_SPEED - SLOW_MUSIC_SPEED)
                    warning = cls.get_warning(team.value, speed_percent, sensitivity.value, opts)
                    threshold = cls.get_threshold(team.value, speed_percent, sensitivity.value, opts)

                    if vibrate:
                        flash_lights_timer += 1
                        if flash_lights_timer > 7:
                            flash_lights_timer = 0
                            flash_lights = not flash_lights
                        if flash_lights:
                            move.set_leds(*Colors.White40.value)
                        else:
                            move.set_leds(*team_color)

                        if time.time() < vibration_time-0.25:
                            move.set_rumble(90)
                        else:
                            move.set_rumble(0)
                        if time.time() > vibration_time:
                            vibrate = False
                    else:
                        move.set_leds(*team_color)

                    if reviving and not vibrate:
                        logger.debug("Revived")
                        reviving = 0
                        dead_move.value = Status.REVIVED.value

                    if not invincible_move.value:
                        if change > threshold and time.time() > no_rumble:
                            dead_move.value = Status.DIED.value

                        elif not vibrate and change > warning and time.time() > no_rumble:
                            vibrate = True
                            vibration_time = time.time() + 0.5
                move.update_leds()
            elif revive.value and dead_move.value == Status.DEAD.value:
                logger.debug("Reviving soon")
                reviving = 1
                no_rumble = time.time() + cls.get_revive_time(move, team.value, opts)
                vibration_time = time.time() + cls.get_revive_time(move, team.value, opts)
                vibrate = True
                dead_move.value = Status.ALIVE.value
            elif dead_move.value == Status.ON.value:
                move.set_leds(*team_color)
                move.update_leds()
                move.set_rumble(0)
            elif dead_move.value == Status.OFF.value:
                move.set_leds(*Colors.Black.value)
                move.update_leds()
                move.set_rumble(0)