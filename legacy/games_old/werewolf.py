from games.game import Game
from piaudio import Audio
import common, colors
import random, time
import logging

logger = logging.getLogger(__name__)

class Joust(Game):

    WERE_SLOW_WARNING = [1.2, 1.4, 1.7, 2.1, 2.9]
    WERE_SLOW_MAX = [1.3, 1.6, 1.9, 2.6, 3.9]
    WERE_FAST_WARNING = [1.4, 1.7, 2.0, 2.8, 3.5]
    WERE_FAST_MAX = [1.6, 1.9, 2.9, 3.3, 4.9]

    def __init__(self, moves, command_queue, ns, red_on_kill, music, teams, game_mode, controller_teams, controller_colors, dead_moves, invincible_moves, force_move_colors, music_speed, show_team_colors, restart, revive):
        super().__init__(
            moves=moves, command_queue=command_queue, ns=ns, red_on_kill=red_on_kill, music=music, teams=teams, game_mode=game_mode, \
            controller_teams=controller_teams, controller_colors=controller_colors, dead_moves=dead_moves, invincible_moves=invincible_moves, \
            force_move_colors=force_move_colors, music_speed=music_speed, show_team_colors=show_team_colors, \
            restart=restart, revive=revive)

        self.num_teams = 1
        self.generate_teams(num_teams=self.num_teams, num_moves=len(self.moves), team_colors=[colors.Colors.Yellow])
        self.werewolf_timer = 35

        self.werewolf_moves = []
        self.werewolf_count = 0

        self.game_loop()

    '''
    Override joust functions
    '''
    # @Override
    # Add additional werewolf sounds
    def init_audio(self):
        super().init_audio()

        if self.play_audio:
            self.wolfdown = Audio('audio/Joust/sounds/wolfdown.wav')
            self.thirty_seconds = Audio('audio/Joust/vox/' + self.voice + '/30 werewolf.wav')
            self.ten_seconds = Audio('audio/Joust/vox/' + self.voice + '/10 werewolf.wav')
            self.reveal_sound = Audio('audio/Joust/vox/' + self.voice + '/werewolf reveal 2.wav')

    # @Override
    # Generate random teams with X werewolves
    def generate_random_teams(self, num_teams, num_moves):
        super().generate_random_teams(num_teams, num_moves)

        were_num = int((num_moves * 7) / 16)

        copy_serials = self.move_serials[:]
        while were_num > 0:
            serial = random.choice(copy_serials)
            copy_serials.remove(serial)
            logger.debug("Werewolf selected: {}".format(serial))
            self.teams[serial] = -1
            were_num -= 1

    # @Override
    # Handle werewolf pre-game reveal
    def before_game_loop(self):
        self.restart.value = 0
        self.init_moves()

        for move_serial in self.teams.keys():
            if self.teams[move_serial] == -1:
                self.werewolf_moves.append(move_serial)

        self.werewolf_count = len(self.werewolf_moves)

        # If there is only one werewolf, play a shortened version of the intro
        if self.play_audio:
            if self.werewolf_count == 1:
                Audio('audio/Joust/vox/' + self.voice + '/werewolf intro_1.wav').start_effect()
            else:
                Audio('audio/Joust/vox/' + self.voice + '/werewolf intro.wav').start_effect()
        time.sleep(3)

        for move_serial in self.werewolf_moves:
            logger.debug("Setting to rumble: {}".format(move_serial))
            self.dead_moves[move_serial].value = common.Status.RUMBLE.value

        time.sleep(2)

        # Only do the reveal for others if there are more than 1 werewolf
        if self.werewolf_count == 1:
            for move_serial in self.werewolf_moves:
                self.dead_moves[move_serial].value = common.Status.ALIVE.value
            time.sleep(3)
        else:
            for move_serial in self.werewolf_moves:
                logger.debug("Setting to blue: {}".format(move_serial))
                self.dead_moves[move_serial].value = common.Status.ALIVE.value
                colors.change_color(self.force_move_colors[move_serial], *colors.Colors.Blue40.value)
            time.sleep(14)
            self.change_all_move_colors(1, 1, 1)

        time.sleep(6)
        self.start_timer = time.time()

    # @Override
    # Handle werewolf reveal
    def check_winner(self):
        if self.werewolf_timer - (time.time() - self.start_timer) <= 30 and self.audio_cue == 0:
            self.thirty_seconds.start_effect()
            self.audio_cue = 1
        if self.werewolf_timer - (time.time() - self.start_timer) <= 10 and self.audio_cue == 1:
            self.ten_seconds.start_effect()
            self.audio_cue = 2
        if self.werewolf_timer - (time.time() - self.start_timer) <= 0 and self.audio_cue == 2:
            self.reveal_sound.start_effect()

            # Set werewolf team to blue
            for move_serial in self.werewolf_moves:
                logger.debug("Revealing werewolf: {}".format(move_serial))
                colors.change_color(self.controller_colors[move_serial], *colors.Colors.Blue40.value)

            self.audio_cue = 3
            self.change_time = time.time() - 0.001
        elif self.audio_cue == 3:
            self.check_music_speed()

        return super().check_winner()

    # @Override
    # Play werewolf sound when a werewolf dies
    def play_death_sound(self, move_serial):
        if self.play_audio:
            if self.teams[move_serial] < 0:
                self.wolfdown.start_effect()
            else:
                self.explosion.start_effect()

    # @Override
    # Don't change music speed on intervals until after reveal
    def check_music_speed(self):
        if self.audio_cue == 3:
            super().check_music_speed()

    # @Override
    # Play werewolves win if they won
    def winning_team_sound(self):
        if self.winning_team == -1:
            Audio('audio/Joust/vox/' + self.voice + '/werewolf win.wav').start_effect()
        else:
            Audio('audio/Joust/vox/' + self.voice + '/human win.wav').start_effect()

    '''
    Override track_move functions
    '''
    # @Override
    # Return werewolf timing for werewolf
    @classmethod
    def get_slow_warning(cls, team, opts):
        if team < 0:
            return cls.WERE_SLOW_WARNING
        else:
            return cls.SLOW_WARNING

    @classmethod
    def get_fast_warning(cls, team, opts):
        if team < 0:
            return cls.WERE_FAST_WARNING
        else:
            return cls.FAST_WARNING

    @classmethod
    def get_slow_max(cls, team, opts):
        if team < 0:
            return cls.WERE_SLOW_MAX
        else:
            return cls.SLOW_MAX

    @classmethod
    def get_fast_max(cls, team, opts):
        if team < 0:
            return cls.WERE_FAST_MAX
        else:
            return cls.FAST_MAX
