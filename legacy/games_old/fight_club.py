from games.game import Game
from common import Status
from colors import Colors
from piaudio import Audio
import colors
from enum import Enum
import time, random
import logging

logger = logging.getLogger(__name__)

# Zombie Opts
class Opts(Enum):
    SCORE = 0

class Team(Enum):
    IN_LINE = 0
    DEFENDER = 1
    FIGHTER = 2
    FACE_OFF = 3

class Joust(Game):
    def __init__(self, moves, command_queue, ns, red_on_kill, music, teams, game_mode, controller_teams, controller_colors, dead_moves, invincible_moves, force_move_colors, music_speed, show_team_colors, restart, revive, opts):
        super().__init__(
            moves=moves, command_queue=command_queue, ns=ns, red_on_kill=red_on_kill, music=music, teams=teams, game_mode=game_mode, \
            controller_teams=controller_teams, controller_colors=controller_colors, dead_moves=dead_moves, invincible_moves=invincible_moves, \
            force_move_colors=force_move_colors, music_speed=music_speed, show_team_colors=show_team_colors, \
            restart=restart, revive=revive, opts=opts)

        self.audio_cue = 0
        self.num_dead = 0

        self.fighter_list = []
        self.generate_fighter_list()

        self.chosen_defender = self.fighter_list.pop()
        self.chosen_fighter = self.fighter_list.pop()
        self.round_num = len(self.move_serials) * 2
        self.round_counter = -1

        self.round_time = time.time()
        self.round_limit = 22
        self.round_start = 0
        self.revive_time = 0
        self.revive_duration = 4
        self.high_score = 1
        self.current_winner = ""
        self.winning_score = 0
        self.timer_beep = 4

        self.team_colors = [Colors.White20, Colors.Orange, Colors.Blue, Colors.Green]
        # self.revive.value = True # Allow reviving

        self.game_loop()

    '''
    Override joust functions
    '''
    # @Override
    def init_audio(self):
        super().init_audio()
        self.loud_beep = Audio('audio/Joust/sounds/beep_loud.wav')

    # @Override
    # Set up initial moves
    def init_moves(self):
        super().init_moves()
        for move_serial in self.moves:
            self.invincible_moves[move_serial].value = True
            self.switch_teams(move_serial, Team.IN_LINE.value)
            self.dead_moves[move_serial].value = Status.OFF.value

    # @Override
    # Set up initial fighters
    def before_game_loop(self):
        super().before_game_loop()
        self.reset_round()

    # @Override
    # Handle selecting next fighter if either died
    def handle_status(self):
        # If defender just died:
        # Old Defender should go to the back of line and set to invincible
        # Fighter should be set to new defender, made invincible and have score increased
        # Choose a new defender
        if self.dead_moves[self.chosen_defender].value == Status.DEAD.value:
            logger.debug("Defender died {}: {}".format(self.chosen_defender, self.dead_moves[self.chosen_defender].value))
            self.invincible_moves[self.chosen_fighter].value = True
            self.invincible_moves[self.chosen_defender].value = True
            self.play_death_sound(self.chosen_defender)
            self.kill_player(self.chosen_defender)
            self.add_score(self.chosen_fighter)
            self.chosen_defender = self.chosen_fighter
            self.chosen_fighter = self.fighter_list.pop()

            self.reset_round()

        # If fighter just died:
        # Old Fighter should go to back of line and set to invincible
        # Defender should be made invincible and have score increased
        # Choose a new fighter
        elif self.dead_moves[self.chosen_fighter].value == Status.DEAD.value:
            logger.debug("Fighter died {}: {}".format(self.chosen_fighter, self.dead_moves[self.chosen_fighter].value))
            self.invincible_moves[self.chosen_fighter].value = True
            self.invincible_moves[self.chosen_defender].value = True
            self.play_death_sound(self.chosen_defender)
            self.kill_player(self.chosen_fighter)
            self.add_score(self.chosen_defender)
            self.chosen_fighter = self.fighter_list.pop()

            self.reset_round()

        if self.revive_time is not None and time.time() > self.revive_time:
            logger.debug("Removing invincibility")
            self.invincible_moves[self.chosen_fighter].value = False
            self.invincible_moves[self.chosen_defender].value = False
            self.revive_time = None
            self.play_revive_sound()

        super().handle_status()

        self.check_end_round()

    # @Override
    # Handle end of round timing
    # If round ended without winner, select two new moves
    def check_end_round(self):
        if self.play_audio:
            # If round is almost over, play X warning beeps
            if time.time() > self.round_time - (3 * (self.timer_beep/4)):
                self.loud_beep.start_effect()
                self.timer_beep -= 1

        if time.time() > self.round_time:
            self.kill_player(self.chosen_defender)
            self.kill_player(self.chosen_fighter)
            self.dead_moves[self.chosen_defender].value = Status.DIED.value
            self.dead_moves[self.chosen_fighter].value = Status.DIED.value
            self.invincible_moves[self.chosen_fighter].value = True
            self.invincible_moves[self.chosen_defender].value = True

            # Set up next round
            self.chosen_defender = self.fighter_list.pop()
            self.chosen_fighter = self.fighter_list.pop()

            self.reset_round()

    # @Override
    # Check to see if there is a winner,
    # If there is a tie, have them face off, no time limit
    def check_winner(self):
        if self.round_counter >= self.round_num:
            logger.debug("Game Over")
            time.sleep(2)
            self.all_moves_off()
            self.winning_score = 0
            logger.debug("Scores: {}".format([opt[Opts.SCORE.value] for serial, opt in self.opts.items()]))
            for move_serial in self.moves:
                score = self.opts[move_serial][Opts.SCORE.value]
                if score ==  self.winning_score:
                    self.winning_moves.append(move_serial)
                if score > self.winning_score:
                    self.winning_moves = []
                    self.winning_moves.append(move_serial)
                    self.winning_score = score
            if len(self.winning_moves) > 1:
                self.face_off()
                return True
            else:
                return True
        return False

    # Override
    # Play game specific 'game_over'
    def winning_team_sound(self):
        Audio('audio/Fight_Club/vox/' + self.voice + '/game_over.wav').start_effect()

    '''
    Game-specific functions
    '''
    def generate_fighter_list(self):
        self.fighter_list = self.move_serials[:]
        random.shuffle(self.fighter_list)

    # Reset round
    def reset_round(self):
        logger.debug("Resetting round")
        self.round_counter += 1
        self.round_time = time.time() + self.round_limit
        self.revive_time = time.time() + self.revive_duration
        self.timer_beep = 4

        self.switch_teams(self.chosen_defender, Team.DEFENDER.value)
        self.switch_teams(self.chosen_fighter, Team.FIGHTER.value)
        self.dead_moves[self.chosen_defender].value = Status.ALIVE.value
        self.dead_moves[self.chosen_fighter].value = Status.ALIVE.value

        self.set_highest_score_color()

        if self.get_highest_score() > self.high_score :
            self.high_score = self.get_highest_score()
            if self.current_winner != self.chosen_defender:
                self.current_winner = self.chosen_defender
                saying = random.randint(0, 2)
                if saying == 0:
                    Audio('audio/Fight_Club/vox/' + self.voice + '/defender_lead.wav').start_effect()
                elif saying == 1:
                    Audio('audio/Fight_Club/vox/' + self.voice + '/defender_winning.wav').start_effect()
                elif saying == 2:
                    Audio('audio/Fight_Club/vox/' + self.voice + '/Defender_high_score.wav').start_effect()

        if self.round_counter == self.round_num - 5:
            Audio('audio/Fight_Club/vox/' + self.voice + '/5_rounds.wav').start_effect()
        elif self.round_counter == self.round_num - 1:
            Audio('audio/Fight_Club/vox/' + self.voice + '/last_round.wav').start_effect()

    def kill_player(self, serial):
        self.switch_teams(serial, Team.IN_LINE.value)
        self.dead_moves[serial].value = Status.OFF.value

        self.fighter_list.insert(0, serial)

    # If two players are tied, have them face off to decide victor
    def face_off(self):
        Audio('audio/Fight_Club/vox/' + self.voice + '/tie_game.wav').start_effect()
        logging.debug("Face off!")
        for move in self.move_serials:
            self.dead_moves[move].value = Status.OFF.value
        for move in self.winning_moves:
            self.dead_moves[move].value = Status.ALIVE.value
            self.invincible_moves[move].value = False
            self.switch_teams(move, Team.FACE_OFF.value)
            colors.change_color(self.force_move_colors[move], 0, 0, 0)
        count_explode = self.alive_move_count()
        while count_explode > 1:
            if count_explode > self.alive_move_count():
                count_explode = self.alive_move_count()
                if self.play_audio:
                    self.explosion.start_effect()
        self.winning_moves = []
        for move, lives in self.dead_moves.items():
            if lives.value == Status.ALIVE.value:
                self.winning_moves.append(move)

    def alive_move_count(self):
        count = 0
        for move, status in self.dead_moves.items():
            if status.value == Status.ALIVE.value:
                count += 1
        return count

    def add_score(self, serial):
        self.opts[serial][Opts.SCORE.value] += 1

    def get_highest_score(self):
        max_score = 1
        for move_serial in self.moves:
            score = self.opts[move_serial][Opts.SCORE.value]
            if score > max_score:
                max_score = score
        return max_score

    def set_highest_score_color(self):
        max_score = self.get_highest_score()
        for move_serial in self.moves:
            score = self.opts[move_serial][Opts.SCORE.value]
            # Update team according to score
            if score == max_score and self.teams[move_serial] == Team.IN_LINE.value:
                colors.change_color(self.force_move_colors[move_serial], *Colors.Green20.value)
            else:
                colors.change_color(self.force_move_colors[move_serial], 0, 0, 0)