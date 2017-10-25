import common, colors
import psmove
import time
import psutil, os
import random
import numpy
from piaudio import Audio
from enum import Enum
from multiprocessing import Process, Value, Array
import json


#How long the winning moves shall sparkle
END_GAME_PAUSE = 6
KILL_GAME_PAUSE = 2


class Opts(Enum):
    alive = 0
    selection = 1
    holding = 2
    team = 3
    has_bomb = 4

class Selections(Enum):
    nothing = 0
    a_button = 1
    trigger = 2
    counter = 3
    false_trigger = 4

class Holding(Enum):
    not_holding = 0
    holding = 1

class Bool(Enum):
    no = 0
    yes = 1

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

def track_move(move_serial, move_num, dead_move, force_color,bomb_color, move_opts, game_start, false_color, faked, rumble):
    #proc = psutil.Process(os.getpid())
    #proc.nice(3)


    start = False
    no_rumble = time.time() + 1
    move_last_value = None
    move = common.get_move(move_serial, move_num)

    #keep on looping while move is not dead
    ready = False
    move.set_leds(0,0,0)
    move.update_leds()
    time.sleep(1)
    super_dead = False
    no_bomb_color = [0,0,200]
    fake_bomb_color = [0, 255, 0]
    no_fake_bomb_color = [0,0,200]



    death_time = 8
    time_of_death = time.time()
    can_fake = True
    faking = False

    move_opts[Opts.holding.value] = Holding.not_holding.value
    move_opts[Opts.selection.value] = Selections.nothing.value
    while  not super_dead:
        if sum(force_color) != 0 and game_start.value == 1:
            no_rumble_time = time.time() + 5
            time.sleep(0.01)
            move.set_leds(*force_color)
            move.update_leds()
            move.set_rumble(rumble.value)
            no_rumble = time.time() + 0.5
        #if we are not dead

        elif dead_move.value > 0:
            move.set_rumble(rumble.value)
            if dead_move.value == 2:
                no_bomb_color = [150,150,150]
                no_fake_bomb_color = [120,255,120]
            else:
                no_bomb_color = [30,30,30]
                no_fake_bomb_color = [100,100,100]
            if move.poll():

                button = common.Button(move.get_buttons())
                if move_opts[Opts.has_bomb.value] == Bool.yes.value:
                    if(move.get_trigger() > 50 and can_fake):

                        faking = True
                        #move_opts[Opts.holding.value] = Holding.holding.value
                        
                        move_opts[Opts.selection.value] = Selections.false_trigger.value
                        if (move.get_trigger() <= 127):
                            col1 = int(common.lerp(fake_bomb_color[0], no_fake_bomb_color[0], (move.get_trigger()-50)/77))
                            col2 = int(common.lerp(fake_bomb_color[1], no_fake_bomb_color[1], (move.get_trigger()-50)/77))
                            col3 = int(common.lerp(fake_bomb_color[2], no_fake_bomb_color[2], (move.get_trigger()-50)/77))
                            move.set_leds(col1,col2,col3)
                        #if (move.get_trigger() > 127 and move.get_trigger() <= 140):
                        #    move.set_leds(*no_fake_bomb_color)
                        if (move.get_trigger() > 127):
                            col1 = int(common.lerp(no_fake_bomb_color[0], fake_bomb_color[0], (move.get_trigger()-127)/128))
                            col2 = int(common.lerp(no_fake_bomb_color[1], fake_bomb_color[1], (move.get_trigger()-127)/128))
                            col3 = int(common.lerp(no_fake_bomb_color[2], fake_bomb_color[2], (move.get_trigger()-127)/128))
                            move.set_leds(col1,col2,col3)
                            #move.set_leds(0,200,0)


                    else:
                        move.set_leds(*bomb_color)
                        if game_start.value == 0:
                            move.set_leds(*force_color)
                            move.update_leds()
                        #move_opts[Opts.holding.value] == Holding.not_holding.value

                        if faking:
                            #move_opts[Opts.selection.value] = Selections.not_holding.value
                            if game_start.value == 1:
                                can_fake = False
                            faking = False

                #non bomb holder
                else:
                    can_fake = True
                    faking = False
                    if false_color.value == 1:
                        move.set_leds(150,20,20)
                    else:
                        move.set_leds(*no_bomb_color)
                    if  move_opts[Opts.holding.value] == Holding.not_holding.value and (move.get_trigger() > 50 or button == common.Button.MIDDLE):
                        if move_opts[Opts.has_bomb.value] == Bool.no.value:
                            move_opts[Opts.holding.value] = Holding.holding.value

                            if game_start.value == 1 and false_color.value == 1:
                                print("JUST DIED TO BEING FAKED!!!")
                                faked.value = 1
                                #dead_move.value -= 1
                    move.set_rumble(0)

                if move_opts[Opts.holding.value] == Holding.not_holding.value and (button in  common.all_shapes):
                    move_opts[Opts.selection.value] = Selections.counter.value
                    move_opts[Opts.holding.value] = Holding.holding.value

                if button == common.Button.MIDDLE and move_opts[Opts.holding.value] == Holding.not_holding.value:
                    move_opts[Opts.selection.value] = Selections.a_button.value
                    move_opts[Opts.holding.value] = Holding.holding.value




                elif move_opts[Opts.holding.value] == Holding.holding.value and button == common.Button.NONE and move.get_trigger() <= 50:
                    move_opts[Opts.selection.value] = Selections.nothing.value
                    move_opts[Opts.holding.value] = Holding.not_holding.value

        else:
            if super_dead == False:
                #for i in range(100):
                #    time.sleep(0.01)
                #    move.set_leds(0,random.randrange(100, 200),0)
                #    move.set_rumble(200)
                #    move.update_leds()
                super_dead = True
            move.set_rumble(0)
            move.set_leds(0,0,0)

        move.update_leds()
        #if we are dead


class Bomb():
    def __init__(self, moves, command_queue, ns, music):

        self.command_queue = command_queue
        self.ns = ns

        self.play_audio = self.ns.settings['play_audio']
        self.move_serials = moves
        self.tracked_moves = {}
        self.dead_moves = {}
        self.alive_moves = []
        self.teams = {}
        self.music_speed = Value('d', 1)
        self.running = True
        self.force_move_colors = {}
        self.bomb_color = Array('i', [0] * 3)
        self.start_timer = time.time()
        self.audio_cue = 0
        self.num_bombs = 2
        self.move_opts = {}
        self.false_colors = {}
        self.was_faked = {}
        self.rumble = {}
        self.bomb_length = 5.0

        self.game_start = Value('i', 0)
        self.current_rand_holder = ''
        self.next_rand_holder = ''
        self.prev_rand_holder = ''

        
        self.update_time = 0

        if self.play_audio:
##            try:
##                music = 'audio/Commander/music/' + random.choice(os.listdir('audio/Commander/music'))
##            except:
##                print('no music in audio/Commander/music')
            self.start_beep = Audio('audio/Joust/sounds/start.wav')
            self.start_game = Audio('audio/Joust/sounds/start3.wav')
            self.explosion = Audio('audio/Joust/sounds/Explosion34.wav')
            self.fakedout = Audio('audio/Joust/sounds/Fakedout.wav')
            self.explosion40 = Audio('audio/Joust/sounds/Explosion40.wav')
            self.countered = Audio('audio/Joust/sounds/countered.wav')
            self.Fakecountered = Audio('audio/Joust/sounds/FakedoutCounter.wav')
            self.explosiondeath = Audio('audio/Joust/sounds/explosiondeath.wav')

            end = False
            try:
                self.audio = music
            except:
                print('no audio loaded')


        self.game_end = False


        self.game_loop()

    def reset_bomb_length(self):
        self.bomb_length = 4.0

    def get_bomb_length(self):
        self.bomb_length -= 0.3
        if self.bomb_length < 1:
            self.bomb_length = 1
        return self.bomb_length

    def get_prev_random_holder(self):
        return self.bomb_serial


    def get_next_random_holder(self):
        #if self.current_rand_holder != self.bomb_serial:
            #self.current_rand_holder = self.move_serials[random.choice(range(len(self.move_serials)))]
            #while self.current_rand_holder == self.bomb_serial:
            #    self.current_rand_holder = self.move_serials[random.choice(range(len(self.move_serials)))]
        if self.next_rand_holder == self.bomb_serial:
            self.next_rand_holder = self.move_serials[random.choice(range(len(self.move_serials)))]
            while self.next_rand_holder == self.bomb_serial or self.dead_moves[self.next_rand_holder].value <= 0:
                self.next_rand_holder = self.move_serials[random.choice(range(len(self.move_serials)))]
                self.current_rand_holder = self.bomb_serial
        #print("returning " + self.next_rand_holder)
        return self.next_rand_holder




    def get_next_bomb_holder(self, serial=None):
        if serial:
            holder = self.get_serial_pos(serial)
        else:
            holder = random.choice(range(len(self.move_serials)))
        while True:
            yield self.get_next_random_holder()
            #new_serial = self.move_serials[holder]
            #if self.dead_moves[new_serial].value > 0:
            #    yield new_serial
            #holder = (holder +1) % len(self.move_serials)


    def reset_bomb_time(self):
        self.bomb_time = time.time() + self.get_bomb_length()
        self.bomb_start_time = time.time()

    def game_loop(self):
        self.track_moves()
        self.rotate_colors()
        self.bomb_serial = self.move_serials[random.choice(range(len(self.move_serials)))]
        self.next_rand_holder = self.bomb_serial
        self.bomb_generator = self.get_next_bomb_holder()

        self.bomb_serial = next(self.bomb_generator)
        self.move_opts[self.bomb_serial][Opts.has_bomb.value] = Bool.yes.value


        self.holding = True
        self.game_start.value = 1
        self.count_down()
        time.sleep(0.02)
        if self.play_audio:
            try:
                self.audio.start_audio_loop()
            except:
                print('no audio loaded to start')
        time.sleep(0.8)

        self.bomb_time = time.time() + self.get_bomb_length()
        self.bomb_start_time = time.time()

        while self.running:

            if time.time() - 0.1 > self.update_time:
                self.update_time = time.time()
                self.check_command_queue()
                self.update_status('in_game')

            percentage = 1-((self.bomb_time - time.time())/(self.bomb_time - self.bomb_start_time))

            if(percentage > 0.8):
                self.bomb_color[0] = random.randrange(int(100+55*percentage), int(200+55*percentage))
            else:
                self.bomb_color[0] = int(common.lerp(90, 255, percentage))
            self.bomb_color[1] = int(common.lerp(30, 0, percentage))
            self.bomb_color[2] = int(common.lerp(30, 0, percentage))

            if self.move_opts[self.bomb_serial][Opts.selection.value] == Selections.nothing.value:
                self.holding = False
            if self.move_opts[self.bomb_serial][Opts.selection.value] == Selections.a_button.value and self.holding == False:
                self.reset_bomb_time()
                self.move_bomb()
                if self.play_audio:
                    self.start_beep.start_effect()
                self.holding = True
            if time.time() > self.bomb_time:
                if self.play_audio:
                    self.explosiondeath.start_effect()

                    self.explosion.start_effect()
                self.pause_for_player_death(self.bomb_serial)

                self.dead_moves[self.bomb_serial].value -= 1

                self.reset_bomb_length()
                self.reset_bomb_time()


                #if player is dead move bomb
                if not self.dead_moves[self.bomb_serial].value > 0:
                    self.move_bomb()

                print("TIME BOMB")


            self.check_dead_moves()
            self.check_faked_out()
            if self.game_end:
                self.end_game()

        self.stop_tracking_moves()

    def move_bomb(self):
        self.move_opts[self.bomb_serial][Opts.has_bomb.value] = Bool.no.value
        self.bomb_serial = next(self.bomb_generator)
        self.move_opts[self.bomb_serial][Opts.has_bomb.value] = Bool.yes.value


    def pause_for_player_death(self,  dead_move, faker_move=None):
        end_time = time.time() + 1.5
        while (time.time() < end_time):
            time.sleep(0.01)

            dead_color_array = self.force_move_colors[dead_move]
            if faker_move:
                faker_color_array = self.force_move_colors[faker_move]

            for move_serial in self.move_serials:
                #if move_serial == faker_move:
                #    colors.change_color(faker_color_array, random.randrange(100, 200), 10, 10)
                if move_serial == dead_move:
                    colors.change_color(dead_color_array, 10, random.randrange(100, 200), 10)
                    self.rumble[move_serial].value = 150
                else:
                    colors.change_color(self.force_move_colors[move_serial], 1,1,1)
        self.rumble[dead_move].value = 0
        self.change_all_move_colors(0, 0, 0)

    def check_faked_out(self):
        #check for one controller left first
        for move_serial in self.move_serials:

            if self.dead_moves[move_serial].value > 0:

                #if we faked play sound
                if self.move_opts[move_serial][Opts.selection.value] == Selections.false_trigger.value and self.move_opts[move_serial][Opts.holding.value] == Holding.not_holding.value:
                    print("faked out sound")
                    faker = self.get_next_serial(move_serial)
                    self.reset_bomb_time()
                    self.reset_bomb_length()
                    self.false_colors[faker].value = 1
                    if self.play_audio:
                        self.start_beep.start_effect()
                    self.move_opts[move_serial][Opts.holding.value] = Holding.holding.value


                #we are being faked out
                if self.false_colors[move_serial].value == 1:
                    prev_faker = self.get_prev_serial(move_serial)

                    #Pushed middle button, when faked
                    if self.was_faked[move_serial].value == 1:
                        faker = self.get_prev_serial(move_serial)
                        if self.play_audio:
                            self.explosion40.start_effect()
                            self.fakedout.start_effect()
                        self.pause_for_player_death( move_serial, faker)

                        self.dead_moves[move_serial].value -= 1
                        self.was_faked[move_serial].value = 2

                        self.reset_bomb_time()
                        self.reset_bomb_length()
                        self.move_bomb()


                    elif self.move_opts[move_serial][Opts.selection.value] == Selections.counter.value:
                        if self.play_audio:
                            self.explosion40.start_effect()
                            self.countered.start_effect()
                        self.pause_for_player_death(prev_faker, move_serial )


                        self.dead_moves[prev_faker].value -= 1
                        self.false_colors[move_serial].value = 0
                        self.move_opts[move_serial][Opts.holding.value] = Holding.holding.value


                        self.reset_bomb_length()
                        self.reset_bomb_time()

                        self.move_bomb()

                        print("JUST DIED TO BEING COUNTERED")



                    #only do this once per move
                    if self.move_opts[prev_faker][Opts.holding.value] == Holding.not_holding.value:
                        self.false_colors[move_serial].value = 0

                #Probably should get rid of this, or only when we are being faked out
                #elif self.false_colors[move_serial].value == 0  and self.move_opts[move_serial][Opts.holding.value] == Holding.holding.value :
                #    if self.move_opts[move_serial][Opts.selection.value] == Selections.counter.value and self.move_opts[self.get_prev_serial(move_serial)][Opts.has_bomb.value] == Bool.yes.value:

                #        self.explosion40.start_effect()
                #        self.Fakecountered.start_effect()
                #        self.pause_for_player_death(move_serial)

                #        self.dead_moves[move_serial].value -= 1
                        #self.move_opts[move_serial][Opts.holding.value] = Holding.holding.value

                #        self.reset_bomb_length()
                #        self.reset_bomb_time()

                #        self.move_bomb()
                #        print("JUST DIED TO PRESSING COUNTER")

                        #check for faked



    def get_next_serial(self, serial):
        return self.get_next_random_holder()



        pos = (self.get_serial_pos(serial) + 1) % len(self.move_serials)
        #pos = random.choice(range(len(self.move_serials)))
        #while random_move == pos - 1:
        #   random_move = random.choice(range(len(self.move_serials)))

        new_serial = self.move_serials[pos]
        while self.dead_moves[new_serial].value == 0:
            pos = (pos + 1) % len(self.move_serials)
            new_serial = self.move_serials[pos]
        return self.move_serials[pos]

    def get_prev_serial(self, serial):
        self.get_next_random_holder()
        return self.get_prev_random_holder()


        pos = (self.get_serial_pos(serial) - 1) % len(self.move_serials)
        new_serial = self.move_serials[pos]
        while self.dead_moves[new_serial].value == 0:
            pos = (pos - 1) % len(self.move_serials)
            new_serial = self.move_serials[pos]
        return self.move_serials[pos]

    def get_serial_pos(self, serial):
        for i, move_serial in enumerate(self.move_serials):
            if serial == move_serial:
                return i

    def track_moves(self):
        for move_num, move_serial in enumerate(self.move_serials):
            self.alive_moves.append(move_serial)
            time.sleep(0.02)
            dead_move = Value('i', 2)
            force_color = Array('i', [1] * 3)
            false_color = Value('i', 0)

            opts = Array('i', [0] * 5)
            faked = Value('i', 0)
            rumble = Value('i', 0)

            proc = Process(target=track_move, args=(move_serial,
                                                    move_num,
                                                    dead_move,
                                                    force_color,
                                                    self.bomb_color,
                                                    opts,
                                                    self.game_start,
                                                    false_color,
                                                    faked,
                                                    rumble))
            proc.start()
            self.tracked_moves[move_serial] = proc
            self.dead_moves[move_serial] = dead_move
            self.force_move_colors[move_serial] = force_color
            self.move_opts[move_serial] = opts
            self.false_colors[move_serial] = false_color
            self.was_faked[move_serial] = faked
            self.rumble[move_serial] = rumble


    def rotate_colors(self):
        move_on = False
        time_change = 0.5

        in_cons = []
        for move_serial_beg in self.move_serials:
            self.move_opts[move_serial_beg][Opts.has_bomb.value] = Bool.yes.value
            self.move_opts[move_serial_beg][Opts.holding.value] = Holding.holding.value
        while len(in_cons) != len(self.move_serials):
            for move_serial in self.move_serials:
                for move_serial_beg in self.move_serials:
                    if self.move_opts[move_serial_beg][Opts.selection.value] == Selections.a_button.value:
                        if move_serial_beg not in in_cons:
                            if self.play_audio:
                                self.start_beep.start_effect()
                            in_cons.append(move_serial_beg)
                    if move_serial_beg in in_cons:
                        colors.change_color(self.force_move_colors[move_serial_beg], 100,100,100)
                colors.change_color(self.force_move_colors[move_serial], 100,0,0)
                time.sleep(0.5)
                colors.change_color(self.force_move_colors[move_serial], 0,0,0)
        for move_serial_beg in self.move_serials:
            self.move_opts[move_serial_beg][Opts.has_bomb.value] = Bool.no.value


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


    def change_all_move_colors(self, r, g, b):
        for color in self.force_move_colors.values():
            colors.change_color(color, r, g, b)

    #remove dead controllers, and change bomb holder
    def check_dead_moves(self):
        #check for one controller left first
        for alive_serial in self.alive_moves:
            if self.dead_moves[alive_serial].value == 0:
                if self.move_opts[alive_serial][Opts.has_bomb.value] == Bool.yes.value:
                    self.move_opts[alive_serial][Opts.has_bomb.value] = Bool.no.value
                    self.move_bomb()

                    #for i, bomb_serial in enumerate(self.bomb_serials):
                    #if self.bomb_serial == alive_serial:
                    #    self.bomb_serial = next(self.bomb_generators[i])
                    #self.move_opts[self.bomb_serial][Opts.has_bomb.value] = Bool.yes.value
                #remove alive move:

                self.alive_moves.remove(alive_serial)
                if self.play_audio:
                    self.explosion.start_effect()
                self.reset_bomb_time()

        if len(self.alive_moves) <= 1:
            self.end_game()

    def stop_tracking_moves(self):
        for proc in self.tracked_moves.values():
            proc.terminate()
            proc.join()
            time.sleep(0.02)

    def end_game(self):
        if self.play_audio:
            try:
                self.audio.stop_audio()
            except:
                print('no audio loaded to stop')
        end_time = time.time() + END_GAME_PAUSE

        self.update_status('ending')

        h_value = 0

        while (time.time() < end_time):
            time.sleep(0.01)
            win_color = colors.hsv2rgb(h_value, 1, 1)
            if len(self.alive_moves) > 0:
                win_move = self.alive_moves[0]
                win_color_array = self.force_move_colors[win_move]
                colors.change_color(win_color_array, *win_color)
                h_value = (h_value + 0.01)
                if h_value >= 1:
                    h_value = 0
        self.running = False

    def check_command_queue(self):
        package = None
        while not(self.command_queue.empty()):
            package = self.command_queue.get()
            command = package['command']
        if not(package == None):
            if command == 'killgame':
                self.kill_game()

    def update_status(self,game_status,winning_team=-1):
        data ={'game_status' : game_status,
               'game_mode' : 'Ninja',
               'winning_team' : winning_team,
               'total_players': len(self.move_serials),
               'remaining_players': len(self.alive_moves)}

        self.ns.status = data

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
