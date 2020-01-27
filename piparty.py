import psmove
import common, colors, joust, webui
import yaml
import time, random, json, os, os.path, sys, glob
from piaudio import Music, DummyMusic, Audio, InitAudio
from enum import Enum
from multiprocessing import Process, Value, Array, Queue, Manager, freeze_support
from games import ffa, zombie, commander, swapper, tournament, speed_bomb, fight_club
from sys import platform
if platform == "linux" or platform == "linux2":
    import jm_dbus
    import pair
elif "win" in platform:
    import win_jm_dbus as jm_dbus
    import win_pair as pair
import controller_process
import update

TEAM_NUM = len(colors.team_color_list)
#TEAM_COLORS = colors.generate_colors(TEAM_NUM)


SENSITIVITY_MODES = 5
RANDOM_TEAM_SIZES = 6

class Opts(Enum):
    alive = 0
    selection = 1
    holding = 2
    team = 3
    game_mode = 4
    random_start = 5

class Alive(Enum):
    on = 0
    off = 1

class Selections(Enum):
    nothing = 0
    change_mode_forward = 1
    change_mode_backward = 2
    add_game = 3
    change_sensitivity = 4
    change_instructions = 5
    show_battery = 6
    update = 7
    admin = 8
    change_setting_control = 9
    start_game = 10
    force_start_game = 11

class Holding(Enum):
    not_holding = 0
    holding = 1

class Sensitivity(Enum):
    ultra_slow = 0
    slow = 1
    mid = 2
    fast = 3
    ultra_fast = 4

def track_move(serial, move_num, move, move_opts, force_color, battery, dead_count, restart, menu, kill_proc):
    move.set_leds(0,0,0)
    move.update_leds()
    random_color = random.random()
    force_start_timer = 0


    while True:
        if(restart.value ==1 or menu.value == 0 or kill_proc.value):
            return
        time.sleep(0.01)
        if move.poll():
            game_mode = common.Games(move_opts[Opts.game_mode.value])
            move_button = common.Button(move.get_buttons())
            if move_opts[Opts.alive.value] == Alive.off.value:
                if move_button == common.Button.SYNC:
                    move_opts[Opts.alive.value] = Alive.on.value
                    dead_count.value = dead_count.value - 1
                time.sleep(0.1)
            else:
                if move_button == common.Button.SHAPES:
                    move_opts[Opts.selection.value] = Selections.admin.value
                    move_opts[Opts.holding.value] = Holding.holding.value

                if move_button == common.Button.UPDATE:
                    move_opts[Opts.selection.value] = Selections.update.value
                    move_opts[Opts.holding.value] = Holding.holding.value

                #show battery level
                if battery.value == 1:
                    battery_level = move.get_battery()
                    #granted a charging move should be dead
                    #so it won't light up anyway
                    if battery_level == psmove.Batt_CHARGING:
                        move.set_leds(*colors.Colors.White20.value)

                    elif battery_level == psmove.Batt_CHARGING_DONE:
                        move.set_leds(*colors.Colors.White.value)

                    elif battery_level == psmove.Batt_MAX:
                        move.set_leds(*colors.Colors.Green.value)

                    elif battery_level == psmove.Batt_80Percent:
                        move.set_leds(*colors.Colors.Turquoise.value)

                    elif battery_level == psmove.Batt_60Percent:
                        move.set_leds(*colors.Colors.Blue.value)

                    elif battery_level == psmove.Batt_40Percent:
                        move.set_leds(*colors.Colors.Yellow.value)

                    else : # under 40% - you should charge it!
                        move.set_leds(*colors.Colors.Red.value)

                #custom team mode is the only game mode that
                #can't be added to con mode
                elif game_mode == common.Games.JoustTeams:
                    if move_opts[Opts.team.value] >= TEAM_NUM:
                        move_opts[Opts.team.value] = 3
                    move.set_leds(*colors.team_color_list[move_opts[Opts.team.value]].value)


                #set leds to forced color
                elif sum(force_color) != 0:
                    move.set_leds(*force_color)

                elif game_mode == common.Games.JoustFFA:
                    move.set_leds(*colors.Colors.Orange.value)

                elif game_mode == common.Games.JoustRandomTeams:
                    color = time.time()/10%1
                    color = colors.hsv2rgb(color, 1, 1)
                    move.set_leds(*color)

                elif game_mode == common.Games.Traitor:
                    if move_num%4 == 2 and time.time()/3%1 < .15:
                        move.set_leds(*colors.Colors.Red80.value)
                    else:
                        color = 1 - time.time()/10%1
                        color = colors.hsv2rgb(color, 1, 1)
                        move.set_leds(*color)

                elif game_mode == common.Games.WereJoust:
                    if move_num <= 0:
                        move.set_leds(*colors.Colors.Blue40.value)
                    else:
                        move.set_leds(*colors.Colors.Yellow.value)

                elif game_mode == common.Games.Zombies:
                        move.set_leds(*colors.Colors.Zombie.value)

                elif game_mode == common.Games.Commander:
                    if move_num % 2 == 0:
                        move.set_leds(*colors.Colors.Orange.value)
                    else:
                        move.set_leds(*colors.Colors.Blue.value)

                elif game_mode == common.Games.Swapper:
                    if (time.time()/5 + random_color)%1 > 0.5:
                        move.set_leds(*colors.Colors.Magenta.value)
                    else:

                        move.set_leds(*colors.Colors.Green.value)

                elif game_mode == common.Games.FightClub:
                        move.set_leds(*colors.Colors.Green80.value)

                elif game_mode == common.Games.NonStop:
                        move.set_leds(*colors.Colors.Turquoise.value)

                elif game_mode == common.Games.Tournament:
                    if move_num <= 0:
                        color = time.time()/10%1
                        color = colors.hsv2rgb(color, 1, 1)
                        move.set_leds(*color)
                    else:
                        move.set_leds(*colors.Colors.Blue40.value)


                elif game_mode == common.Games.Ninja:
                    if move_num <= 0:
                        move.set_leds(random.randrange(100, 200),0,0)
                    else:
                        move.set_leds(*colors.Colors.Red60.value)


                elif game_mode == common.Games.Random:

                        move.set_leds(0,0,255)



                if move_opts[Opts.holding.value] == Holding.not_holding.value:
                    if move.get_trigger() > 100:
                            move_opts[Opts.selection.value] = Selections.start_game.value
                            move_opts[Opts.holding.value] = Holding.holding.value
                            force_start_timer = time.time()

                    #Change game mode backwards
                    if move_button == common.Button.SELECT:
                        move_opts[Opts.selection.value] = Selections.change_mode_backward.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                    #Change game mode forwards
                    if move_button == common.Button.START:
                        move_opts[Opts.selection.value] = Selections.change_mode_forward.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                    #as an admin controller add or remove game from convention mode
                    if move_button == common.Button.CROSS:
                        move_opts[Opts.selection.value] = Selections.add_game.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                    #as an admin controller change sensitivity of controllers
                    if move_button == common.Button.CIRCLE:
                        move_opts[Opts.selection.value] = Selections.change_sensitivity.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                    #as an admin controller change if instructions play
                    if move_button == common.Button.SQUARE:
                        move_opts[Opts.selection.value] = Selections.change_instructions.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                    #as an admin show battery level of controllers
                    if move_button == common.Button.TRIANGLE:
                        move_opts[Opts.selection.value] = Selections.show_battery.value
                        move_opts[Opts.holding.value] = Holding.holding.value
                        
                    if move_button == common.Button.MIDDLE:
                        #allow players to increase their own team
                        move_opts[Opts.selection.value] = Selections.change_setting_control.value
                        if game_mode == common.Games.JoustTeams:
                            move_opts[Opts.team.value] = (move_opts[Opts.team.value] + 1) % TEAM_NUM
                        move_opts[Opts.holding.value] = Holding.holding.value
                
                if  (move_opts[Opts.selection.value] == Selections.start_game.value and \
                     move_opts[Opts.holding.value] == Holding.holding.value and \
                     time.time()-force_start_timer >2):
                    move_opts[Opts.selection.value] = Selections.force_start_game.value
                    
                if move_opts[Opts.random_start.value] == Alive.off.value:
                    move.set_leds(255,255,255)


                if move_opts[Opts.holding.value] == Holding.holding.value and move_button == common.Button.NONE and move.get_trigger() <= 100:
                    move_opts[Opts.holding.value] = Holding.not_holding.value


        move.update_leds()

class Menu():
    def __init__(self):

        self.command_queue = Queue()
        self.joust_manager = Manager()
        self.ns = self.joust_manager.Namespace()
        self.web_proc = Process(target=webui.start_web, args=(self.command_queue,self.ns))
        self.web_proc.start()
        self.ns.status = dict()
        self.ns.settings = dict()
        self.ns.battery_status = dict()
        self.command_from_web = ''
        self.initialize_settings()
        self.update_settings_file()
        
        self.admin_options = ["random_team_size"]
        self.admin_control_option = 0

        #check for update
        if platform == "linux" or platform == "linux2":
            self.big_update = update.check_for_update(self.ns.settings['menu_voice'])
            self.git_hash = update.run_command("git rev-parse HEAD")[:7]
        else:
            self.git_hash = "0000000"


        #defined outside of ns.settings as it's a purely dev option
        self.experimental = False
        self.move_count = psmove.count_connected()
        self.dead_count = Value('i', 0)
        self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
        self.admin_move = None
        #move controllers that have been taken out of play
        self.out_moves = {}
        self.random_added = []
        self.rand_game_list = []

        self.show_battery = Value('i', 0)

        #only allow one move to be paired at a time
        self.pair_one_move = True
        self.tracked_moves = {}
        self.force_color = {}
        self.paired_moves = []
        self.move_opts = {}
        self.teams = {}
        self.game_mode = common.Games[self.ns.settings['current_game']]
        self.old_game_mode = self.game_mode
        self.pair = pair.Pair()

        self.menu = Value('i', 1)
        self.controller_game_mode = Value('i',1)
        self.restart = Value('i',0)
        self.controller_teams = {}
        self.controller_colors = {}
        self.dead_moves = {}
        self.music_speed= Value('d', 0)
        self.werewolf_reveal = Value('i', 2)
        self.show_team_colors = Value('i', 0)
        self.red_on_kill = Value('i', 0)
        self.zombie_opts = {}
        self.commander_intro = Value('i',1)
        self.commander_move_opts = {}
        self.commander_powers = [Value('d', 0.0), Value('d', 0.0)]
        self.commander_overdrive = [Value('i', 0), Value('i', 0)]
        self.five_controller_opts = {}
        self.swapper_team_colors = Array('i',[0]*6)
        self.fight_club_colors = {}
        self.invincible_moves = {}
        self.num_teams = Value('i',1)
        self.bomb_color = Array('i', [0] * 3)
        self.game_start = Value('i', 0)
        self.false_colors = {}
        self.was_faked = {}
        self.rumble = {}
        self.kill_controller_proc = {}
        self.controller_sensitivity = Array('d', [0] *10)
        self.dead_invince = Value('b', False)

        self.i = 0
        #load audio now so it converts before the game begins
        self.menu_music = Music("menu")
        self.joust_music = Music("joust")
        self.zombie_music = Music("zombie")
        self.commander_music = Music("commander")
        self.choose_new_music()


    def choose_new_music(self):
        self.joust_music.load_audio(random.choice(glob.glob("audio/Joust/music/*")))
        self.zombie_music.load_audio(random.choice(glob.glob("audio/Zombie/music/*")))
        self.commander_music.load_audio(random.choice(glob.glob("audio/Commander/music/*")))

    def check_for_new_moves(self):
        self.enable_bt_scanning(True)
        #need to start tracking of new moves in here

        if psmove.count_connected() != self.move_count:
            self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
            self.move_count = len(self.moves)
        #doesn't work
        #self.alive_count = len([move.get_serial() for move in self.moves if self.move_opts[move.get_serial()][Opts.alive.value] == Alive.on.value])


    def enable_bt_scanning(self, on=True):
        if platform == "linux" or platform == "linux2":
            bt_hcis = list(jm_dbus.get_hci_dict().keys())

            for hci in bt_hcis:
                if jm_dbus.enable_adapter(hci):
                    self.pair.update_adapters()
                if on:
                    jm_dbus.enable_pairable(hci)
                else:
                    jm_dbus.disable_pairable(hci)

    def pair_usb_move(self, move):
        move_serial = move.get_serial()
        if move_serial not in self.tracked_moves:
            if move.connection_type == psmove.Conn_USB:
                if move_serial not in self.paired_moves:
                    self.pair.pair_move(move)
                    move.set_leds(255,255,255)
                    move.update_leds()
                    self.paired_moves.append(move_serial)
                    self.pair_one_move = False

    def pair_move(self, move, move_num):
        move_serial = move.get_serial()
        if move_serial not in self.tracked_moves:
            color = Array('i', [0] * 3)
            opts = Array('i', [0] * 6)

            if move_serial in self.teams:
                opts[Opts.team.value] = self.teams[move_serial]
            else:
                #initialize to team Yellow
                opts[Opts.team.value] = 3
            if move_serial in self.out_moves:
                opts[Opts.alive.value] = self.out_moves[move_serial]
            opts[Opts.game_mode.value] = self.game_mode.value

            #now start tracking the move controller



            team = Value('i',0)
            team_color_enum = Array('i',[0]*3)
            dead_move = Value( 'i',0)
            zombie_opt = Array('i', [0, 0, 0, 1, 0, 1, 1])
            five_controller_opt = Array('i',[0]*5)


            commander_move_opt = Array('i', [0] * 5)
            invincibility = Value('b', True)
            fight_club_color = Value('i', 0)
            false_color = Value('i', 0)
            faked = Value('i', 0)
            rumble = Value('i', 0)
            kill_proc = Value('b', False)


            proc = Process(target= controller_process.main_track_move, args=(self.menu, self.restart, move_serial, move_num, opts, color, self.show_battery, \
                                                                              self.dead_count, self.controller_game_mode, team, team_color_enum, self.controller_sensitivity, dead_move, \
                                                                             self.music_speed, self.werewolf_reveal, self.show_team_colors, self.red_on_kill,zombie_opt,\
                                                                             self.commander_intro, commander_move_opt, self.commander_powers, self.commander_overdrive,\
                                                                             five_controller_opt, self.swapper_team_colors, invincibility, fight_club_color, self.num_teams,\
                                                                             self.bomb_color,self.game_start,false_color, faked, rumble, self.dead_invince, kill_proc))

            proc.start()
            self.move_opts[move_serial] = opts

            self.tracked_moves[move_serial] = proc
            self.force_color[move_serial] = color
            self.controller_teams[move_serial] = team
            self.controller_colors[move_serial] = team_color_enum
            self.dead_moves[move_serial] = dead_move
            self.zombie_opts[move_serial] = zombie_opt
            self.commander_move_opts[move_serial] = commander_move_opt
            self.five_controller_opts[move_serial] = five_controller_opt
            self.fight_club_colors[move_serial] = fight_club_color
            self.invincible_moves[move_serial] = invincibility
            self.false_colors[move_serial] = false_color
            self.was_faked[move_serial] = faked
            self.rumble[move_serial] = rumble
            self.kill_controller_proc[move_serial] = kill_proc
            self.out_moves[move.get_serial()] = Alive.on.value


    def remove_controller(self, move_serial):
            self.kill_controller_proc[move_serial].value = True
            self.tracked_moves[move_serial].join()
            self.tracked_moves[move_serial].terminate()
            del self.move_opts[move_serial]
            #del self.tracked_moves[move_serial]
            del self.force_color[move_serial]
            del self.controller_teams[move_serial]
            del self.controller_colors[move_serial]
            del self.dead_moves[move_serial]
            del self.zombie_opts[move_serial]
            del self.commander_move_opts[move_serial]
            del self.five_controller_opts[move_serial]
            del self.fight_club_colors[move_serial]
            del self.invincible_moves[move_serial]
            del self.false_colors[move_serial]
            del self.was_faked[move_serial]
            del self.rumble[move_serial]
            del self.kill_controller_proc[move_serial]

    def game_mode_announcement(self):
        if self.game_mode == common.Games.JoustFFA:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Joust FFA.wav').start_effect()
        if self.game_mode == common.Games.JoustTeams:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Joust Teams.wav').start_effect()
        if self.game_mode == common.Games.JoustRandomTeams:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Joust Random Teams.wav').start_effect()
        if self.game_mode == common.Games.Traitor:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Traitor.wav').start_effect()
        if self.game_mode == common.Games.WereJoust:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Werewolves.wav').start_effect()
        if self.game_mode == common.Games.Zombies:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Zombies.wav').start_effect()
        if self.game_mode == common.Games.Commander:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Commander.wav').start_effect()
        if self.game_mode == common.Games.Swapper:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Swapper.wav').start_effect()
        if self.game_mode == common.Games.Tournament:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Tournament.wav').start_effect()
        if self.game_mode == common.Games.Ninja:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu ninjabomb.wav').start_effect()
        if self.game_mode == common.Games.Random:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Random.wav').start_effect()
        if self.game_mode == common.Games.FightClub:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu FightClub.wav').start_effect()
        if self.game_mode == common.Games.NonStop:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu NonStopJoust.wav').start_effect()

    def check_game_trigger(self):
        for move, move_opt in self.move_opts.items():
            if move != self.admin_move:
                if move_opt[Opts.selection.value] == Selections.start_game.value:
                    move_opt[Opts.random_start.value] = Alive.off.value
                    move_opt[Opts.selection.value] = Selections.nothing.value
            else:
                if (move_opt[Opts.selection.value] == Selections.start_game.value and \
                    move_opt[Opts.holding.value] == Holding.not_holding.value):
                    #turn admin back to regular player
                    self.force_color[self.admin_move][0] = 0
                    self.force_color[self.admin_move][1] = 0
                    self.force_color[self.admin_move][2] = 0
                    self.admin_move = None
                    move_opt[Opts.selection.value] = Selections.nothing.value
            
        

    def check_change_mode(self):
        change_mode = False
        change_forward = True
        for move, move_opt in self.move_opts.items():
            if move != self.admin_move:
                if move_opt[Opts.selection.value] == Selections.change_mode_forward.value:
                    #change the game mode if allowed
                    if self.ns.settings['move_can_be_admin']:
                        change_mode = True
                        change_forward = True
                    move_opt[Opts.selection.value] = Selections.nothing.value

                if move_opt[Opts.selection.value] == Selections.change_mode_backward.value:
                    #change the game mode if allowed
                    if self.ns.settings['move_can_be_admin']:
                        change_mode = True
                        change_forward = False
                    move_opt[Opts.selection.value] = Selections.nothing.value

        if self.command_from_web == 'changemode':
            self.command_from_web = ''
            change_mode = True

        if change_mode:
            if change_forward:
                self.game_mode = self.game_mode.next()
            else:
                self.game_mode = self.game_mode.previous()
            self.update_setting('current_game',self.game_mode.name)
            self.reset_controller_game_state()
            if not self.ns.settings['play_audio']:
                if self.game_mode == common.Games.Commander:
                    self.game_mode = self.game_mode.next()
                if self.game_mode == common.Games.WereJoust:
                    self.game_mode = self.game_mode.next()
            for opt in self.move_opts.values():
                opt[Opts.game_mode.value] = self.game_mode.value
            if self.ns.settings['play_audio']:
                self.game_mode_announcement()

    def check_new_admin(self):
        for move, move_opt in self.move_opts.items():
            if move_opt[Opts.selection.value] == Selections.admin.value:
                #remove previous admin, and set new one
                if self.ns.settings['move_can_be_admin']:
                    #set the old admin_move to have no colors
                    if self.admin_move:
                        self.force_color[self.admin_move][0] = 0
                        self.force_color[self.admin_move][1] = 0
                        self.force_color[self.admin_move][2] = 0
                    self.admin_move = move
                move_opt[Opts.selection.value] = Selections.nothing.value


    #all controllers need to opt-in again in order fo the game to start
    def reset_controller_game_state(self):
        for move_opt in self.move_opts.values():
            #on means off here
            move_opt[Opts.random_start.value] = Alive.on.value
        for serial in self.move_opts.keys():
            for i in range(3):
                self.force_color[serial][i] = 0
        self.random_added = []

    def check_update(self):
         for move, move_opt in self.move_opts.items():
            if move_opt[Opts.selection.value] == Selections.update.value:
                if self.big_update:
                    update.big_update(self.ns.settings['menu_voice'])
                    self.big_update = False

    def game_loop(self):
        self.play_menu_music = True
        while True:
            if self.play_menu_music:
                self.play_menu_music = False
                self.menu_music.load_audio(random.choice(glob.glob("audio/Menu/music/*")))
                self.menu_music.start_audio_loop()
            self.i=self.i+1
            if "linux" in platform:
                if not self.pair_one_move and "0" in os.popen('lsusb | grep "PlayStation Move motion controller" | wc -l').read():
                    self.pair_one_move = True
                    self.paired_moves = []
            else:
                if not self.pair_one_move:
                    self.pair_one_move = True
                    self.paired_moves = []
            if self.pair_one_move:
                #check if there are any controllers that were shut off
                if psmove.count_connected() > len(self.tracked_moves):
                    for move_num, move in enumerate(self.moves):
                        if move.connection_type == psmove.Conn_USB and self.pair_one_move:
                            self.pair_usb_move(move)
                        elif move.connection_type != psmove.Conn_USB:
                            self.pair_move(move, move_num)
                elif(len(self.tracked_moves) > len(self.moves)):
                    connected_serials = [x.get_serial() for x in self.moves]
                    tracked_serials = self.tracked_moves.keys()
                    keys_to_kill = []
                    for serial in tracked_serials:
                        if serial not in connected_serials:
                            #self.kill_controller_proc[serial].value = True
                            self.remove_controller(serial)
                            #self.tracked_moves[serial].join()
                            #self.tracked_moves[serial].terminate()
                            keys_to_kill.append(serial)
                    for key in keys_to_kill:
                        del self.tracked_moves[key]
                        if key == self.admin_move:
                            self.admin_move = None

                self.check_for_new_moves()
                if len(self.tracked_moves) > 0:
                    self.check_new_admin()
                    self.check_change_mode()
                    self.check_game_trigger()
                    self.check_admin_controls()
                    self.check_start_game()
                    self.check_update()
                self.check_command_queue()
                self.update_status('menu')


    def check_admin_controls(self):
        show_bat = False
        for move_opt in self.move_opts.values():
            if move_opt[Opts.selection.value] == Selections.show_battery.value and move_opt[Opts.holding.value] == Holding.holding.value:
                show_bat = True
        if show_bat:
            self.show_battery.value = 1
        else:
            self.show_battery.value = 0

        if not self.ns.settings['move_can_be_admin'] and self.admin_move != None:
            self.force_color[self.admin_move][0] = 0
            self.force_color[self.admin_move][1] = 0
            self.force_color[self.admin_move][2] = 0
            self.admin_move = None

        if self.admin_move:
            #you can't add custom teams mode to con mode, don't set colors
            admin_opt = self.move_opts[self.admin_move]
            
            if admin_opt[Opts.selection.value] == Selections.force_start_game.value:
                admin_opt[Opts.random_start.value] = Alive.off.value
                self.start_game()
                return;
            
            #change game settings
            if admin_opt[Opts.selection.value] == Selections.change_setting_control.value:
                admin_opt[Opts.selection.value] = Selections.nothing.value
                self.admin_control_option = (self.admin_control_option + 1) % len(self.admin_options)
                if(self.admin_options[self.admin_control_option] == 'random_team_size'):
                    Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/adminop_random_team_size.wav').start_effect()
                    
            if admin_opt[Opts.selection.value] == Selections.change_mode_forward.value:
                admin_opt[Opts.selection.value] = Selections.nothing.value
                if(self.admin_options[self.admin_control_option] == 'random_team_size'):
                    self.update_setting('random_team_size', (self.ns.settings['random_team_size'] + 1) %  (RANDOM_TEAM_SIZES+1))
                    if (self.ns.settings['random_team_size'] < 2):
                        self.update_setting('random_team_size', 2)
                    Audio('audio/Menu/vox/{}/adminop_{}.wav'.format(self.ns.settings['menu_voice'],self.ns.settings['random_team_size'])).start_effect()
                
            if admin_opt[Opts.selection.value] == Selections.change_mode_backward.value:
                admin_opt[Opts.selection.value] = Selections.nothing.value
                if(self.admin_options[self.admin_control_option] == 'random_team_size'):
                    self.update_setting('random_team_size', (self.ns.settings['random_team_size'] - 1))
                    if (self.ns.settings['random_team_size'] < 2):
                        self.update_setting('random_team_size', RANDOM_TEAM_SIZES)
                    Audio('audio/Menu/vox/{}/adminop_{}.wav'.format(self.ns.settings['menu_voice'],self.ns.settings['random_team_size'])).start_effect()
                
            #to play instructions or not
            if admin_opt[Opts.selection.value] == Selections.change_instructions.value:
                admin_opt[Opts.selection.value] = Selections.nothing.value
                self.update_setting('play_instructions', not self.ns.settings['play_instructions'])
                if self.ns.settings['play_audio']:
                    if self.ns.settings['play_instructions']:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/instructions_on.wav').start_effect()
                    else:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/instructions_off.wav').start_effect()

            #change sensitivity
            if admin_opt[Opts.selection.value] == Selections.change_sensitivity.value:
                admin_opt[Opts.selection.value] = Selections.nothing.value

                self.update_setting('sensitivity', (self.ns.settings['sensitivity'] + 1) %  SENSITIVITY_MODES)
                if self.ns.settings['play_audio']:
                    if self.ns.settings['sensitivity'] == Sensitivity.ultra_slow.value:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/ultra_high.wav').start_effect()
                    elif self.ns.settings['sensitivity'] == Sensitivity.slow.value:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/high.wav').start_effect()
                    elif self.ns.settings['sensitivity'] == Sensitivity.mid.value:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/medium.wav').start_effect()
                    elif self.ns.settings['sensitivity'] == Sensitivity.fast.value:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/low.wav').start_effect()
                    elif self.ns.settings['sensitivity'] == Sensitivity.ultra_fast.value:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/ultra_low.wav').start_effect()

            #no admin colors in con custom teams mode
            if self.game_mode == common.Games.JoustTeams or self.game_mode == common.Games.Random:
                self.force_color[self.admin_move][0] = 0
                self.force_color[self.admin_move][1] = 0
                self.force_color[self.admin_move][2] = 0
            else:
                #if game is in con mode, admin is green, otherwise admin is red
                if self.game_mode.name in self.ns.settings['random_modes']:
                    self.force_color[self.admin_move][0] = 0
                    self.force_color[self.admin_move][1] = 200

                else:
                    self.force_color[self.admin_move][0] = 200
                    self.force_color[self.admin_move][1] = 0

                #add or remove game from con mode
                if admin_opt[Opts.selection.value] == Selections.add_game.value:
                    admin_opt[Opts.selection.value] = Selections.nothing.value
                    if self.game_mode.name not in self.ns.settings['random_modes']:
                        temp_random_modes = self.ns.settings['random_modes']
                        temp_random_modes.append(self.game_mode.name)
                        self.update_setting('random_modes',temp_random_modes)
                        if self.ns.settings['play_audio']:
                            Audio('audio/Menu/sounds/game_on.wav').start_effect()
                    elif len(self.ns.settings['random_modes']) > 1:
                        temp_random_modes = self.ns.settings['random_modes']
                        temp_random_modes.remove(self.game_mode.name)
                        self.update_setting('random_modes',temp_random_modes)
                        if self.ns.settings['play_audio']:
                            Audio('audio/Menu/sounds/game_off.wav').start_effect()
                    else:
                        if self.ns.settings['play_audio']:
                            Audio('audio/Menu/sounds/game_err.wav').start_effect()
                    self.update_settings_file()

    def initialize_settings(self):
        #default settings
        temp_settings = ({
            'sensitivity': Sensitivity.mid.value,
            'play_instructions': True,
            #we store the name, not the enum, so the webui can process it more easily
            'random_modes': [common.Games.JoustFFA.name,common.Games.JoustRandomTeams.name,common.Games.WereJoust.name,common.Games.Swapper.name],
            'current_game': common.Games.JoustFFA.name,
            'play_audio': True,
            'menu_voice': 'ivy',
            'move_can_be_admin': True,
            'enforce_minimum': True,
            'red_on_kill': True,
            'random_teams': True,
            'color_lock': False,
            'random_team_size': 4,
            'color_lock_choices':{
                2: ['Magenta','Green'],
                3: ['Orange','Turquoise','Purple'],
                4: ['Yellow','Green','Blue','Purple']
            }
        })
        try:
            #if anything fails during the settings file load, ignore file and stick with defaults
            with open(common.SETTINGSFILE,'r') as yaml_file:
                file_settings = yaml.load(yaml_file)

            temp_colors = file_settings['color_lock_choices']
            for key in temp_colors.keys():
                colorset = temp_colors[key]
                if len(colorset) != len(set(colorset)):
                    temp_colors[key] = temp_settings['color_lock_choices'][key]

            for setting in file_settings.keys():
                if setting not in common.REQUIRED_SETTINGS:
                    file_settings.pop(setting)

            for game in [common.Games.JoustTeams,common.Games.Random]:
                if game.name in file_settings['random_modes']:
                    file_settings['random_modes'].remove(game.name)
            for game in file_settings['random_modes']:
                if game not in [game.name for game in common.Games]:
                    file_settings['random_modes'].remove(game)
            if file_settings['random_modes'] == []:
                file_settings['random_modes'] = [common.Games.JoustFFA.name]

            temp_settings.update(file_settings)
            temp_settings['color_lock_choices'] = temp_colors

        except:
            pass

        #force these settings
        temp_settings.update({
            'play_audio': True,
            'move_can_be_admin': True,
            'enforce_minimum': True
        })
        self.ns.settings = temp_settings

    def update_settings_file(self):
        with open(common.SETTINGSFILE,'w') as yaml_file:
            yaml.dump(self.ns.settings,yaml_file)
        #option to make file editable by non-root
        #let's leave it as root only, people shouldn't
        #mess with the config file for now
        if platform == "linux" or platform == "linux2":
            os.system('chmod 666 %s' % common.SETTINGSFILE)

    def update_setting(self,key,val):
        temp_settings = self.ns.settings
        temp_settings[key] = val
        self.ns.settings = temp_settings
        self.update_settings_file()


    def check_command_queue(self):
        if not(self.command_queue.empty()):
            package = self.command_queue.get()
            command = package['command']
            if command == 'admin_update':
                self.web_admin_update(package['admin_info'])
            else:
                self.command_from_web = command

    def update_status(self,game_status):
        self.ns.status ={
            'game_status' : game_status,
            'game_mode' : self.game_mode.pretty_name,
            'move_count' : self.move_count,
            'alive_count' : self.move_count - self.dead_count.value,
            'ticker': self.i,
            'git_hash': self.git_hash
        }

        battery_status = {}
        for move in self.moves:
            move.poll()
            battery_status[move.get_serial()] = move.get_battery()
        self.ns.battery_status = battery_status

        self.ns.out_moves = self.out_moves

    def stop_tracking_moves(self):
        for proc in self.tracked_moves.values():
            proc.terminate()
            proc.join()

    def check_start_game(self):
        #if self.game_mode == common.Games.Random:
            start_game = True
            for serial in self.move_opts.keys():
                #on means off here
                if self.out_moves[serial] == Alive.on.value and self.move_opts[serial][Opts.random_start.value] == Alive.on.value:
                    start_game = False
                if self.move_opts[serial][Opts.random_start.value] == Alive.off.value and serial not in self.random_added:
                    self.random_added.append(serial)
                    if self.ns.settings['play_audio']:
                        Audio('audio/Joust/sounds/start.wav').start_effect()


            if start_game:
                print("starting game")
                if self.game_mode == common.Games.Random:
                    self.start_game(random_mode=True)
                else:
                    self.start_game()


        #else:
        #    if self.ns.settings['move_can_be_admin']:
        #        for move_opt in self.move_opts.values():
        #            if move_opt[Opts.selection.value] == Selections.start_game.value:
        #                self.start_game()
            if self.command_from_web == 'startgame':
                self.command_from_web = ''
                self.start_game()

    def play_random_instructions(self):
        if self.game_mode == common.Games.JoustFFA:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/FFA-instructions.wav').start_effect_and_wait()
        if self.game_mode == common.Games.JoustRandomTeams:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Teams-instructions.wav').start_effect_and_wait()
        if self.game_mode == common.Games.Traitor:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Traitor-instructions.wav').start_effect_and_wait()
        if self.game_mode == common.Games.WereJoust:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/werewolf-instructions.wav').start_effect_and_wait()
        if self.game_mode == common.Games.Zombies:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/zombie-instructions.wav').start_effect_and_wait()
        if self.game_mode == common.Games.Commander:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/commander-instructions.wav').start_effect_and_wait()
        if self.game_mode == common.Games.Ninja:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Ninjabomb-instructions.wav').start_effect_and_wait()
        if self.game_mode == common.Games.Swapper:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Swapper-instructions.wav').start_effect_and_wait()
        if self.game_mode == common.Games.Tournament:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Tournament-instructions.wav').start_effect_and_wait()
        if self.game_mode == common.Games.FightClub:
            if self.ns.settings['menu_voice'] == 'aaron':
                os.popen('espeak -ven -p 70 -a 200 "Two players fight, the winner must defend their title, the player with the highest score wins')
            else:
                Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Fightclub-instructions.wav').start_effect_and_wait()
            time.sleep(5)


    def start_game(self, random_mode=False):
        self.enable_bt_scanning(False)
        time.sleep(1)
        self.teams = {serial: self.move_opts[serial][Opts.team.value] for serial in self.tracked_moves.keys() if self.out_moves[serial] == Alive.on.value}
        game_moves = [move.get_serial() for move in self.moves if self.out_moves[move.get_serial()] == Alive.on.value and (self.move_opts[move.get_serial()])[Opts.random_start.value] == Alive.off.value  ]
        try:
            self.menu_music.stop_audio()
        except:
            pass

        if len(game_moves) < self.game_mode.minimum_players and self.ns.settings['enforce_minimum']:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/notenoughplayers.wav').start_effect()
            self.reset_controller_game_state()
            return
        self.menu.value = 0
        self.restart.value =1
        self.update_status('starting')

        self.sensitivity = self.ns.settings['sensitivity']
        self.controller_sensitivity[0] = common.SLOW_MAX[self.sensitivity]
        self.controller_sensitivity[1] = common.SLOW_WARNING[self.sensitivity]
        self.controller_sensitivity[2] = common.FAST_MAX[self.sensitivity]
        self.controller_sensitivity[3] = common.FAST_WARNING[self.sensitivity]

        self.controller_sensitivity[4] = common.WERE_SLOW_MAX[self.sensitivity]
        self.controller_sensitivity[5] = common.WERE_SLOW_WARNING[self.sensitivity]
        self.controller_sensitivity[6] = common.WERE_FAST_MAX[self.sensitivity]
        self.controller_sensitivity[7] = common.WERE_FAST_WARNING[self.sensitivity]

        self.controller_sensitivity[8] = common.ZOMBIE_MAX[self.sensitivity]
        self.controller_sensitivity[9] = common.ZOMBIE_WARNING[self.sensitivity]

        if random_mode:
            good_random_modes = [game for game in common.Games if game.name in self.ns.settings['random_modes']]
            good_random_modes = [common.Games[game] for game in self.ns.settings['random_modes']]
            if self.ns.settings['enforce_minimum']:
                good_random_modes = [game for game in good_random_modes if game.minimum_players <= len(game_moves)]
            if len(good_random_modes) == 0:
                selected_game = common.Games.JoustFFA  #force Joust FFA
            elif len(good_random_modes) == 1:
                selected_game = good_random_modes[0]
            else:
                if len(self.rand_game_list) >= len(good_random_modes):
                    #empty rand game list, append old game, to not play it twice
                    self.rand_game_list = [self.old_game_mode]

                selected_game = random.choice(good_random_modes)
                while selected_game in self.rand_game_list:
                    selected_game = random.choice(good_random_modes)

                self.old_game_mode = selected_game
                self.rand_game_list.append(selected_game)

            self.game_mode = selected_game
        self.controller_game_mode.value = self.game_mode.value

        if self.ns.settings['play_instructions'] and self.ns.settings['play_audio']:
            self.play_random_instructions()

        if self.game_mode == common.Games.Zombies:
            zombie.Zombie(game_moves, self.command_queue, self.ns, self.zombie_music, self.restart, self.zombie_opts)
        elif self.game_mode == common.Games.Commander:
            commander.Commander(game_moves, self.command_queue, self.ns, self.commander_music, self.dead_moves,  self.commander_intro, self.commander_move_opts, \
                                self.commander_powers, self.commander_overdrive, self.music_speed, self.force_color, self.restart, self.controller_teams)
        elif self.game_mode == common.Games.Ninja:
            speed_bomb.Bomb(game_moves, self.command_queue, self.ns, self.commander_music,  self.bomb_color, self.game_start, self.five_controller_opts, self.dead_moves, self.force_color, self.false_colors, self.was_faked, self.rumble, self.music_speed,self.restart)
        elif self.game_mode == common.Games.Swapper:
            swapper.Swapper(game_moves, self.command_queue, self.ns, self.joust_music, \
                            self.swapper_team_colors, self.dead_moves, self.music_speed, self.force_color, self.five_controller_opts, self.controller_teams, self.restart)
        elif self.game_mode == common.Games.FightClub:
            if random.randint(0,1)==1:
                fight_music = self.commander_music
            else:
                fight_music = self.joust_music
            fight_club.Fight_club(game_moves, self.command_queue, self.ns, fight_music, self.show_team_colors, self.music_speed, self.dead_moves, self.force_color, self.invincible_moves, self.fight_club_colors, self.restart)
        elif self.game_mode == common.Games.Tournament:
            tournament.Tournament(game_moves, self.command_queue, self.ns, self.joust_music,  self.show_team_colors, self.music_speed, self.controller_teams, self.dead_moves, self.force_color, self.invincible_moves, self.num_teams, self.restart)
        else:
            if self.game_mode == common.Games.JoustFFA and self.experimental:
                print("Playing EXPERIMENTAL FFA Mode.")
                moves = [ common.get_move(serial, num) for num, serial in enumerate(game_moves) ]
                game = ffa.FreeForAll(moves, self.joust_music)
                game.run_loop()
            else:
                #may need to put in moves that have selected to not be in the game
                joust.Joust(game_moves, self.command_queue, self.ns, self.joust_music, self.teams, self.game_mode, self.controller_teams, self.controller_colors, self.dead_moves, self.force_color,self.music_speed,self.werewolf_reveal, self.show_team_colors, self.red_on_kill, self.restart,self.ns.settings['random_team_size'])
        if random_mode:
            self.game_mode = common.Games.Random
            if self.ns.settings['play_instructions']:
                if self.ns.settings['play_audio']:
                    Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/tradeoff2.wav').start_effect_and_wait()
        self.play_menu_music = True
        #reset music
        self.choose_new_music()
        #turn off admin mode so someone can't accidentally press a button
        self.admin_move = None
        self.random_added = []
        self.reset_controller_game_state()
        self.menu.value = 1
        self.restart.value =0
        self.reset_controller_game_state()


if __name__ == "__main__":
    if "win" in platform:
        freeze_support()
    InitAudio()
    piparty = Menu()
    piparty.game_loop()
