import psmove
import time
import random
import common, colors
import os
from multiprocessing import Process, Value, Array
from piaudio import Audio
import json
from math import sqrt


human_warning = 1
human_max = 1.8

zombie_warning = 0.6
zombie_max = 1.0
zombie_spawn_invincibility = 2

zombie_max_respawn_time = 30
zombie_min_respawn_time = 2

#Need to update this to enums
#OPTS:
#0. Player Type
#1. Button Selection
#2. Holding button
#3. dead/alive
#4. ammo amount
#5. weapons selection
#6. weapons acquired

#(0) Player Type:
#0. Human
#1. Zombie
#2. Speed Zombie
#3. Hulk Zombie

#(1) button Selection:
#0. no button
#1. trigger
#2. pistol
#3. shotgun
#4. molotov

#(2) Holding Button:
#0. not holding
#1. Holding button

#(3) Dead/Alive
#0. Dead
#1. Alive

#(4) ammo amount
#Numbers range from 0-5

#(5)weapon selection
#0. nothing
#1. pistol
#2. shotgun
#3. molotov

#(6) weapons acquired
#0. no weapons
#1. pistol
#2. pistol/shotgun
#3. pistol/molotov
#4. all weapons



def track_controller(serial, num_try, opts):
    move = psmove.PSMove(num_try)
    if move.get_serial() != serial:
        for move_num in range(psmove.count_connected()):
            move = psmove.PSMove(move_num)
            if move.get_serial() == serial:
                break
    time.sleep(0.01)
    move.set_leds(200,200,200)
    move.update_leds()
    time.sleep(0.01)
    move_last_value = None
    vibrate = False
    vibration_time = time.time() + 1
    flash_lights = True
    flash_lights_timer = 0
    change_arr=[0,0,0]
    
    while True:
        if move.poll():
            ax, ay, az = move.get_accelerometer_frame(psmove.Frame_SecondHalf)
            #total = sum([ax, ay, az])
            total = sqrt(sum([ax**2, ay**2, az**2]))
            if move_last_value is not None:
                change_real = abs(move_last_value - total)
                change_arr[0] = change_arr[1]
                change_arr[1] = change_arr[2]
                change_arr[2] = change_real
                change = (change_arr[0] + change_arr[1]+change_arr[2])/3
                # Dead

                #TODO: should probably only change this
                # when the state changes (i.e. human death)
                if opts[0] == 0:
                    warning = human_warning
                    threshold = human_max
                if opts[0] == 1:
                    warning = zombie_warning
                    threshold = zombie_max



                if change > threshold:
                    move.set_leds(255,0,0)
                    move.set_rumble(100)
                    opts[3] = 0

                # Warn
                elif change > warning and not vibrate:
                    move.set_leds(20,50,100)
                    vibrate = True
                    vibration_time = time.time() + 0.5
                    move.update_leds()

            #if we are dead
            if opts[3] == 0:
                vibrate = False
                move.set_leds(255,0,0)
                move.update_leds()
                move.set_rumble(70)
            #regular colors
            else:
                #need gun selection color in here
                #if human
                if opts[0] == 1:
                    move.set_leds(20,139,16)
                move.set_rumble(0)
                #move.update_leds()

            #not holding button
            if (move.get_buttons() == 0 and move.get_trigger() < 10):
                opts[2] = 0

            #human update
            if opts[0] == 0:
                #128, 16 ,32
                button = move.get_buttons()
                #pistol


                # middle button to show bullet count (0-5)

                if opts[4] == 5:
                    move.set_leds(255,0,255)
                if opts[4] == 4:
                    move.set_leds(0,0,255)
                if opts[4] == 3:
                    move.set_leds(0,0,255)
                if opts[4] == 2:
                    move.set_leds(0,0,255)
                if opts[4] == 1:
                    move.set_leds(0,0,255)
                if opts[4] == 0:
                    move.set_leds(100,100,100)

                #not holding button, selected pistol, has bullets, and presses trigger
                if (opts[2] == 0  and opts[4] > 0 and opts[4] < 5 and move.get_trigger() > 100):
                    opts[2] = 1
                    opts[1] = 2
                    opts[4] = opts[4] - 1
                    

                #molotov
                elif(opts[2] == 0  and opts[4] >= 5 and move.get_trigger() > 100):
                    opts[2] = 1
                    opts[1] = 4
                    opts[4] = 0

            if vibrate:
                flash_lights_timer += 1
                if flash_lights_timer > 7:
                    flash_lights_timer = 0
                    flash_lights = not flash_lights
                if flash_lights:
                    move.set_leds(50,0,0)
                if time.time() < vibration_time - 0.22:
                    move.set_rumble(70)
                else:
                    move.set_rumble(0)
                if time.time() > vibration_time:
                    vibrate = False


            #else:
            #    move.set_leds(*team_colors[team.value])
            move.update_leds()
            move_last_value = total


#we should try one process per controller,
#since only normal music will be playing
#need to make this a class with zombie killing defs
class Zombie:
    def __init__(self, cont_alive, command_queue, ns, music):
        
        self.command_queue = command_queue
        self.ns = ns

        self.sensitivity = self.ns.settings['sensitivity']
        self.play_audio = self.ns.settings['play_audio']

        self.music = music

        global human_warning
        global human_max
        global zombie_warning
        global zombie_max
        
        human_warning = common.FAST_WARNING[self.sensitivity]
        human_max = common.FAST_MAX[self.sensitivity]
        zombie_warning = common.ZOMBIE_WARNING[self.sensitivity]
        zombie_max = common.ZOMBIE_MAX[self.sensitivity]
        
        self.update_time = 0
        self.humans = []
        self.alive_zombies = []
        self.dead_zombies = {}
        self.controller_opts = {}
        self.controllers_alive = cont_alive
        self.win_time =  ((len(self.controllers_alive) * 3)/16) * 60
        if self.win_time <= 0:
            self.win_time = 60
        self.start_time = time.time()
        if self.play_audio:
            self.pickup = Audio('audio/Zombie/sound_effects/pickup.wav')
        self.effect_cue = 0

        self.kill_game = False
        self.Start()

        
    def get_kill_time(self):
        percent_to_win = 1.0 * (time.time() - self.start_time)/(self.win_time * 1.0)
        random_num = ((1.0 - percent_to_win) * 7) + 2
        return random.uniform(random_num, random_num +2)

    def kill_zombies(self, num_zombies, random_bullet_chance):
        kill_zombie = False
        for i in range(num_zombies):
            if self.alive_zombies:
                kill_zombie = True
                shot_zombie_serial = random.choice(self.alive_zombies)
                self.controller_opts[shot_zombie_serial][3] = 0
                self.dead_zombies[shot_zombie_serial] = time.time() + self.get_kill_time()
                self.alive_zombies.remove(shot_zombie_serial)

        if kill_zombie:
            self.reward(random_bullet_chance)

    def reward(self, random_bullet_chance):
        if (len(self.dead_zombies) + len(self.alive_zombies)) > 3:
            random_bullet = random.choice(random_bullet_chance)
            sound = False
            for i in range(random_bullet):
                sound = True
                random_human = random.choice(self.humans)
                if self.controller_opts[random_human][4] < 5:
                    self.controller_opts[random_human][4] += 1
            if sound:
                self.pickup.start_effect()
            #one in 5 chance of getting a weapon
            #self.get_weapon(5)

    def audio_cue(self):
        if self.win_time - (time.time() - self.start_time) <= 10 and self.effect_cue <= 4:
            Audio('audio/Zombie/sound_effects/10 seconds left.wav').start_effect()
            self.effect_cue = 5
        elif self.win_time - (time.time() - self.start_time) <= 30 and self.effect_cue <= 3:
            Audio('audio/Zombie/sound_effects/30 seconds.wav').start_effect()
            self.effect_cue = 4
        elif self.win_time - (time.time() - self.start_time) <= 1*60 and self.effect_cue <= 2:
            Audio('audio/Zombie/sound_effects/1 minute.wav').start_effect()
            self.effect_cue = 3
        elif self.win_time - (time.time() - self.start_time) <= 3*60 and self.effect_cue <= 1:
            Audio('audio/Zombie/sound_effects/3 minutes.wav').start_effect()
            self.effect_cue = 2
        #elif self.win_time - (time.time() - self.start_time) <= 5*60 and self.effect_cue <= 0:
        #   Audio('audio/Zombie/sound_effects/5 minutes.wav').start_effect()
        #   self.effect_cue = 1

        
    
    def Start(self):
        running = True
        moves = []
        for move_num in range(len(self.controllers_alive)):
            moves.append(common.get_move(self.controllers_alive[move_num], move_num))

        serials = self.controllers_alive
        processes = []
        
        for num_try, serial in enumerate(serials):
            starting_bullets = 0
            #starting_bullets = random.choice([0, 1])
            opts = Array('i', [0, 0, 0, 1, starting_bullets, 1, 1])
            p = Process(target=track_controller, args=(serial, num_try, opts))
            p.start()
            processes.append(p)
            self.controller_opts[serial] = opts
            self.humans.append(serial)
            
        if self.play_audio:
            human_victory = Audio('audio/Zombie/sound_effects/human_victory.wav')
            zombie_victory = Audio('audio/Zombie/sound_effects/zombie_victory.wav')
            death = Audio('audio/Zombie/sound_effects/zombie_death.wav')
            pistol = Audio('audio/Zombie/sound_effects/pistol.wav')
            shotgun = Audio('audio/Zombie/sound_effects/shotgun.wav')
            molotov = Audio('audio/Zombie/sound_effects/molotov.wav')
            try:
                self.music.start_audio_loop()
##                music = Audio('audio/Zombie/music/' + random.choice(os.listdir('audio/Zombie/music/')))
##                music.start_effect_music()
            except:
                print('no music in audio/Zombie/music/')

        start_kill = time.time() + 5
        while time.time() < start_kill:
            pass

        #kill first humans
        for random_human in random.sample(set(self.humans),2):
            #random_human = random.choice(self.humans)
            self.controller_opts[random_human][3] = 0
        
        while running:
            if self.play_audio:
                self.audio_cue()
            if time.time() - 0.1 > self.update_time:
                self.update_time = time.time()
                self.check_command_queue()
                self.update_status('in_game')

            #human update, loop through the different human controllers
            for serial in self.humans:
                #human is dead and now a zombie
                if self.controller_opts[serial][3] == 0:
                    self.controller_opts[serial][0] = 1
                    self.dead_zombies[serial] = time.time() + self.get_kill_time()
                    
                #pistol fired(1 bullet 1 random alive zombie)
                elif self.controller_opts[serial][1] == 2:
                    if self.play_audio:
                        pistol.start_effect()
                    self.kill_zombies(1, [0, 0, 0, 0, 1, 1, 1])
                    self.controller_opts[serial][1] = 0


                #molotov fired(5 bullets all alive zombies)
                elif self.controller_opts[serial][1] == 4:
                    if self.play_audio:
                        molotov.start_effect()
                    self.kill_zombies(50, [0, 0, 1, 1, 2, 3])
                    self.controller_opts[serial][1] = 0

                    
            for serial, spawn_time in self.dead_zombies.items():
                if serial in self.humans:
                    self.humans.remove(serial)
                if spawn_time < time.time():
                    #set zombie to alive
                    self.controller_opts[serial][3] = 1
                    self.alive_zombies.append(serial)

            #loop through dead zombies
            for serial in self.alive_zombies:
                if serial in self.dead_zombies:
                    del self.dead_zombies[serial]

                #melee
                if self.controller_opts[serial][3] == 0:
                    self.controller_opts[serial][0] = 1
                    self.dead_zombies[serial] = time.time() + self.get_kill_time()
                    self.alive_zombies.remove(serial)
                    self.reward([0, 0, 1, 1, 2])
                    death.start_effect()

            #win scenario
            if len(self.humans) <= 0 or (time.time() - self.start_time) > self.win_time or self.kill_game:
                for proc in processes:
                    proc.terminate()
                    proc.join()
                pause_time = time.time() + 3
                HSV = [(x*1.0/(50*len(self.controllers_alive)), 0.9, 1) for x in range(50*len(self.controllers_alive))]
                colour_range = [[int(x) for x in colors.hsv2rgb(*colour)] for colour in HSV]
                win_controllers = []
                if len(self.humans) <= 0:
                    if self.play_audio:
                        zombie_victory.start_effect()
                    self.alive_zombies.extend(self.dead_zombies.keys())
                    self.update_status('ending', 1)
                    win_controllers = self.alive_zombies
                if (time.time() - self.start_time) > self.win_time:
                    if self.play_audio:
                        human_victory.start_effect()
                    win_controllers = self.humans
                    self.update_status('ending', 0)
                if self.kill_game:
                    self.alive_zombies.extend(self.dead_zombies.keys())
                    win_controllers = self.humans + self.alive_zombies
                    self.update_status('killed')
                #This needs to go in it's own function
                while time.time() < pause_time:
                    for win_move in moves:
                        if win_move.get_serial() in win_controllers:
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
                if self.play_audio:
                    try:
                        self.music.stop_audio()
                    except:
                        print('no audio loaded')

    def check_command_queue(self):
        package = None
        while not(self.command_queue.empty()):
            package = self.command_queue.get()
            command = package['command']
        if not(package == None):
            if command == 'killgame':
                self.kill_game = True
                

    def update_status(self,game_status,winning_team=-1):
        data ={'game_status' : game_status,
               'game_mode' : 'Zombies',
               'winning_team' : winning_team,
               'humans': len(self.humans),
               'dead_zombies': len(self.dead_zombies),
               'alive_zombies': len(self.alive_zombies),
               'ticker': self.update_time,
               'time_left': int(self.win_time - (time.time() - self.start_time)),
               'team_names' : ['Humans', 'Zombies']}

        self.ns.status = data


