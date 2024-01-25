from games.game import Game
import time, random
import common, colors
from common import Button, Status
from piaudio import Audio
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# Commander Opts
class Opts(Enum):
    INTRO = 0
    HOLDING = 1
    SELECTION = 2
    OVERDRIVE = 3
    POWER_PERCENT = 4
    IS_COMMANDER = 5
    DEATHS = 6
    COMMANDER_SET = 7

class Team(Enum):
    ALPHA = 0
    BRAVO = 1

class Selection(Enum):
    NOTHING = 0
    TRIGGER = 1
    PLAYER_READY = 2
    COMMANDER_READY = 3

class Overdrive(Enum):
    CHARGING = 0
    READY = 1
    ACTIVE = 2

class Intro(Enum):
    ON = 0 # Because all opts are defaulted to 0, we want the init value to match 0
    OFF = 1

# TODO - Vox has colors as Red and Blue...
COMMANDER_COLORS = [colors.Colors.Red, colors.Colors.Blue]
OVERDRIVE_COLORS = [colors.Colors.Orange, colors.Colors.Purple]
CURRENT_COMMANDER_COLORS = [colors.Colors.Magenta, colors.Colors.Green]

class Joust(Game):
    def __init__(self, moves, command_queue, ns, red_on_kill, music, teams, game_mode, controller_teams, controller_colors, dead_moves, invincible_moves, force_move_colors, music_speed, show_team_colors, restart, revive, opts):
        super().__init__(
            moves=moves, command_queue=command_queue, ns=ns, red_on_kill=red_on_kill, music=music, teams=teams, game_mode=game_mode, \
            controller_teams=controller_teams, controller_colors=controller_colors, dead_moves=dead_moves, invincible_moves=invincible_moves, \
            force_move_colors=force_move_colors, music_speed=music_speed, show_team_colors=show_team_colors, \
            restart=restart, revive=revive, opts=opts)

        self.current_commander = [None] * 2
        self.time_to_power = [20, 20]
        self.overdrive_duration = 5
        self.overdrive_start_time = [time.time(), time.time()]
        self.overdrive_end_time = [time.time(), time.time()]
        self.overdrive_status = [Overdrive.CHARGING.value, Overdrive.CHARGING.value]
        self.powers_percent = [0.0, 0.0]
        self.first_charge = 1

        self.num_teams = 2 # Alpha and Bravo
        self.generate_teams(num_teams=self.num_teams, team_colors=COMMANDER_COLORS)

        self.revive.value = 1 # For normal players to revive
        self.red_on_kill.value = False # Because one of the teams is Red

        self.game_loop()

    '''
    Override joust functions
    '''
    # @Override
    # Add additional werewolf sounds
    def init_audio(self):
        super().init_audio()

        if self.play_audio:
            self.overdrive_sfx = Audio('audio/Commander/sounds/overdrive.wav')
            self.power_ready_sfx = Audio('audio/Commander/sounds/power_ready.wav')
            self.power_ready = Audio('audio/Commander/vox/' + self.voice + '/power_ready.wav')
            self.red_power_ready = Audio('audio/Commander/vox/' + self.voice + '/red_power_ready.wav')
            self.blue_power_ready = Audio('audio/Commander/vox/' + self.voice + '/blue_power_ready.wav')
            self.red_overdrive = Audio('audio/Commander/vox/' + self.voice + '/red_overdrive.wav')
            self.blue_overdrive = Audio('audio/Commander/vox/' + self.voice + '/blue_overdrive.wav')

    # @Override
    # Allow teams to select commanders
    def before_game_loop(self):
        super().before_game_loop()

        intro_sound = Audio('audio/Commander/vox/' + self.voice + '/commander intro.wav')
        intro_sound.start_effect()

        play_last_one = True
        commander_select_time = time.time() + 50
        battle_ready_time = time.time() + 40

        while time.time() < commander_select_time:
            self.check_commander_select()
            if self.check_everyone_in():
                break

            if time.time() > battle_ready_time and play_last_one:
                play_last_one = False
                Audio('audio/Commander/vox/' + self.voice + '/10 seconds begins.wav').start_effect()

        time.sleep(1)

        intro_sound.stop_effect()

        if self.current_commander[Team.ALPHA.value] is None:
            self.change_random_commander(Team.ALPHA.value)
        if self.current_commander[Team.BRAVO.value] is None:
            self.change_random_commander(Team.BRAVO.value)

        for move_serial in self.moves:
            self.opts[move_serial][Opts.INTRO.value] = Intro.OFF.value

        Audio('audio/Commander/vox/' + self.voice + '/commanders chosen.wav').start_effect_and_wait()
        self.reset_powers()

    # @Override
    # Handle overdrive and charging
    def handle_status(self):
        super().handle_status()

        self.update_team_powers()
        self.check_commander_power()
        self.check_end_of_overdrive()

    # @Override
    # Game ends if commander dies
    def check_winner(self):
        for commander in self.current_commander:
            if self.dead_moves[commander].value == Status.DEAD.value:
                self.winning_team = (self.teams[commander] + 1) % 2 # Winning team is the other team
                return True
        return False

    '''
    Game-specific functions
    '''
    def check_commander_select(self):
        # Handle commanders first
        for move_serial in self.moves:
            if self.opts[move_serial][Opts.SELECTION.value] == Selection.COMMANDER_READY.value and self.opts[move_serial][Opts.HOLDING.value]:
                Audio('audio/Commander/sounds/commanderselect.wav').start_effect()
                self.change_commander(move_serial)
                self.opts[move_serial][Opts.SELECTION.value] = Selection.NOTHING.value
                # Set all of the team members to having their commander set
                logger.debug("Teams: {}".format(self.teams))
                for serial, team in self.teams.items():
                    if team == self.teams[move_serial]:
                        self.opts[serial][Opts.COMMANDER_SET.value] = True
            elif self.opts[move_serial][Opts.SELECTION.value] == Selection.PLAYER_READY.value and self.opts[move_serial][Opts.HOLDING.value]:
                Audio('audio/Commander/sounds/buttonselect.wav').start_effect()
                self.opts[move_serial][Opts.SELECTION.value] = Selection.NOTHING.value

    def change_commander(self, new_commander):
        #print 'changing commander to ' + str(new_commander)
        commander_team = self.teams[new_commander]
        if self.current_commander[commander_team] is not None:
            self.opts[self.current_commander[commander_team]][Opts.IS_COMMANDER.value] = False

        self.opts[new_commander][Opts.IS_COMMANDER.value] = True
        self.current_commander[commander_team] = new_commander

    def change_random_commander(self, team, exclude_commander=None):
        team_move_serials = [ move_serial for move_serial in self.opts.keys() if (self.teams[move_serial] == team and move_serial != exclude_commander and self.dead_moves[move_serial].value >= 1) ]
        logger.debug("Team move serials: {}".format(team_move_serials))
        if len(team_move_serials) > 0:
            new_commander = random.choice(team_move_serials)
            self.change_commander(new_commander)
            return True
        return False

    def check_everyone_in(self):
        for move_serial in self.opts.keys():
            if not self.opts[move_serial][Opts.HOLDING.value]:
                return False
        return True

    def reset_powers(self):
        for team in [Team.ALPHA.value, Team.BRAVO.value]:
            self.reset_power(team)

    def reset_power(self, team):
        self.powers_percent[team] = 0.0
        self.overdrive_start_time[team] = time.time()
        self.overdrive_status[team] = Overdrive.CHARGING.value
        for move_serial in self.moves:
            if self.teams[move_serial] == team:
                self.opts[move_serial][Opts.OVERDRIVE.value] = Overdrive.CHARGING.value
                self.opts[move_serial][Opts.POWER_PERCENT.value] = 0

    def update_team_powers(self):
        for team in [Team.ALPHA.value, Team.BRAVO.value]:
            # TODO - Could we make this go backwards as power is used up?
            self.powers_percent[team] = max(min((time.time() - self.overdrive_start_time[team]) / (self.time_to_power[team] * 1.0), 1.0), 0.0)

            if self.overdrive_status[team] == Overdrive.CHARGING.value:
                if self.powers_percent[team] >= 1.0:
                    logger.debug("Power activated for team: {}".format(team))
                    self.overdrive_status[team] = Overdrive.READY.value
                    self.opts[self.current_commander[team]][Opts.OVERDRIVE.value] = Overdrive.READY.value
                    self.power_ready_sfx.start_effect()

                    # Avoid double playing sound effects on first charge
                    if self.first_charge and team == Team.ALPHA.value:
                        self.power_ready.start_effect()
                    elif team == Team.ALPHA.value:
                        self.red_power_ready.start_effect()
                    elif not self.first_charge:
                        self.blue_power_ready.start_effect()
                else:
                    self.opts[self.current_commander[team]][Opts.POWER_PERCENT.value] = int(self.powers_percent[team] * 100)

    def check_commander_power(self):
        for commander in self.current_commander:
            if self.opts[commander][Opts.SELECTION.value] == Selection.TRIGGER.value:
                self.overdrive(self.teams[commander])
                self.opts[commander][Opts.SELECTION.value] = Selection.NOTHING.value

    def overdrive(self, team):
        self.first_charge = 0 # Set this to false the first time overdrive is used
        logger.debug("Overdrive active for: {}".format(team))
        self.overdrive_sfx.start_effect()

        # Turn on overdrive for all controllers on this team
        for move_serial in self.moves:
            if self.teams[move_serial] == team:
                logger.debug("Activating overdrive for: {}".format(move_serial))
                self.opts[move_serial][Opts.OVERDRIVE.value] = Overdrive.ACTIVE.value

        self.overdrive_status[team] = Overdrive.ACTIVE.value
        self.overdrive_end_time[team] = time.time() + self.overdrive_duration

        if self.play_audio:
            if team == Team.ALPHA.value:
                self.red_overdrive.start_effect()
            else:
                self.blue_overdrive.start_effect()

    def check_end_of_overdrive(self):
        for team in [Team.ALPHA.value, Team.BRAVO.value]:
            if self.overdrive_status[team] == Overdrive.ACTIVE.value:
                if time.time() >= self.overdrive_end_time[team]:
                    logger.debug("Overdrive ended for team: {}".format(team))
                    self.overdrive_status[team] = Overdrive.CHARGING.value
                    # Turn off overdrive for all moves on this team
                    for move_serial in self.moves:
                        if self.teams[move_serial] == team:
                            logger.debug("Deactivating overdrive for: {}".format(move_serial))
                            self.opts[move_serial][Opts.OVERDRIVE.value] = Overdrive.CHARGING.value
                            self.opts[move_serial][Opts.HOLDING.value] = False
                    self.reset_power(team)

    '''
    Override track_move functions
    '''
    @classmethod
    def pre_game_loop(cls, move, team, opts):
        # Loop while the intro is still playing to capture move inputs
        while opts[Opts.INTRO.value] == Intro.ON.value:
            if move.poll():
                button = Button(move.get_buttons())
                # Only allow players to ready after commander is selected
                if button == Button.MIDDLE and not opts[Opts.HOLDING.value] and opts[Opts.COMMANDER_SET.value]:
                    opts[Opts.SELECTION.value] = Selection.PLAYER_READY.value
                    opts[Opts.HOLDING.value] = True
                elif button == Button.TRIANGLE and not opts[Opts.HOLDING.value]:
                    opts[Opts.SELECTION.value] = Selection.COMMANDER_READY.value
                    opts[Opts.HOLDING.value] = True
                elif not opts[Opts.IS_COMMANDER.value] and opts[Opts.HOLDING.value]:
                    move.set_leds(200, 200, 200)
                elif opts[Opts.IS_COMMANDER.value] and opts[Opts.HOLDING.value]:
                    move.set_leds(*CURRENT_COMMANDER_COLORS[team].value)
                else:
                    move.set_leds(*COMMANDER_COLORS[team].value)
            move.update_leds()

        opts[Opts.HOLDING.value] = False
        opts[Opts.SELECTION.value] = Selection.NOTHING.value

    # Handle sensitivity based on overdrive
    @classmethod
    def get_warning(cls, team, speed_percent, sensitivity, opts):
        # Only normal players get FAST during overdrive
        if not opts[Opts.IS_COMMANDER.value] and opts[Opts.OVERDRIVE.value] == Overdrive.ACTIVE.value:
            return cls.FAST_WARNING[sensitivity]
        else:
            return cls.SLOW_WARNING[sensitivity]

    @classmethod
    def get_threshold(cls, team, speed_percent, sensitivity, opts):
        # Only normal players get FAST during overdrive
        if not opts[Opts.IS_COMMANDER.value] and opts[Opts.OVERDRIVE.value] == Overdrive.ACTIVE.value:
            return cls.FAST_MAX[sensitivity]
        else:
            return cls.SLOW_MAX[sensitivity]

    # @Override
    # Set opts for commander
    @classmethod
    def handle_opts(cls, move, team, opts, dead_move):
        if opts[Opts.IS_COMMANDER.value] and opts[Opts.OVERDRIVE.value] == Overdrive.READY.value:
            # Unset values
            if move.get_buttons() == 0 and move.get_trigger() < 10:
                opts[Opts.HOLDING.value] = False

            # Press trigger for overdrive
            if opts[Opts.OVERDRIVE.value] == Overdrive.READY.value and not opts[Opts.HOLDING.value] and move.get_trigger() > 100:
                logger.debug("Trying to trigger overdrive")
                opts[Opts.SELECTION.value] = Selection.TRIGGER.value
                opts[Opts.HOLDING.value] = True

        if dead_move == Status.DIED.value:
            opts[Opts.DEATHS.value] += 1

        return opts

    # @Override
    # Return team color based on overdrive and commander status
    @classmethod
    def handle_team_color(cls, move, team, opts, team_color):
        if not opts[Opts.IS_COMMANDER.value]:
            if opts[Opts.OVERDRIVE.value] == Overdrive.ACTIVE.value:
                return OVERDRIVE_COLORS[team].value
            else:
                return team_color
        else:
            return cls.calculate_flash_time(*CURRENT_COMMANDER_COLORS[team].value, opts[Opts.POWER_PERCENT.value] / 100)

    @classmethod
    def get_revive_time(cls, move, team, opts):
        # 8s + 2 for every death, with a max of 25s
        return min(2 * opts[Opts.DEATHS.value] + 8, 25)

    # Fade from white to commander color as power is restored
    @classmethod
    def calculate_flash_time(cls, r, g, b, score):
        flash_percent = max(min(float(score)+0.2,1.0),0.0)
        #val_percent = (val-(flash_speed/2))/(flash_speed/2)
        new_r = int(common.lerp(255, r, flash_percent))
        new_g = int(common.lerp(255, g, flash_percent))
        new_b = int(common.lerp(255, b, flash_percent))
        return new_r, new_g, new_b
