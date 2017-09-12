import psmove, pair
import common, colors, joust, webui
import yaml
import zombie, commander, swapper, tournament, speed_bomb
import time, random, json, os, os.path, sys, glob
from piaudio import Audio
from enum import Enum
from multiprocessing import Process, Value, Array, Queue, Manager

TEAM_NUM = len(colors.TeamColors)
#TEAM_COLORS = colors.generate_colors(TEAM_NUM)

#the number of game modes
GAME_MODES = len(common.Games)

SENSITIVITY_MODES = 3

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
    change_mode = 1
    start_game = 2
    add_game = 3
    change_sensitivity = 4
    change_instructions = 5
    show_battery = 6

class Holding(Enum):
    not_holding = 0
    holding = 1

class Sensitivity(Enum):
    slow = 0
    mid = 1
    fast = 2


#These buttons are based off of
#The mapping of PS Move controllers
class Buttons(Enum):
    middle = 524288
    all_buttons = 240
    sync = 65536
    start = 2048
    select = 256
    circle = 32
    triangle = 16
    cross = 64
    square = 128
    nothing = 0

def track_move(serial, move_num, move_opts, force_color, battery, dead_count):
    move = common.get_move(serial, move_num)
    move.set_leds(0,0,0)
    move.update_leds()
    random_color = random.random()

    
    while True:
        time.sleep(0.01)
        if move.poll():
            game_mode = move_opts[Opts.game_mode.value]
            move_button = move.get_buttons()
            if move_opts[Opts.alive.value] == Alive.off.value:
                if move_button == Buttons.sync.value:
                    move_opts[Opts.alive.value] = Alive.on.value
                    dead_count.value = dead_count.value - 1
                time.sleep(0.1)
            else:
                if move_button == Buttons.all_buttons.value:
                    move_opts[Opts.alive.value] = Alive.off.value
                    dead_count.value = dead_count.value + 1
                    move.set_leds(0,0,0)
                    move.set_rumble(0)
                    move.update_leds()
                    continue

                #show battery level
                if battery.value == 1:
                    battery_level = move.get_battery()
                    #granted a charging move should be dead 
                    #so it won't light up anyway
                    if battery_level == 238: # charging - dim
                        move.set_leds(10,10,10)
                    elif battery_level == 239: # fully charged - white
                        move.set_leds(255,255,255)
                    elif battery_level == 5: # full - green
                        move.set_leds(0,255,0)
                    elif battery_level == 4: # 75% - cyan
                        move.set_leds(0,255,255)
                    elif battery_level == 3: # 50% - blue
                        move.set_leds(0,0,255)
                    elif battery_level == 2: # 25% - yellow
                        move.set_leds(191,255,0)
                    else : # under 25% - red
                        move.set_leds(0, 0, 0)
                    
                #custom team mode is the only game mode that
                #can't be added to con mode
                elif game_mode == common.Games.JoustTeams.value:
                    if move_opts[Opts.team.value] >= TEAM_NUM:
                        move_opts[Opts.team.value] = 0
                    move.set_leds(*colors.color_list[move_opts[Opts.team.value]].value)
                    if move_button == Buttons.middle.value:
                        #allow players to increase their own team
                        if move_opts[Opts.holding.value] == Holding.not_holding.value:
                            move_opts[Opts.team.value] = (move_opts[Opts.team.value] + 1) % TEAM_NUM
                            move_opts[Opts.holding.value] = Holding.holding.value

                #set leds to forced color
                elif sum(force_color) != 0:
                    move.set_leds(*force_color)

                elif game_mode == common.Games.JoustFFA.value:
                    move.set_leds(*colors.ExtraColors.White.value)
                            
                            
                elif game_mode == common.Games.JoustRandomTeams.value:
                    color = time.time()/10%1
                    color = colors.hsv2rgb(color, 1, 1)
                    move.set_leds(*color)

                elif game_mode == common.Games.Traitor.value:
                    if move_num%4 == 2 and time.time()/3%1 < .15:
                        move.set_leds(*colors.ExtraColors.Red80.value)
                    else:
                        color = 1 - time.time()/10%1
                        color = colors.hsv2rgb(color, 1, 1)
                        move.set_leds(*color)

                elif game_mode == common.Games.WereJoust.value:
                    if move_num <= 0:
                        move.set_leds(*colors.ExtraColors.Red60.value)
                    else:
                        move.set_leds(*colors.ExtraColors.White80.value)

                elif game_mode == common.Games.Zombies.value:
                        move.set_leds(*colors.ExtraColors.Zombie.value)

                elif game_mode == common.Games.Commander.value:
                    if move_num % 2 == 0:
                        move.set_leds(*colors.TeamColors.Orange.value)
                    else:
                        move.set_leds(*colors.TeamColors.Blue.value)

                elif game_mode == common.Games.Swapper.value:
                    if (time.time()/5 + random_color)%1 > 0.5:
                        move.set_leds(*colors.TeamColors.Magenta.value)
                    else:
                        move.set_leds(*colors.TeamColors.Green.value)
                elif game_mode == common.Games.Tournament.value:
                    if move_num <= 0:
                        color = time.time()/10%1
                        color = colors.hsv2rgb(color, 1, 1)
                        move.set_leds(*color)
                    else:
                        move.set_leds(*colors.ExtraColors.White80.value)


                elif game_mode == common.Games.Ninja.value:
                    if move_num <= 0:
                        move.set_leds(random.randrange(100, 200),0,0)
                    else:
                        move.set_leds(*colors.ExtraColors.White80.value)


                elif game_mode == common.Games.Random.value:
                    
                    if move_button == Buttons.middle.value:
                        move_opts[Opts.random_start.value] = Alive.off.value
                    if move_opts[Opts.random_start.value] == Alive.on.value:
                        move.set_leds(0,0,255)
                    else:
                        move.set_leds(255,255,0)
                    

                if move_opts[Opts.holding.value] == Holding.not_holding.value:
                    #Change game mode and become admin controller
                    if move_button == Buttons.select.value:
                        move_opts[Opts.selection.value] = Selections.change_mode.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                    #start the game
                    if move_button == Buttons.start.value:
                        move_opts[Opts.selection.value] = Selections.start_game.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                    #as an admin controller add or remove game from convention mode
                    if move_button == Buttons.cross.value:
                        move_opts[Opts.selection.value] = Selections.add_game.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                    #as an admin controller change sensitivity of controllers
                    if move_button == Buttons.circle.value:
                        move_opts[Opts.selection.value] = Selections.change_sensitivity.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                    #as an admin controller change if instructions play
                    if move_button == Buttons.square.value:
                        move_opts[Opts.selection.value] = Selections.change_instructions.value
                        move_opts[Opts.holding.value] = Holding.holding.value

                    #as an admin show battery level of controllers
                    if move_button == Buttons.triangle.value:
                        move_opts[Opts.selection.value] = Selections.show_battery.value
                        move_opts[Opts.holding.value] = Holding.holding.value
                    

                if move_button == Buttons.nothing.value:
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

        self.move_count = psmove.count_connected()
        self.dead_count = Value('i', 0)
        self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
        self.admin_move = None
        #move controllers that have been taken out of play
        self.out_moves = {}
        self.random_added = []
        self.rand_game_list = []

        self.show_battery = Value('i', 0)
        
        self.tracked_moves = {}
        self.force_color = {}
        self.paired_moves = []
        self.move_opts = {}
        self.teams = {}
        self.game_mode = common.Games.Random.value
        self.old_game_mode = common.Games.Random.value
        self.pair = pair.Pair()

        self.i = 0
        #load audio now so it converts before the game begins
        self.choose_new_music()

    def choose_new_music(self):
        self.joust_music = Audio(random.choice(glob.glob("audio/Joust/music/*")),False)
        try:
            self.zombie_music = Audio(random.choice(glob.glob("audio/Zombie/music/*")),False)
        except Exception:
            self.zombie_music = Audio("",False,False)
        try:
            self.commander_music = Audio(random.choice(glob.glob("audio/Commander/music/*")),False)
        except Exception:
            self.commander_music = Audio("",False,False)

    def exclude_out_moves(self):
        for move in self.moves:
            serial = move.get_serial()
            if serial in self.move_opts:
                if self.move_opts[move.get_serial()][Opts.alive.value] == Alive.off.value:
                    self.out_moves[move.get_serial()] = Alive.off.value
                else:
                    self.out_moves[move.get_serial()] = Alive.on.value

    def check_for_new_moves(self):
        self.enable_bt_scanning(True)
        #need to start tracking of new moves in here
        if psmove.count_connected() != self.move_count:
            self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
            self.move_count = len(self.moves)
        #doesn't work
        #self.alive_count = len([move.get_serial() for move in self.moves if self.move_opts[move.get_serial()][Opts.alive.value] == Alive.on.value])
        

    def enable_bt_scanning(self, on=True):
        scan_cmd = "hciconfig {0} {1}"
        if on:
            scan = "pscan"
        else:
            scan = "noscan"
        bt_hcis = os.popen("hcitool dev | grep hci | awk '{print $1}'").read().split('\n')
        bt_hcis = [bt for bt in bt_hcis if bt]
        for hci in bt_hcis:
            scan_enabled = os.popen(scan_cmd.format(hci, scan)).read()
        if not bt_hcis:
            for i in range(8):
                os.popen("sudo hciconfig hci{} up".format(i))

            
        
    def pair_move(self, move, move_num):
        move_serial = move.get_serial()
        if move_serial not in self.tracked_moves:
            if move.connection_type == psmove.Conn_USB:
                if move_serial not in self.paired_moves:
                    self.pair.pair_move(move)
                    move.set_leds(255,255,255)
                    move.update_leds()
                    self.paired_moves.append(move_serial)
            #the move is connected via bluetooth
            else:
                color = Array('i', [0] * 3)
                opts = Array('i', [0] * 6)
                if move_serial in self.teams:
                    opts[Opts.team.value] = self.teams[move_serial]
                if move_serial in self.out_moves:
                    opts[Opts.alive.value] = self.out_moves[move_serial]
                opts[Opts.game_mode.value] = self.game_mode
                opts[Opts.team.value] = 3 #starts at yellow
                
                #now start tracking the move controller
                proc = Process(target=track_move, args=(move_serial, move_num, opts, color, self.show_battery, self.dead_count))
                proc.start()
                self.move_opts[move_serial] = opts
                self.tracked_moves[move_serial] = proc
                self.force_color[move_serial] = color
                self.exclude_out_moves()


    def game_mode_announcement(self):
        if self.game_mode == common.Games.JoustFFA.value:
            Audio('audio/Menu/menu Joust FFA.wav').start_effect()
        if self.game_mode == common.Games.JoustTeams.value:
            Audio('audio/Menu/menu Joust Teams.wav').start_effect()
        if self.game_mode == common.Games.JoustRandomTeams.value:
            Audio('audio/Menu/menu Joust Random Teams.wav').start_effect()
        if self.game_mode == common.Games.Traitor.value:
            Audio('audio/Menu/menu Traitor.wav').start_effect()
        if self.game_mode == common.Games.WereJoust.value:
            Audio('audio/Menu/menu werewolfs.wav').start_effect()
        if self.game_mode == common.Games.Zombies.value:
            Audio('audio/Menu/menu Zombies.wav').start_effect()
        if self.game_mode == common.Games.Commander.value:
            Audio('audio/Menu/menu Commander.wav').start_effect()
        if self.game_mode == common.Games.Swapper.value:
            Audio('audio/Menu/menu Swapper.wav').start_effect()
        if self.game_mode == common.Games.Tournament.value:
            Audio('audio/Menu/menu Tournament.wav').start_effect()
        if self.game_mode == common.Games.Ninja.value:
            Audio('audio/Menu/menu ninjabomb.wav').start_effect()
        if self.game_mode == common.Games.Random.value:
            Audio('audio/Menu/menu Random.wav').start_effect()

    def check_change_mode(self):
        change_mode = False
        for move, move_opt in self.move_opts.items():
            if move_opt[Opts.selection.value] == Selections.change_mode.value:
                #remove previous admin, and set new one
                if self.ns.settings['move_can_be_admin']:
                    if self.admin_move:
                        self.force_color[self.admin_move][0] = 0
                        self.force_color[self.admin_move][1] = 0
                        self.force_color[self.admin_move][2] = 0
                    self.admin_move = move
                    change_mode = True
                move_opt[Opts.selection.value] = Selections.nothing.value

        if self.command_from_web == 'changemode':
            self.command_from_web = ''
            change_mode = True

        if change_mode:
            self.game_mode = (self.game_mode + 1) %  GAME_MODES
            if not self.ns.settings['play_audio']:
                if self.game_mode == common.Games.Commander.value:
                    self.game_mode = (self.game_mode + 1) %  GAME_MODES
                if self.game_mode == common.Games.WereJoust.value:
                    self.game_mode = (self.game_mode + 1) %  GAME_MODES
            for opt in self.move_opts.values():
                opt[Opts.game_mode.value] = self.game_mode
            if self.ns.settings['play_audio']:
                self.game_mode_announcement()


    def game_loop(self):
        while True:
            self.i=self.i+1
            if psmove.count_connected() != len(self.tracked_moves):
                for move_num, move in enumerate(self.moves):
                    self.pair_move(move, move_num)
            self.check_for_new_moves()
            if len(self.tracked_moves) > 0:
                self.check_change_mode()
                self.check_admin_controls()
                self.check_start_game()
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

            #to play instructions or not
            if admin_opt[Opts.selection.value] == Selections.change_instructions.value:
                admin_opt[Opts.selection.value] = Selections.nothing.value
                self.update_setting('play_instructions', not self.ns.settings['play_instructions'])
                if self.ns.settings['play_audio']:
                    if self.ns.settings['play_instructions']:
                        Audio('audio/Menu/instructions_on.wav').start_effect()
                    else:
                        Audio('audio/Menu/instructions_off.wav').start_effect()

            #change sensitivity
            if admin_opt[Opts.selection.value] == Selections.change_sensitivity.value:
                admin_opt[Opts.selection.value] = Selections.nothing.value

                self.update_setting('sensitivity', (self.ns.settings['sensitivity'] + 1) %  SENSITIVITY_MODES)
                if self.ns.settings['play_audio']:
                    if self.ns.settings['sensitivity'] == Sensitivity.slow.value:
                        Audio('audio/Menu/slow_sensitivity.wav').start_effect()
                    elif self.ns.settings['sensitivity'] == Sensitivity.mid.value:
                        Audio('audio/Menu/mid_sensitivity.wav').start_effect()
                    elif self.ns.settings['sensitivity'] == Sensitivity.fast.value:
                        Audio('audio/Menu/fast_sensitivity.wav').start_effect()
                
            #no admin colors in con custom teams mode
            if self.game_mode == common.Games.JoustTeams.value or self.game_mode == common.Games.Random.value:
                self.force_color[self.admin_move][0] = 0
                self.force_color[self.admin_move][1] = 0
                self.force_color[self.admin_move][2] = 0
            else:
                #if game is in con mode, admin is green, otherwise admin is red
                if self.game_mode in self.ns.settings['con_games']:
                    self.force_color[self.admin_move][0] = 0
                    self.force_color[self.admin_move][1] = 200

                else:
                    self.force_color[self.admin_move][0] = 200
                    self.force_color[self.admin_move][1] = 0

                #add or remove game from con mode
                if admin_opt[Opts.selection.value] == Selections.add_game.value:
                    admin_opt[Opts.selection.value] = Selections.nothing.value
                    if self.game_mode not in self.ns.settings['con_games']:
                        temp_con_games = self.ns.settings['con_games']
                        temp_con_games.append(self.game_mode)
                        self.update_setting('con_games',temp_con_games)
                        if self.ns.settings['play_audio']:
                            Audio('audio/Menu/game_on.wav').start_effect()
                    elif len(self.ns.settings['con_games']) > 1:
                        temp_con_games = self.ns.settings['con_games']
                        temp_con_games.remove(self.game_mode)
                        self.update_setting('con_games',temp_con_games)
                        if self.ns.settings['play_audio']:
                            Audio('audio/Menu/game_off.wav').start_effect()
                    else:
                        if self.ns.settings['play_audio']:
                            Audio('audio/Menu/game_err.wav').start_effect()
                    self.update_settings_file()
            

    def initialize_settings(self):
        #default settings
        temp_settings = ({ 
            'sensitivity': Sensitivity.mid.value,
            'play_instructions': True,
            'con_games': [common.Games.JoustFFA.value],
            'play_audio': True,
            'move_can_be_admin': True,
            'enforce_minimum': True
        })
        try:
            #catch either file opening or yaml loading failing
            with open(common.SETTINGSFILE,'r') as yaml_file:
                temp_settings.update(yaml.load(yaml_file))
                print(temp_settings)
        except Exception as err:
            print('error in loading yaml: %s' % err)
        for setting in common.REQUIRED_SETTINGS:
            if setting not in temp_settings.keys():
                temp_settings.pop(setting)
        #random mode games can't be empty
        if temp_settings['con_games'] == []:
            temp_settings['con_games'] = [common.Games.JoustFFA.value]
        for i in [common.Games.JoustTeams.value,common.Games.Random.value]:
            if i in temp_settings['con_games']:
                temp_settings['con_games'].pop(i)
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
        #os.system('chmod 666 %s' % com mon.SETTINGSFILE)

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
            'game_mode' : common.game_mode_names[self.game_mode],
            'move_count' : self.move_count,
            'alive_count' : self.move_count - self.dead_count.value,
            'ticker': self.i
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
        if self.game_mode == common.Games.Random.value:
            self.exclude_out_moves()
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
                self.start_game(random_mode=True)
                

        else:
            if self.ns.settings['move_can_be_admin']:
                for move_opt in self.move_opts.values():
                    if move_opt[Opts.selection.value] == Selections.start_game.value:
                        self.start_game()
            if self.command_from_web == 'startgame':
                self.command_from_web = ''
                self.start_game()

    def play_random_instructions(self):
        if self.game_mode == common.Games.JoustFFA.value:
            Audio('audio/Menu/FFA-instructions.wav').start_effect()
            time.sleep(15)
        if self.game_mode == common.Games.JoustRandomTeams.value:
            Audio('audio/Menu/Teams-instructions.wav').start_effect()
            time.sleep(20)
        if self.game_mode == common.Games.Traitor.value:
            Audio('audio/Menu/Traitor-instructions.wav').start_effect()
            time.sleep(18)
        if self.game_mode == common.Games.WereJoust.value:
            Audio('audio/Menu/werewolf-instructions.wav').start_effect()
            time.sleep(20)
        if self.game_mode == common.Games.Zombies.value:
            Audio('audio/Menu/zombie-instructions.wav').start_effect()
            time.sleep(48)
        if self.game_mode == common.Games.Commander.value:
            Audio('audio/Menu/commander-instructions.wav').start_effect()
            time.sleep(41)
        if self.game_mode == common.Games.Ninja.value:
            Audio('audio/Menu/Ninjabomb-instructions.wav').start_effect()
            time.sleep(32)
        if self.game_mode == common.Games.Swapper.value:
            Audio('audio/Menu/Swapper-instructions.wav').start_effect()
            time.sleep(14)
        if self.game_mode == common.Games.Tournament.value:
            Audio('audio/Menu/Tournament-instructions.wav').start_effect()
            time.sleep(21)


    def start_game(self, random_mode=False):
        self.enable_bt_scanning(False)
        self.exclude_out_moves()
        self.stop_tracking_moves()
        time.sleep(0.2)
        self.teams = {serial: self.move_opts[serial][Opts.team.value] for serial in self.tracked_moves.keys() if self.out_moves[serial] == Alive.on.value}
        game_moves = [move.get_serial() for move in self.moves if self.out_moves[move.get_serial()] == Alive.on.value]

        if len(game_moves) < common.minimum_players[self.game_mode] and self.ns.settings['enforce_minimum']:
            Audio('audio/Menu/notenoughplayers.wav').start_effect()
            self.tracked_moves = {}
            return
        self.update_status('starting')

        if random_mode:
            if self.ns.settings['enforce_minimum']:
                good_con_games = [i for i in self.ns.settings['con_games'] if common.minimum_players[i] <= len(game_moves)]
            else:
                good_con_games = self.ns.settings['con_games']
            if len(good_con_games) == 0:
                selected_game = 0 #force Joust FFA
            elif len(good_con_games) == 1:
                selected_game = good_con_games[0]
            else:
                if len(self.rand_game_list) >= len(good_con_games):
                    #empty rand game list, append old game, to not play it twice
                    self.rand_game_list = [self.old_game_mode]

                selected_game = random.choice(good_con_games)
                while selected_game in self.rand_game_list:
                    selected_game = random.choice(good_con_games)

                self.old_game_mode = selected_game
                self.rand_game_list.append(selected_game)

            self.game_mode = selected_game

        if self.ns.settings['play_instructions'] and self.ns.settings['play_audio']:
            self.play_random_instructions()
        
        if self.game_mode == common.Games.Zombies.value:
            zombie.Zombie(game_moves, self.command_queue, self.ns, self.zombie_music)
            self.tracked_moves = {}
        elif self.game_mode == common.Games.Commander.value:
            commander.Commander(game_moves, self.command_queue, self.ns, self.commander_music)
            self.tracked_moves = {}
        elif self.game_mode == common.Games.Ninja.value:
            speed_bomb.Bomb(game_moves, self.command_queue, self.ns, self.commander_music)
            self.tracked_moves = {}
        elif self.game_mode == common.Games.Swapper.value:
            swapper.Swapper(game_moves, self.command_queue, self.ns, self.joust_music)
            self.tracked_moves = {}
        elif self.game_mode == common.Games.Tournament.value:
            tournament.Tournament(game_moves, self.command_queue, self.ns, self.joust_music)
            self.tracked_moves = {}
        else:
            #may need to put in moves that have selected to not be in the game
            joust.Joust(game_moves, self.command_queue, self.ns, self.joust_music, self.teams, self.game_mode)
            self.tracked_moves = {}
        if random_mode:
            self.game_mode = common.Games.Random.value
            if self.ns.settings['play_instructions']:
                if self.ns.settings['play_audio']:
                    Audio('audio/Menu/tradeoff2.wav').start_effect()
                    time.sleep(8)
        #reset music
        self.choose_new_music()
        #turn off admin mode so someone can't accidentally press a button    
        self.admin_move = None
        self.random_added = []
            
if __name__ == "__main__":
    piparty = Menu()
    piparty.game_loop()
