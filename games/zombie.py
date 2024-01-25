from games.game import Game
from piaudio import Audio
from enum import Enum
from common import Button, Status
from colors import Colors
import colors
import random, time
import logging

logger = logging.getLogger(__name__)

# Zombie Opts
class Opts(Enum):
    HOLDING = 0
    SELECTION = 1
    PLAYER_TYPE = 2
    AMMO = 3

class PlayerType(Enum):
    HUMAN = 0
    ZOMBIE = 1

class Selection(Enum):
    NO_BUTTON = 0
    TRIGGER = 1
    PISTOL = 2
    MOLOTOV = 3

MELEE_ODDS = [0, 0, 1, 1, 2]
PISTOL_ODDS = [0, 0, 0, 0, 1, 1, 1]
MOLOTOV_ODDS = [0, 0, 1, 1, 2, 3]

class Joust(Game):

    ZOMBIE_WARNING = [1.2, 1.5, 1.8, 2.6, 2.7]
    ZOMBIE_MAX = [1.4, 1.7, 2.7, 3.1, 3.4]

    def __init__(self, moves, command_queue, ns, red_on_kill, music, teams, game_mode, controller_teams, controller_colors, dead_moves, invincible_moves, force_move_colors, music_speed, show_team_colors, restart, revive, opts):
        super().__init__(
            moves=moves, command_queue=command_queue, ns=ns, red_on_kill=red_on_kill, music=music, teams=teams, game_mode=game_mode, \
            controller_teams=controller_teams, controller_colors=controller_colors, dead_moves=dead_moves, invincible_moves=invincible_moves, \
            force_move_colors=force_move_colors, music_speed=music_speed, show_team_colors=show_team_colors, \
            restart=restart, revive=revive, opts=opts)

        self.humans = []
        self.zombies = {}
        self.shot_zombies = []

        self.win_time = ((len(self.moves) * 3)/16) * 60
        if self.win_time <= 0:
            self.win_time = 60
        self.start_time = time.time()
        self.effect_cue = 0

        # Players will revive as zombies
        self.revive.value = True

        self.num_teams = 1 # Everyone on one team
        self.generate_teams(num_teams=self.num_teams, team_colors=[Colors.White])

        self.game_loop()

    '''
    Override joust functions
    '''
    # @Override
    # Add additional zombie sounds
    def init_audio(self):
        super().init_audio()

        # TODO - should this all load ahead of time?
        if self.play_audio:
            self.pickup = Audio('audio/Zombie/sounds/pickup.wav')
            self.ten_seconds = Audio('audio/Zombie/vox/' + self.voice + '/10 seconds left.wav')
            self.thirty_seconds = Audio('audio/Zombie/vox/' + self.voice + '/30 seconds.wav')
            self.one_minute = Audio('audio/Zombie/vox/' + self.voice + '/1 minute.wav')
            self.three_minutes = Audio('audio/Zombie/vox/' + self.voice + '/3 minutes.wav')
            # self.five_minutes = Audio('audio/Zombie/vox/' + self.voice + '/5 minutes.wav')
            self.human_victory = Audio('audio/Zombie/vox/' + self.voice + '/human_victory.wav')
            self.zombie_victory = Audio('audio/Zombie/vox/' + self.voice + '/zombie_victory.wav')
            self.death = Audio('audio/Zombie/vox/' + self.voice + '/zombie_death.wav')
            self.pistol = Audio('audio/Zombie/sounds/pistol.wav')
            # self.shotgun = Audio('audio/Zombie/sounds/shotgun.wav')
            self.molotov = Audio('audio/Zombie/sounds/molotov.wav')

    '''
    Override generic functions
    '''
    # @Override
    # Set the initial opts
    def init_moves(self):
        super().init_moves()

        # Setting up human team
        for move_serial in self.moves:
            self.humans.append(move_serial)

    # @Override
    # Killing initial humans
    def before_game_loop(self):
        super().before_game_loop()

        # Kill first humans
        for random_human in random.sample(set(self.humans), 2):
            self.kill_human(random_human)
            self.dead_moves[random_human].value = Status.ALIVE.value

    # @Override
    # Handle all human/zombie stuff
    def handle_status(self):
        self.shot_zombies = []
        for move_serial in self.humans:
            # Human died from jostling
            if self.dead_moves[move_serial].value == Status.DIED.value:
                logger.debug("Human has died, switching to zombie: {}".format(move_serial))
                if self.play_audio:
                    self.play_death_sound(move_serial)
                self.kill_human(move_serial)

            # Pistol fired (Shoot one random zombie)
            elif self.opts[move_serial][Opts.SELECTION.value] == Selection.PISTOL.value:
                logger.debug("Human has fired pistol: {}".format(move_serial))
                if self.play_audio:
                    self.pistol.start_effect()
                self.shoot_zombies(targets=1, reward_odds=PISTOL_ODDS)
                self.opts[move_serial][Opts.SELECTION.value] = Selection.NO_BUTTON.value

            # Molotov fired (Shoot all alive zombies)
            elif self.opts[move_serial][Opts.SELECTION.value] == Selection.MOLOTOV.value:
                logger.debug("Human has thrown molotov: {}".format(move_serial))
                if self.play_audio:
                    self.molotov.start_effect()
                self.shoot_zombies(targets=50, reward_odds=MOLOTOV_ODDS)
                self.opts[move_serial][Opts.SELECTION.value] = Selection.NO_BUTTON.value

        for move_serial, spawn_time in self.zombies.items():
            # If a zombie died
            if self.dead_moves[move_serial].value == Status.DIED.value:
                logger.debug("Zombie has died by melee: {}".format(move_serial))
                if self.play_audio:
                    self.play_death_sound(move_serial)
                self.kill_zombie(move_serial)
                # If the zombie was jostled
                if move_serial not in self.shot_zombies:
                    self.reward(MELEE_ODDS)
            # If zombie is ready to revive
            elif self.dead_moves[move_serial].value == Status.REVIVED.value:
                logger.debug("Zombie has revived: {}".format(move_serial))
                if self.play_audio:
                    self.revive_sound.start_effect()
                self.revive_zombie(move_serial)

    # @Override
    # Play zombie sound when a zombie dies
    def play_death_sound(self, move_serial):
        if self.play_audio:
            if self.teams[move_serial] < 0:
                self.death.start_effect()
            else:
                self.explosion.start_effect()

    # @Override
    # Handle zombie winner
    def check_winner(self):
        if self.win_time - (time.time() - self.start_time) <= 10 and self.effect_cue <= 4:
            self.ten_seconds.start_effect()
            self.effect_cue = 5
        elif self.win_time - (time.time() - self.start_time) <= 30 and self.effect_cue <= 3:
            self.thirty_seconds.start_effect()
            self.effect_cue = 4
        elif self.win_time - (time.time() - self.start_time) <= 1*60 and self.effect_cue <= 2:
            self.one_minute.start_effect()
            self.effect_cue = 3
        elif self.win_time - (time.time() - self.start_time) <= 3*60 and self.effect_cue <= 1:
            self.three_minutes.start_effect()
            self.effect_cue = 2
        # elif self.win_time - (time.time() - self.start_time) <= 5*60 and self.effect_cue <= 0:
        #     self.three_minutes.start_effect()
        #     self.effect_cue = 1

        if len(self.humans) <= 0:
            self.winning_team = -1
            return True
        elif (time.time() - self.start_time) > self.win_time:
            self.winning_team = 0
            return True
        else:
            return False

    # @Override
    # Play zombies win if they won
    def winning_team_sound(self):
        logger.debug("")
        if self.winning_team == -1:
            Audio('audio/Zombie/vox/' + self.voice + '/zombie_victory.wav').start_effect()
        else:
            Audio('audio/Zombie/vox/' + self.voice + '/human_victory.wav').start_effect()

    '''
    Game-specific functions
    '''
    # Move a human to a zombie
    def kill_human(self, move_serial):
        self.switch_teams(move_serial, -1)
        colors.change_color(self.controller_colors[move_serial], *Colors.Zombie.value)
        self.dead_moves[move_serial].value = Status.DEAD.value
        self.zombies[move_serial] = time.time() + 1
        self.humans.remove(move_serial)

    # Kill a zombie
    def kill_zombie(self, move_serial):
        if move_serial not in self.shot_zombies:
            self.dead_moves[move_serial].value = Status.DEAD.value
        self.zombies[move_serial] = time.time() + 2 # self.get_respawn_time() TODO - reimplement this

    # Revive zombie
    def revive_zombie(self, move_serial):
        self.dead_moves[move_serial].value = Status.ALIVE.value
        self.zombies[move_serial] = None

    # Shoot zombie
    def shoot_zombie(self, move_serial):
        self.dead_moves[move_serial].value = Status.DIED.value
        self.zombies[move_serial] = time.time() + 2 # self.get_respawn_time() TODO - reimplement this
        self.shot_zombies.append(move_serial)

    # Shoot multiple zombies
    def shoot_zombies(self, targets, reward_odds):
        kill_zombie = False
        logger.debug("All Zombies: {}".format(self.zombies))
        alive_zombies = [key for key, value in self.zombies.items() if value is None]
        logger.debug("Alive Zombies: {}".format(alive_zombies))
        # For the power of the gun
        for i in range(targets):
            # If there are remaining zombies
            if len(alive_zombies) > 0:
                kill_zombie = True
                zombie_serial = random.choice(alive_zombies)
                logger.debug("Zombie has died by gun: {}".format(zombie_serial))
                self.shoot_zombie(zombie_serial)

        if kill_zombie:
            self.reward(reward_odds)

    # Only get a reward if there are more than 4+ zombies
    def reward(self, reward_odds):
        if (len(self.zombies)) > 3:
            bullet_count = random.choice(reward_odds)
            found_bullets = False
            # For the number of bullets you randomly received
            for i in range(bullet_count):
                found_bullets = True
                random_human = random.choice(self.humans)
                if self.opts[random_human][Opts.AMMO.value] < 5:
                    self.opts[random_human][Opts.AMMO.value] += 1
            if found_bullets and self.play_audio:
                self.pickup.start_effect()

    # As we get closer to end, spawn more slowly TODO - look into this
    def get_respawn_time(self):
        percent_to_win = 1.0 * (time.time() - self.start_time)/(self.win_time * 1.0)
        random_num = ((1.0 - percent_to_win) * 7)
        return random.uniform(random_num, random_num + 2)

    '''
    Override track_move functions
    '''
    # @Override
    # Update warning and thresholds for zombies
    @classmethod
    def get_warning(cls, team, speed_percent, sensitivity, opts):
        if team == -1:
            return cls.ZOMBIE_WARNING[sensitivity]
        else:
            return super().get_warning(team, speed_percent, sensitivity, opts)

    @classmethod
    def get_threshold(cls, team, speed_percent, sensitivity, opts):
        if team == -1:
            return cls.ZOMBIE_MAX[sensitivity]
        else:
            return super().get_threshold(team, speed_percent, sensitivity, opts)

    # @Override
    # Handle button presses for humans
    @classmethod
    def handle_opts(cls, move, team, opts, dead_move):
        if opts[Opts.PLAYER_TYPE.value] == PlayerType.HUMAN.value:
            if move.get_buttons() == 0 and move.get_trigger() < 10:
                opts[Opts.HOLDING.value] = True

            # Not holding button, selected pistol, has bullets, and presses trigger
            if (not opts[Opts.HOLDING.value] and
                    0 < opts[Opts.AMMO.value] < 5 and
                    move.get_trigger() > 100):
                logger.debug("Pressing trigger (Pistol)")
                opts[Opts.HOLDING.value] = True
                opts[Opts.SELECTION.value] = Selection.PISTOL.value
                opts[Opts.AMMO.value] -= 1
            # Molotov
            elif (not opts[Opts.HOLDING.value] and
                 opts[Opts.AMMO.value] >= 5 and
                 move.get_trigger() > 100):
                logger.debug("Pressing trigger (Molotov)")
                opts[Opts.HOLDING.value] = True
                opts[Opts.SELECTION.value] = Selection.MOLOTOV.value
                opts[Opts.AMMO.value] = 0

        return opts

    # @Override
    # Show human color according to the number of bullets, not team
    @classmethod
    def handle_team_color(cls, move, team, opts, team_color):
        if team >= 0:
            # TODO - middle button to show bullet count (0-5)
            if opts[Opts.AMMO.value] == 5:
                return 255,0,255
            if opts[Opts.AMMO.value] == 4:
                return 0,0,255
            if opts[Opts.AMMO.value] == 3:
                return 0,0,255
            if opts[Opts.AMMO.value] == 2:
                return 0,0,255
            if opts[Opts.AMMO.value] == 1:
                return 0,0,255
            if opts[Opts.AMMO.value] == 0:
                return 100,100,100
        return team_color

    # @Override
    # Return a random number between 2 and 20 seconds
    @classmethod
    def get_revive_time(cls, move, team, opts):
        return random.randint(2, 10)