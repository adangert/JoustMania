import psmove
import common, colors, webui
from colors import Colors
from common import Button, Games, Status, Sensitivity
import yaml
import time, random, os, os.path
from datetime import datetime
from piaudio import Music, Audio, InitAudio
from enum import Enum
from multiprocessing import Process, Value, Array, Queue, Manager, freeze_support
from games import joust_ffa, joust_teams, joust_random_teams, joust_non_stop, traitor, werewolf, ffa, zombie, commander, swapper, tournament, speed_bomb, fight_club
from sys import platform
from dotenv import find_dotenv, load_dotenv
import logging.config

if platform == "linux" or platform == "linux2":
    import jm_dbus
    import pair
elif "win" in platform:
    import win_jm_dbus as jm_dbus
    import win_pair as pair
import controller_process
import update

# find .env file in parent directory
env_file = find_dotenv()
load_dotenv()

CONFIG_DIR = "./conf"
LOG_DIR = "./logs"

log_configs = {"dev": "logging.dev.ini", "prod": "logging.prod.ini"}
config = log_configs.get(os.environ["ENV"], "logging.dev.ini")
config_path = "/".join([CONFIG_DIR, config])

timestamp = datetime.now().strftime("%Y%m%d-%H:%M:%S")

logging.config.fileConfig(
    config_path,
    disable_existing_loggers=False,
    defaults={"logfilename": f"{LOG_DIR}/{timestamp}.log"},
)

logger = logging.getLogger(__name__)


TEAM_NUM = len(colors.team_color_list)
#TEAM_COLORS = colors.generate_colors(TEAM_NUM)

SENSITIVITY_MODES = 5
RANDOM_TEAM_SIZES = 6

# Menu specific opts
class Opts(Enum):
    HOLDING = 0      # If buttons are currently held
    SELECTION = 1    # Current selection (depending on buttons pressed)
    STATUS = 2       # Status of the move
    TEAM = 3         # Team of the move
    GAME_MODE = 4    # Current game_mode
    RANDOM_START = 5 # Start without all moves ready
    CHARGING = 6     # Charging status of move

# Selections from either webui or admin move
class Selections(Enum):
    NOTHING = 0
    CHANGE_MODE_FORWARD = 1     # Change to next mode
    CHANGE_MODE_BACKWARD = 2    # Change to previous mode
    ADD_GAME = 3                # Add selected game mode to random_mode options
    CHANGE_SENSITIVITY = 4      # Update sensitivity
    CHANGE_INSTRUCTIONS = 5     # Toggle instructions enabled
    SHOW_BATTERY = 6            # Show battery status on all moves
    update = 7                  # Confirm complete big update
    ADMIN = 8                   # Switch move to admin
    CHANGE_SETTING_CONTROL = 9  # ? TODO
    START_GAME = 10             # start game (from webui)
    FORCE_START_GAME = 11       # force start (from admin move)

# Process running for each move to track that move while in the menu
def track_move(serial, move_num, move, menu_opts, force_color, battery, dead_count, restart, menu, kill_proc):
    # Set up move color
    move.set_leds(0,0,0) # Turn move to black
    move.update_leds()
    random_color = random.random()
    force_start_timer = 0

    while True:
        if(restart.value == 1 or menu.value == 0 or kill_proc.value):
            return # Stop tracking move if restarting, exiting menu, or kill_procedures
        time.sleep(0.01)
        # If there is a new event from the move
        if move.poll():

            game_mode = Games(menu_opts[Opts.GAME_MODE.value]) # Set local game_mode to controller game_mode
            move_button = Button(move.get_buttons()) # Map move button to comm.Button
            battery_level = move.get_battery() # Get battery level
            move_color = Colors.White.value

            # Set this move charging parameter to charging status
            if battery_level == psmove.Batt_CHARGING or battery_level == psmove.Batt_CHARGING_DONE:
                menu_opts[Opts.CHARGING.value] = True
            else:
                menu_opts[Opts.CHARGING.value] =  False

            if menu_opts[Opts.STATUS.value] == Status.DEAD.value:
                # If this move has been plugged in turn off LEDs
                move_color = Colors.Black.value
                # If the sync button is being pressed then remove move from dead value and set to alive
                if move_button == Button.SYNC:
                    menu_opts[Opts.STATUS.value] = Status.ALIVE.value
                    dead_count.value = dead_count.value - 1
                time.sleep(0.1)
            else:
                # If the move is holding all buttons set move as admin
                if move_button == Button.SHAPES:
                    menu_opts[Opts.SELECTION.value] = Selections.ADMIN.value
                    menu_opts[Opts.HOLDING.value] = True

                # If the move is holding start and select, confirm big update
                if move_button == Button.UPDATE:
                    menu_opts[Opts.SELECTION.value] = Selections.update.value
                    menu_opts[Opts.HOLDING.value] = True

                # Show battery level
                if battery.value == 1: # If batteries have been toggled
                    battery_level = move.get_battery() #TODO - Getting this a second time?

                    # Granted a charging move should be dead, so it won't light up anyway
                    if battery_level == psmove.Batt_CHARGING:
                        move_color = Colors.White20.value

                    elif battery_level == psmove.Batt_CHARGING_DONE:
                        move_color = Colors.White.value

                    elif battery_level == psmove.Batt_MAX:
                        move_color = Colors.Green.value

                    elif battery_level == psmove.Batt_80Percent:
                        move_color = Colors.Turquoise.value

                    elif battery_level == psmove.Batt_60Percent:
                        move_color = Colors.Blue.value

                    elif battery_level == psmove.Batt_40Percent:
                        move_color = Colors.Yellow.value

                    else : # under 40% - you should charge it!
                        move_color = Colors.Red.value

                # Custom team mode is the only game mode that
                # Can't be added to con mode
                elif game_mode == Games.JoustTeams:
                    # If the team number is too high, set it to 3
                    # for example the admin reduced the number
                    if menu_opts[Opts.TEAM.value] >= TEAM_NUM:
                        menu_opts[Opts.TEAM.value] = 3

                    # Set move color to team
                    move_color = colors.team_color_list[menu_opts[Opts.TEAM.value]].value

                # Set leds to forced color
                elif sum(force_color) != 0: # If forcing a color, set it
                    move_color = force_color

                # Everyone tracked is orange for FFA
                elif game_mode == Games.JoustFFA:
                    move_color = Colors.Orange.value

                # Everyone is a random color
                elif game_mode == Games.JoustRandomTeams:
                    color = time.time()/10%1
                    color = colors.hsv2rgb(color, 1, 1)
                    move_color = color

                # TODO - some complicated color scheme here
                elif game_mode == Games.Traitor:
                    if move_num%4 == 2 and time.time()/3%1 < .15:
                        move_color = Colors.Red80.value
                    else:
                        color = 1 - time.time()/10%1
                        color = colors.hsv2rgb(color, 1, 1)
                        move_color = color

                # Set everyone to only move zero to Blue
                elif game_mode == Games.Werewolf:
                    if move_num <= 0:
                        move_color = Colors.Blue40.value
                    else:
                        move_color = Colors.Yellow.value

                # Set everyone to Zombie color (probably green)
                elif game_mode == Games.Zombies:
                    move_color = Colors.Zombie.value

                # Set even moves to red and odds to blue
                elif game_mode == Games.Commander:
                    if move_num % 2 == 0:
                        move_color = Colors.Red.value
                    else:
                        move_color = Colors.Blue.value

                # Set colors to bounce between Magenta and Green
                elif game_mode == Games.Swapper:
                    if (time.time()/5 + random_color)%1 > 0.5:
                        move_color = Colors.Magenta.value
                    else:
                        move_color = Colors.Green.value

                # Set all moves to green
                elif game_mode == Games.FightClub:
                    move_color = Colors.Green80.value

                # Set all moves to turquoise
                elif game_mode == Games.NonStop:
                    move_color = Colors.Turquoise.value

                # Set moves to random colors
                elif game_mode == Games.Tournament:
                    if move_num <= 0:
                        color = time.time()/10%1
                        color = colors.hsv2rgb(color, 1, 1)
                        move_color = color
                    else:
                        move_color = Colors.Blue40.value

                # Set moves to random colors
                elif game_mode == Games.Ninja:
                    if move_num <= 0: # TODO - How does this happen?
                        move_color = tuple([random.randrange(100, 200),0,0])
                    else:
                        move_color = Colors.Red60.value

                # Set moves to blue
                elif game_mode == Games.Random:
                    move_color = Colors.Blue.value

                # If not holding buttons
                if not menu_opts[Opts.HOLDING.value]:
                    # If trigger fully pressed
                    if move.get_trigger() > 100:
                        # Mark trying to start the game and marking button is being held
                        menu_opts[Opts.SELECTION.value] = Selections.START_GAME.value
                        menu_opts[Opts.HOLDING.value] = True
                        force_start_timer = time.time()

                    # Select moves game mode backwards
                    if move_button == Button.SELECT:
                        menu_opts[Opts.SELECTION.value] = Selections.CHANGE_MODE_BACKWARD.value
                        menu_opts[Opts.HOLDING.value] = True

                    # Start moves game mode forwards
                    if move_button == Button.START:
                        menu_opts[Opts.SELECTION.value] = Selections.CHANGE_MODE_FORWARD.value
                        menu_opts[Opts.HOLDING.value] = True

                    # As an admin controller add or remove game from convention mode (used in check_admin_controls)
                    if move_button == Button.CROSS:
                        menu_opts[Opts.SELECTION.value] = Selections.ADD_GAME.value
                        menu_opts[Opts.HOLDING.value] = True

                    # As an admin controller change sensitivity of controllers (used in check_admin_controls)
                    if move_button == Button.CIRCLE:
                        menu_opts[Opts.SELECTION.value] = Selections.CHANGE_SENSITIVITY.value
                        menu_opts[Opts.HOLDING.value] = True

                    # As an admin controller change if instructions play (used in check_admin_controls)
                    if move_button == Button.SQUARE:
                        menu_opts[Opts.SELECTION.value] = Selections.CHANGE_INSTRUCTIONS.value
                        menu_opts[Opts.HOLDING.value] = True

                    # As an admin show battery level of controllers (used in check_admin_controls)
                    if move_button == Button.TRIANGLE:
                        menu_opts[Opts.SELECTION.value] = Selections.SHOW_BATTERY.value
                        menu_opts[Opts.HOLDING.value] = True

                    # Allow players to increase their own team
                    if move_button == Button.MIDDLE:
                        menu_opts[Opts.SELECTION.value] = Selections.CHANGE_SETTING_CONTROL.value
                        # If playing JoustTeams, move player to next team
                        if game_mode == Games.JoustTeams:
                            menu_opts[Opts.TEAM.value] = (menu_opts[Opts.TEAM.value] + 1) % TEAM_NUM
                        menu_opts[Opts.HOLDING.value] = True

                # If the admin has been holding the trigger for 2 seconds, force the game start (used in check_admin_controls)
                if  (menu_opts[Opts.SELECTION.value] == Selections.START_GAME.value and \
                     menu_opts[Opts.HOLDING.value] == True and \
                     time.time()-force_start_timer >2):
                    menu_opts[Opts.SELECTION.value] = Selections.FORCE_START_GAME.value

                # Show team color if user has pressed trigger
                if not(menu_opts[Opts.RANDOM_START.value] and sum(force_color) == 0):
                    move_color = colors.darken_color(move_color, .95)

                # If trigger is no longer being held, reset the start
                if menu_opts[Opts.HOLDING.value] == True and move_button == Button.NONE and move.get_trigger() <= 100:
                    menu_opts[Opts.HOLDING.value] = False
                    # TODO - do you want to reset the force_start_timer?
            move.set_leds(*move_color)
        #Update colors
        move.update_leds()

class Menu():
    def __init__(self):

        # Set up shared namespace between webserver and joustmania
        self.command_queue = Queue()
        self.joust_manager = Manager()
        self.ns = self.joust_manager.Namespace()
        # Start web server
        self.web_proc = Process(target=webui.start_web, args=(self.command_queue,self.ns))
        self.web_proc.start()
        self.ns.status = dict()
        self.ns.settings = dict()
        self.ns.battery_status = dict()
        self.command_from_web = ''
        self.initialize_settings()
        self.update_settings_file() # Update settings from joustmania.yaml

        self.admin_options = ["random_team_size","force_all_start"]
        self.admin_control_option = 0

        # Check for git update
        if platform == "linux" or platform == "linux2":
            self.big_update = update.check_for_update(self.ns.settings['menu_voice'])
            self.git_hash = update.run_command("git rev-parse HEAD")[:7]
        else:
            self.git_hash = "0000000"

        self.experimental = False # Testing new version of FFA
        self.dead_count = Value('i', 0) # Number of dead moves used in webui

        # All of the moves connected via BT or USB, moves connected via both will appear twice
        self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]

        self.move_count = self.get_move_count() # Number of connected moves used in webui

        self.admin_move = None # Move with admin privileges
        self.out_moves = {} # Array to store alive status per move, used to disable charging moves
        self.paired_moves = [] # Moves paired via USB
        self.tracked_moves = {} # Moves that are currently tracked / have process spawned
        logger.debug("Number of moves: {}".format(len(self.moves)))
        logger.debug("Moves serial: {}".format([move.get_serial() for move in self.moves]))
        self.random_added = [] # Added to a random team yet TODO - confirm
        self.rand_game_list = [] # List of random games
        self.show_battery = Value('i', 0) # Shared variable across all move processes to control whether to display battery status
        self.pair_one_move = True # Only allow one move to be paired via USB at a time TODO - does this do anything anymore??
        self.force_color = {} # Not sure

        self.menu_opts = {} # Menu options stored per move
        self.game_opts = {} # Game options stored per move
        self.teams = {} # Serial to team list TODO - seems to be the same as controller_teams
        self.game_mode = Games[self.ns.settings['current_game']] # Get game mode from ns (which is shared with web admin)
        self.old_game_mode = self.game_mode #Previous game mode
        self.pair = pair.Pair() # Start bluetooth pairing

        self.menu = Value('i', 1) # Whether in the menu or not (1 - Menu, 0 - Game)
        self.controller_game_mode = Value('i',1) # Game mode shared across all processes
        self.restart = Value('i',0) # Restart value shared across all processes - stops tracking moves
        self.controller_teams = {} # Track team per controller for multiple team games, e.g. JoustTeams
        self.controller_colors = {} # Track color per controller
        self.controller_sensitivity = {} # Track sensitivity per controller
        self.dead_moves = {} # Track moves that have died
        self.invincible_moves = {} # Moves that can't be killed
        self.music_speed= Value('d', 0) # Current music speed
        self.red_on_kill = Value('i', 0) # Turn red on death - also in webui / admin
        self.show_team_colors = Value('i', 0) # Whether to display team colors TODO - might be able to remove
        self.kill_controller_proc = {} # ? TODO
        self.revive = Value('b', False)
        self.i = 0 # Game tick count

        # Load audio now so it converts before the game begins
        self.menu_music = Music("menu")
        self.joust_music = Music("joust")
        self.zombie_music = Music("zombie")
        self.commander_music = Music("commander")
        self.choose_new_music()

    def choose_new_music(self):
        self.joust_music.load_audio("audio/Joust/music/*")
        self.zombie_music.load_audio("audio/Zombie/music/*")
        self.commander_music.load_audio("audio/Commander/music/*")

    # Check if new moves have joined/dropped via Bluetooth
    def check_for_new_moves(self):
        self.enable_bt_scanning(True)

        # Start tracking of new moves in here
        if psmove.count_connected() != len(self.moves):
            self.moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]
            if self.move_count > len(self.moves):
                logger.debug("Move disconnected")
            else:
                logger.debug("Move connected")
            self.move_count = self.get_move_count()

    # Turn on bluetooth scanning
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

    # Pair USB move
    def pair_usb_move(self, move):
        move_serial = move.get_serial()
        if move_serial not in self.tracked_moves:
            if move.connection_type == psmove.Conn_USB:
                if move_serial not in self.paired_moves:
                    logger.debug("Pairing USB move: {}".format(move_serial))
                    self.pair.pair_move(move)
                    move.set_leds(255,255,255)
                    move.update_leds()
                    self.paired_moves.append(move_serial)
                    #self.pair_one_move = False

    # Pair Bluetooth move
    def pair_move(self, move, move_num):
        move_serial = move.get_serial()
        #If move is not already being tracked
        if move_serial not in self.tracked_moves:
            logger.debug("Pairing BT move: {}".format(move_serial))
            color = Array('i', [0] * 3)
            # TODO: this probably should be tracked above
            # Individual move run-time parameters, initialize them all to 0
            menu_opts = Array('i', [0] * len(Opts))
            game_opts = Array('i', [0] * 10)

            # If move is in list of teams, set param for team
            if move_serial in self.teams:
                menu_opts[Opts.TEAM.value] = self.teams[move_serial]
            else:
                # Initialize to team Yellow
                menu_opts[Opts.TEAM.value] = 3

            # If move is in list of out_moves, set param for alive
            if move_serial in self.out_moves:
                menu_opts[Opts.STATUS.value] = self.out_moves[move_serial]

            # Set game_mode
            menu_opts[Opts.GAME_MODE.value] = self.game_mode.value

            # Generic game parameters
            team = Value('i',0) # Which team you are on
            team_color_enum = Array('i',[0]*3)
            dead_move = Value('i', 0)
            invincible_move = Value('i', 0)
            kill_proc = Value('b', False)
            sensitivity = Value('i', 0)
            sensitivity.value = self.ns.settings['sensitivity']

            # Kick off new process to track move
            proc = Process(target= controller_process.main_track_move, args=(self.menu, self.restart, move_serial, move_num, menu_opts, game_opts, color, self.show_battery, \
                                                                             self.dead_count, self.controller_game_mode, team, team_color_enum, sensitivity, dead_move, \
                                                                             invincible_move, self.music_speed, self.show_team_colors, self.red_on_kill, \
                                                                             self.revive, kill_proc))

            proc.start()

            #Track across all moves
            self.menu_opts[move_serial] = menu_opts
            self.game_opts[move_serial] = game_opts
            self.tracked_moves[move_serial] = proc
            self.force_color[move_serial] = color
            self.controller_teams[move_serial] = team
            self.controller_colors[move_serial] = team_color_enum
            self.controller_sensitivity[move_serial] = sensitivity
            self.dead_moves[move_serial] = dead_move
            self.invincible_moves[move_serial] = invincible_move
            self.kill_controller_proc[move_serial] = kill_proc
            self.out_moves[move.get_serial()] = Status.ALIVE.value #Set this move as alive

    def remove_controller(self, move_serial):
        if (move_serial not in self.kill_controller_proc):
            #already removed the controller (could have been plugged in)
            return
        logger.debug("Removing move: {}".format(move_serial))
        self.kill_controller_proc[move_serial].value = True
        self.tracked_moves[move_serial].join()
        self.tracked_moves[move_serial].terminate()
        #del self.tracked_moves[move_serial] # TODO - why commented?
        del self.force_color[move_serial]
        del self.controller_teams[move_serial]
        del self.controller_colors[move_serial]
        del self.controller_sensitivity[move_serial]
        del self.dead_moves[move_serial]
        del self.invincible_moves[move_serial]
        del self.menu_opts[move_serial]
        del self.game_opts[move_serial]
        del self.kill_controller_proc[move_serial]
        del self.out_moves[move_serial] # Remove from out_moves array

    def game_mode_announcement(self):
        if self.game_mode == Games.JoustFFA:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Joust FFA.wav').start_effect()
        if self.game_mode == Games.JoustTeams:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Joust Teams.wav').start_effect()
        if self.game_mode == Games.JoustRandomTeams:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Joust Random Teams.wav').start_effect()
        if self.game_mode == Games.Traitor:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Traitor.wav').start_effect()
        if self.game_mode == Games.Werewolf:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Werewolves.wav').start_effect()
        if self.game_mode == Games.Zombies:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Zombies.wav').start_effect()
        if self.game_mode == Games.Commander:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Commander.wav').start_effect()
        if self.game_mode == Games.Swapper:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Swapper.wav').start_effect()
        if self.game_mode == Games.Tournament:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Tournament.wav').start_effect()
        if self.game_mode == Games.Ninja:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu ninjabomb.wav').start_effect()
        if self.game_mode == Games.Random:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu Random.wav').start_effect()
        if self.game_mode == Games.FightClub:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu FightClub.wav').start_effect()
        if self.game_mode == Games.NonStop:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/menu NonStopJoust.wav').start_effect()

    # Check if admin has triggered the start
    def check_game_trigger(self):
        for move, move_opt in self.menu_opts.items():
            # If move is not an admin, set start_game for this move
            if move != self.admin_move:
                if move_opt[Opts.SELECTION.value] == Selections.START_GAME.value:
                    logger.debug("Move ready: {}".format(move))
                    move_opt[Opts.RANDOM_START.value] = True
                    move_opt[Opts.SELECTION.value] = Selections.NOTHING.value
            # If move is an admin, and selection = start_game, turn admin back to normal player
            else:
                if (move_opt[Opts.SELECTION.value] == Selections.START_GAME.value and \
                        move_opt[Opts.HOLDING.value] == False):
                    # Turn admin back to regular player
                    self.force_color[self.admin_move][0] = 0
                    self.force_color[self.admin_move][1] = 0
                    self.force_color[self.admin_move][2] = 0
                    self.admin_move = None
                    move_opt[Opts.SELECTION.value] = Selections.NOTHING.value


    def check_change_mode(self):
        change_mode = False
        change_forward = True

        #Determine if person who clicked to change mode was actually the admin, if so change it
        for move, move_opt in self.menu_opts.items():
            if move != self.admin_move:
                if move_opt[Opts.SELECTION.value] == Selections.CHANGE_MODE_FORWARD.value:
                    #change the game mode if allowed
                    if self.ns.settings['move_can_be_admin']:
                        change_mode = True
                        change_forward = True
                    move_opt[Opts.SELECTION.value] = Selections.NOTHING.value

                if move_opt[Opts.SELECTION.value] == Selections.CHANGE_MODE_BACKWARD.value:
                    #change the game mode if allowed
                    if self.ns.settings['move_can_be_admin']:
                        change_mode = True
                        change_forward = False
                    move_opt[Opts.SELECTION.value] = Selections.NOTHING.value

        #If webui updated change
        if self.command_from_web == 'changemode':
            self.command_from_web = ''
            change_mode = True

        #If change mode is true, update the game_mode
        if change_mode:
            if change_forward:
                self.game_mode = self.game_mode.next()
            else:
                self.game_mode = self.game_mode.previous()


            self.update_setting('current_game',self.game_mode.name)
            self.reset_controller_game_state()
            if not self.ns.settings['play_audio']:
                if self.game_mode == Games.Commander:
                    self.game_mode = self.game_mode.next()
                if self.game_mode == Games.Werewolf:
                    self.game_mode = self.game_mode.next()
            for opt in self.menu_opts.values():
                opt[Opts.GAME_MODE.value] = self.game_mode.value
            if self.ns.settings['play_audio']:
                self.game_mode_announcement()

    def check_new_admin(self):
        for move, move_opt in self.menu_opts.items():
            if move_opt[Opts.SELECTION.value] == Selections.ADMIN.value:
                # Remove previous admin, and set new one
                if self.ns.settings['move_can_be_admin'] and not self.admin_move == move:
                    # Set the old admin_move to have no forced colors
                    if self.admin_move:
                        self.force_color[self.admin_move][0] = 0
                        self.force_color[self.admin_move][1] = 0
                        self.force_color[self.admin_move][2] = 0
                    logger.debug("New admin: {}".format(move))
                    self.admin_move = move
                move_opt[Opts.SELECTION.value] = Selections.NOTHING.value


    #all controllers need to opt-in again in order for the game to start
    def reset_controller_game_state(self):
        for move_opt in self.menu_opts.values():
            move_opt[Opts.RANDOM_START.value] = False
        for serial in self.menu_opts.keys():
            for i in range(3):
                self.force_color[serial][i] = 0
        self.random_added = []

    # If the admin has confirmed the update, perform it
    def check_update(self):
        for move, move_opt in self.menu_opts.items():
            if move_opt[Opts.SELECTION.value] == Selections.update.value:
                if self.big_update:
                    update.big_update(self.ns.settings['menu_voice'])
                    self.big_update = False

    # This checks if there is a charging controller
    # if it is, then set controller to Dead
    def check_charging_controller(self):
        for serial, move_opt in self.menu_opts.items():
            # FIX Toggle charging property if necessary
            if move_opt[Opts.CHARGING.value] == True and self.out_moves[serial] == Status.ALIVE.value:
                logger.debug("Move charging: {}".format(serial))
                self.out_moves[serial] = Status.DEAD.value # If move is charging, set it to dead
                move_opt[Opts.STATUS.value] = Status.DEAD.value # If move is charging, set it to dead
            elif move_opt[Opts.CHARGING.value] == False and self.out_moves[serial] == Status.DEAD.value:
                logger.debug("Move no longer charging: {}".format(serial))
                self.out_moves[serial] = Status.ALIVE.value # If move is not charging, set it to alive
                move_opt[Opts.STATUS.value] = Status.ALIVE.value #If move is not charging, set it to alive

    def game_loop(self):
        self.play_menu_music = True
        while True:
            # Only start the music the first loop
            if self.play_menu_music:
                self.play_menu_music = False
                self.menu_music.load_audio("audio/Menu/music/*")
                self.menu_music.start_audio_loop()
            self.i = self.i + 1 # Track loop counter
            if "linux" in platform:
                # If pair_one_move is false and there are 0 lines in list usbs
                if not self.pair_one_move and "0" in os.popen('lsusb | grep "PlayStation Move motion controller" | wc -l').read():
                    # Allow move to be paired via USB
                    self.pair_one_move = True
                    self.paired_moves = []
            else:
                if not self.pair_one_move:
                    self.pair_one_move = True
                    self.paired_moves = []

            # If allowing moves to be paired
            if self.pair_one_move:
                # Check if the number of psmoves connected is more than those tracked
                if psmove.count_connected() > len(self.tracked_moves):
                    for move_num, move in enumerate(self.moves):
                        # If move is connected via USB, pair it
                        if move.connection_type == psmove.Conn_USB and self.pair_one_move:
                            self.pair_usb_move(move)
                        # If move is connected via BT, pair it
                        elif move.connection_type != psmove.Conn_USB:
                            self.pair_move(move, move_num)
                # If the number of tracked moves is greater than the connected ones
                # kill the tracked moves no longer connected
                elif(len(self.tracked_moves) > len(self.moves)):
                    connected_serials = [x.get_serial() for x in self.moves]
                    tracked_serials = self.tracked_moves.keys()
                    keys_to_kill = []
                    for serial in tracked_serials:
                        if serial not in connected_serials:
                            #self.kill_controller_proc[serial].value = True TODO - why is this commented
                            #check to see if the controller has not been removed already TODO - what is this?
                            if serial in self.menu_opts.keys():
                                self.remove_controller(serial)
                            #self.tracked_moves[serial].join() TODO - ?
                            #self.tracked_moves[serial].terminate() TODO - ?
                            keys_to_kill.append(serial) # Add new serials to kill

                    # For all keys to kill, remove from tracked_moves
                    for key in keys_to_kill:
                        del self.tracked_moves[key]
                        if key == self.admin_move:
                            self.admin_move = None

                self.check_for_new_moves()
                if len(self.tracked_moves) > 0:
                    self.check_new_admin()
                    self.check_change_mode() # TODO - do we want to make this so only admins can change mode?
                    self.check_game_trigger()
                    self.check_admin_controls()
                    self.check_start_game()
                    self.check_update()
                    self.check_charging_controller()
                self.check_command_queue()
                self.update_status('menu')


    def check_admin_controls(self):
        show_bat = False
        for move_opt in self.menu_opts.values():
            if move_opt[Opts.SELECTION.value] == Selections.SHOW_BATTERY.value and move_opt[Opts.HOLDING.value] == True:
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
            admin_opt = self.menu_opts[self.admin_move]

            if admin_opt[Opts.SELECTION.value] == Selections.FORCE_START_GAME.value:
                admin_opt[Opts.RANDOM_START.value] = Status.DEAD.value
                self.start_game()
                return;

            #change game settings
            if admin_opt[Opts.SELECTION.value] == Selections.CHANGE_SETTING_CONTROL.value:
                admin_opt[Opts.SELECTION.value] = Selections.NOTHING.value
                self.admin_control_option = (self.admin_control_option + 1) % len(self.admin_options)
                if(self.admin_options[self.admin_control_option] == 'random_team_size'):
                    Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/adminop_random_team_size.wav').start_effect()
                elif(self.admin_options[self.admin_control_option] == 'force_all_start'):
                    Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/adminop_force_all_start.wav').start_effect()

            if admin_opt[Opts.SELECTION.value] == Selections.CHANGE_MODE_FORWARD.value:
                admin_opt[Opts.SELECTION.value] = Selections.NOTHING.value
                if(self.admin_options[self.admin_control_option] == 'random_team_size'):
                    self.update_setting('random_team_size', (self.ns.settings['random_team_size'] + 1) %  (RANDOM_TEAM_SIZES+1))
                    if (self.ns.settings['random_team_size'] < 2):
                        self.update_setting('random_team_size', 2)
                    Audio('audio/Menu/vox/{}/adminop_{}.wav'.format(self.ns.settings['menu_voice'],self.ns.settings['random_team_size'])).start_effect()
                elif(self.admin_options[self.admin_control_option] == 'force_all_start'):
                    self.update_setting('force_all_start', not self.ns.settings['force_all_start'] )
                    Audio('audio/Menu/vox/{}/adminop_{}.wav'.format(self.ns.settings['menu_voice'],self.ns.settings['force_all_start'])).start_effect()

            if admin_opt[Opts.SELECTION.value] == Selections.CHANGE_MODE_BACKWARD.value:
                admin_opt[Opts.SELECTION.value] = Selections.NOTHING.value
                if(self.admin_options[self.admin_control_option] == 'random_team_size'):
                    self.update_setting('random_team_size', (self.ns.settings['random_team_size'] - 1))
                    if (self.ns.settings['random_team_size'] < 2):
                        self.update_setting('random_team_size', RANDOM_TEAM_SIZES)
                    Audio('audio/Menu/vox/{}/adminop_{}.wav'.format(self.ns.settings['menu_voice'],self.ns.settings['random_team_size'])).start_effect()
                elif(self.admin_options[self.admin_control_option] == 'force_all_start'):
                    self.update_setting('force_all_start', not self.ns.settings['force_all_start'] )
                    Audio('audio/Menu/vox/{}/adminop_{}.wav'.format(self.ns.settings['menu_voice'],self.ns.settings['force_all_start'])).start_effect()

            #to play instructions or not
            if admin_opt[Opts.SELECTION.value] == Selections.CHANGE_INSTRUCTIONS.value:
                admin_opt[Opts.SELECTION.value] = Selections.NOTHING.value
                self.update_setting('play_instructions', not self.ns.settings['play_instructions'])
                if self.ns.settings['play_audio']:
                    if self.ns.settings['play_instructions']:
                        logger.debug("Turning on instructions")
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/instructions_on.wav').start_effect()
                    else:
                        logger.debug("Turning off instructions")
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/instructions_off.wav').start_effect()

            #change sensitivity
            if admin_opt[Opts.SELECTION.value] == Selections.CHANGE_SENSITIVITY.value:
                admin_opt[Opts.SELECTION.value] = Selections.NOTHING.value

                self.update_setting('sensitivity', (self.ns.settings['sensitivity'] + 1) %  SENSITIVITY_MODES)
                if self.ns.settings['play_audio']:
                    logger.debug("Updating sensitivity")
                    if self.ns.settings['sensitivity'] == Sensitivity.ULTRA_SLOW.value:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/ultra_high.wav').start_effect()
                    elif self.ns.settings['sensitivity'] == Sensitivity.SLOW.value:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/high.wav').start_effect()
                    elif self.ns.settings['sensitivity'] == Sensitivity.MID.value:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/medium.wav').start_effect()
                    elif self.ns.settings['sensitivity'] == Sensitivity.FAST.value:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/low.wav').start_effect()
                    elif self.ns.settings['sensitivity'] == Sensitivity.ULTRA_FAST.value:
                        Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/ultra_low.wav').start_effect()

            # No admin colors in con custom teams mode
            if self.game_mode == Games.JoustTeams or self.game_mode == Games.Random:
                self.force_color[self.admin_move][0] = 0
                self.force_color[self.admin_move][1] = 0
                self.force_color[self.admin_move][2] = 0
            else:
                # If game is in random mode, admin is green, otherwise admin is red
                if self.game_mode.name in self.ns.settings['random_modes']:
                    self.force_color[self.admin_move][0] = 0
                    self.force_color[self.admin_move][1] = 200
                else:
                    self.force_color[self.admin_move][0] = 200
                    self.force_color[self.admin_move][1] = 0

                # Add or remove game from con mode
                if admin_opt[Opts.SELECTION.value] == Selections.ADD_GAME.value:
                    admin_opt[Opts.SELECTION.value] = Selections.NOTHING.value
                    if self.game_mode.name not in self.ns.settings['random_modes']:
                        logger.debug("Adding {} to random mode".format(self.game_mode.name))
                        temp_random_modes = self.ns.settings['random_modes']
                        temp_random_modes.append(self.game_mode.name)
                        self.update_setting('random_modes',temp_random_modes)
                        if self.ns.settings['play_audio']:
                            Audio('audio/Menu/sounds/game_on.wav').start_effect()
                    elif len(self.ns.settings['random_modes']) > 1:
                        logger.debug("Removing {} from random mode".format(self.game_mode.name))
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
        # Default settings
        temp_settings = ({
            'sensitivity': Sensitivity.MID.value,
            'play_instructions': True,
            # We store the name, not the enum, so the webui can process it more easily
            'random_modes': [Games.JoustFFA.name,Games.JoustRandomTeams.name,Games.Werewolf.name,Games.Swapper.name],
            'current_game': Games.JoustFFA.name,
            'play_audio': True,
            'menu_voice': 'ivy',
            'move_can_be_admin': True,
            'enforce_minimum': True,
            'red_on_kill': True,
            'random_teams': True,
            'color_lock': False,
            'random_team_size': 4,
            'force_all_start':False,
            'color_lock_choices':{
                2: ['Magenta','Green'],
                3: ['Orange','Turquoise','Purple'],
                4: ['Yellow','Green','Blue','Purple']
            }
        })
        try:
            #if anything fails during the settings file load, ignore file and stick with defaults
            logger.debug("Loading settings")
            with open(common.SETTINGSFILE,'r') as yaml_file:
                file_settings = yaml.safe_load(yaml_file)
            logger.debug(file_settings)

            temp_colors = file_settings['color_lock_choices']
            for key in temp_colors.keys():
                colorset = temp_colors[key]
                if len(colorset) != len(set(colorset)):
                    temp_colors[key] = temp_settings['color_lock_choices'][key]

            for setting in file_settings.keys():
                if setting not in common.REQUIRED_SETTINGS:
                    file_settings.pop(setting)

            for game in [Games.JoustTeams,Games.Random]:
                if game.name in file_settings['random_modes']:
                    file_settings['random_modes'].remove(game.name)
            for game in file_settings['random_modes']:
                if game not in [game.name for game in Games]:
                    file_settings['random_modes'].remove(game)
            if file_settings['random_modes'] == []:
                file_settings['random_modes'] = [Games.JoustFFA.name]

            temp_settings.update(file_settings)
            temp_settings['color_lock_choices'] = temp_colors

        except Exception as e:
            logger.error("We found an exception when loading the settings!", e)

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


    #Update the settings[key] with value
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
            'game_count' : len(self.get_game_moves()),
            'ready_count' : len(self.get_ready_moves(True)),
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
        #if self.game_mode == Games.Random: TODO - what's this for?

        # FIX - start_game is always False if there are 0 moves alive
        start_game = len(self.get_game_moves()) > 0
        for serial in self.menu_opts.keys():
            if self.out_moves[serial] == Status.ALIVE.value and not self.menu_opts[serial][Opts.RANDOM_START.value]:
                start_game = False
            if self.menu_opts[serial][Opts.RANDOM_START.value] and serial not in self.random_added:
                self.random_added.append(serial)
                if self.ns.settings['play_audio']:
                    Audio('audio/Joust/sounds/start.wav').start_effect()


        if start_game:
            logger.debug("Starting game")
            if self.game_mode == Games.Random:
                self.start_game(random_mode=True)
            else:
                self.start_game()


        #else:
        #    if self.ns.settings['move_can_be_admin']:
        #        for move_opt in self.menu_opts.values():
        #            if move_opt[Opts.SELECTION.value] == Selections.start_game.value:
        #                self.start_game()
        if self.command_from_web == 'startgame':
            self.command_from_web = ''
            self.start_game()

    def play_random_instructions(self):
        if self.game_mode == Games.JoustFFA:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/FFA-instructions.wav').start_effect_and_wait()
        if self.game_mode == Games.JoustRandomTeams:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Teams-instructions.wav').start_effect_and_wait()
        if self.game_mode == Games.Traitor:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Traitor-instructions.wav').start_effect_and_wait()
        if self.game_mode == Games.Werewolf:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/werewolf-instructions.wav').start_effect_and_wait()
        if self.game_mode == Games.Zombies:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/zombie-instructions.wav').start_effect_and_wait()
        if self.game_mode == Games.Commander:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/commander-instructions.wav').start_effect_and_wait()
        if self.game_mode == Games.Ninja:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Ninjabomb-instructions.wav').start_effect_and_wait()
        if self.game_mode == Games.Swapper:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Swapper-instructions.wav').start_effect_and_wait()
        if self.game_mode == Games.Tournament:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Tournament-instructions.wav').start_effect_and_wait()
        if self.game_mode == Games.FightClub:
            if self.ns.settings['menu_voice'] == 'aaron':
                os.popen('espeak -ven -p 70 -a 200 "Two players fight, the winner must defend their title, the player with the highest score wins')
            else:
                Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/Fightclub-instructions.wav').start_effect_and_wait()
            time.sleep(5)

    # Get all moves, deduplicating serials
    def get_move_count(self):
        return len(set([move.get_serial() for move in self.moves]))

    # Set a move to ready
    def ready_move(self, move):
        # TODO - create a reusable function to ready a move
        # Update move opt for ready
        # Set move team - if FFA, just give it the next team
        return 0;

    # Moves that are available to start a game, use force_all_start = False if just wanting to see alive moves
    def get_ready_moves(self, force_all_start):
        if force_all_start:
            return [move.get_serial() for move in self.moves if self.out_moves.get(move.get_serial(), Status.DEAD.value) == Status.ALIVE.value and move.get_serial() in self.menu_opts and (self.menu_opts[move.get_serial()])[Opts.RANDOM_START.value]  ]
        else:
            return [move.get_serial() for move in self.moves if self.out_moves.get(move.get_serial(), Status.DEAD.value) == Status.ALIVE.value and move.get_serial() in self.menu_opts]

    # Get moves that are currently Alive (not charging)
    def get_game_moves(self):
        return self.get_ready_moves(False)

    # Get list of teams from Alive moves (not charging)
    def get_game_teams(self):
        return {serial: self.menu_opts[serial][Opts.TEAM.value] for serial in self.tracked_moves.keys() if self.out_moves[serial] == Status.ALIVE.value}

    def start_game(self, random_mode=False):
        self.enable_bt_scanning(False)
        time.sleep(1)

        # FIX - Added helper functions for this
        game_moves = self.get_ready_moves(self.ns.settings['force_all_start'])
        self.teams = self.get_game_teams()

        logger.debug("Number of game moves: {}".format(len(game_moves)))
        if len(game_moves) < self.game_mode.minimum_players and self.ns.settings['enforce_minimum']:
            Audio('audio/Menu/vox/' + self.ns.settings['menu_voice'] + '/notenoughplayers.wav').start_effect()
            self.reset_controller_game_state()
            logger.debug("Not enough players")
            return

        for move in [move.get_serial() for move in self.moves if move.get_serial() not in game_moves]:
            logger.debug("We are removing controller from game: {}".format(move))
            self.remove_controller(move)
        try:
            self.menu_music.stop_audio()
        except:
            pass

        self.menu.value = 0
        self.restart.value = 1
        self.update_status('starting')

        if random_mode:
            good_random_modes = [Games[game] for game in self.ns.settings['random_modes']]
            if self.ns.settings['enforce_minimum']:
                good_random_modes = [game for game in good_random_modes if game.minimum_players <= len(game_moves)]
            if len(good_random_modes) == 0:
                selected_game = Games.JoustFFA  #force Joust FFA
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

        # Joust FFA
        if self.game_mode == Games.JoustFFA:
            if self.experimental:
                logger.debug("Playing EXPERIMENTAL FFA Mode.")
                moves = [ common.get_move(serial, num) for num, serial in enumerate(game_moves) ]
                game = ffa.FreeForAll(moves, self.joust_music)
                game.run_loop()
            else:
                joust_ffa.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill, \
                                music=self.joust_music, teams=self.teams, game_mode=self.game_mode, \
                                controller_teams=self.controller_teams, controller_colors=self.controller_colors, \
                                dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, force_move_colors=self.force_color, \
                                music_speed=self.music_speed, show_team_colors=self.show_team_colors, restart=self.restart, \
                                revive=self.revive)
        # Joust Teams
        elif self.game_mode == Games.JoustTeams:
            joust_teams.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill, \
                              music=self.joust_music, teams=self.teams, game_mode=self.game_mode, \
                              controller_teams=self.controller_teams, controller_colors=self.controller_colors, \
                              dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, force_move_colors=self.force_color, \
                              music_speed=self.music_speed, show_team_colors=self.show_team_colors, restart=self.restart, \
                              revive=self.revive)
        # Joust Random Teams
        elif self.game_mode == Games.JoustRandomTeams:
            joust_random_teams.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill, \
                                     music=self.joust_music, teams=self.teams, game_mode=self.game_mode, \
                                     controller_teams=self.controller_teams, controller_colors=self.controller_colors, \
                                     dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, force_move_colors=self.force_color, \
                                     music_speed=self.music_speed, show_team_colors=self.show_team_colors, restart=self.restart, \
                                     revive=self.revive)
        # Traitors
        elif self.game_mode == Games.Traitor:
            traitor.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill, \
                          music=self.joust_music, teams=self.teams, game_mode=self.game_mode, \
                          controller_teams=self.controller_teams, controller_colors=self.controller_colors, \
                          dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, force_move_colors=self.force_color, \
                          music_speed=self.music_speed, show_team_colors=self.show_team_colors, restart=self.restart, \
                          revive=self.revive)
        # Werewolf
        elif self.game_mode == Games.Werewolf:
            werewolf.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill, \
                           music=self.joust_music, teams=self.teams, game_mode=self.game_mode, \
                           controller_teams=self.controller_teams, controller_colors=self.controller_colors, \
                           dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, force_move_colors=self.force_color, \
                           music_speed=self.music_speed, show_team_colors=self.show_team_colors, restart=self.restart, \
                           revive=self.revive)
        # Zombies
        elif self.game_mode == Games.Zombies:
            zombie.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill, \
                         music=self.zombie_music, teams=self.teams, game_mode=self.game_mode, \
                         controller_teams=self.controller_teams, controller_colors=self.controller_colors, \
                         dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, force_move_colors=self.force_color, \
                         music_speed=self.music_speed, show_team_colors=self.show_team_colors, restart=self.restart, \
                         revive=self.revive, opts=self.game_opts)
        # Commanders
        elif self.game_mode == Games.Commander:
            commander.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill, \
                            music=self.commander_music, teams=self.teams, game_mode=self.game_mode, \
                            controller_teams=self.controller_teams, controller_colors=self.controller_colors, \
                            dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, force_move_colors=self.force_color, \
                            music_speed=self.music_speed, show_team_colors=self.show_team_colors, restart=self.restart, \
                            revive=self.revive, opts=self.game_opts)
        # Swapper
        if self.game_mode == Games.Swapper:
            swapper.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill,\
                          music=self.joust_music, teams=self.teams, game_mode=self.game_mode, \
                          controller_teams=self.controller_teams, controller_colors=self.controller_colors, \
                          dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, force_move_colors=self.force_color, \
                          music_speed=self.music_speed, show_team_colors=self.show_team_colors, restart=self.restart, \
                          revive=self.revive)
        # Fight Club
        elif self.game_mode == Games.FightClub:
            if random.random() > 0.2:
                fight_music = self.commander_music
            else:
                fight_music = self.joust_music

            fight_club.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill, \
                             music=fight_music, teams=self.teams, game_mode=self.game_mode, controller_teams=self.controller_teams, \
                             controller_colors=self.controller_colors, dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, \
                             force_move_colors=self.force_color, music_speed=self.music_speed, show_team_colors=self.show_team_colors, \
                             restart=self.restart, revive=self.revive, opts=self.game_opts)
        #Tournament
        elif self.game_mode == Games.Tournament:
            tournament.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill, \
                             music=self.joust_music, teams=self.teams, game_mode=self.game_mode, \
                             controller_teams=self.controller_teams, controller_colors=self.controller_colors, \
                             dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, force_move_colors=self.force_color, \
                             music_speed=self.music_speed, show_team_colors=self.show_team_colors, restart=self.restart, \
                             revive=self.revive)
        # Non-stop Joust
        elif self.game_mode == Games.NonStop:
            joust_non_stop.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill, \
                                 music=self.joust_music, teams=self.teams, game_mode=self.game_mode, \
                                 controller_teams=self.controller_teams, controller_colors=self.controller_colors, \
                                 dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, force_move_colors=self.force_color, \
                                 music_speed=self.music_speed, show_team_colors=self.show_team_colors, restart=self.restart, \
                                 revive=self.revive, opts=self.game_opts)
        # Ninja
        elif self.game_mode == Games.Ninja:
            speed_bomb.Joust(moves=game_moves, command_queue=self.command_queue, ns=self.ns, red_on_kill=self.red_on_kill, \
                            music=self.commander_music, teams=self.teams, game_mode=self.game_mode, \
                            controller_teams=self.controller_teams, controller_colors=self.controller_colors, \
                            dead_moves=self.dead_moves, invincible_moves=self.invincible_moves, force_move_colors=self.force_color, \
                            music_speed=self.music_speed, show_team_colors=self.show_team_colors, restart=self.restart, \
                            revive=self.revive, opts=self.game_opts)
        # Random
        if random_mode:
            self.game_mode = Games.Random
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
        self.restart.value = 0
        self.reset_controller_game_state()
        self.retrack_removed_controllers(game_moves)

    def retrack_removed_controllers(self, game_moves):
        self.check_for_new_moves()
        for move_serial in [move.get_serial() for move in self.moves if move.get_serial() not in game_moves]:
            #This allows joustmania to re-find the removed controller
            if move_serial in self.tracked_moves.keys():
                del self.tracked_moves[move_serial]

if __name__ == "__main__":
    logger.info("Starting piparty")
    if "win" in platform:
        freeze_support()
    InitAudio()
    piparty = Menu()
    piparty.game_loop()
